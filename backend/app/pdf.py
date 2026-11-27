"""ED handover PDF (ATMIST-structured) with verification QR."""
from __future__ import annotations

import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle)

try:
    import qrcode
    HAS_QR = True
except Exception:  # pragma: no cover
    HAS_QR = False

INK = colors.HexColor("#0b0f14")
ACCENT = colors.HexColor("#0e9f8a")
MUTED = colors.HexColor("#5b6675")
RED = colors.HexColor("#c0392b")
AMBER = colors.HexColor("#b7791f")
LINE = colors.HexColor("#d9dee5")


def _styles():
    ss = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle("h1", parent=ss["Title"], fontName="Helvetica-Bold", fontSize=17, textColor=INK, alignment=0, spaceAfter=2),
        "sub": ParagraphStyle("sub", parent=ss["Normal"], fontName="Helvetica", fontSize=8.5, textColor=MUTED),
        "h2": ParagraphStyle("h2", parent=ss["Heading2"], fontName="Helvetica-Bold", fontSize=10.5, textColor=ACCENT, spaceBefore=8, spaceAfter=4),
        "body": ParagraphStyle("body", parent=ss["Normal"], fontName="Helvetica", fontSize=9, leading=12, textColor=INK),
        "small": ParagraphStyle("small", parent=ss["Normal"], fontName="Helvetica", fontSize=7.5, leading=10, textColor=MUTED),
        "mono": ParagraphStyle("mono", parent=ss["Normal"], fontName="Courier", fontSize=7, leading=9, textColor=MUTED),
    }


def _table(rows, widths, header=True):
    t = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    style = [
        ("FONT", (0, 0), (-1, -1), "Helvetica", 8.5),
        ("TEXTCOLOR", (0, 0), (-1, -1), INK),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef3f6")), ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8.5)]
    t.setStyle(TableStyle(style))
    return t


def _esc(v) -> str:
    return str(v or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render(inc: dict, entries: list[dict], vitals: list[dict], alerts: list[dict], verify: dict, public_url: str = "") -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm, bottomMargin=14 * mm,
                            title=f"FieldScribe handover {inc.get('dispatch_id')}", author="FieldScribe")
    S = _styles()
    pat = inc.get("patient") or {}
    wf = inc.get("workflow") or {}
    story = []
    head = [[Paragraph("FieldScribe · ED Handover Note", S["h1"]),
             Paragraph(f"<b>Triage</b> {inc.get('triage') or '—'}", ParagraphStyle("t", parent=S["body"], alignment=2,
                       textColor=RED if inc.get("triage") == "RED" else AMBER if inc.get("triage") == "YELLOW" else ACCENT, fontSize=11))]]
    ht = Table(head, colWidths=[130 * mm, 48 * mm])
    ht.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LINEBELOW", (0, 0), (-1, 0), 1.2, ACCENT)]))
    story += [ht, Spacer(0, 3),
              Paragraph(f"Dispatch {inc.get('dispatch_id')} · Vehicle {inc.get('vehicle')} · Crew {inc.get('crew')} · "
                        f"Generated {datetime.now().strftime('%d %b %Y %H:%M')} (offline edge device)", S["sub"])]

    # ATMIST summary
    meds = [e for e in entries if e["kind"] == "medication" and e["status"] != "withheld"]
    procs = [e for e in entries if e["kind"] == "procedure"]
    tx = ", ".join(f"{e['payload'].get('drug')} {e['payload'].get('dose') or ''}{e['payload'].get('unit') or '' if e['payload'].get('dose') else ''} "
                   f"{e['payload'].get('route') or ''}".strip() for e in meds) or "None recorded"
    tx += ("; " + ", ".join(e["payload"].get("procedure") for e in procs)) if procs else ""
    latest = {}
    for v in vitals:
        latest[v["name"]] = f"{v['value']}{v.get('unit') or ''}"
    signs = ", ".join(f"{k.upper()} {v}" for k, v in latest.items()) or "Not recorded"
    age = pat.get("age")
    atmist = [
        ["A", "Age / sex", f"{age if age is not None else '?'} y · {pat.get('sex') or 'unknown'}" + (f" · {pat['weight_kg']:g} kg" if pat.get('weight_kg') else "")],
        ["T", "Time of onset / call", wf.get("call_received") or "—"],
        ["M", "Mechanism / complaint", inc.get("complaint") or "—"],
        ["I", "Injuries / findings", inc.get("place") or "—"],
        ["S", "Signs (latest vitals)", signs],
        ["T", "Treatment given", tx],
    ]
    story += [Paragraph("ATMIST summary", S["h2"]),
              _table([[Paragraph(f"<b>{a}</b>", S["body"]), Paragraph(b, S["small"]), Paragraph(c, S["body"])] for a, b, c in atmist],
                     [8 * mm, 40 * mm, 130 * mm], header=False)]
    allergy = ", ".join(pat.get("allergies", [])) or pat.get("allergies_status") or "Not documented"
    story.append(Spacer(0, 3))
    story.append(Paragraph(f"<b>Allergies:</b> <font color='{'#c0392b' if pat.get('allergies') else '#0b0f14'}'>{allergy}</font>"
                           + (" &nbsp; · &nbsp; <b>Medico-legal case</b>" if pat.get("medico_legal") else "")
                           + (" &nbsp; · &nbsp; <b>Refusal noted</b>" if pat.get("refusal_noted") else ""), S["body"]))
    lg = inc.get("legal") or {}
    ident = []
    if pat.get("abha"):
        ident.append(f"<b>ABHA:</b> {pat['abha']} ({'verified' if pat.get('abha_verified') else 'linked, not yet verified with ABDM'})")
    if pat.get("name"):
        ident.append(f"<b>Name:</b> {_esc(pat['name'])}")
    if pat.get("relative_name") or pat.get("relative_phone"):
        ident.append(f"<b>Relative:</b> {_esc(pat.get('relative_name') or '')} {_esc(pat.get('relative_phone') or '')}")
    if ident:
        story.append(Paragraph(" &nbsp; · &nbsp; ".join(ident), S["body"]))
    m = lg.get("mlc") or {}
    if m.get("is_mlc"):
        story += [Paragraph("Medico-legal case (MLC)", S["h2"]),
                  _table([["Category", "Police station", "Informed", "Officer / GD no.", "Brought by"],
                          [m.get("category") or "—", m.get("police_station") or "—",
                           (f"Yes, {m.get('informed_at')}" if m.get("informed") else "Not yet"),
                           " / ".join(x for x in (m.get("officer"), m.get("gd_number")) if x) or "—", m.get("brought_by") or "—"]],
                         [34 * mm, 38 * mm, 26 * mm, 42 * mm, 38 * mm])]
    rf = lg.get("refusal")
    if rf:
        story += [Paragraph("Refusal of care (LAMA)", S["h2"]),
                  Paragraph(f"Refused <b>{rf.get('what')}</b>. Reason: {_esc(rf.get('reason') or 'not stated')}. Risks explained: yes. "
                            f"Capacity: {'patient has capacity' if rf.get('capacity') == 'yes' else 'decision by representative'}. "
                            f"Signed by {_esc(rf.get('signed_by'))} ({_esc(rf.get('relation') or 'self')})"
                            + (f", witness {_esc(rf.get('witness'))}" if rf.get("witness") else "")
                            + f". Recorded by {_esc(rf.get('recorded_by'))} at {rf.get('recorded_at')}. "
                            f"Signature SHA-256 {rf.get('signature_sha256', '')[:16]}… sealed in the audit ledger.", S["body"])]
        try:
            import base64
            from reportlab.platypus import Image as RLImage
            raw = base64.b64decode(rf["signature"].split(",", 1)[1])
            story.append(RLImage(io.BytesIO(raw), width=60 * mm, height=22 * mm))
        except Exception:
            pass

    # 108 timeline
    labels = [("call_received", "Call"), ("at_scene", "At scene"), ("patient_contact", "Pt contact"),
              ("left_scene", "Left scene"), ("at_hospital", "At hospital"), ("handover", "Handover")]
    story += [Paragraph("108 workflow timeline", S["h2"]),
              _table([[l for _, l in labels], [wf.get(k) or "—" for k, _ in labels]], [29.6 * mm] * 6)]

    # medications
    rows = [["Time", "Medication", "Dose", "Route", "RxNorm", "Status", "Conf."]]
    for e in [x for x in entries if x["kind"] == "medication"]:
        p = e["payload"]
        dose = p.get("rate") or (f"{p.get('dose'):g} {p.get('unit')}" if isinstance(p.get("dose"), (int, float)) else "—")
        rows.append([p.get("time") or e.get("time") or "—", p.get("drug"), dose, p.get("route") or "—",
                     p.get("rxnorm") or "—", "WITHHELD" if e["status"] == "withheld" else ("edited" if e.get("edited") else "confirmed"),
                     f"{(e.get('confidence') or 0):.0%}"])
    story += [Paragraph("Medications administered", S["h2"]), _table(rows, [16 * mm, 40 * mm, 26 * mm, 16 * mm, 20 * mm, 38 * mm, 22 * mm])]
    if procs:
        rows = [["Time", "Procedure", "Details", "Code"]]
        for e in procs:
            p = e["payload"]
            det = ", ".join(str(p[k]) for k in ("device", "site", "energy") if p.get(k)) or "—"
            rows.append([p.get("time") or e.get("time") or "—", p.get("procedure"), det, p.get("snomed") or "—"])
        story += [Paragraph("Procedures", S["h2"]), _table(rows, [16 * mm, 60 * mm, 70 * mm, 32 * mm])]
    if vitals:
        rows = [["Time", "Vital", "Value"]]
        for v in vitals:
            rows.append([v.get("time") or "—", v["name"].upper(), f"{v['value']} {v.get('unit') or ''}"])
        story += [Paragraph("Serial vitals", S["h2"]), _table(rows, [20 * mm, 40 * mm, 118 * mm])]
    crit = [a for a in alerts if a.get("level") in ("critical", "warning")]
    if crit:
        story += [Paragraph("Safety flags reviewed by EMT", S["h2"])]
        for a in crit[:12]:
            col = "#c0392b" if a["level"] == "critical" else "#b7791f"
            story.append(Paragraph(f"<font color='{col}'><b>{a['level'].upper()}</b></font> {a['code']} — {a['message']}", S["small"]))

    # integrity footer
    head_hash = verify.get("head", "")
    qr_img = None
    if HAS_QR:
        q = qrcode.QRCode(box_size=3, border=1)
        q.add_data(f"fieldscribe://verify?incident={inc['id']}&head={head_hash}&key={verify.get('key_id')}")
        q.make(fit=True)
        b = io.BytesIO()
        q.make_image(fill_color="black", back_color="white").save(b, format="PNG")
        b.seek(0)
        qr_img = Image(b, width=26 * mm, height=26 * mm)
    status = "VERIFIED" if verify.get("valid") else f"INTEGRITY FAILURE at block {verify.get('first_bad_seq')}"
    col = "#0e9f8a" if verify.get("valid") else "#c0392b"
    integ = [Paragraph(f"<b>Audit chain:</b> <font color='{col}'><b>{status}</b></font> · {verify.get('blocks')} blocks · "
                       f"{verify.get('algorithm')}", S["small"]),
             Paragraph(f"Ledger head: {head_hash}", S["mono"]),
             Paragraph(f"Device key id: {verify.get('key_id')} · Signed by {inc.get('crew')}"
                       + (f" · Received by {inc.get('handover_by')} at {inc.get('handover_at')}" if inc.get("handover_by") else ""), S["mono"]),
             Paragraph("Low-confidence and defaulted fields were presented to the EMT for confirmation before signing. "
                       "Reference ranges are demo values; verify against local 108 protocol.", S["small"])]
    ft = Table([[integ, qr_img or ""]], colWidths=[148 * mm, 30 * mm])
    ft.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEABOVE", (0, 0), (-1, 0), 0.8, LINE), ("TOPPADDING", (0, 0), (-1, -1), 6)]))
    story += [Spacer(0, 8), KeepTogether(ft)]
    doc.build(story)
    return buf.getvalue()
