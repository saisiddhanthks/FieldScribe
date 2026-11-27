import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { Siren, RotateCcw, Tag, CircleStop, Footprints, Wind, HeartPulse, Brain, Activity } from 'lucide-react'
import clsx from 'clsx'
import { api, TRIAGE_COLOR } from '../lib/api'
import { Panel, Spinner, useFetch, useToast } from '../components/ui'
import { useAuth } from '../components/Auth'
import { beep } from '../lib/speech'

const T = ['RED', 'YELLOW', 'GREEN', 'BLACK'] as const
const T_LABEL: Record<string, string> = { RED: 'Immediate', YELLOW: 'Delayed', GREEN: 'Minor (walking)', BLACK: 'Expectant / dead' }

type Step = { id: string; q: string; icon: any; yes: string; no: string; yesLabel?: string; noLabel?: string }
// START: Simple Triage And Rapid Treatment. Each answer is either the next question or a colour.
const START: Record<string, Step> = {
  walk: { id: 'walk', q: 'Can the casualty walk?', icon: Footprints, yes: 'GREEN', no: 'breathing' },
  breathing: { id: 'breathing', q: 'Are they breathing?', icon: Wind, yes: 'rr', no: 'airway' },
  airway: { id: 'airway', q: 'Open the airway. Breathing now?', icon: Wind, yes: 'RED', no: 'BLACK' },
  rr: { id: 'rr', q: 'Breathing faster than 30 a minute?', icon: Activity, yes: 'RED', no: 'perfusion' },
  perfusion: { id: 'perfusion', q: 'No radial pulse, or capillary refill over 2 seconds?', icon: HeartPulse, yes: 'RED', no: 'mental', yesLabel: 'Yes, poor', noLabel: 'No, pulse present' },
  mental: { id: 'mental', q: 'Can they follow a simple command?', icon: Brain, yes: 'YELLOW', no: 'RED', yesLabel: 'Yes', noLabel: 'No' },
}

export default function Mci() {
  const { data, reload, loading } = useFetch(() => api.mci(), [], 5000)
  const ev = data?.active
  if (loading && !data) return <div className="flex justify-center py-24"><Spinner size={24} /></div>
  return ev ? <Active ev={ev} reload={reload} /> : <Declare onDone={reload} />
}

function Declare({ onDone }: { onDone: () => void }) {
  const toast = useToast()
  const { can } = useAuth()
  const [f, setF] = useState({ name: '', place: '' })
  const go = async (e: React.FormEvent) => {
    e.preventDefault()
    try { await api.mciStart({ ...f, lat: 12.9172, lng: 77.6229 }); beep(); toast('ok', 'Mass casualty incident declared'); onDone() } catch (e: any) { toast('err', e.message) }
  }
  return (
    <div className="max-w-[980px] space-y-4">
      <div>
        <h1 className="font-num text-[34px] font-semibold leading-none">Mass casualty</h1>
        <p className="text-dim mt-1.5">When casualties outnumber crews: a bus crash, a stampede, a building collapse. Tag everyone in seconds, then treat Red first.</p>
      </div>
      <div className="grid md:grid-cols-2 gap-4">
        <Panel title="Declare an incident" sub="Every crew on this device joins the same casualty board">
          {can('capture') ? (
            <form onSubmit={go} className="space-y-3">
              <label className="block"><span className="text-[13px] text-dim">What happened</span>
                <input className="input mt-1 h-10" value={f.name} onChange={e => setF({ ...f, name: e.target.value })} placeholder="KSRTC bus overturned" required /></label>
              <label className="block"><span className="text-[13px] text-dim">Where</span>
                <input className="input mt-1 h-10" value={f.place} onChange={e => setF({ ...f, place: e.target.value })} placeholder="Hosur Road, near Silk Board" required /></label>
              <button className="btn-danger h-11 w-full text-[15px]"><Siren size={17} />Declare mass casualty</button>
            </form>
          ) : <p className="text-[14px] text-dim">Only ambulance crew and supervisors can declare one. You’ll see the board here once it starts.</p>}
        </Panel>
        <Panel title="How START triage works" sub="About 30 seconds per casualty, no equipment">
          <ol className="space-y-2 text-[14px]">
            {[['GREEN', 'Can walk: send to the green area'], ['BLACK', 'Not breathing even after opening the airway'],
              ['RED', 'Breathing over 30, weak or no radial pulse, or can’t follow commands'], ['YELLOW', 'Everyone else: injured but stable for now']].map(([c, t]) => (
              <li key={c} className="flex items-start gap-2.5"><span className="w-3 h-3 rounded-sm mt-1 shrink-0" style={{ background: TRIAGE_COLOR[c] }} /><span><b>{T_LABEL[c]}.</b> <span className="text-dim">{t}.</span></span></li>
            ))}
          </ol>
        </Panel>
      </div>
    </div>
  )
}

function useElapsed(since: string) {
  const [n, setN] = useState(Date.now())
  useEffect(() => { const t = setInterval(() => setN(Date.now()), 1000); return () => clearInterval(t) }, [])
  const s = Math.max(0, Math.floor((n - new Date(since).getTime()) / 1000))
  return `${String(Math.floor(s / 3600)).padStart(2, '0')}:${String(Math.floor(s / 60) % 60).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
}

function Active({ ev, reload }: { ev: any; reload: () => void }) {
  const toast = useToast()
  const { can } = useAuth()
  const elapsed = useElapsed(ev.started_at)
  const [step, setStep] = useState('walk')
  const [path, setPath] = useState<{ q: string; a: string }[]>([])
  const [result, setResult] = useState<string | null>(null)
  const [note, setNote] = useState('')
  const [last, setLast] = useState<any>(null)
  const reset = () => { setStep('walk'); setPath([]); setResult(null); setNote('') }
  const answer = (yes: boolean) => {
    const s = START[step]; const next = yes ? s.yes : s.no
    const p = [...path, { q: s.q, a: yes ? (s.yesLabel || 'Yes') : (s.noLabel || 'No') }]
    setPath(p)
    if ((T as readonly string[]).includes(next)) setResult(next); else setStep(next)
  }
  const tag = async (colour: string, start?: any) => {
    try {
      const r: any = await api.mciAdd(ev.id, { triage: colour, note, start })
      beep(); setLast({ tag: r.tag, colour, id: r.incident.id }); reset(); reload()
      toast('ok', `${r.tag} tagged ${T_LABEL[colour]}`)
    } catch (e: any) { toast('err', e.message) }
  }
  const close = async () => {
    if (!confirm('Close this mass casualty incident? Casualty records stay; the board is cleared.')) return
    await api.mciClose(ev.id); toast('info', 'Mass casualty incident closed'); reload()
  }
  const S = START[step]
  return (
    <div className="max-w-[1600px] mx-auto space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-alarm text-[13px] font-semibold"><span className="w-2 h-2 rounded-full bg-alarm blink" />MASS CASUALTY ACTIVE · {ev.id}</div>
          <h1 className="font-num text-[34px] font-semibold leading-tight">{ev.name}</h1>
          <p className="text-dim">{ev.place} · declared by {ev.started_by}</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="text-right"><div className="text-[12px] text-dim">Elapsed</div><div className="num text-[32px] font-semibold leading-none tabular-nums">{elapsed}</div></div>
          {can('capture') && <button className="btn-sec h-10" onClick={close}><CircleStop size={15} />Close incident</button>}
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-6 gap-2.5">
        {T.map(c => (
          <div key={c} className="rounded-lg border px-4 py-3 bg-black" style={{ borderColor: TRIAGE_COLOR[c] + '66' }}>
            <div className="text-[13px] font-semibold" style={{ color: TRIAGE_COLOR[c] }}>{T_LABEL[c]}</div>
            <div className="num text-[48px] font-semibold leading-none mt-1" style={{ color: TRIAGE_COLOR[c] }}>{ev.counts[c]}</div>
          </div>
        ))}
        <div className="rounded-lg border border-line px-4 py-3 bg-black"><div className="text-[13px] text-dim">Total casualties</div><div className="num text-[48px] font-semibold leading-none mt-1">{ev.total}</div></div>
        <div className="rounded-lg border border-line px-4 py-3 bg-black"><div className="text-[13px] text-dim">Transported</div><div className="num text-[48px] font-semibold leading-none mt-1">{ev.transported}</div></div>
      </div>

      <div className="grid grid-cols-12 gap-4">
        {can('capture') && (
          <Panel className="col-span-12 lg:col-span-5" title="Triage the next casualty" sub="START: answer what you see"
            actions={path.length ? <button className="btn-ghost h-8" onClick={reset}><RotateCcw size={14} />Start over</button> : undefined}>
            <AnimatePresence mode="wait">
              {!result ? (
                <motion.div key={step} initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -12 }} transition={{ duration: 0.14 }}>
                  <div className="flex items-center gap-3 py-3">
                    <S.icon size={28} className="text-spo2 shrink-0" />
                    <div className="font-num text-[28px] font-semibold leading-tight">{S.q}</div>
                  </div>
                  <div className="grid grid-cols-2 gap-2.5 mt-2">
                    <button className="h-20 rounded-lg border border-line2 bg-raise text-[20px] font-semibold hover:border-hr hover:text-hr" onClick={() => answer(true)}>{S.yesLabel || 'Yes'}</button>
                    <button className="h-20 rounded-lg border border-line2 bg-raise text-[20px] font-semibold hover:border-hr hover:text-hr" onClick={() => answer(false)}>{S.noLabel || 'No'}</button>
                  </div>
                </motion.div>
              ) : (
                <motion.div key="result" initial={{ opacity: 0, scale: 0.97 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.16 }}>
                  <div className="rounded-lg p-4 text-black" style={{ background: TRIAGE_COLOR[result] }}>
                    <div className="text-[13px] font-semibold opacity-70">Tag as</div>
                    <div className="font-num text-[40px] font-semibold leading-none">{result} · {T_LABEL[result]}</div>
                  </div>
                  <input className="input h-10 mt-3" value={note} onChange={e => setNote(e.target.value)} placeholder="Short note: adult male, open leg fracture (optional)" autoFocus
                    onKeyDown={e => { if (e.key === 'Enter') tag(result, { answers: path }) }} />
                  <button className="btn-pri h-12 w-full mt-2.5 text-[16px]" onClick={() => tag(result, { answers: path })}><Tag size={17} />Tag casualty</button>
                </motion.div>
              )}
            </AnimatePresence>
            {path.length > 0 && (
              <ol className="mt-4 space-y-1 text-[13px] text-dim">
                {path.map((p, i) => <li key={i}>{p.q} <b className="text-ink">{p.a}</b></li>)}
              </ol>
            )}
            <div className="mt-5 pt-4 border-t border-line">
              <div className="text-[12.5px] text-faint mb-2">Already know? Tag directly</div>
              <div className="grid grid-cols-4 gap-1.5">
                {T.map(c => <button key={c} onClick={() => tag(c)} className="h-10 rounded-md text-[13px] font-semibold text-black hover:opacity-90" style={{ background: TRIAGE_COLOR[c] }}>{c}</button>)}
              </div>
            </div>
            {last && <p className="mt-3 text-[13.5px]">Last tagged: <Link className="text-spo2" to={`/incidents/${last.id}`}>{last.tag}</Link> as {T_LABEL[last.colour]}. Write the tag number on the casualty’s wrist.</p>}
          </Panel>
        )}
        <Panel className={clsx('col-span-12', can('capture') ? 'lg:col-span-7' : '')} title="Casualty board" sub="Red first. Re-triage as conditions change." bodyClass="px-0">
          {!ev.patients.length ? <p className="px-4 pb-4 text-[14px] text-faint">No casualties tagged yet.</p> : (
            <div className="overflow-x-auto">
              <table className="w-full text-[14px]">
                <thead><tr className="text-left text-[12.5px] text-faint border-b border-line"><th className="font-normal px-4 h-9">Tag</th><th className="font-normal">Triage</th><th className="font-normal">Note</th><th className="font-normal">Status</th><th className="font-normal px-4">Re-triage</th></tr></thead>
                <tbody>
                  {[...ev.patients].sort((a: any, b: any) => T.indexOf(a.triage) - T.indexOf(b.triage) || a.mci_tag.localeCompare(b.mci_tag)).map((p: any) => (
                    <tr key={p.id} className="border-b border-line/70 h-11">
                      <td className="px-4"><Link to={`/incidents/${p.id}`} className="num text-[18px] font-semibold hover:text-spo2">{p.mci_tag}</Link></td>
                      <td><span className="chip text-black font-semibold" style={{ background: TRIAGE_COLOR[p.triage] }}>{p.triage}</span></td>
                      <td className="text-dim max-w-[260px] truncate">{(p.complaint || '').replace(/^MCI casualty T-\d+:?\s*/, '') || '—'}</td>
                      <td className="text-dim">{p.status.replace('_', ' ')}{p.destination ? ` → ${p.destination}` : ''}</td>
                      <td className="px-4">
                        <div className="flex gap-1">
                          {T.map(c => (
                            <button key={c} disabled={!can('capture') || p.triage === c} aria-label={`Re-triage ${p.mci_tag} as ${c}`}
                              onClick={async () => { await api.mciRetriage(p.id, c); reload() }}
                              className={clsx('w-6 h-6 rounded-sm border', p.triage === c ? 'opacity-100 ring-2 ring-white/60' : 'opacity-40 hover:opacity-100')}
                              style={{ background: TRIAGE_COLOR[c], borderColor: TRIAGE_COLOR[c] }} />
                          ))}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      </div>
    </div>
  )
}
