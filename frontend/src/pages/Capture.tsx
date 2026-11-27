import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { Mic, Square, Keyboard, PenLine, Check, X, ChevronDown, ShieldCheck, Plus, Sparkles, Ban, Loader2 } from 'lucide-react'
import clsx from 'clsx'
import { Languages } from 'lucide-react'
import { ASR_LANGS, asrLang, setAsrLang, type AsrLang } from '../lib/lang'
import { api, ROUTE_LABEL, VITAL_COLOR, VITAL_LABEL } from '../lib/api'
import { entrySentence, listenConfirm, readbackOn, speak } from '../lib/speech'
import { ClockPanel } from '../components/Clinical'
import { useAuth } from '../components/Auth'
import { ConfBar, Empty, FlagLine, Hash, Modal, Numeric, Panel, Status, Triage, useFetch, useToast } from '../components/ui'

const SAMPLES = [
  { label: 'Deck example', text: 'Gave aspirin 300 mg oral at 10:42, started IV normal saline 500 ml, oxygen 4 litres by mask.' },
  { label: 'Chest pain', text: '62 year old male, chest pain radiating to left arm since 30 minutes. no known allergies. bp 158/96, pulse 104, spo2 94. ecosprin three hundred milligram chewed at 11:02. sorbitrate 5 mg sublingual at 11:06. 12 lead ecg done. 18g cannula right forearm at 11:08. triage red.' },
  { label: 'Hinglish trauma', text: 'RTA, bike se gira, 27 year old male. gcs 14, bp 104/70, pulse 118. patient ko RL 500 ml iv chadhaya at 09:31, txa 1 g iv diya, c collar lagaya, pressure dressing applied. fentanyl 50 mcg iv at 09:40. medico legal case.' },
  { label: 'हिंदी · low sugar', text: '50 साल की महिला, बेहोश, शुगर कम, GRBS 38. डेक्सट्रोज़ 25 प्रतिशत 100 एमएल नस में दिया 10:20 बजे. फिर GRBS 112, होश में आई.' },
  { label: 'ಕನ್ನಡ · chest pain', text: 'ಎದೆ ನೋವು, 60 ವರ್ಷದ ಗಂಡಸು, BP 150/90, SpO2 94. ಆಸ್ಪಿರಿನ್ 300 mg ಬಾಯಲ್ಲಿ ಕೊಟ್ಟಿದ್ದೀನಿ 11:02 ಕ್ಕೆ, ಸಾರ್ಬಿಟ್ರೇಟ್ 5 mg ನಾಲಿಗೆ ಕೆಳಗೆ ಕೊಟ್ಟಿದ್ದೀನಿ.' },
  { label: 'Kanglish · breathing', text: 'rogige usiraata tondare, 45 varshada hengasu, SpO2 86. asthalin nebulisation 5 mg kottiddini 08:15, oxygen 6 litre per minute mask mulaka. hydrocortisone 200 mg IV kottiddini.' },
  { label: 'Anaphylaxis', text: '29 year old female, allergic to penicillin, urticaria and lip swelling after injection. bp 86/50, pulse 132, spo2 91, wheeze. adrenaline 0.5 mg im at 14:11 into the thigh. avil 22.75 mg iv at 14:14. oxygen 10 litres by non rebreather. efcorlin 200 mg iv.' },
  { label: 'Paediatric seizure', text: '4 year old boy weight 16 kg, fits for 8 minutes. gcs 8, grbs 62, spo2 90. midazolam 1.6 mg intranasal at 16:20. d10 80 ml iv at 16:25. recovery position. suction done.' },
  { label: 'Noisy ASR + traps', text: 'patient allergic to aspirin. gave asprin 300 mg, ondansatron 4 mg iv, adrenaline 5 mg im at 12:30. no morphine given. aspirin 300 mg oral again at 12:41.' },
]

type Ent = any

export default function Capture() {
  const toast = useToast()
  const { user, authOn } = useAuth()
  const { data: incs, reload: reloadIncs } = useFetch(api.incidents, [])
  const { data: lex } = useFetch(api.lexicon, [])
  const { data: sys } = useFetch(api.system, [])
  const [incId, setIncId] = useState<string>('')
  const [mode, setMode] = useState<'voice' | 'text'>('text')
  const [text, setText] = useState('')
  const [asrText, setAsrText] = useState<string | null>(null)
  const [asrMeta, setAsrMeta] = useState<any>(null)
  const [ex, setEx] = useState<any>(null)
  const [ents, setEnts] = useState<Ent[]>([])
  const [ack, setAck] = useState<Record<string, boolean>>({})
  const [busy, setBusy] = useState(false)
  const [signer, setSigner] = useState('')
  const [result, setResult] = useState<any>(null)
  const [newOpen, setNewOpen] = useState(false)
  const t0 = useRef<number | null>(null)

  const active = useMemo(() => (incs || []).filter((i: any) => i.status !== 'handed_over'), [incs])
  useEffect(() => { if (!incId && active.length) setIncId(active[0].id) }, [active, incId])
  const inc = (incs || []).find((i: any) => i.id === incId)
  useEffect(() => { if (authOn && user) setSigner(user.name); else if (inc) setSigner(inc.crew) }, [inc?.id, user?.id])

  // live extraction (debounced)
  useEffect(() => {
    if (!text.trim()) { setEx(null); setEnts([]); return }
    if (t0.current == null) t0.current = performance.now()
    const h = setTimeout(async () => {
      try {
        const r: any = await api.extract(text, incId || undefined)
        setEx(r)
        setEnts(r.entities.map((e: any) => ({ ...e, status: e.negated ? 'withheld' : 'confirmed', original: Object.fromEntries(Object.entries(e.fields).map(([k, v]: any) => [k, v.value])) })))
        setAck({})
      } catch (e: any) { toast('err', e.message) }
    }, 350)
    return () => clearTimeout(h)
  }, [text, incId])

  const alerts = useMemo(() => {
    if (!ex) return []
    const kept = new Set(ents.filter(e => e.status !== 'rejected').map(e => e.id))
    const rank: Record<string, number> = { critical: 0, warning: 1, info: 2 }
    return ex.alerts.filter((a: any) => !a.entity_id || kept.has(a.entity_id)).sort((a: any, b: any) => rank[a.level] - rank[b.level])
  }, [ex, ents])
  const [showInfo, setShowInfo] = useState(false)
  const mustAck = alerts.filter((a: any) => a.level === 'critical')
  const allAck = mustAck.every((a: any, i: number) => ack[a.code + i])

  const updateField = (id: string, k: string, v: any) => setEnts(es => es.map(e => e.id !== id ? e : {
    ...e, edited: true, fields: { ...e.fields, [k]: { ...(e.fields[k] || {}), value: v, confidence: 1, source: 'emt' } },
  }))
  const setStatus = (id: string, s: string) => setEnts(es => es.map(e => e.id === id ? { ...e, status: s } : e))

  const [phase, setPhase] = useState<'' | 'reading' | 'listening'>('')
  const { data: clk, reload: reloadClock } = useFetch(() => incId ? api.clock(incId) : Promise.resolve({ timers: [] }), [incId], 15000)
  const sign = async () => {
    if (!incId) return toast('err', 'Choose or open an incident first')
    if (!readbackOn()) return doSign()
    const kept = ents.filter(e => e.status !== 'rejected')
    const vit = (ex?.vitals || []).filter((v: any) => v.name !== 'pupils').map((v: any) => `${VITAL_LABEL[v.name] || v.name} ${v.value}`)
    setPhase('reading')
    await speak(`Ready to sign ${kept.length} ${kept.length === 1 ? 'entry' : 'entries'}. ${kept.map(entrySentence).join('. ')}. ${vit.length ? 'Vitals: ' + vit.join(', ') + '.' : ''} Say confirm to sign, or cancel.`)
    setPhase('listening')
    const ans = await listenConfirm(4)
    setPhase('')
    if (ans === 'confirm') return doSign()
    if (ans === 'cancel') { speak('Not signed.'); return toast('info', 'Not signed. Make your corrections, then sign again.') }
    toast('info', "Didn't catch a confirm. Press the sign button again, or switch read-back off to sign directly.")
  }
  const doSign = async () => {
    setBusy(true)
    try {
      const r: any = await api.sign(incId, {
        source: asrText ? 'voice' : 'text', asr_text: asrText, final_text: text,
        capture_ms: t0.current ? Math.round(performance.now() - t0.current) : null, signer,
        entries: ents.map(e => ({ ...e, negated: e.status === 'withheld' })),
        vitals: ex?.vitals || [], patient: ex?.patient || {}, workflow: ex?.workflow || {}, alerts, stats: ex?.stats, asr_meta: asrMeta,
      })
      setResult(r)
      toast('ok', `Signed · block #${r.ledger.seq} appended to the audit chain`)
      speak(`Signed. Block ${r.ledger.seq}.`)
      reloadClock()
      window.dispatchEvent(new Event('fs:refresh'))
      reloadIncs()
    } catch (e: any) { toast('err', e.message) } finally { setBusy(false) }
  }
  const reset = () => { setText(''); setAsrText(null); setAsrMeta(null); setResult(null); t0.current = null }

  return (
    <div className="max-w-[1600px] mx-auto space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-num text-[34px] font-semibold leading-none">Capture</h1>
          <p className="text-dim mt-1.5">Speak or type the way you would hand over. Check the highlighted fields, then sign.</p>
        </div>
        <div className="flex items-center gap-2 w-full sm:w-auto min-w-0">
          <select className="input w-full sm:w-[320px] min-w-0" value={incId} onChange={e => setIncId(e.target.value)} aria-label="Incident">
            {active.length === 0 && <option value="">No open incidents</option>}
            {active.map((i: any) => <option key={i.id} value={i.id}>{i.vehicle} · {i.complaint || 'New'} · {i.place}</option>)}
          </select>
          <button className="btn-sec shrink-0" onClick={() => setNewOpen(true)} aria-label="New incident"><Plus size={15} /><span className="hidden sm:inline">New incident</span></button>
        </div>
      </div>

      <div className="grid grid-cols-12 gap-4">
        <div className="col-span-12 xl:col-span-7 space-y-4">
          <Panel title="Dictation" sub={inc ? <span className="flex items-center gap-2"><Triage t={inc.triage} /><Status s={inc.status} /> {inc.dispatch_id}</span> : 'Open an incident to begin'}
            actions={
              <div className="flex rounded-md border border-line2 p-0.5">
                {(['voice', 'text'] as const).map(m => (
                  <button key={m} onClick={() => setMode(m)} className={clsx('h-8 px-3 rounded text-[13px] flex items-center gap-1.5', mode === m ? 'bg-raise text-ink' : 'text-dim')}>
                    {m === 'voice' ? <Mic size={14} /> : <Keyboard size={14} />}{m === 'voice' ? 'Voice' : 'Type'}
                  </button>
                ))}
              </div>
            }>
            {mode === 'voice' && <LangPicker />}
            {mode === 'voice' && <Recorder asr={sys?.asr} onText={(t, meta) => { setText(x => (x ? x + ' ' : '') + t); setAsrText(a => (a ? a + ' ' : '') + t); setAsrMeta(meta); if (t0.current == null) t0.current = performance.now() - (meta?.audio_seconds || 0) * 1000 }} />}
            <textarea value={text} onChange={e => setText(e.target.value)} rows={mode === 'voice' ? 4 : 6}
              placeholder={mode === 'voice' ? 'The transcript appears here. Correct anything before signing.' : 'e.g. gave ecosprin 300 mg chewed at 10:42, started RL 500 ml iv, oxygen 4 litres by mask'}
              className="w-full bg-black border border-line2 rounded-md p-3 text-[15px] leading-relaxed resize-y focus:outline-none focus:border-spo2 placeholder:text-faint" />
            <div className="flex flex-wrap gap-1.5 mt-2.5">
              {SAMPLES.map(s => (
                <button key={s.label} className="chip h-7 px-2.5 bg-raise border border-line2 text-dim hover:text-ink" onClick={() => { reset(); setText(s.text) }}>
                  <Sparkles size={12} />{s.label}
                </button>
              ))}
            </div>
          </Panel>

          <Panel title="What FieldScribe heard" sub={ex ? `${ex.stats.medications} medications · ${ex.stats.procedures} procedures · ${ex.stats.vitals} vitals · ${ex.latency_ms} ms on-device · ${ex.engine?.transformer ? 'rules + DistilBERT' : 'rules + fuzzy'}` : 'Normalised transcript with highlighted entities'}>
            {!ex ? <Empty title="Nothing to read yet">Pick a sample or start dictating. Extraction runs locally as you type.</Empty> : (
              <>
                {ex.language?.code_mixed && (
                  <div className="mb-3 rounded-md border border-spo2/30 bg-spo2/[.06] px-3 py-2">
                    <div className="flex items-center gap-2 text-[13.5px]"><Languages size={15} className="text-spo2" />
                      <b>{ex.language.language === 'kannada' ? 'Kannada' : 'Hindi'} + English understood</b>
                      <span className="text-dim">{ex.language.script !== 'latin' ? `${ex.language.script === 'kannada' ? 'Kannada' : 'Devanagari'} script read on-device · ` : ''}{ex.language.translated.length} phrases mapped to clinical English</span>
                    </div>
                    <div className="flex flex-wrap gap-1.5 mt-1.5">
                      {ex.language.translated.slice(0, 14).map((t: any, i: number) => (
                        <span key={i} className="chip bg-black border border-line2 text-[12px]"><span className="text-dim">{t.from}</span><span className="text-faint">→</span><span>{t.to}</span></span>
                      ))}
                    </div>
                  </div>
                )}
                <Highlighted text={ex.normalised} ents={ents} vitals={ex.vitals} />
                <div className="flex flex-wrap gap-3 mt-3 text-[12px] text-dim">
                  <span><span className="ent-medication px-1 rounded">drug</span> medication</span>
                  <span><span className="ent-procedure px-1 rounded">proc</span> procedure</span>
                  <span><span className="ent-vital px-1 rounded">vital</span> vital sign</span>
                  <span><span className="ent-neg px-1 rounded">neg</span> withheld</span>
                  <span><span className="ent-low px-1 rounded">dashed</span> needs review</span>
                </div>
              </>
            )}
          </Panel>

          <Panel title="Structured entries" sub="Edit any field. Edited fields are marked in the audit record.">
            {!ents.length ? <Empty title="No medications or procedures detected yet" /> : (
              <div className="space-y-2.5">
                {ents.map(e => <EntityCard key={e.id} e={e} lex={lex} onField={updateField} onStatus={setStatus} />)}
              </div>
            )}
          </Panel>
        </div>

        <div className="col-span-12 xl:col-span-5 space-y-4">
          <Panel title="Patient & vitals" sub="Detected from this dictation">
            {!ex ? <Empty title="Waiting for dictation" /> : (
              <div className="space-y-3">
                <div className="flex flex-wrap gap-1.5 text-[13px]">
                  {ex.patient.age != null && <span className="chip bg-raise">{ex.patient.age} y</span>}
                  {ex.patient.sex && <span className="chip bg-raise">{ex.patient.sex}</span>}
                  {ex.patient.weight_kg && <span className="chip bg-raise">{ex.patient.weight_kg} kg</span>}
                  {ex.patient.triage && <Triage t={ex.patient.triage} />}
                  {(ex.patient.chief_complaints || []).map((c: string) => <span key={c} className="chip bg-spo2/10 text-spo2">{c}</span>)}
                  {ex.patient.allergies?.length ? <span className="chip bg-alarm/15 text-alarm">Allergy: {ex.patient.allergies.join(', ')}</span>
                    : ex.patient.allergies_status === 'NKDA' ? <span className="chip bg-hr/10 text-hr">NKDA</span> : <span className="chip bg-warn/10 text-warn">Allergies not stated</span>}
                  {ex.patient.medico_legal && <span className="chip bg-co2/15 text-co2">Medico-legal</span>}
                </div>
                {ex.vitals.length > 0 && (
                  <div className="grid grid-cols-3 gap-2">
                    {ex.vitals.filter((v: any) => v.name !== 'pupils').map((v: any, i: number) => (
                      <Numeric key={i} size="md" label={VITAL_LABEL[v.name] || v.name} value={v.value} unit={v.unit} color={VITAL_COLOR[v.name]}
                        alarm={ex.alerts.some((a: any) => a.code === 'VITAL_OUT_OF_RANGE' && a.message.toLowerCase().startsWith(v.name === 'bp' ? 'bp' : v.name))} hint={v.time ? `at ${v.time}` : undefined} />
                    ))}
                  </div>
                )}
                {Object.keys(ex.workflow).length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {Object.entries(ex.workflow).map(([k, v]: any) => <span key={k} className="chip bg-raise text-dim">{k.replace(/_/g, ' ')} <span className="num text-ink">{v}</span></span>)}
                  </div>
                )}
                <Abcde a={ex.abcde} />
              </div>
            )}
          </Panel>

          <Panel title="Safety review" sub={mustAck.length ? `${mustAck.length} critical item${mustAck.length > 1 ? 's' : ''} must be acknowledged before signing` : 'Flags from protocol checks'}>
            {!alerts.length ? <Empty title={ex ? 'No flags raised' : 'Flags appear here'}>{ex ? 'Doses, routes and allergies passed the reference checks.' : ''}</Empty> : (
              <div className="space-y-2">
                {alerts.filter((a: any) => a.level !== 'info' || showInfo).map((a: any, i: number) => (
                  <div key={i} className={clsx('rounded-md px-3 py-2 border', a.level === 'critical' ? 'border-alarm/50 bg-alarm/[.06]' : 'border-line')}>
                    <FlagLine f={a} />
                    {a.level === 'critical' && (
                      <label className="flex items-center gap-2 mt-1.5 text-[13px] text-ink cursor-pointer">
                        <input type="checkbox" className="accent-[#ff4b4b] w-4 h-4" checked={!!ack[a.code + mustAck.indexOf(a)]}
                          onChange={ev => setAck(x => ({ ...x, [a.code + mustAck.indexOf(a)]: ev.target.checked }))} />
                        I have checked this with the patient / protocol
                      </label>
                    )}
                  </div>
                ))}
                {alerts.some((a: any) => a.level === 'info') && (
                  <button className="text-[13px] text-dim hover:text-ink flex items-center gap-1" onClick={() => setShowInfo(x => !x)}>
                    <ChevronDown size={14} className={clsx('transition-transform', showInfo && 'rotate-180')} />
                    {showInfo ? 'Hide' : 'Show'} {alerts.filter((a: any) => a.level === 'info').length} informational notes
                  </button>
                )}
              </div>
            )}
          </Panel>

          <Panel title="Clinical clock" sub={inc ? `${inc.vehicle}: reminders from what is logged` : 'Select an incident'}>
            <ClockPanel timers={clk?.timers || []} compact />
          </Panel>

          <Panel title="Confirm & sign" sub="Appends a hash-chained, Ed25519-signed block. Works offline.">
            <div className="space-y-3">
              <label className="block text-[13px] text-dim">Signing EMT
                <input className="input mt-1" value={signer} onChange={e => setSigner(e.target.value)} readOnly={authOn} title={authOn ? 'Taken from your login' : undefined} />
              </label>
              <div className="grid grid-cols-3 gap-2 text-center">
                <MiniStat l="Keep" v={ents.filter(e => e.status === 'confirmed').length} c="#3ee07f" />
                <MiniStat l="Withheld" v={ents.filter(e => e.status === 'withheld').length} c="#ff4b4b" />
                <MiniStat l="Rejected" v={ents.filter(e => e.status === 'rejected').length} c="#8a979f" />
              </div>
              <button className="btn-pri w-full h-11 justify-center text-[15px]" disabled={!ex || busy || !!phase || !allAck || !incId || !signer} onClick={sign}>
                {busy ? <Loader2 size={16} className="animate-spin" /> : <ShieldCheck size={17} />}Confirm and sign record
              </button>
              {!allAck && <p className="text-[13px] text-alarm">Acknowledge the critical flags above to enable signing.</p>}
              {phase && <p className="text-[13px] text-spo2 flex items-center gap-2"><Loader2 size={14} className="animate-spin" />{phase === 'reading' ? 'Reading the record back…' : 'Listening: say "confirm" or "cancel"'}</p>}
              {readbackOn() && !phase && <p className="text-[12px] text-faint">Read-back is on: the record is read aloud and you confirm by voice.</p>}
              <AnimatePresence>
                {result && (
                  <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="rounded-md border border-hr/40 bg-hr/[.06] p-3">
                    <div className="flex items-center gap-2 text-hr font-medium"><Check size={16} />Block #{result.ledger.seq} signed · {result.entries} entries</div>
                    <div className="mt-1.5 space-y-0.5">
                      <div className="text-[12px] text-dim">hash <Hash h={result.ledger.hash} n={24} /></div>
                      <div className="text-[12px] text-dim">prev <Hash h={result.ledger.prev_hash} n={24} /></div>
                    </div>
                    <div className="flex gap-2 mt-2.5">
                      <Link to={`/incidents/${incId}`} className="btn-sec h-8">Open incident</Link>
                      <a href={api.pdfUrl(incId)} className="btn-sec h-8">Handover PDF</a>
                      <button className="btn-ghost h-8" onClick={reset}>New dictation</button>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </Panel>
        </div>
      </div>
      <NewIncident open={newOpen} onClose={() => setNewOpen(false)} onCreated={(i: any) => { reloadIncs(); setIncId(i.id); setNewOpen(false); toast('ok', `Incident ${i.dispatch_id} opened`) }} />
    </div>
  )
}

function MiniStat({ l, v, c }: { l: string; v: number; c: string }) {
  return <div className="rounded-md bg-black border border-line py-1.5"><div className="num text-[24px] font-semibold leading-none" style={{ color: c }}>{v}</div><div className="text-[12px] text-dim">{l}</div></div>
}

function Abcde({ a }: { a: any }) {
  if (!a) return null
  const rows = Object.entries(a)
  return (
    <div className="grid grid-cols-5 gap-1.5">
      {rows.map(([k, v]: any) => (
        <div key={k} className={clsx('rounded-md border px-2 py-1.5 min-h-[52px]', v ? 'border-line2 bg-black' : 'border-dashed border-line')}>
          <div className={clsx('num text-[18px] font-semibold leading-none', v ? 'text-ink' : 'text-faint')}>{k}</div>
          <div className="text-[11px] text-dim leading-tight mt-1 line-clamp-2">{v || 'not stated'}</div>
        </div>
      ))}
    </div>
  )
}

function Highlighted({ text, ents, vitals }: { text: string; ents: Ent[]; vitals: any[] }) {
  const spans = [
    ...ents.map(e => ({ s: e.start, e: e.end, cls: e.status === 'withheld' ? 'ent-neg' : e.kind === 'medication' ? 'ent-medication' : 'ent-procedure', low: e.confidence < 0.75, tip: e.evidence?.join('\n') })),
    ...vitals.map(v => ({ s: v.start, e: v.end, cls: 'ent-vital', low: false, tip: `${v.name}: ${v.value}` })),
  ].sort((a, b) => a.s - b.s)
  const out: any[] = []
  let i = 0
  spans.forEach((sp, k) => {
    if (sp.s < i) return
    if (sp.s > i) out.push(<span key={'t' + k}>{text.slice(i, sp.s)}</span>)
    out.push(<mark key={'m' + k} title={sp.tip} className={clsx(sp.cls, sp.low && 'ent-low', 'rounded px-0.5 bg-transparent')}>{text.slice(sp.s, sp.e)}</mark>)
    i = sp.e
  })
  out.push(<span key="end">{text.slice(i)}</span>)
  return <p className="text-[16px] leading-[1.9] text-dim">{out}</p>
}

const UNITS = ['mg', 'mcg', 'g', 'mL', 'L', 'L/min', 'units', 'puffs', 'tab']

function EntityCard({ e, lex, onField, onStatus }: { e: Ent; lex: any; onField: any; onStatus: any }) {
  const [why, setWhy] = useState(false)
  const f = e.fields
  const isMed = e.kind === 'medication'
  const flagged = e.flags?.some((x: any) => x.level !== 'info') || e.confidence < 0.75
  const crit = e.flags?.some((x: any) => x.level === 'critical')
  return (
    <div className={clsx('rounded-lg border bg-black transition-opacity', e.status === 'rejected' && 'opacity-40',
      crit ? 'border-alarm/50' : flagged ? 'border-warn/40' : 'border-line')}>
      <div className="flex flex-wrap items-center gap-2 px-3 pt-2.5">
        <span className={clsx('chip', isMed ? 'bg-hr/10 text-hr' : 'bg-spo2/10 text-spo2')}>{isMed ? 'Medication' : 'Procedure'}</span>
        {e.status === 'withheld' && <span className="chip bg-alarm/15 text-alarm"><Ban size={12} />Withheld</span>}
        {e.edited && <span className="chip bg-co2/15 text-co2"><PenLine size={12} />Edited</span>}
        <span className="text-[13px] text-faint">heard “{e.text}”</span>
        <div className="ml-auto flex items-center gap-2">
          <ConfBar v={e.confidence} />
          <div className="flex rounded-md border border-line2 p-0.5">
            <IconBtn on={e.status === 'confirmed'} c="#3ee07f" onClick={() => onStatus(e.id, 'confirmed')} label="Keep as given"><Check size={14} /></IconBtn>
            {isMed && <IconBtn on={e.status === 'withheld'} c="#ff4b4b" onClick={() => onStatus(e.id, 'withheld')} label="Mark withheld"><Ban size={14} /></IconBtn>}
            <IconBtn on={e.status === 'rejected'} c="#8a979f" onClick={() => onStatus(e.id, 'rejected')} label="Reject (not a real entry)"><X size={14} /></IconBtn>
          </div>
        </div>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-6 gap-2 p-3">
        {isMed ? (
          <>
            <Field label="Drug" conf={f.drug} className="col-span-2">
              <select className="input" value={f.drug.value || ''} onChange={ev => onField(e.id, 'drug', ev.target.value)}>
                {(lex?.drugs || [{ name: f.drug.value }]).map((d: any) => <option key={d.name}>{d.name}</option>)}
              </select>
            </Field>
            {f.rate ? (
              <Field label="Rate" conf={f.rate}><input className="input num" value={f.rate.value || ''} onChange={ev => onField(e.id, 'rate', ev.target.value)} /></Field>
            ) : (
              <Field label="Dose" conf={f.dose}><input className="input num" inputMode="decimal" value={f.dose.value ?? ''} onChange={ev => onField(e.id, 'dose', ev.target.value === '' ? null : Number(ev.target.value))} /></Field>
            )}
            <Field label="Unit" conf={f.unit}>
              <select className="input" value={f.unit.value || ''} onChange={ev => onField(e.id, 'unit', ev.target.value)}>{UNITS.map(u => <option key={u}>{u}</option>)}</select>
            </Field>
            <Field label="Route" conf={f.route}>
              <select className="input" value={f.route.value || ''} onChange={ev => onField(e.id, 'route', ev.target.value)}>
                {Object.keys(ROUTE_LABEL).map(r => <option key={r} value={r}>{r} · {ROUTE_LABEL[r]}</option>)}
              </select>
            </Field>
            <Field label="Time" conf={f.time}><input className="input num" type="time" value={f.time.value || ''} onChange={ev => onField(e.id, 'time', ev.target.value)} /></Field>
          </>
        ) : (
          <>
            <Field label="Procedure" conf={f.procedure} className="col-span-2 md:col-span-3"><input className="input" value={f.procedure.value} onChange={ev => onField(e.id, 'procedure', ev.target.value)} /></Field>
            <Field label="Details" className="md:col-span-2"><input className="input" value={[f.device?.value, f.site?.value, f.energy?.value].filter(Boolean).join(', ')} readOnly /></Field>
            <Field label="Time" conf={f.time}><input className="input num" type="time" value={f.time.value || ''} onChange={ev => onField(e.id, 'time', ev.target.value)} /></Field>
          </>
        )}
      </div>
      {(e.flags?.length > 0 || e.evidence?.length > 0) && (
        <div className="px-3 pb-2.5 space-y-1.5">
          {e.flags.filter((x: any) => x.level !== 'info').map((x: any, i: number) => <FlagLine key={i} f={x} />)}
          <button className="text-[13px] text-dim hover:text-ink flex items-center gap-1" onClick={() => setWhy(w => !w)}>
            <ChevronDown size={14} className={clsx('transition-transform', why && 'rotate-180')} />Why these values
          </button>
          {why && (
            <ul className="text-[13px] text-dim space-y-0.5 pl-5 list-disc marker:text-faint">
              {e.evidence.map((ev: string, i: number) => <li key={i}>{ev}</li>)}
              {e.codes?.rxnorm && <li>RxNorm ingredient {e.codes.rxnorm} · {e.codes.class}</li>}
              {e.codes?.snomed && <li>Code {e.codes.snomed}</li>}
              {e.flags.filter((x: any) => x.level === 'info').map((x: any, i: number) => <li key={'i' + i}>{x.message}</li>)}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

function IconBtn({ on, c, onClick, label, children }: any) {
  return <button aria-label={label} title={label} onClick={onClick} className="h-7 w-7 rounded flex items-center justify-center" style={on ? { background: c + '22', color: c } : { color: '#55626b' }}>{children}</button>
}

function Field({ label, conf, children, className }: { label: string; conf?: any; children: any; className?: string }) {
  const src = conf?.source
  const tone = !conf ? '' : conf.source === 'emt' ? 'text-co2' : conf.confidence >= 0.85 ? 'text-faint' : conf.confidence >= 0.6 ? 'text-warn' : 'text-alarm'
  return (
    <label className={clsx('block text-[12px] text-dim', className)}>
      <span className="flex justify-between mb-1"><span>{label}</span>{conf && <span className={tone}>{src === 'emt' ? 'EMT' : src === 'default' ? 'default' : src === 'missing' ? 'missing' : src === 'fuzzy' ? 'auto-corrected' : `${Math.round(conf.confidence * 100)}%`}</span>}</span>
      {children}
    </label>
  )
}

// ----------------------------------------------------------------- recorder

function Recorder({ asr, onText }: { asr: any; onText: (t: string, meta: any) => void }) {
  const toast = useToast()
  const [rec, setRec] = useState<MediaRecorder | null>(null)
  const [secs, setSecs] = useState(0)
  const [busy, setBusy] = useState(false)
  const cv = useRef<HTMLCanvasElement>(null)
  const raf = useRef(0)
  const stop = () => rec?.stop()
  const start = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } })
      const mr = new MediaRecorder(stream)
      const chunks: BlobPart[] = []
      const ac = new AudioContext()
      const an = ac.createAnalyser(); an.fftSize = 2048
      ac.createMediaStreamSource(stream).connect(an)
      const buf = new Uint8Array(an.fftSize)
      const started = Date.now()
      const draw = () => {
        const c = cv.current
        if (c) {
          const g = c.getContext('2d')!, w = c.width = c.clientWidth * 2, h = c.height = 140
          an.getByteTimeDomainData(buf)
          g.fillStyle = '#000'; g.fillRect(0, 0, w, h)
          g.strokeStyle = '#35d0f0'; g.lineWidth = 3; g.shadowColor = '#35d0f0'; g.shadowBlur = 8; g.beginPath()
          for (let i = 0; i < buf.length; i++) { const x = (i / buf.length) * w, y = (buf[i] / 255) * h; i ? g.lineTo(x, y) : g.moveTo(x, y) }
          g.stroke()
        }
        setSecs(Math.floor((Date.now() - started) / 1000))
        raf.current = requestAnimationFrame(draw)
      }
      draw()
      mr.ondataavailable = e => chunks.push(e.data)
      mr.onstop = async () => {
        cancelAnimationFrame(raf.current); stream.getTracks().forEach(t => t.stop()); ac.close(); setRec(null)
        const blob = new Blob(chunks, { type: mr.mimeType || 'audio/webm' })
        setBusy(true)
        try {
          const r: any = await api.asr(blob)
          if (!r.text) toast('info', 'No speech detected - try again closer to the mic')
          else { onText(r.text, r); toast('ok', `Transcribed ${r.audio_seconds}s of audio in ${r.elapsed_seconds}s on-device`) }
        } catch (e: any) { toast('err', e.message) } finally { setBusy(false) }
      }
      mr.start(); setRec(mr)
    } catch (e: any) { toast('err', 'Microphone unavailable: ' + e.message) }
  }
  return (
    <div className="mb-3">
      <div className="rounded-md border border-line bg-black overflow-hidden relative">
        <canvas ref={cv} className="w-full h-[70px] block" />
        {!rec && !busy && <div className="absolute inset-0 flex items-center justify-center text-[13px] text-faint">Microphone idle</div>}
        {busy && <div className="absolute inset-0 flex items-center justify-center gap-2 text-[13px] text-spo2"><Loader2 size={14} className="animate-spin" />Transcribing on this device with Whisper ({asr?.model} · {asr?.compute_type})</div>}
      </div>
      <div className="flex items-center gap-3 mt-2.5">
        {!rec ? (
          <button className="btn-pri" onClick={start} disabled={busy}><Mic size={16} />Start dictation</button>
        ) : (
          <button className="btn-danger" onClick={stop}><Square size={14} />Stop · <span className="num">{String(Math.floor(secs / 60)).padStart(2, '0')}:{String(secs % 60).padStart(2, '0')}</span></button>
        )}
        {rec && <span className="w-2.5 h-2.5 rounded-full bg-alarm blink" />}
        <span className={clsx('text-[13px]', asr?.available ? 'text-dim' : 'text-warn')}>
          {asr?.available ? `Offline ASR ready · faster-whisper ${asr.model} ${asr.compute_type}${asr.loaded ? '' : ' (loads on first use)'}` : 'Offline ASR not installed on this server: pip install faster-whisper. Typing still works.'}
        </span>
      </div>
    </div>
  )
}

// ----------------------------------------------------------------- new incident

function NewIncident({ open, onClose, onCreated }: any) {
  const { data: ref } = useFetch(api.reference, [])
  const toast = useToast()
  const [f, setF] = useState<any>({ place: 'Richmond Circle', lat: 12.9634, lng: 77.5960, vehicle: 'KA-01-G-2108', crew: 'EMT-07 R. Kumar', destination: 'Victoria Hospital', eta_min: 12 })
  const set = (k: string, v: any) => setF((x: any) => ({ ...x, [k]: v }))
  const go = async () => {
    try { onCreated(await api.createIncident(f)) } catch (e: any) { toast('err', e.message) }
  }
  return (
    <Modal open={open} onClose={onClose} title="Open a new incident">
      <div className="grid grid-cols-2 gap-3">
        <label className="text-[13px] text-dim col-span-2">Scene location<input className="input mt-1" value={f.place} onChange={e => set('place', e.target.value)} /></label>
        <label className="text-[13px] text-dim">Latitude<input className="input mt-1 num" value={f.lat} onChange={e => set('lat', Number(e.target.value))} /></label>
        <label className="text-[13px] text-dim">Longitude<input className="input mt-1 num" value={f.lng} onChange={e => set('lng', Number(e.target.value))} /></label>
        <label className="text-[13px] text-dim">Vehicle<input className="input mt-1" value={f.vehicle} onChange={e => set('vehicle', e.target.value)} /></label>
        <label className="text-[13px] text-dim">Crew
          <select className="input mt-1" value={f.crew} onChange={e => set('crew', e.target.value)}>{(ref?.crew || [f.crew]).map((c: string) => <option key={c}>{c}</option>)}</select>
        </label>
        <label className="text-[13px] text-dim">Destination
          <select className="input mt-1" value={f.destination} onChange={e => set('destination', e.target.value)}>{(ref?.hospitals || []).map((h: any) => <option key={h.id}>{h.name}</option>)}</select>
        </label>
        <label className="text-[13px] text-dim">ETA (min)<input className="input mt-1 num" type="number" value={f.eta_min} onChange={e => set('eta_min', Number(e.target.value))} /></label>
      </div>
      <div className="flex justify-end gap-2 mt-4">
        <button className="btn-ghost" onClick={onClose}>Cancel</button>
        <button className="btn-pri" onClick={go}><Plus size={15} />Open incident</button>
      </div>
    </Modal>
  )
}

function LangPicker() {
  const [l, setL] = useState<AsrLang>(asrLang())
  useEffect(() => { const h = () => setL(asrLang()); window.addEventListener('fs:asrlang', h); return () => window.removeEventListener('fs:asrlang', h) }, [])
  return (
    <div className="flex flex-wrap items-center gap-2 mb-2.5">
      <span className="text-[13px] text-dim flex items-center gap-1.5"><Languages size={14} />Listening for</span>
      <div className="flex flex-wrap rounded-md border border-line2 p-0.5" role="radiogroup" aria-label="Dictation language">
        {ASR_LANGS.map(o => (
          <button key={o.k} role="radio" aria-checked={l === o.k} title={o.hint} onClick={() => { setAsrLang(o.k); setL(o.k) }}
            className={clsx('h-8 px-3 rounded text-[13.5px]', l === o.k ? 'bg-raise text-ink' : 'text-dim hover:text-ink')}>{o.label}</button>
        ))}
      </div>
    </div>
  )
}
