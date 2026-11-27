"""Seed realistic, fully synthetic demo incidents (no real PHI)."""
from __future__ import annotations

import random
from datetime import timedelta

from . import audit, db, services
from .nlp.ner import extract

SCENARIOS = [
    {"place": "Silk Board junction, Hosur Rd", "lat": 12.9177, "lng": 77.6233, "dest": "Jayadeva Institute of Cardiology", "eta": 9,
     "status": "transporting", "hours_ago": 0.4, "crew": 0,
     "notes": ["call received at {t0}, reached scene at {t1}. 58 year old male, chest pain since 40 minutes, sweating. bp 150/94, pulse 108, spo2 93. no known allergies.",
               "ecosprin 300 mg chewed at {t2}. sorbitrate 5 mg sublingual at {t3}. ecg done at {t3}, st elevation. oxygen 4 litres by nasal cannula. 18g cannula left forearm at {t4}. triage red. left scene at {t5}", "reassessed at {t5}: bp 138/88, pulse 96, spo2 97, pain 4/10."]},
    {"place": "Outer Ring Rd, Marathahalli", "lat": 12.9569, "lng": 77.7011, "dest": "Victoria Hospital", "eta": 14,
     "status": "transporting", "hours_ago": 0.7, "crew": 1,
     "notes": ["call received at {t0}, on scene at {t1}. rta two wheeler, 24 year old male, helmet absent. gcs 13, e3 v4 m6. bp 100/64, pulse 122. bleeding from scalp, pressure dressing applied. c collar applied.",
               "ringer lactate 500 ml iv started at {t2}. txa 1 g iv at {t3}. fentanyl 50 mcg iv at {t4}. pupils equal reactive. triage red. medico legal case, police informed. left scene at {t5}", "en route at {t5}: bp 112/72, pulse 108, gcs 14, spo2 98."]},
    {"place": "Jayanagar 4th Block", "lat": 12.9293, "lng": 77.5824, "dest": "St. John's Medical College Hospital", "eta": 0,
     "status": "handed_over", "hours_ago": 3.2, "crew": 2,
     "notes": ["call received at {t0}, reached scene at {t1}. 9 year old girl weight 28 kg, wheezing, breathless. spo2 89, rr 34. allergic to penicillin.",
               "asthalin 2.5 mg nebulised at {t2}. ipravent 250 mcg nebulised at {t3}. at {t4} spo2 95, rr 26. hydrocortisone 100 mg iv at {t4}. triage yellow. reached hospital at {t5}"]},
    {"place": "Yeshwanthpur industrial area", "lat": 13.0285, "lng": 77.5401, "dest": "K.C. General Hospital", "eta": 0,
     "status": "handed_over", "hours_ago": 6.5, "crew": 3,
     "notes": ["call received at {t0}, reached scene at {t1}. 46 year old female, known diabetic, unresponsive. grbs 42. gcs 9.",
               "d25 100 ml iv at {t2}. at {t4} grbs 118, gcs 14. avil 22.75 mg im not given. triage yellow. reached hospital at {t5}"]},
    {"place": "Hebbal flyover", "lat": 13.0358, "lng": 77.5970, "dest": "NIMHANS", "eta": 11,
     "status": "on_scene", "hours_ago": 0.15, "crew": 4,
     "notes": ["call received at {t0}, reached scene at {t1}. 67 year old male, sudden slurred speech and weakness of right arm, onset 50 minutes. bp 182/104, grbs 136, gcs 14. triage red."]},
    {"place": "Whitefield, ITPL main rd", "lat": 12.9855, "lng": 77.7362, "dest": "Victoria Hospital", "eta": 0,
     "status": "handed_over", "hours_ago": 9.0, "crew": 5,
     "notes": ["call received at {t0}, reached scene at {t1}. 31 year old female, allergic reaction after prawns, lip swelling, urticaria, wheeze. bp 88/56, pulse 128.",
               "adrenaline 0.5 mg im at {t2} into the thigh. avil 45.5 mg iv at {t3}. normal saline 1000 ml iv. efcorlin 200 mg iv at {t4}. at {t4} bp 110/70, pulse 104, spo2 97. triage red. reached hospital at {t5}"]},
    {"place": "KR Puram railway station", "lat": 13.0007, "lng": 77.6770, "dest": "Victoria Hospital", "eta": 0,
     "status": "handed_over", "hours_ago": 13.0, "crew": 0,
     "notes": ["call received at {t0}, reached scene at {t1}. 35 year old male, generalised fits for 6 minutes. gcs 8, spo2 90.",
               "midazolam 5 mg im at {t2}. oxygen 10 litres by non rebreather. recovery position. fits stopped. grbs 104. triage yellow. reached hospital at {t5}"]},
    {"place": "Electronic City phase 1", "lat": 12.8452, "lng": 77.6602, "dest": "St. John's Medical College Hospital", "eta": 0,
     "status": "handed_over", "hours_ago": 17.5, "crew": 1,
     "notes": ["call received at {t0}, reached scene at {t1}. 52 year old male, fall from ladder, deformity of left forearm. pain 8/10. bp 132/84, pulse 96.",
               "splint applied to left forearm at {t2}. voveran 75 mg im at {t3}. emeset 4 mg iv at {t4}. triage green. reached hospital at {t5}"]},
    {"place": "Banashankari 2nd stage", "lat": 12.9255, "lng": 77.5468, "dest": "Jayadeva Institute of Cardiology", "eta": 0,
     "status": "handed_over", "hours_ago": 21.0, "crew": 2,
     "notes": ["call received at {t0}, reached scene at {t1}. 71 year old female, collapsed, no pulse. cpr started at {t1}. aed shock given 200 joules at {t2}.",
               "adrenaline 1 mg iv at {t3}. igel inserted. rosc at {t4}. amiodarone 300 mg iv at {t4}. triage red. reached hospital at {t5}"]},
]


def _fmt(dt):
    return dt.astimezone().strftime("%H:%M")


def seed(reset: bool = False) -> None:
    if reset:
        db.reset()
        db.get()
    random.seed(108)
    db.set_setting("online", "1")
    db.set_setting("manual_baseline_s", "210")
    now = services.now()
    for i, sc in enumerate(sorted(SCENARIOS, key=lambda s: -s["hours_ago"])):
        start = now - timedelta(hours=sc["hours_ago"])
        times = [min(start + timedelta(minutes=m), now - timedelta(minutes=6 - j)) for j, m in enumerate((0, 12, 15, 19, 23, 31))]
        tk = {f"t{j}": _fmt(t) for j, t in enumerate(times)}
        inc = services.create_incident({
            "vehicle": f"KA-{random.choice(['01', '02', '03', '04', '05'])}-G-{1080 + i * 37}",
            "crew": services.CREW[sc["crew"]], "place": sc["place"], "lat": sc["lat"], "lng": sc["lng"],
            "destination": sc["dest"], "eta_min": sc["eta"] or None, "status": "on_scene",
        }, ts=start)
        for k, note in enumerate(sc["notes"]):
            text = note.format(**tk)
            r = extract(text, services.history_for(inc["id"]))
            ents = []
            for e in r["entities"]:
                e = dict(e)
                e["status"] = "withheld" if e["negated"] else "confirmed"
                ents.append(e)
            source = "voice" if (i + k) % 2 == 0 else "text"
            asr_text = _asr_like(text) if source == "voice" else None
            services.sign_record(inc["id"], {
                "source": source, "asr_text": asr_text, "final_text": text, "capture_ms": random.randint(24000, 62000),
                "signer": inc["crew"], "entries": ents, "vitals": r["vitals"], "patient": r["patient"],
                "workflow": r["workflow"], "alerts": r["alerts"], "stats": r["stats"],
            }, ts=times[min(2 + k * 2, 5)] + timedelta(minutes=k * 4 if k > 1 else 0))
        if sc["status"] != "on_scene":
            services.update_incident(inc["id"], {"status": "transporting"}, inc["crew"], ts=times[5])
        if sc["status"] == "handed_over":
            services.handover(inc["id"], random.choice(["Dr. A. Rao (ED)", "Dr. K. Menon (ED)", "Dr. S. Patil (ED)"]),
                              ts=times[5] + timedelta(minutes=random.randint(14, 26)))
    # first 6 incidents synced; the two live ones keep items queued to show offline buffering
    services.run_sync()
    db.set_setting("online", "1")
    live = [i["id"] for i in services.list_incidents() if i["status"] in ("on_scene", "transporting")]
    with db.tx() as c:
        for iid in live:
            c.execute("UPDATE outbox SET status='queued', synced_at=NULL WHERE incident_id=? AND kind='record'", (iid,))


def _asr_like(text: str) -> str:
    """Make a plausible raw-ASR transcript (the EMT later corrected it) for field-WER stats."""
    swaps = {"ecosprin": "eco sprin", "sorbitrate": "sorbi trate", "asthalin": "asthaline", "ipravent": "ipra vent",
             "efcorlin": "f corlin", "voveran": "vover an", "emeset": "emme set", "txa": "t x a", "igel": "i gel"}
    out = text
    for k, v in swaps.items():
        out = out.replace(k, v)
    return out


if __name__ == "__main__":
    seed(reset=True)
    print("seeded", db.q1("SELECT COUNT(*) n FROM incidents")["n"], "incidents;", audit.verify()["blocks"], "ledger blocks")
