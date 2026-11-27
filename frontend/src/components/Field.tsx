import { useEffect, useRef, useState } from 'react'
import { Hospital, Navigation, CheckCircle2, XCircle, Scale, IdCard, FileSignature, Eye, Eraser, AlertTriangle, ShieldCheck } from 'lucide-react'
import clsx from 'clsx'
import { api } from '../lib/api'
import { Panel, Spinner, useFetch, useToast } from './ui'
import { useAuth } from './Auth'

const nowHM = () => new Date().toTimeString().slice(0, 5)

/* ------------------------------------------------------------------ right hospital */

export function Destinations({ inc, onChange }: { inc: any; onChange: () => void }) {
  const toast = useToast()
  const { can } = useAuth()
  const { data, loading, reload } = useFetch(() => api.destinations(inc.id), [inc.id, inc.complaint, inc.version])
  const [busy, setBusy] = useState<string | null>(null)
  const choose = async (h: any) => {
    setBusy(h.id)
    try {
      await api.patchIncident(inc.id, { destination: h.name, eta_min: h.eta_min ?? undefined })
      toast('ok', `Destination set: ${h.name}${h.eta_min != null ? ` · ${h.eta_min} min` : ''}. The ED sees you coming.`)
      onChange(); reload(); window.dispatchEvent(new Event('fs:refresh'))
    } catch (e: any) { toast('err', e.message) } finally { setBusy(null) }
  }
  return (
    <Panel title="Right hospital" sub={data?.condition ? `For ${data.condition.toLowerCase()}: capability first, then drive time` : 'Capability first, then drive time'}>
      {loading && !data ? <Spinner /> : data && (
        <>
          <div className="flex flex-wrap gap-1.5 mb-3">
            {data.needs.map((n: any) => <span key={n.key} title={n.why} className="chip bg-spo2/10 text-spo2 border border-spo2/30">{n.label}</span>)}
          </div>
          {data.note && (
            <div className="flex gap-2 rounded-md border border-warn/40 bg-warn/10 px-3 py-2 mb-3 text-[13.5px]">
              <AlertTriangle size={16} className="text-warn shrink-0 mt-0.5" /><span>{data.note}</span>
            </div>
          )}
          <ol className="space-y-1.5">
            {data.hospitals.map((h: any, i: number) => (
              <li key={h.id} className={clsx('rounded-md border px-3 py-2.5 flex items-center gap-3',
                h.id === data.recommended ? 'border-hr/50 bg-hr/[.06]' : 'border-line', !h.suitable && 'opacity-70')}>
                <div className={clsx('num text-[20px] font-semibold w-5 text-center', h.id === data.recommended ? 'text-hr' : 'text-faint')}>{i + 1}</div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium text-[15px]">{h.name}</span>
                    {h.id === data.recommended && <span className="chip bg-hr/15 text-hr">Recommended</span>}
                    {h.current && <span className="chip bg-raise text-ink border border-line2">Current destination</span>}
                  </div>
                  <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[12.5px] mt-0.5">
                    {h.has.map((k: string) => <span key={k} className="text-hr flex items-center gap-1"><CheckCircle2 size={12} />{data.needs.find((n: any) => n.key === k)?.label.split(' (')[0]}</span>)}
                    {h.missing.map((k: string) => <span key={k} className="text-alarm flex items-center gap-1"><XCircle size={12} /><span className="line-through decoration-alarm/60">{data.needs.find((n: any) => n.key === k)?.label.split(' (')[0]}</span></span>)}
                  </div>
                </div>
                <div className="text-right shrink-0">
                  <div className="num text-[22px] font-semibold leading-none">{h.eta_min ?? '–'}<span className="text-[12px] text-dim font-sans font-normal"> min</span></div>
                  <div className="text-[11.5px] text-faint">{h.distance_km != null ? `${h.distance_km} km` : ''}{h.route_source === 'estimate' ? ' · est.' : ''}</div>
                </div>
                {can('capture') && !h.current && (
                  <button className="btn-sec h-8 px-2.5 shrink-0" disabled={busy === h.id} onClick={() => choose(h)} aria-label={`Go to ${h.name}`}>
                    {busy === h.id ? <Spinner /> : <Navigation size={14} />}<span className="hidden sm:inline">Go here</span>
                  </button>
                )}
              </li>
            ))}
          </ol>
          <p className="text-[12px] text-faint mt-2.5 flex items-center gap-1.5"><Hospital size={13} />Capabilities are a sample directory. Your control room keeps the real one in backend/hospitals.json.</p>
        </>
      )}
    </Panel>
  )
}

/* ------------------------------------------------------------------ patient identity + ABHA */

export function PatientIdentity({ inc, onChange }: { inc: any; onChange: () => void }) {
  const toast = useToast()
  const { can } = useAuth()
  const p = inc.patient || {}
  const [edit, setEdit] = useState(false)
  const [f, setF] = useState<any>({})
  const [err, setErr] = useState('')
  useEffect(() => { setF({ abha: p.abha || '', name: p.name || '', relative_name: p.relative_name || '', relative_phone: p.relative_phone || '' }) }, [inc.version, edit])
  const save = async (e: React.FormEvent) => {
    e.preventDefault(); setErr('')
    try { await api.setPatient(inc.id, f); toast('ok', f.abha ? 'Patient identity saved and ABHA linked' : 'Patient identity saved'); setEdit(false); onChange() }
    catch (e: any) { setErr(e.message) }
  }
  return (
    <Panel title="Patient identity" sub="ABHA links this record to the patient’s national health record (ABDM)"
      actions={can('capture') && !edit ? <button className="btn-sec h-8" onClick={() => setEdit(true)}><IdCard size={14} />{p.abha || p.name ? 'Edit' : 'Add'}</button> : undefined}>
      {!edit ? (
        <dl className="grid grid-cols-[120px_1fr] gap-y-2 text-[14px]">
          <dt className="text-dim">ABHA</dt>
          <dd>{p.abha ? <span className="flex items-center gap-2 flex-wrap"><span className="font-mono">{p.abha}</span><span className="chip bg-warn/10 text-warn">Linked · verify at ED</span></span> : <span className="text-faint">Not linked. Ask for the ABHA card, or the address like name@abdm</span>}</dd>
          <dt className="text-dim">Name</dt><dd>{p.name || <span className="text-faint">Unknown</span>}</dd>
          <dt className="text-dim">Relative</dt><dd>{p.relative_name || p.relative_phone ? `${p.relative_name || ''} ${p.relative_phone || ''}` : <span className="text-faint">None recorded</span>}</dd>
        </dl>
      ) : (
        <form onSubmit={save} className="space-y-2.5">
          <label className="block"><span className="text-[13px] text-dim">ABHA number or ABHA address</span>
            <input className="input mt-1 h-10 font-mono" value={f.abha} onChange={e => setF({ ...f, abha: e.target.value })} placeholder="91-1234-5678-9012 or name@abdm" autoFocus /></label>
          <label className="block"><span className="text-[13px] text-dim">Patient name (if known)</span>
            <input className="input mt-1 h-10" value={f.name} onChange={e => setF({ ...f, name: e.target.value })} /></label>
          <div className="grid grid-cols-2 gap-2">
            <label className="block"><span className="text-[13px] text-dim">Relative / bystander</span>
              <input className="input mt-1 h-10" value={f.relative_name} onChange={e => setF({ ...f, relative_name: e.target.value })} /></label>
            <label className="block"><span className="text-[13px] text-dim">Their phone</span>
              <input className="input mt-1 h-10" inputMode="tel" value={f.relative_phone} onChange={e => setF({ ...f, relative_phone: e.target.value })} /></label>
          </div>
          {err && <p className="text-[13px] text-alarm" role="alert">{err}</p>}
          <div className="flex gap-2 justify-end"><button type="button" className="btn-ghost h-9" onClick={() => setEdit(false)}>Cancel</button><button className="btn-pri h-9">Save</button></div>
          <p className="text-[12px] text-faint">The format is checked here. The ED confirms it against ABDM when the hospital is online. The audit ledger stores only the last 4 digits.</p>
        </form>
      )}
    </Panel>
  )
}

/* ------------------------------------------------------------------ medico-legal case */

const MLC_CATS = ['Road traffic accident', 'Assault / injury by another person', 'Burns', 'Poisoning / overdose', 'Fall from height',
  'Hanging / strangulation', 'Drowning', 'Electrocution', 'Unknown cause / found unconscious', 'Other']

export function MedicoLegal({ inc, onChange }: { inc: any; onChange: () => void }) {
  const toast = useToast()
  const { can } = useAuth()
  const m = inc.legal?.mlc
  const sugg: string[] = inc.mlc_suggest || []
  const [open, setOpen] = useState(false)
  const [f, setF] = useState<any>({})
  useEffect(() => {
    setF({ category: m?.category || sugg[0] || MLC_CATS[0], police_station: m?.police_station || '', informed: m?.informed || false,
      informed_at: m?.informed_at || '', officer: m?.officer || '', gd_number: m?.gd_number || '', brought_by: m?.brought_by || '', belongings: m?.belongings || '' })
  }, [inc.version, open])
  const save = async (is_mlc: boolean) => {
    try {
      await api.setMlc(inc.id, is_mlc ? { is_mlc, ...f } : { is_mlc, reason: 'Assessed: not a medico-legal case' })
      toast('ok', is_mlc ? 'MLC recorded and sealed in the ledger' : 'Marked as not medico-legal'); setOpen(false); onChange()
    } catch (e: any) { toast('err', e.message) }
  }
  const pending = sugg.length > 0 && !m
  return (
    <Panel title="Medico-legal case" sub="Police intimation for accidents, assault, burns, poisoning and similar cases"
      className={clsx(pending && 'ring-1 ring-warn/50')}
      actions={can('capture') && !open ? <button className={clsx('h-8', pending ? 'btn-pri' : 'btn-sec')} onClick={() => setOpen(true)}><Scale size={14} />{m ? 'Edit' : 'Record'}</button> : undefined}>
      {!open && (
        m?.is_mlc ? (
          <dl className="grid grid-cols-[130px_1fr] gap-y-1.5 text-[14px]">
            <dt className="text-dim">Category</dt><dd><span className="chip bg-alarm/10 text-alarm">MLC</span> {m.category}</dd>
            <dt className="text-dim">Police station</dt><dd>{m.police_station || '—'}</dd>
            <dt className="text-dim">Informed</dt><dd>{m.informed ? `Yes, at ${m.informed_at || '—'}` : <span className="text-warn">Not yet</span>}{m.officer ? ` · ${m.officer}` : ''}{m.gd_number ? ` · GD ${m.gd_number}` : ''}</dd>
            <dt className="text-dim">Brought by</dt><dd>{m.brought_by || '—'}</dd>
            {m.belongings && <><dt className="text-dim">Belongings</dt><dd>{m.belongings}</dd></>}
          </dl>
        ) : m && !m.is_mlc ? <p className="text-[14px] text-dim">Assessed as not medico-legal by {m.decided_by}.</p>
          : pending ? (
            <div className="flex gap-2 text-[14px]"><AlertTriangle size={17} className="text-warn shrink-0 mt-0.5" />
              <div><b className="text-warn">Likely medico-legal:</b> {sugg.join(', ')}. <span className="text-dim">Inform the police and record it before handover. The ED must register an MLC.</span></div></div>
          ) : <p className="text-[14px] text-faint">Nothing suggests a medico-legal case so far.</p>
      )}
      {open && (
        <div className="space-y-2.5">
          <label className="block"><span className="text-[13px] text-dim">Category</span>
            <select className="input mt-1 h-10" value={f.category} onChange={e => setF({ ...f, category: e.target.value })}>
              {[...new Set([...sugg, ...MLC_CATS])].map(c => <option key={c}>{c}</option>)}
            </select></label>
          <div className="grid grid-cols-2 gap-2">
            <label className="block"><span className="text-[13px] text-dim">Police station</span><input className="input mt-1 h-10" value={f.police_station} onChange={e => setF({ ...f, police_station: e.target.value })} placeholder="e.g. Madiwala" /></label>
            <label className="block"><span className="text-[13px] text-dim">Brought by</span><input className="input mt-1 h-10" value={f.brought_by} onChange={e => setF({ ...f, brought_by: e.target.value })} placeholder="Bystander, police, relative" /></label>
          </div>
          <label className="flex items-center gap-2 text-[14px]"><input type="checkbox" className="w-4 h-4 accent-[#3ee07f]" checked={f.informed}
            onChange={e => setF({ ...f, informed: e.target.checked, informed_at: e.target.checked ? (f.informed_at || nowHM()) : '' })} />Police informed</label>
          {f.informed && (
            <div className="grid grid-cols-3 gap-2">
              <label className="block"><span className="text-[13px] text-dim">At</span><input className="input mt-1 h-10" type="time" value={f.informed_at} onChange={e => setF({ ...f, informed_at: e.target.value })} /></label>
              <label className="block"><span className="text-[13px] text-dim">Officer</span><input className="input mt-1 h-10" value={f.officer} onChange={e => setF({ ...f, officer: e.target.value })} /></label>
              <label className="block"><span className="text-[13px] text-dim">GD / FIR no.</span><input className="input mt-1 h-10" value={f.gd_number} onChange={e => setF({ ...f, gd_number: e.target.value })} /></label>
            </div>
          )}
          <label className="block"><span className="text-[13px] text-dim">Belongings handed over (optional)</span><input className="input mt-1 h-10" value={f.belongings} onChange={e => setF({ ...f, belongings: e.target.value })} placeholder="Phone, wallet ₹ 420, helmet" /></label>
          <div className="flex flex-wrap gap-2 justify-end pt-1">
            <button className="btn-ghost h-9 mr-auto" onClick={() => save(false)}>Not an MLC</button>
            <button className="btn-ghost h-9" onClick={() => setOpen(false)}>Cancel</button>
            <button className="btn-pri h-9" onClick={() => save(true)}><Scale size={14} />Record MLC</button>
          </div>
        </div>
      )}
    </Panel>
  )
}

/* ------------------------------------------------------------------ refusal of care */

function SignaturePad({ onChange }: { onChange: (dataUrl: string | null) => void }) {
  const ref = useRef<HTMLCanvasElement>(null)
  const drawing = useRef(false)
  const dirty = useRef(false)
  useEffect(() => {
    const c = ref.current!; const r = c.getBoundingClientRect()
    c.width = r.width * 2; c.height = r.height * 2
    const x = c.getContext('2d')!; x.scale(2, 2); x.lineWidth = 2.2; x.lineCap = 'round'; x.lineJoin = 'round'; x.strokeStyle = '#0b0f14'
    x.fillStyle = '#ffffff'; x.fillRect(0, 0, r.width, r.height)
  }, [])
  const pos = (e: React.PointerEvent) => { const r = ref.current!.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top] }
  const down = (e: React.PointerEvent) => { ref.current!.setPointerCapture(e.pointerId); drawing.current = true; const [x, y] = pos(e); const g = ref.current!.getContext('2d')!; g.beginPath(); g.moveTo(x, y) }
  const move = (e: React.PointerEvent) => { if (!drawing.current) return; const [x, y] = pos(e); const g = ref.current!.getContext('2d')!; g.lineTo(x, y); g.stroke(); dirty.current = true }
  const up = () => { if (!drawing.current) return; drawing.current = false; if (dirty.current) onChange(ref.current!.toDataURL('image/png')) }
  const clear = () => { const c = ref.current!; const g = c.getContext('2d')!; const r = c.getBoundingClientRect(); g.fillStyle = '#fff'; g.fillRect(0, 0, r.width, r.height); dirty.current = false; onChange(null) }
  return (
    <div>
      <div className="relative">
        <canvas ref={ref} className="w-full h-[130px] rounded-md bg-white touch-none cursor-crosshair" aria-label="Signature pad: sign with finger, stylus or mouse"
          onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerLeave={up} />
        <span className="pointer-events-none absolute left-3 bottom-2 text-[12px] text-[#8a979f]">Sign here</span>
        <button type="button" className="absolute right-2 top-2 btn-ghost h-7 px-2 bg-black/70" onClick={clear}><Eraser size={13} />Clear</button>
      </div>
    </div>
  )
}

export function Refusal({ inc, onChange }: { inc: any; onChange: () => void }) {
  const toast = useToast()
  const { can } = useAuth()
  const r = inc.legal?.refusal
  const [open, setOpen] = useState(false)
  const [f, setF] = useState<any>({ what: 'transport', reason: '', risks_explained: false, capacity: 'yes', signed_by: '', relation: 'Self', witness: '', advice_given: 'Call 108 again at once if symptoms worsen.' })
  const [sig, setSig] = useState<string | null>(null)
  const [err, setErr] = useState('')
  const save = async () => {
    setErr('')
    try { await api.setRefusal(inc.id, { ...f, signature: sig || '' }); toast('ok', 'Refusal recorded, signed and sealed in the ledger'); setOpen(false); onChange() }
    catch (e: any) { setErr(e.message) }
  }
  return (
    <Panel title="Refusal of care (LAMA)" sub="When the patient refuses treatment or transport against advice"
      actions={can('capture') && !r && !open ? <button className="btn-sec h-8" onClick={() => setOpen(true)}><FileSignature size={14} />Record refusal</button> : undefined}>
      {r ? (
        <div className="flex gap-4 flex-wrap">
          <dl className="grid grid-cols-[110px_1fr] gap-y-1.5 text-[14px] flex-1 min-w-[260px]">
            <dt className="text-dim">Refused</dt><dd><span className="chip bg-warn/10 text-warn capitalize">{r.what}</span></dd>
            <dt className="text-dim">Reason</dt><dd>{r.reason || '—'}</dd>
            <dt className="text-dim">Signed by</dt><dd>{r.signed_by} ({r.relation}){r.witness ? ` · witness ${r.witness}` : ''}</dd>
            <dt className="text-dim">Capacity</dt><dd>{r.capacity === 'yes' ? 'Patient has capacity' : 'Representative decided'}</dd>
            <dt className="text-dim">Advice</dt><dd>{r.advice_given || '—'}</dd>
            <dt className="text-dim">Sealed</dt><dd className="flex items-center gap-1.5 text-hr"><ShieldCheck size={14} /><span className="font-mono text-[12px]">{r.signature_sha256?.slice(0, 16)}…</span></dd>
          </dl>
          {r.signature && <img src={r.signature} alt={`Signature of ${r.signed_by}`} className="h-[90px] rounded-md bg-white border border-line" />}
        </div>
      ) : !open ? <p className="text-[14px] text-faint">No refusal recorded.</p> : (
        <div className="space-y-2.5">
          <div className="grid grid-cols-3 gap-1 p-1 rounded-lg bg-raise border border-line2" role="radiogroup" aria-label="What was refused">
            {[['transport', 'Transport'], ['treatment', 'Treatment'], ['both', 'Both']].map(([k, l]) => (
              <button type="button" key={k} role="radio" aria-checked={f.what === k} onClick={() => setF({ ...f, what: k })}
                className={clsx('h-9 rounded-md text-[14px]', f.what === k ? 'bg-black text-ink border border-line2' : 'text-dim')}>{l}</button>
            ))}
          </div>
          <label className="block"><span className="text-[13px] text-dim">Reason given</span><input className="input mt-1 h-10" value={f.reason} onChange={e => setF({ ...f, reason: e.target.value })} placeholder="Wants to see family doctor" /></label>
          <div className="grid grid-cols-2 gap-2">
            <label className="block"><span className="text-[13px] text-dim">Who is deciding</span>
              <select className="input mt-1 h-10" value={f.capacity} onChange={e => setF({ ...f, capacity: e.target.value, relation: e.target.value === 'yes' ? 'Self' : '' })}>
                <option value="yes">Patient (has capacity)</option><option value="representative">Representative / guardian</option>
              </select></label>
            <label className="block"><span className="text-[13px] text-dim">Relation</span><input className="input mt-1 h-10" value={f.relation} onChange={e => setF({ ...f, relation: e.target.value })} /></label>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <label className="block"><span className="text-[13px] text-dim">Name of person signing</span><input className="input mt-1 h-10" value={f.signed_by} onChange={e => setF({ ...f, signed_by: e.target.value })} /></label>
            <label className="block"><span className="text-[13px] text-dim">Witness</span><input className="input mt-1 h-10" value={f.witness} onChange={e => setF({ ...f, witness: e.target.value })} placeholder="Name of witness" /></label>
          </div>
          <label className="block"><span className="text-[13px] text-dim">Advice given</span><input className="input mt-1 h-10" value={f.advice_given} onChange={e => setF({ ...f, advice_given: e.target.value })} /></label>
          <label className="flex items-start gap-2 text-[14px]"><input type="checkbox" className="w-4 h-4 mt-0.5 accent-[#3ee07f]" checked={f.risks_explained} onChange={e => setF({ ...f, risks_explained: e.target.checked })} />
            I explained the risks of refusing, including death or disability, in a language they understand.</label>
          <SignaturePad onChange={setSig} />
          {err && <p className="text-[13px] text-alarm" role="alert">{err}</p>}
          <div className="flex gap-2 justify-end">
            <button className="btn-ghost h-9" onClick={() => setOpen(false)}>Cancel</button>
            <button className="btn-pri h-9" disabled={!sig || !f.risks_explained || !f.signed_by} onClick={save}><FileSignature size={14} />Sign and seal</button>
          </div>
        </div>
      )}
    </Panel>
  )
}

/* ------------------------------------------------------------------ access log */

export function AccessLog({ id }: { id: string }) {
  const { data } = useFetch(() => api.access(id), [id], 30000)
  const role: Record<string, string> = { emt: 'Crew', ed: 'ED', admin: 'Supervisor' }
  return (
    <Panel title="Who viewed this record" sub="Every view and export, per person (DPDP Act 2023)">
      {!data?.length ? <p className="text-[14px] text-faint">No views logged yet.</p> : (
        <ul className="divide-y divide-line/70 max-h-[220px] overflow-auto -mx-1">
          {data.map((a: any, i: number) => (
            <li key={i} className="flex items-center gap-2 h-9 px-1 text-[14px]">
              <Eye size={14} className="text-dim shrink-0" />
              <span className="font-medium truncate">{a.user_name}</span>
              <span className="chip bg-raise text-dim">{role[a.role] || a.role}</span>
              <span className="text-dim truncate">{a.action}</span>
              <span className="ml-auto num text-dim tabular-nums shrink-0">{new Date(a.at).toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}</span>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  )
}
