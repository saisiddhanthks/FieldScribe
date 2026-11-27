import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { Send, Mic, Square, Loader2, Bot, User, Wrench, ShieldCheck, AlertOctagon, Cloud, HardDrive, ChevronDown, Check, X, Ban, Trash2 } from 'lucide-react'
import clsx from 'clsx'
import { api } from '../lib/api'
import { listenConfirm, readbackOn, speak } from '../lib/speech'
import { Panel, Status, Triage, useFetch, useToast } from '../components/ui'

type Msg = { role: 'user' | 'assistant'; content: string; meta?: any }

const QUICK = [
  'Bike accident, 25 yr male, heavy bleeding from right thigh, pulse 130, bp 88/60',
  'Lips swelling and wheeze after bee sting, 30 yr female',
  '62 yr old, crushing chest pain, sweating, bp 150/90, spo2 95',
  'Gave ecosprin 300 mg chewed at 10:42',
  'What has this patient received so far?',
  'Draft the ED handover',
]

const store: Record<string, Msg[]> = {}

export default function Copilot() {
  const toast = useToast()
  const { data: incs, reload: reloadIncs } = useFetch(api.incidents, [], 10000)
  const { data: st } = useFetch(api.agentStatus, [], 15000)
  const [incId, setIncId] = useState<string>('')
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [protocol, setProtocol] = useState<any>(null)
  const [checked, setChecked] = useState<Record<string, boolean>>({})
  const [autoSend, setAutoSend] = useState(true)
  const end = useRef<HTMLDivElement>(null)
  const active = useMemo(() => (incs || []).filter((i: any) => i.status !== 'handed_over'), [incs])
  const inc = (incs || []).find((i: any) => i.id === incId)
  const { data: detail, reload: reloadDetail } = useFetch(() => incId ? api.incident(incId) : Promise.resolve(null), [incId])

  useEffect(() => { setMsgs(store[incId || 'none'] || []) }, [incId])
  useEffect(() => { store[incId || 'none'] = msgs; end.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }) }, [msgs])

  const send = async (text?: string) => {
    const content = (text ?? input).trim()
    if (!content || busy) return
    const next: Msg[] = [...msgs, { role: 'user', content }]
    setMsgs(next); setInput(''); setBusy(true)
    try {
      const r: any = await api.agentChat(next.map(m => ({ role: m.role, content: m.content })), incId || undefined, inc?.crew)
      setMsgs(m => [...m, { role: 'assistant', content: r.reply, meta: r }])
      if (readbackOn()) {
        const logged = (r.logged || []).flatMap((l: any) => l.entries.map((e: any) => e.name))
        const first = r.reply.split(/\n+/).slice(0, 3).join('. ').slice(0, 320)
        await speak(logged.length && !r.pending ? `Logged: ${logged.join(', ')}.` : first)
        if (r.pending) {
          await speak(`Held: ${r.pending.items.join(', ')}. ${r.pending.alerts.map((a: any) => a.message).join('. ')}. Say confirm to log it, or cancel.`)
          const ans = await listenConfirm(4)
          if (ans === 'confirm') { const idx = next.length; await confirm(r.pending, idx) }
          else if (ans === 'cancel') speak('Not logged.')
        }
      }
      if (r.protocols?.length) { setProtocol(r.protocols[0]); setChecked({}) }
      if (r.opened) { await reloadIncs(); store[r.opened] = [...next, { role: 'assistant', content: r.reply, meta: r }]; setIncId(r.opened); toast('ok', 'New incident opened by Copilot') }
      if (r.logged?.length) { toast('ok', `Logged to the signed record · block #${r.logged[r.logged.length - 1].block}`); reloadDetail(); window.dispatchEvent(new Event('fs:refresh')) }
    } catch (e: any) {
      setMsgs(m => [...m, { role: 'assistant', content: `Request failed: ${e.message}` }])
    } finally { setBusy(false) }
  }
  const confirm = async (pending: any, idx: number) => {
    const r: any = await api.agentConfirm(pending, inc?.crew)
    speak(r.reply)
    setMsgs(m => m.map((x, i) => i === idx ? { ...x, meta: { ...x.meta, pending: null, resolved: 'confirmed' } } : x).concat([{ role: 'assistant', content: r.reply, meta: r }]))
    reloadDetail(); window.dispatchEvent(new Event('fs:refresh'))
  }
  const cancel = (idx: number) => setMsgs(m => m.map((x, i) => i === idx ? { ...x, meta: { ...x.meta, pending: null, resolved: 'cancelled' } } : x)
    .concat([{ role: 'assistant', content: 'Not logged. Tell me the corrected drug, dose or route when ready.' }]))

  const prov = st?.active
  const meds = (detail?.entries || [])
  return (
    <div className="max-w-[1600px] mx-auto space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-num text-[34px] font-semibold leading-none">Copilot</h1>
          <p className="text-dim mt-1.5">Describe the patient for first-aid steps. Say what you have done and it goes into the signed record.</p>
        </div>
        <div className="flex items-center gap-2">
          <select className="input w-[340px]" value={incId} onChange={e => setIncId(e.target.value)} aria-label="Incident">
            <option value="">No incident: Copilot opens one when you report a call</option>
            {active.map((i: any) => <option key={i.id} value={i.id}>{i.vehicle} · {i.complaint || 'New'} · {i.place}</option>)}
          </select>
        </div>
      </div>

      <div className="grid grid-cols-12 gap-4">
        <section className="col-span-12 xl:col-span-8 panel flex flex-col h-[calc(100vh-210px)] min-h-[560px]">
          <header className="panel-h border-b border-line">
            <div className="flex items-center gap-2.5 min-w-0">
              <div className="w-8 h-8 rounded-md bg-hr/10 text-hr flex items-center justify-center"><Bot size={18} /></div>
              <div className="min-w-0">
                <div className="panel-t">FieldScribe Copilot</div>
                <div className="text-[13px] text-dim truncate">{inc ? <span className="flex items-center gap-1.5"><Triage t={inc.triage} /><Status s={inc.status} /> {inc.dispatch_id}</span> : 'No incident selected'}</div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {prov && <span className={clsx('chip h-7 px-2.5', prov.cloud ? 'bg-spo2/10 text-spo2' : 'bg-hr/10 text-hr')} title={prov.cloud ? 'Only de-identified clinical fields are sent: no names, places or vehicle numbers' : 'Runs entirely on this device'}>
                {prov.cloud ? <Cloud size={13} /> : <HardDrive size={13} />}{prov.label} · {prov.model}
              </span>}
              <button className="btn-ghost h-8 px-2" onClick={() => setMsgs([])} title="Clear conversation" aria-label="Clear conversation"><Trash2 size={15} /></button>
            </div>
          </header>
          <div className="flex-1 overflow-auto px-4 py-4 space-y-4">
            {msgs.length === 0 && (
              <div className="max-w-xl mx-auto text-center pt-8">
                <div className="font-num text-[26px] font-semibold">What are you looking at?</div>
                <p className="text-dim mt-1.5 text-[14px]">Talk or type the way you would radio it in. Copilot checks protocol cards, flags dose and allergy problems, and logs what you report as done.</p>
                <div className="flex flex-wrap justify-center gap-2 mt-5">
                  {QUICK.map(q => <button key={q} onClick={() => send(q)} className="chip h-auto py-1.5 px-2.5 bg-raise border border-line2 text-dim hover:text-ink text-left text-[13px]">{q}</button>)}
                </div>
              </div>
            )}
            {msgs.map((m, i) => <Bubble key={i} m={m} onConfirm={p => confirm(p, i)} onCancel={() => cancel(i)} />)}
            {busy && <div className="flex items-center gap-2 text-dim text-[14px] pl-11"><Loader2 size={15} className="animate-spin" />Checking protocol and the record…</div>}
            <div ref={end} />
          </div>
          <div className="border-t border-line p-3">
            <div className="flex items-end gap-2">
              <Dictate onText={t => autoSend ? send(t) : setInput(x => (x ? x + ' ' : '') + t)} disabled={busy} />
              <textarea value={input} onChange={e => setInput(e.target.value)} rows={2}
                onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
                placeholder="e.g. RTA, 25 yr male, bleeding from thigh, pulse 130 · or · gave TXA 1 g IV at 10:12"
                className="flex-1 bg-black border border-line2 rounded-md px-3 py-2 text-[15px] resize-none focus:outline-none focus:border-spo2 placeholder:text-faint" />
              <button className="btn-pri h-[52px] px-4" onClick={() => send()} disabled={busy || !input.trim()} aria-label="Send"><Send size={17} /></button>
            </div>
            <label className="flex items-center gap-2 mt-2 text-[12px] text-dim"><input type="checkbox" className="accent-[#3ee07f]" checked={autoSend} onChange={e => setAutoSend(e.target.checked)} />Send automatically after dictation (hands-free)</label>
          </div>
        </section>

        <div className="col-span-12 xl:col-span-4 space-y-4">
          <Panel title="Protocol card" sub={protocol ? `Priority ${protocol.priority.toLowerCase()} · tick steps as you go` : 'Appears when you describe a patient'}>
            {!protocol ? <p className="text-[14px] text-dim">Describe what happened and the matching first-aid card opens here.</p> : (
              <div className="space-y-3">
                <div className="flex items-center gap-2"><Triage t={protocol.priority} /><span className="font-medium">{protocol.title}</span></div>
                <ol className="space-y-1.5">
                  {protocol.steps.map((s: string, i: number) => (
                    <li key={i}>
                      <label className={clsx('flex gap-2.5 items-start rounded-md px-2 py-1.5 cursor-pointer text-[14px] leading-snug', checked[i] ? 'bg-hr/[.06] text-dim line-through decoration-faint' : 'hover:bg-raise')}>
                        <input type="checkbox" className="mt-0.5 accent-[#3ee07f] w-4 h-4 shrink-0" checked={!!checked[i]} onChange={e => setChecked(c => ({ ...c, [i]: e.target.checked }))} />
                        <span><span className="num text-[15px] text-faint mr-1">{i + 1}</span>{s}</span>
                      </label>
                    </li>
                  ))}
                </ol>
                {protocol.do_not?.length > 0 && <div className="rounded-md border border-alarm/40 bg-alarm/[.05] px-3 py-2"><div className="text-[13px] font-semibold text-alarm mb-1">Do not</div><ul className="text-[13px] text-dim space-y-0.5">{protocol.do_not.map((d: string) => <li key={d}>{d}</li>)}</ul></div>}
                {protocol.red_flags?.length > 0 && <div className="rounded-md border border-warn/40 px-3 py-2"><div className="text-[13px] font-semibold text-warn mb-1">Red flags</div><ul className="text-[13px] text-dim space-y-0.5">{protocol.red_flags.map((d: string) => <li key={d}>{d}</li>)}</ul></div>}
                {protocol.meds?.length > 0 && <div><div className="text-[13px] text-dim mb-1">Per your 108 protocol / medical direction</div>{protocol.meds.map((m: any) => (
                  <div key={m.drug} className="flex justify-between gap-2 text-[13px] py-1 border-b border-line last:border-0"><span className="font-medium">{m.drug}</span><span className="text-dim text-right">{m.dose}<br /><span className="text-faint">{m.note}</span></span></div>))}</div>}
              </div>
            )}
          </Panel>
          <Panel title="Signed record" sub={inc ? `${meds.length} entries · ${detail?.vitals?.length || 0} vitals` : 'Select or open an incident'} actions={inc && <Link to={`/incidents/${inc.id}`} className="btn-ghost h-8 text-[13px]">Open</Link>}>
            {!detail ? <p className="text-[14px] text-dim">Nothing yet.</p> : !meds.length ? <p className="text-[14px] text-dim">No care logged yet.</p> : (
              <ul className="space-y-1.5 max-h-[260px] overflow-auto">
                {meds.map((e: any) => (
                  <li key={e.id} className="flex items-center gap-2 text-[14px]">
                    <span className="num text-[15px] w-11 text-dim">{e.payload.time}</span>
                    <span className={clsx('w-1.5 h-1.5 rounded-full', e.kind === 'medication' ? (e.status === 'withheld' ? 'bg-alarm' : 'bg-hr') : 'bg-spo2')} />
                    <span className={clsx('flex-1 truncate', e.status === 'withheld' && 'line-through text-dim')}>{e.name} {e.payload.rate || (e.payload.dose != null ? `${e.payload.dose} ${e.payload.unit}` : '')}</span>
                    {e.signer?.includes('Copilot') && <span className="chip bg-co2/15 text-co2 text-[11px]">Copilot</span>}
                  </li>
                ))}
              </ul>
            )}
          </Panel>
          <Panel title="AI providers" sub="Tried in order; the offline engine always answers">
            <ul className="space-y-1.5">
              {(st?.providers || []).map((p: any) => (
                <li key={p.name} className="flex items-center gap-2 text-[13px]">
                  <span className={clsx('w-2 h-2 rounded-full', p.configured ? 'bg-hr' : 'bg-line2')} />
                  <span className={clsx('flex-1', p.configured ? 'text-ink' : 'text-faint')}>{p.label}</span>
                  <span className="text-faint">{p.configured ? p.model : p.name === 'ollama' ? 'not running' : 'no key'}</span>
                </li>
              ))}
            </ul>
            {!st?.providers?.some((p: any) => p.configured && p.cloud) && <p className="text-[12px] text-faint mt-2">Add a free Gemini or Groq key to backend/.env for the full conversational agent. See README.</p>}
          </Panel>
        </div>
      </div>
    </div>
  )
}

function Bubble({ m, onConfirm, onCancel }: { m: Msg; onConfirm: (p: any) => void; onCancel: () => void }) {
  const [open, setOpen] = useState(false)
  const r = m.meta
  if (m.role === 'user') return (
    <div className="flex justify-end gap-2.5">
      <div className="max-w-[80%] rounded-lg rounded-tr-sm bg-raise border border-line2 px-3.5 py-2.5 text-[15px] whitespace-pre-wrap">{m.content}</div>
      <div className="w-8 h-8 rounded-md bg-raise flex items-center justify-center shrink-0 text-dim"><User size={16} /></div>
    </div>
  )
  return (
    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="flex gap-2.5">
      <div className="w-8 h-8 rounded-md bg-hr/10 text-hr flex items-center justify-center shrink-0"><Bot size={16} /></div>
      <div className="max-w-[88%] min-w-0 space-y-2">
        <div className="rounded-lg rounded-tl-sm bg-black border border-line px-3.5 py-2.5 text-[15px] leading-relaxed whitespace-pre-wrap">{m.content}</div>
        {r?.logged?.map((l: any) => (
          <div key={l.record_id} className="rounded-md border border-hr/40 bg-hr/[.05] px-3 py-2 text-[13px]">
            <div className="flex items-center gap-1.5 text-hr font-medium"><ShieldCheck size={14} />Signed into the record · block #{l.block}</div>
            <div className="flex flex-wrap gap-1.5 mt-1.5">
              {l.entries.map((e: any, i: number) => <span key={i} className={clsx('chip', e.status === 'withheld' ? 'bg-alarm/15 text-alarm' : e.kind === 'medication' ? 'bg-hr/10 text-hr' : 'bg-spo2/10 text-spo2')}>{e.status === 'withheld' && <Ban size={11} />}{e.name}{e.dose != null ? ` ${e.dose} ${e.unit || ''}` : e.rate ? ` ${e.rate}` : ''}{e.route ? ` ${e.route}` : ''}{e.time ? ` · ${e.time}` : ''}</span>)}
              {l.vitals.map((v: any, i: number) => <span key={'v' + i} className="chip bg-resp/10 text-resp">{v.name.toUpperCase()} {v.value}</span>)}
            </div>
          </div>
        ))}
        {r?.pending && (
          <div className="rounded-md border border-alarm/60 bg-alarm/[.07] px-3 py-2.5">
            <div className="flex items-center gap-1.5 text-alarm font-medium text-[14px]"><AlertOctagon size={15} />Held for your confirmation: {(r.pending.items || []).join(', ')}</div>
            <ul className="text-[13px] text-dim mt-1 space-y-0.5">{r.pending.alerts.map((a: any, i: number) => <li key={i}>{a.message}</li>)}</ul>
            <div className="flex gap-2 mt-2">
              <button className="btn-danger h-8" onClick={() => onConfirm(r.pending)}><Check size={14} />Checked, log it</button>
              <button className="btn-ghost h-8" onClick={onCancel}><X size={14} />Don't log</button>
            </div>
          </div>
        )}
        {r?.resolved && <div className="text-[12px] text-faint">{r.resolved === 'confirmed' ? 'Confirmed by EMT' : 'Cancelled by EMT'}</div>}
        {r && (
          <div className="text-[12px] text-faint flex flex-wrap items-center gap-x-3 gap-y-1">
            {r.provider && <span className="flex items-center gap-1">{r.provider.cloud ? <Cloud size={12} /> : <HardDrive size={12} />}{r.provider.label}{r.latency_ms ? ` · ${(r.latency_ms / 1000).toFixed(1)}s` : ''}</span>}
            {r.fallbacks?.length > 0 && <span title={r.fallbacks.map((f: any) => `${f.provider}: ${f.error}`).join('\n')} className="text-warn">fell back from {r.fallbacks.map((f: any) => f.provider).join(', ')}</span>}
            {r.tool_calls?.length > 0 && <button className="flex items-center gap-1 hover:text-ink" onClick={() => setOpen(o => !o)}><Wrench size={12} />{r.tool_calls.length} tool call{r.tool_calls.length > 1 ? 's' : ''}<ChevronDown size={12} className={clsx('transition-transform', open && 'rotate-180')} /></button>}
          </div>
        )}
        <AnimatePresence>
          {open && (
            <motion.ul initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden space-y-1">
              {r.tool_calls.map((t: any, i: number) => (
                <li key={i} className="font-mono text-[11px] text-dim bg-black border border-line rounded px-2 py-1">
                  <span className={t.ok ? 'text-hr' : 'text-alarm'}>{t.name}</span>({Object.entries(t.args || {}).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(', ')}) → {t.summary} <span className="text-faint">{t.ms}ms</span>
                </li>
              ))}
            </motion.ul>
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  )
}

function Dictate({ onText, disabled }: { onText: (t: string) => void; disabled?: boolean }) {
  const toast = useToast()
  const [rec, setRec] = useState<MediaRecorder | null>(null)
  const [busy, setBusy] = useState(false)
  const start = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } })
      const mr = new MediaRecorder(stream)
      const chunks: BlobPart[] = []
      mr.ondataavailable = e => chunks.push(e.data)
      mr.onstop = async () => {
        stream.getTracks().forEach(t => t.stop()); setRec(null); setBusy(true)
        try {
          const r: any = await api.asr(new Blob(chunks, { type: mr.mimeType || 'audio/webm' }))
          r.text ? onText(r.text) : toast('info', 'No speech detected')
        } catch (e: any) { toast('err', e.message) } finally { setBusy(false) }
      }
      mr.start(); setRec(mr)
    } catch (e: any) { toast('err', 'Microphone unavailable: ' + e.message) }
  }
  if (busy) return <button className="btn-sec h-[52px] w-[52px] justify-center" disabled aria-label="Transcribing"><Loader2 size={18} className="animate-spin" /></button>
  return rec
    ? <button className="btn-danger h-[52px] w-[52px] justify-center" onClick={() => rec.stop()} aria-label="Stop dictation"><Square size={16} /></button>
    : <button className="btn-sec h-[52px] w-[52px] justify-center" onClick={start} disabled={disabled} aria-label="Dictate" title="Dictate (offline Whisper)"><Mic size={18} /></button>
}
