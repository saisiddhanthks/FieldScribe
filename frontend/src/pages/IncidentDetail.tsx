import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis, Scatter, ErrorBar } from 'recharts'
import { FileDown, Braces, Mic, ShieldCheck, ShieldAlert, Ambulance, Hospital, Ban, PenLine, History, XCircle } from 'lucide-react'
import { ClockPanel, Readiness } from '../components/Clinical'
import { useAuth } from '../components/Auth'
import clsx from 'clsx'
import { api, download, ROUTE_LABEL, VITAL_COLOR, VITAL_LABEL } from '../lib/api'
import { Destinations, PatientIdentity, MedicoLegal, Refusal, AccessLog } from '../components/Field'
import { chartTheme, Empty, FlagLine, Hash, JsonView, Modal, Numeric, Panel, Spinner, Status, Triage, useFetch, useToast } from '../components/ui'
import { EcgTrace } from '../components/Ecg'

const STEPS = [
  ['call_received', 'Call received'], ['at_scene', 'At scene'], ['patient_contact', 'Patient contact'],
  ['left_scene', 'Left scene'], ['at_hospital', 'At hospital'], ['handover', 'Handover'],
] as const

const mins = (a?: string, b?: string) => {
  if (!a || !b) return null
  const [h1, m1] = a.split(':').map(Number), [h2, m2] = b.split(':').map(Number)
  let d = h2 * 60 + m2 - (h1 * 60 + m1); if (d < 0) d += 1440
  return d
}

export default function IncidentDetail() {
  const { id = '' } = useParams()
  const toast = useToast()
  const { data: inc, reload } = useFetch(() => api.incident(id), [id], 10000)
  const { can } = useAuth()
  const [edit, setEdit] = useState<{ e: any; mode: 'amend' | 'void' } | null>(null)
  const [fhir, setFhir] = useState<any>(null)
  const [fhirMode, setFhirMode] = useState<'bundle' | 'lite'>('bundle')
  const vit = inc?.vitals || []
  const series = useMemo(() => {
    const byTime: Record<string, any> = {}
    vit.forEach((v: any, i: number) => {
      const t = v.time || `#${i}`
      byTime[t] = byTime[t] || { t }
      if (v.name === 'bp') { const [s, d] = String(v.value).split('/').map(Number); byTime[t].sbp = s; byTime[t].dbp = d; byTime[t].map = Math.round((s + 2 * d) / 3); byTime[t].bpErr = [(s - d) / 2, (s - d) / 2]; byTime[t].bpMid = (s + d) / 2 }
      else if (['hr', 'spo2', 'rr', 'gcs', 'glucose'].includes(v.name)) byTime[t][v.name] = Number(v.value)
    })
    return Object.values(byTime).sort((a: any, b: any) => String(a.t).localeCompare(String(b.t)))
  }, [vit])
  if (!inc) return <div className="flex justify-center py-24"><Spinner size={24} /></div>
  const latest = (n: string) => [...vit].reverse().find((v: any) => v.name === n)
  const wf = inc.workflow || {}
  const setStatus = async (s: string) => { await api.patchIncident(id, { status: s, actor: inc.crew }); reload(); toast('ok', `Status set to ${s.replace('_', ' ')}`); window.dispatchEvent(new Event('fs:refresh')) }
  const openFhir = async (m: 'bundle' | 'lite') => { setFhirMode(m); setFhir(m === 'bundle' ? await api.fhir(id) : await api.fhirLite(id)) }
  const timeline = [
    ...inc.entries.map((e: any) => ({ t: e.payload.time || e.time, kind: e.kind, e })),
    ...Object.entries(wf).map(([k, v]) => ({ t: v as string, kind: 'workflow', label: STEPS.find(s => s[0] === k)?.[1] || k })),
  ].sort((a, b) => String(a.t).localeCompare(String(b.t)))
  const hr = Number(latest('hr')?.value) || 0
  return (
    <div className="max-w-[1600px] mx-auto space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-[13px] text-dim"><Link to="/incidents" className="hover:text-ink">Incidents</Link><span>/</span><span>{inc.dispatch_id}</span></div>
          <h1 className="font-num text-[34px] font-semibold leading-tight">{inc.complaint || 'Assessment in progress'}</h1>
          <div className="flex flex-wrap items-center gap-2 mt-1 text-[14px] text-dim">
            <Triage t={inc.triage} /><Status s={inc.status} />
            <span>{inc.patient?.age != null && `${inc.patient.age} y`} {inc.patient?.sex}</span>
            <span>· {inc.vehicle} · {inc.crew}</span>
            <span>· {inc.place} → {inc.destination || 'destination not set'}</span>
            {inc.mci_tag && <span className="chip bg-alarm/10 text-alarm border border-alarm/30">Mass casualty {inc.mci_tag}</span>}
            {inc.legal?.mlc?.is_mlc && <span className="chip bg-alarm/10 text-alarm border border-alarm/30">MLC</span>}
            {!inc.legal?.mlc && inc.mlc_suggest?.length > 0 && <span className="chip bg-warn/10 text-warn border border-warn/30">Possible MLC</span>}
            {inc.patient?.abha && <span className="chip bg-spo2/10 text-spo2 border border-spo2/30">ABHA linked</span>}
            {inc.legal?.refusal && <span className="chip bg-warn/10 text-warn border border-warn/30">Refused {inc.legal.refusal.what}</span>}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link to="/capture" className="btn-sec"><Mic size={15} />Add dictation</Link>
          <a className="btn-sec" href={api.pdfUrl(id)}><FileDown size={15} />Handover PDF</a>
          <button className="btn-sec" onClick={() => openFhir('bundle')}><Braces size={15} />FHIR bundle</button>
          {inc.status === 'on_scene' && <button className="btn-pri" onClick={() => setStatus('transporting')}><Ambulance size={15} />Depart scene</button>}
          {inc.status === 'transporting' && <Link to="/handover" className="btn-pri"><Hospital size={15} />Hand over at ED</Link>}
        </div>
      </div>

      <Panel title="108 workflow" sub={`Response ${mins(wf.call_received, wf.at_scene) ?? '—'} min · on scene ${mins(wf.at_scene, wf.left_scene) ?? '—'} min · transport ${mins(wf.left_scene, wf.at_hospital) ?? '—'} min`}>
        <ol className="grid grid-cols-3 md:grid-cols-6 gap-2">
          {STEPS.map(([k, l], i) => {
            const v = wf[k]
            return (
              <li key={k} className={clsx('relative rounded-md border px-3 py-2', v ? 'border-hr/40 bg-hr/[.05]' : 'border-dashed border-line')}>
                <div className="text-[12px] text-dim">{i + 1}. {l}</div>
                <div className={clsx('num text-[24px] font-semibold leading-none mt-1', v ? 'text-ink' : 'text-faint')}>{v || '--:--'}</div>
              </li>
            )
          })}
        </ol>
      </Panel>

      <div className="grid grid-cols-12 gap-4">
        <Panel className="col-span-12 xl:col-span-7" title="Handover readiness" sub="What the receiving ED needs, checked against the signed record">
          <Readiness c={inc.completeness} />
        </Panel>
        <Panel className="col-span-12 xl:col-span-5" title="Clinical clock" sub="Reminders from what has been logged">
          <ClockPanel timers={inc.clock} compact />
        </Panel>
      </div>

      <div className="grid grid-cols-12 gap-4">
        <div className="col-span-12 xl:col-span-7"><Destinations inc={inc} onChange={reload} /></div>
        <div className="col-span-12 xl:col-span-5"><PatientIdentity inc={inc} onChange={reload} /></div>
      </div>

      <div className="grid grid-cols-12 gap-4">
        <div className="col-span-12 xl:col-span-6"><MedicoLegal inc={inc} onChange={reload} /></div>
        <div className="col-span-12 xl:col-span-6"><Refusal inc={inc} onChange={reload} /></div>
      </div>

      <div className="grid grid-cols-12 gap-4">
        <Panel className="col-span-12 xl:col-span-8" title="Vitals" sub="Serial observations from dictation">
          {!vit.length ? <Empty title="No vitals recorded" /> : (
            <>
              <div className="rounded-md border border-line overflow-hidden mb-3">
                {hr ? <><EcgTrace bpm={hr} height={58} /><EcgTrace bpm={hr} kind="pleth" color="#35d0f0" height={42} /></> : <EcgTrace kind="resp" color="#f3cf3a" height={48} />}
              </div>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-2 mb-3">
                {['hr', 'spo2', 'bp', 'rr', 'gcs', 'glucose'].filter(n => latest(n)).slice(0, 5).map(n => {
                  const v = latest(n)
                  return <Numeric key={n} label={VITAL_LABEL[n]} value={v.value} unit={v.unit} color={VITAL_COLOR[n]} size="md" hint={v.time ? `at ${v.time}` : undefined} />
                })}
              </div>
              {series.length > 1 && (
                <div className="h-[230px]">
                  <ResponsiveContainer>
                    <ComposedChart data={series} margin={{ left: -12, right: 10, top: 8 }}>
                      <CartesianGrid stroke={chartTheme.grid} vertical={false} />
                      <XAxis dataKey="t" stroke={chartTheme.axis} tick={{ fontSize: 12 }} />
                      <YAxis stroke={chartTheme.axis} tick={{ fontSize: 12 }} domain={[0, 'auto']} />
                      <Tooltip {...chartTheme.tooltip} />
                      <Scatter dataKey="bpMid" name="NIBP" fill="#f2f4f5" shape={() => null as any}><ErrorBar dataKey="bpErr" width={8} stroke="#f2f4f5" strokeWidth={2} /></Scatter>
                      <Line dataKey="hr" name="HR" stroke="#3ee07f" strokeWidth={2} dot={{ r: 3 }} connectNulls />
                      <Line dataKey="spo2" name="SpO₂" stroke="#35d0f0" strokeWidth={2} dot={{ r: 3 }} connectNulls />
                      <Line dataKey="rr" name="Resp" stroke="#f3cf3a" strokeWidth={2} dot={{ r: 3 }} connectNulls />
                      <Line dataKey="glucose" name="GRBS" stroke="#ffa733" strokeWidth={2} dot={{ r: 3 }} connectNulls />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
              )}
            </>
          )}
        </Panel>
        <Panel className="col-span-12 xl:col-span-4" title="Patient" sub="Merged from every signed record">
          <dl className="grid grid-cols-[110px_1fr] gap-y-2 text-[14px]">
            <dt className="text-dim">Age / sex</dt><dd>{inc.patient?.age ?? '—'} {inc.patient?.sex || ''}{inc.patient?.weight_kg ? ` · ${inc.patient.weight_kg} kg` : ''}</dd>
            <dt className="text-dim">Allergies</dt><dd className={inc.patient?.allergies?.length ? 'text-alarm font-medium' : ''}>{inc.patient?.allergies?.join(', ') || inc.patient?.allergies_status || 'Not documented'}</dd>
            <dt className="text-dim">Complaints</dt><dd>{(inc.patient?.chief_complaints || []).join(', ') || '—'}</dd>
            <dt className="text-dim">Medico-legal</dt><dd>{inc.patient?.medico_legal ? 'Yes · police informed' : 'No'}</dd>
            <dt className="text-dim">Handover</dt><dd>{inc.handover_by ? `${inc.handover_by}` : 'Pending'}</dd>
            <dt className="text-dim">Integrity</dt>
            <dd className={inc.integrity?.scope_valid ? 'text-hr' : 'text-alarm'}>
              <span className="flex items-center gap-1.5">{inc.integrity?.scope_valid ? <ShieldCheck size={15} /> : <ShieldAlert size={15} />}{inc.integrity?.scope_valid ? `${inc.ledger.length} blocks verified` : 'Tampering detected'}</span>
            </dd>
          </dl>
          {inc.alerts?.filter((a: any) => a.level !== 'info').length > 0 && (
            <div className="mt-4 space-y-1.5 border-t border-line pt-3">
              <div className="text-[13px] text-dim mb-1">Flags reviewed at signing</div>
              {inc.alerts.filter((a: any) => a.level !== 'info').slice(0, 6).map((a: any, i: number) => <FlagLine key={i} f={a} />)}
            </div>
          )}
        </Panel>
      </div>

      <div className="grid grid-cols-12 gap-4">
        <Panel className="col-span-12 xl:col-span-7" title="Care timeline" sub="Medications, procedures and 108 milestones in order">
          {!timeline.length ? <Empty title="Nothing recorded yet" /> : (
            <ol className="relative border-l border-line2 ml-2 space-y-3 py-1">
              {timeline.map((x: any, i) => {
                const c = x.kind === 'medication' ? (x.e.status === 'withheld' ? '#ff4b4b' : '#3ee07f') : x.kind === 'procedure' ? '#35d0f0' : '#8a979f'
                const p = x.e?.payload
                return (
                  <li key={i} className="pl-5 relative">
                    <span className="absolute -left-[6px] top-1.5 w-[11px] h-[11px] rounded-full border-2 bg-black" style={{ borderColor: c }} />
                    <div className="flex flex-wrap items-baseline gap-x-3">
                      <span className="num text-[18px] font-semibold w-[52px]" style={{ color: c }}>{x.t || '--:--'}</span>
                      {x.kind === 'workflow' ? <span className="text-dim">{x.label}</span> : x.kind === 'medication' ? (
                        <span className="flex flex-wrap items-center gap-2">
                          <span className="font-medium">{p.drug}</span>
                          <span className="num text-[17px]">{p.rate || (p.dose != null ? `${p.dose} ${p.unit}` : '')}</span>
                          <span className="text-dim">{ROUTE_LABEL[p.route] || p.route}{p.device ? ` · ${p.device}` : ''}</span>
                          {x.e.status === 'withheld' && <span className="chip bg-alarm/15 text-alarm"><Ban size={12} />Withheld</span>}
                          {x.e.edited ? <span className="chip bg-co2/15 text-co2"><PenLine size={12} />Edited</span> : null}
                          {p.time_source === 'capture' && <span className="text-[12px] text-faint">time from capture</span>}
                          {x.e.amends && <span className="chip bg-co2/15 text-co2" title={x.e.change_reason}><History size={12} />Amended</span>}
                          {can('amend') && <EntryActions e={x.e} onEdit={setEdit} />}
                        </span>
                      ) : (
                        <span className="flex flex-wrap items-center gap-2"><span className="font-medium">{p.procedure}</span><span className="text-dim">{[p.device, p.site, p.energy].filter(Boolean).join(' · ')}</span>
                          {x.e.amends && <span className="chip bg-co2/15 text-co2" title={x.e.change_reason}><History size={12} />Amended</span>}
                          {can('amend') && <EntryActions e={x.e} onEdit={setEdit} />}</span>
                      )}
                    </div>
                  </li>
                )
              })}
            </ol>
          )}
          {inc.history?.length > 0 && (
            <div className="mt-4 border-t border-line pt-3">
              <div className="text-[13px] text-dim mb-2 flex items-center gap-1.5"><History size={14} />Correction history (originals are never deleted)</div>
              <ul className="space-y-1.5">
                {inc.history.map((h: any) => (
                  <li key={h.id} className="text-[13px]">
                    <span className="line-through text-faint">{h.name} {h.payload.dose != null ? `${h.payload.dose} ${h.payload.unit || ''}` : ''} {h.payload.route || ''} {h.payload.time || ''}</span>
                    <span className={clsx('ml-2 chip', h.status === 'voided' ? 'bg-alarm/15 text-alarm' : 'bg-co2/15 text-co2')}>{h.status === 'voided' ? 'voided' : 'amended'}</span>
                    <span className="text-dim"> · "{h.change_reason}" · {h.changed_by} · {h.changed_at ? new Date(h.changed_at).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' }) : ''}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Panel>
        <Panel className="col-span-12 xl:col-span-5" title="Signed records" sub="Original words are kept alongside the structured data">
          <div className="space-y-3">
            {inc.records.map((r: any) => (
              <div key={r.id} className="rounded-md border border-line bg-black p-3">
                <div className="flex items-center justify-between text-[13px]">
                  <span className="flex items-center gap-2"><span className={clsx('chip', r.source === 'voice' ? 'bg-spo2/10 text-spo2' : 'bg-raise text-dim')}>{r.source}</span>{r.signer}</span>
                  <span className="text-faint">block #{r.ledger_seq} · {r.capture_ms ? `${Math.round(r.capture_ms / 1000)}s` : ''}</span>
                </div>
                <p className="text-[14px] text-dim mt-2 leading-relaxed">{r.final_text}</p>
                {r.asr_text && r.asr_text !== r.final_text && <p className="text-[12px] text-faint mt-1.5">ASR heard: “{r.asr_text}”</p>}
              </div>
            ))}
          </div>
        </Panel>
      </div>

      <Panel title="Ledger blocks for this incident" sub="Each block commits to the one before it">
        <div className="flex gap-2 overflow-x-auto pb-1">
          {inc.ledger.map((b: any) => (
            <div key={b.seq} className="shrink-0 w-[210px] rounded-md border border-line bg-black p-2.5">
              <div className="flex justify-between text-[13px]"><span className="num text-[18px] font-semibold">#{b.seq}</span><span className="text-dim">{b.event_type.replace(/_/g, ' ').toLowerCase()}</span></div>
              <div className="mt-1"><Hash h={b.hash} n={14} /></div>
              <div className="text-[12px] text-faint mt-0.5">{new Date(b.ts).toLocaleTimeString('en-GB')} · {b.signer}</div>
            </div>
          ))}
        </div>
      </Panel>

      <AccessLog id={id} />

      <AmendModal edit={edit} onClose={() => setEdit(null)} onDone={() => { setEdit(null); reload(); window.dispatchEvent(new Event('fs:refresh')) }} />
      <Modal open={!!fhir} onClose={() => setFhir(null)} wide title={
        <span className="flex items-center gap-3">FHIR R4 export
          <span className="flex rounded-md border border-line2 p-0.5 text-[13px] font-normal">
            {(['bundle', 'lite'] as const).map(m => <button key={m} onClick={() => openFhir(m)} className={clsx('h-7 px-2.5 rounded', fhirMode === m ? 'bg-raise text-ink' : 'text-dim')}>{m === 'bundle' ? 'Full bundle' : 'FHIR-lite'}</button>)}
          </span>
        </span>}>
        {fhir && <>
          {fhirMode === 'bundle' && <div className="flex flex-wrap gap-1.5 mb-3">{Object.entries(fhir.entry.reduce((a: any, e: any) => ({ ...a, [e.resource.resourceType]: (a[e.resource.resourceType] || 0) + 1 }), {})).map(([k, v]: any) => <span key={k} className="chip bg-raise text-dim">{k} <span className="num text-ink">{v}</span></span>)}</div>}
          <JsonView data={fhir} />
          <div className="flex justify-end mt-3"><button className="btn-pri" onClick={() => download(`${inc.dispatch_id}_${fhirMode}.json`, fhir)}><FileDown size={15} />Download JSON</button></div>
        </>}
      </Modal>
    </div>
  )
}


function EntryActions({ e, onEdit }: { e: any; onEdit: (x: any) => void }) {
  return (
    <span className="inline-flex gap-1 ml-1">
      <button className="text-[12px] text-dim hover:text-ink flex items-center gap-1 px-1.5 py-0.5 rounded hover:bg-raise" onClick={() => onEdit({ e, mode: 'amend' })}><PenLine size={12} />Amend</button>
      <button className="text-[12px] text-dim hover:text-alarm flex items-center gap-1 px-1.5 py-0.5 rounded hover:bg-raise" onClick={() => onEdit({ e, mode: 'void' })}><XCircle size={12} />Void</button>
    </span>
  )
}

const REASONS = ['Wrong dose dictated', 'Wrong time', 'Wrong route', 'Misheard drug name', 'Entered on wrong patient', 'Not actually given']

function AmendModal({ edit, onClose, onDone }: { edit: { e: any; mode: 'amend' | 'void' } | null; onClose: () => void; onDone: () => void }) {
  const toast = useToast()
  const [f, setF] = useState<any>({})
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => { if (edit) { setF({ ...edit.e.payload }); setReason('') } }, [edit])
  if (!edit) return null
  const { e, mode } = edit
  const isMed = e.kind === 'medication'
  const set = (k: string, v: any) => setF((x: any) => ({ ...x, [k]: v }))
  const save = async () => {
    setBusy(true)
    try {
      if (mode === 'void') await api.voidEntry(e.id, reason)
      else {
        const changed = Object.fromEntries(Object.entries(f).filter(([k, v]) => ['drug', 'dose', 'unit', 'route', 'time', 'rate', 'procedure', 'device', 'site'].includes(k) && v !== e.payload[k]))
        await api.amend(e.id, changed, reason)
      }
      toast('ok', mode === 'void' ? 'Entry voided and signed into the audit chain' : 'Amendment signed into the audit chain; original kept')
      onDone()
    } catch (err: any) { toast('err', err.message) } finally { setBusy(false) }
  }
  return (
    <Modal open onClose={onClose} title={mode === 'void' ? `Void entry: ${e.name}` : `Amend entry: ${e.name}`}>
      {mode === 'amend' && (
        <div className="grid grid-cols-2 gap-3 mb-4">
          {isMed ? <>
            <label className="text-[13px] text-dim">Drug<input className="input mt-1" value={f.drug || ''} onChange={x => set('drug', x.target.value)} /></label>
            <label className="text-[13px] text-dim">Dose<input className="input mt-1 num" inputMode="decimal" value={f.dose ?? ''} onChange={x => set('dose', x.target.value === '' ? null : Number(x.target.value))} /></label>
            <label className="text-[13px] text-dim">Unit<input className="input mt-1" value={f.unit || ''} onChange={x => set('unit', x.target.value)} /></label>
            <label className="text-[13px] text-dim">Route
              <select className="input mt-1" value={f.route || ''} onChange={x => set('route', x.target.value)}>{Object.keys(ROUTE_LABEL).map(r => <option key={r} value={r}>{r} · {ROUTE_LABEL[r]}</option>)}</select>
            </label>
          </> : <label className="text-[13px] text-dim col-span-2">Procedure<input className="input mt-1" value={f.procedure || ''} onChange={x => set('procedure', x.target.value)} /></label>}
          <label className="text-[13px] text-dim">Time<input className="input mt-1 num" type="time" value={f.time || ''} onChange={x => set('time', x.target.value)} /></label>
        </div>
      )}
      {mode === 'void' && <p className="text-[14px] text-dim mb-3">The entry stays in the record and the audit chain, marked as entered in error. It is removed from handover, FHIR and the clinical clock.</p>}
      <label className="text-[13px] text-dim block">Reason (required)
        <input className="input mt-1" value={reason} onChange={x => setReason(x.target.value)} placeholder="Why is this being corrected?" />
      </label>
      <div className="flex flex-wrap gap-1.5 mt-2">{REASONS.map(r => <button key={r} className="chip h-7 px-2 bg-raise border border-line2 text-dim hover:text-ink" onClick={() => setReason(r)}>{r}</button>)}</div>
      <div className="flex justify-end gap-2 mt-4">
        <button className="btn-ghost" onClick={onClose}>Cancel</button>
        <button className={mode === 'void' ? 'btn-danger' : 'btn-pri'} disabled={!reason.trim() || busy} onClick={save}>{mode === 'void' ? 'Void and sign' : 'Sign amendment'}</button>
      </div>
    </Modal>
  )
}
