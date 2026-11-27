import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { FileDown, Braces, CheckCheck, AlertOctagon } from 'lucide-react'
import clsx from 'clsx'
import { api, download, ROUTE_LABEL, VITAL_COLOR, VITAL_LABEL } from '../lib/api'
import { Empty, FlagLine, Numeric, Panel, Spinner, Status, Triage, useFetch, useToast } from '../components/ui'
import { Readiness } from '../components/Clinical'
import { useAuth } from '../components/Auth'

const PRI: Record<string, number> = { RED: 0, YELLOW: 1, GREEN: 2 }

export default function Handover() {
  const toast = useToast()
  const { data: incs, reload } = useFetch(api.incidents, [], 6000)
  const { data: rt } = useFetch(api.routes, [], 20000)
  const [fetchedAt, setFetchedAt] = useState(Date.now())
  useEffect(() => { setFetchedAt(Date.now()) }, [rt])
  const routeBy: Record<string, any> = Object.fromEntries((rt?.routes || []).map((r: any) => [r.incident_id, r]))
  const [sel, setSel] = useState<string>('')
  const [now, setNow] = useState(Date.now())
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t) }, [])
  const incoming = useMemo(() => (incs || []).filter((i: any) => i.status === 'transporting' || i.status === 'on_scene')
    .sort((a: any, b: any) => (PRI[a.triage] ?? 3) - (PRI[b.triage] ?? 3)), [incs])
  const done = (incs || []).filter((i: any) => i.status === 'handed_over').slice(0, 6)
  useEffect(() => { if (!sel && incoming.length) setSel(incoming[0].id) }, [incoming, sel])
  const { data: inc, reload: reloadInc } = useFetch(() => sel ? api.incident(sel) : Promise.resolve(null), [sel])
  const { user, authOn, can } = useAuth()
  const [by, setBy] = useState('Dr. A. Rao (ED)')
  const ack = async () => {
    try { await api.handover(sel, by) } catch (e: any) { return toast('err', e.message) }
    toast('ok', `Handover acknowledged by ${authOn && user ? user.name : by} · signed into the ledger`)
    window.dispatchEvent(new Event('fs:refresh'))
    reload(); setSel(''); reloadInc()
  }
  const eta = (i: any) => {
    if (i.status !== 'transporting') return null
    const r = routeBy[i.id]
    if (r) return Math.max(0, r.remaining_s * 1000 - (now - fetchedAt))   // road-route ETA, counting down
    if (!i.eta_min) return null
    return Math.max(0, new Date(i.updated_at).getTime() + i.eta_min * 60000 - now)
  }
  return (
    <div className="max-w-[1600px] mx-auto space-y-4">
      <div>
        <h1 className="font-num text-[34px] font-semibold leading-none">ED handover</h1>
        <p className="text-dim mt-1.5">Records arrive before the patient does. Read the summary, then acknowledge at the bedside.</p>
      </div>
      <div className="grid grid-cols-12 gap-4">
        <Panel className="col-span-12 lg:col-span-4" title="Incoming" sub="Sorted by triage, then arrival">
          {!incs ? <Spinner /> : incoming.length === 0 ? <Empty title="No ambulances inbound" /> : (
            <div className="space-y-2">
              {incoming.map((i: any) => {
                const ms = eta(i)
                return (
                  <button key={i.id} onClick={() => setSel(i.id)} className={clsx('w-full text-left rounded-lg border p-3 transition-colors',
                    sel === i.id ? 'border-spo2/60 bg-spo2/[.05]' : 'border-line bg-black hover:border-line2')}>
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <div className="flex gap-1.5"><Triage t={i.triage} /><Status s={i.status} /></div>
                        <div className="font-medium mt-1.5 truncate">{i.complaint || 'Assessment pending'}</div>
                        <div className="text-[13px] text-dim truncate">{i.patient?.age != null ? `${i.patient.age} y ${i.patient.sex || ''} · ` : ''}{i.vehicle}</div>
                        <div className="text-[12px] text-faint truncate">→ {i.destination}</div>
                      </div>
                      <div className="text-right shrink-0">
                        {ms != null ? <>
                          <div className="num text-[34px] font-semibold leading-none text-spo2">{Math.floor(ms / 60000)}:{String(Math.floor(ms / 1000) % 60).padStart(2, '0')}</div>
                          <div className="text-[12px] text-dim">to arrival{routeBy[i.id] ? ` · ${(routeBy[i.id].distance_m / 1000).toFixed(1)} km` : ''}</div></> : <div className="text-[13px] text-warn">on scene</div>}
                      </div>
                    </div>
                  </button>
                )
              })}
            </div>
          )}
        </Panel>

        <div className="col-span-12 lg:col-span-8 space-y-4">
          {!inc ? <Panel title="Select an ambulance"><Empty title="Pick an incoming unit to read its handover" /></Panel> : <Summary inc={inc} by={by} setBy={setBy} ack={ack} who={authOn ? user?.name : null} allowed={can('handover')} />}
        </div>
      </div>
      <Panel title="Recently handed over">
        <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
          {done.map((i: any) => (
            <Link key={i.id} to={`/incidents/${i.id}`} className="rounded-md border border-line bg-black p-3 hover:border-line2 flex items-center justify-between gap-2">
              <div className="min-w-0"><div className="font-medium truncate">{i.complaint}</div><div className="text-[13px] text-dim truncate">{i.handover_by} · {i.destination}</div></div>
              <a href={api.pdfUrl(i.id)} onClick={e => e.stopPropagation()} className="btn-ghost h-8 px-2" aria-label="Download PDF"><FileDown size={15} /></a>
            </Link>
          ))}
        </div>
      </Panel>
    </div>
  )
}

function Summary({ inc, by, setBy, ack, who, allowed }: any) {
  const p = inc.patient || {}
  const meds = inc.entries.filter((e: any) => e.kind === 'medication')
  const procs = inc.entries.filter((e: any) => e.kind === 'procedure')
  const latest: Record<string, any> = {}
  inc.vitals.forEach((v: any) => { latest[v.name] = v })
  const crit = inc.alerts.filter((a: any) => a.level === 'critical')
  const atmist = [
    ['Age', `${p.age ?? '?'} y · ${p.sex || 'sex unknown'}${p.weight_kg ? ` · ${p.weight_kg} kg` : ''}`],
    ['Time', `Call ${inc.workflow?.call_received || '—'} · scene ${inc.workflow?.at_scene || '—'} · left ${inc.workflow?.left_scene || '—'}`],
    ['Mechanism', inc.complaint || '—'],
    ['Injuries / illness', (p.chief_complaints || []).join(', ') || '—'],
    ['Signs', Object.values(latest).filter((v: any) => v.name !== 'pupils').map((v: any) => `${VITAL_LABEL[v.name]} ${v.value}`).join(' · ') || '—'],
    ['Treatment', `${meds.filter((m: any) => m.status !== 'withheld').length} medications · ${procs.length} procedures`],
  ]
  return (
    <>
      <Panel title={<span className="flex items-center gap-2">{inc.complaint || 'Incoming patient'} <Triage t={inc.triage} /></span>}
        sub={`${inc.dispatch_id} · ${inc.vehicle} · ${inc.crew}`}
        actions={<>
          <a className="btn-sec h-8" href={api.pdfUrl(inc.id)}><FileDown size={14} />PDF</a>
          <button className="btn-sec h-8" onClick={async () => download(`${inc.dispatch_id}_fhir.json`, await api.fhir(inc.id))}><Braces size={14} />FHIR</button>
        </>}>
        {(p.allergies?.length || crit.length) ? (
          <div className="rounded-md border border-alarm/50 bg-alarm/[.07] px-3 py-2.5 mb-3 flex items-start gap-2.5">
            <AlertOctagon size={18} className="text-alarm mt-0.5 shrink-0" />
            <div className="text-[14px]">
              {p.allergies?.length ? <div><span className="font-semibold text-alarm">Allergy:</span> {p.allergies.join(', ')}</div> : null}
              {crit.map((a: any, i: number) => <div key={i} className="text-dim">{a.message}</div>)}
            </div>
          </div>
        ) : null}
        <div className="grid md:grid-cols-[1fr_300px] gap-4">
          <dl className="divide-y divide-line">
            {atmist.map(([k, v]) => (
              <div key={k} className="grid grid-cols-[130px_1fr] py-2 text-[14px]"><dt className="text-dim">{k}</dt><dd>{v}</dd></div>
            ))}
          </dl>
          <div className="grid grid-cols-2 gap-2 content-start">
            {['hr', 'spo2', 'bp', 'gcs', 'rr', 'glucose'].filter(n => latest[n]).slice(0, 4).map(n => (
              <Numeric key={n} size="md" label={VITAL_LABEL[n]} value={latest[n].value} unit={latest[n].unit} color={VITAL_COLOR[n]} hint={latest[n].time ? `at ${latest[n].time}` : undefined} />
            ))}
          </div>
        </div>
      </Panel>
      <Panel title="Medications given" sub="Confirmed and signed by the crew">
        {!meds.length ? <Empty title="No medications recorded" /> : (
          <div className="overflow-x-auto -mx-4">
            <table className="tbl w-full min-w-[560px]">
              <thead><tr><th>Time</th><th>Medication</th><th>Dose</th><th>Route</th><th>Status</th></tr></thead>
              <tbody>{meds.map((m: any) => (
                <tr key={m.id}>
                  <td className="num text-[16px]">{m.payload.time}</td>
                  <td className="font-medium">{m.payload.drug}<div className="text-[12px] text-faint">RxNorm {m.payload.rxnorm || 'unmapped'}</div></td>
                  <td className="num text-[16px]">{m.payload.rate || (m.payload.dose != null ? `${m.payload.dose} ${m.payload.unit}` : '—')}</td>
                  <td className="text-dim">{ROUTE_LABEL[m.payload.route] || m.payload.route}</td>
                  <td>{m.status === 'withheld' ? <span className="chip bg-alarm/15 text-alarm">Withheld</span> : <span className="chip bg-hr/10 text-hr">Given</span>}</td>
                </tr>))}
              </tbody>
            </table>
          </div>
        )}
        {procs.length > 0 && <div className="flex flex-wrap gap-1.5 mt-3">{procs.map((x: any) => <span key={x.id} className="chip bg-spo2/10 text-spo2">{x.payload.time} {x.payload.procedure}</span>)}</div>}
        {inc.alerts.filter((a: any) => a.level === 'warning').length > 0 && <div className="mt-3 space-y-1">{inc.alerts.filter((a: any) => a.level === 'warning').slice(0, 4).map((a: any, i: number) => <FlagLine key={i} f={a} />)}</div>}
      </Panel>
      <Panel title="Handover readiness" sub="Checked against the signed record before you accept the patient">
        <Readiness c={inc.completeness} compact />
      </Panel>
      <Panel title="Acknowledge handover" sub="Signs a HANDOVER_ACK block and closes the crew's responsibility">
        <div className="flex flex-wrap items-center gap-2">
          {who ? <span className="text-[14px] text-dim">Signing as <span className="text-ink font-medium">{who}</span></span>
            : <input className="input max-w-xs" value={by} onChange={e => setBy(e.target.value)} aria-label="Receiving clinician" />}
          <button className="btn-pri" onClick={ack} disabled={!allowed || (!who && !by)}><CheckCheck size={16} />Acknowledge handover</button>
          {!allowed && <span className="text-[13px] text-warn">Only ED staff or a supervisor can acknowledge.</span>}
          {inc.completeness && !inc.completeness.ready && allowed && <span className="text-[13px] text-warn">{inc.completeness.missing.filter((m: any) => m.severity === 'required').length} required items missing; ask the crew before accepting.</span>}
        </div>
      </Panel>
    </>
  )
}
