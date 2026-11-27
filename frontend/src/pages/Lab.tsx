import { useEffect, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis, Cell, ReferenceLine } from 'recharts'
import { RefreshCw, FlaskConical } from 'lucide-react'
import { api } from '../lib/api'
import { chartTheme, ConfBar, Empty, FlagLine, Numeric, Panel, Spinner, useFetch } from '../components/ui'

const SLICE_LABEL: Record<string, string> = {
  clean: 'Clean English', brand: 'Indian brands', hinglish: 'Hinglish', asr_noise: 'ASR misspellings', negation: 'Negation',
  spoken_numbers: 'Spoken numbers', multi_drug: 'Multi-drug', narrative: 'Narrative + vitals',
}

export default function Lab() {
  const { data: ev, reload, loading } = useFetch(() => api.eval(), [])
  const [refreshing, setRefreshing] = useState(false)
  const rerun = async () => { setRefreshing(true); await api.eval(true); await reload(); setRefreshing(false) }
  return (
    <div className="max-w-[1600px] mx-auto space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-num text-[34px] font-semibold leading-none">Model lab</h1>
          <p className="text-dim mt-1.5">How well the on-device extractor reads dictations, where it breaks, and how often it fails silently.</p>
        </div>
        <button className="btn-sec" onClick={rerun} disabled={refreshing}><RefreshCw size={15} className={refreshing ? 'animate-spin' : ''} />Re-run benchmark</button>
      </div>
      <Compare />
      <Codemix />
      {!ev || loading ? <div className="py-20 flex justify-center"><Spinner size={24} /></div> : <Results ev={ev} />}
      <div className="grid grid-cols-12 gap-4">
        <Probe />
        <Wer />
      </div>
    </div>
  )
}

function Results({ ev }: { ev: any }) {
  const slices = Object.entries(ev.slices).map(([k, v]: any) => ({ name: SLICE_LABEL[k] || k, f1: +(v.f1 * 100).toFixed(1), recall: +(v.recall * 100).toFixed(1) }))
  const fields = Object.entries(ev.fields).map(([k, v]: any) => ({ name: k, acc: +(v * 100).toFixed(1) }))
  const stress = ev.stress.map((s: any) => ({ cer: `${Math.round(s.char_error_rate * 100)}%`, recall: s.drug_recall * 100, flagged: s.auto_corrected_and_flagged * 100, wrong: s.wrong_drug * 100, missed: s.missed * 100 }))
  return (
    <>
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
        <Numeric label="Entity F1" value={(ev.entity.f1 * 100).toFixed(1)} unit="%" color="#3ee07f" hint={`${ev.cases} dictations · ${ev.gold_entities} gold entities`} />
        <Numeric label="Precision" value={(ev.entity.precision * 100).toFixed(1)} unit="%" color="#3ee07f" hint={`${ev.entity.fp} false positives`} />
        <Numeric label="Recall" value={(ev.entity.recall * 100).toFixed(1)} unit="%" color="#3ee07f" hint={`${ev.entity.fn} missed`} />
        <Numeric label="Negation" value={(ev.negation_accuracy * 100).toFixed(0)} unit="%" color="#35d0f0" hint="withheld vs given" />
        <Numeric label="Silent errors" value={(ev.silent_critical_error_rate * 100).toFixed(2)} unit="%" color={ev.silent_critical_error_rate > 0.01 ? '#ff4b4b' : '#3ee07f'} hint="wrong & not flagged" />
        <Numeric label="Latency p95" value={ev.latency_ms.p95} unit="ms" color="#c08bff" hint={`CPU, mean ${ev.latency_ms.mean} ms`} />
      </div>
      <div className="grid grid-cols-12 gap-4">
        <Panel className="col-span-12 xl:col-span-7" title="Robustness to ASR noise" sub="Drug names randomly corrupted at increasing character error rates (120 trials per level)">
          <div className="h-[280px]">
            <ResponsiveContainer>
              <LineChart data={stress} margin={{ left: -10, right: 12, top: 8 }}>
                <CartesianGrid stroke={chartTheme.grid} vertical={false} />
                <XAxis dataKey="cer" stroke={chartTheme.axis} tick={{ fontSize: 12 }} label={{ value: 'character error rate', position: 'insideBottom', offset: -2, fill: '#55626b', fontSize: 12 }} height={36} />
                <YAxis stroke={chartTheme.axis} tick={{ fontSize: 12 }} unit="%" domain={[0, 100]} />
                <Tooltip {...chartTheme.tooltip} formatter={(v: any) => `${Number(v).toFixed(1)}%`} />
                <Legend wrapperStyle={{ fontSize: 12, color: '#8a979f' }} />
                <Line dataKey="recall" name="Drug recovered" stroke="#3ee07f" strokeWidth={2.5} dot={{ r: 3 }} />
                <Line dataKey="flagged" name="Recovered via fuzzy match (flagged)" stroke="#ffa733" strokeWidth={2} dot={{ r: 3 }} />
                <Line dataKey="missed" name="Missed (no entity)" stroke="#8a979f" strokeWidth={2} strokeDasharray="4 3" dot={false} />
                <Line dataKey="wrong" name="Wrong drug" stroke="#ff4b4b" strokeWidth={2} dot={{ r: 3 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <p className="text-[13px] text-dim mt-2">Below ~15% character error the fuzzy matcher recovers most mis-heard names and always flags them for review. Past that it prefers to miss a drug rather than guess a wrong one, which is the safer failure for medication records.</p>
        </Panel>
        <Panel className="col-span-12 xl:col-span-5" title="F1 by slice" sub="Templated regression suite (synthetic)">
          <div className="h-[300px]">
            <ResponsiveContainer>
              <BarChart data={slices} layout="vertical" margin={{ left: 20, right: 20 }}>
                <XAxis type="number" domain={[0, 100]} hide />
                <YAxis type="category" dataKey="name" width={124} stroke={chartTheme.axis} tick={{ fontSize: 12, fill: '#c9d3d8' }} />
                <Tooltip {...chartTheme.tooltip} cursor={{ fill: '#0c1013' }} formatter={(v: any) => `${v}%`} />
                <ReferenceLine x={95} stroke="#242e36" strokeDasharray="3 3" />
                <Bar dataKey="f1" name="F1" radius={[0, 3, 3, 0]} barSize={14}>{slices.map((s, i) => <Cell key={i} fill={s.f1 >= 95 ? '#3ee07f' : s.f1 >= 85 ? '#ffa733' : '#ff4b4b'} />)}</Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Panel>
      </div>
      <div className="grid grid-cols-12 gap-4">
        <Panel className="col-span-12 md:col-span-5" title="Field accuracy" sub="When the drug is found, how often each field is right">
          <div className="space-y-3 pt-1">
            {fields.map(f => (
              <div key={f.name}>
                <div className="flex justify-between text-[14px] mb-1"><span className="capitalize text-dim">{f.name}</span><span className="num text-[17px]">{f.acc}%</span></div>
                <div className="h-2 rounded-full bg-line"><div className="h-full rounded-full bg-spo2" style={{ width: `${f.acc}%` }} /></div>
              </div>
            ))}
          </div>
        </Panel>
        <Panel className="col-span-12 md:col-span-7" title="Honest limits" sub="What this benchmark does and does not prove">
          <ul className="text-[14px] text-dim space-y-2 list-disc pl-5 marker:text-faint">
            <li>The slice suite is generated from templates the extractor was designed against, so near-perfect scores are a regression floor, not a field accuracy claim.</li>
            <li>The noise curve uses random corruption the rules never saw. It is the more realistic signal for ASR failure modes.</li>
            <li>Field WER on the Command centre comes from voice records where the EMT corrected the transcript before signing.</li>
            <li>Next step for the pilot: recorded dictations from 108 crews, scored against clinician-labelled records (n2c2-style annotation).</li>
          </ul>
          {ev.errors.length > 0 && <div className="mt-3 text-[13px] text-warn">{ev.errors.length} benchmark errors listed in the API response (/api/eval).</div>}
        </Panel>
      </div>
    </>
  )
}

function Probe() {
  const [t, setT] = useState('pt ko dolo 650 diya orally at 1530, then ondansatron 4 mg iv. no aspirin as allergic to aspirin')
  const [r, setR] = useState<any>(null)
  useEffect(() => { const h = setTimeout(async () => t.trim() && setR(await api.extract(t)), 300); return () => clearTimeout(h) }, [t])
  return (
    <Panel className="col-span-12 xl:col-span-7" title="Live probe" sub="Try to break it. Runs the same engine as Capture.">
      <textarea className="w-full bg-black border border-line2 rounded-md p-3 text-[15px] focus:outline-none focus:border-spo2" rows={3} value={t} onChange={e => setT(e.target.value)} />
      {!r ? <Empty title="Type a dictation" /> : (
        <div className="mt-3 space-y-2">
          <div className="text-[13px] text-faint">normalised: <span className="text-dim">{r.normalised}</span> · {r.latency_ms} ms</div>
          {r.entities.map((e: any) => (
            <div key={e.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-md border border-line bg-black px-3 py-2 text-[14px]">
              <span className={e.negated ? 'text-alarm line-through' : 'text-hr font-medium'}>{e.fields.drug?.value || e.fields.procedure?.value}</span>
              {Object.entries(e.fields).filter(([k]) => !['drug', 'procedure'].includes(k)).map(([k, v]: any) => v.value != null && <span key={k} className="text-dim">{k} <span className="text-ink num text-[16px]">{String(v.value)}</span></span>)}
              <span className="ml-auto"><ConfBar v={e.confidence} /></span>
            </div>
          ))}
          {r.alerts.filter((a: any) => a.level !== 'info').map((a: any, i: number) => <FlagLine key={i} f={a} />)}
        </div>
      )}
    </Panel>
  )
}

function Wer() {
  const [ref, setRef] = useState('ecosprin 300 mg chewed at 10:42 sorbitrate 5 mg sublingual')
  const [hyp, setHyp] = useState('eco sprin 300 mg chewed at 10 42 sorbi trait 5 mg sub lingual')
  const [r, setR] = useState<any>(null)
  useEffect(() => { const h = setTimeout(async () => setR(await api.wer(ref, hyp)), 250); return () => clearTimeout(h) }, [ref, hyp])
  return (
    <Panel className="col-span-12 xl:col-span-5" title="WER calculator" sub="Word error rate between a reference and an ASR hypothesis">
      <label className="text-[13px] text-dim block">Reference (what was said)<textarea rows={2} className="w-full mt-1 bg-black border border-line2 rounded-md p-2.5 text-[14px] focus:outline-none focus:border-spo2" value={ref} onChange={e => setRef(e.target.value)} /></label>
      <label className="text-[13px] text-dim block mt-2">Hypothesis (what ASR produced)<textarea rows={2} className="w-full mt-1 bg-black border border-line2 rounded-md p-2.5 text-[14px] focus:outline-none focus:border-spo2" value={hyp} onChange={e => setHyp(e.target.value)} /></label>
      {r && <div className="grid grid-cols-4 gap-2 mt-3">
        <Numeric size="md" label="WER" value={(r.wer * 100).toFixed(1)} unit="%" color={r.wer < .1 ? '#3ee07f' : r.wer < .25 ? '#ffa733' : '#ff4b4b'} />
        <Numeric size="md" label="Subs" value={r.substitutions} color="#f3cf3a" />
        <Numeric size="md" label="Dels" value={r.deletions} color="#f3cf3a" />
        <Numeric size="md" label="Ins" value={r.insertions} color="#f3cf3a" />
      </div>}
    </Panel>
  )
}


const ENG_COLOR: Record<string, string> = { rules: '#8a979f', distilbert: '#35d0f0', hybrid: '#3ee07f' }
const ENG_LABEL: Record<string, string> = { rules: 'Rules + fuzzy', distilbert: 'DistilBERT only', hybrid: 'Hybrid (shipped)' }

function Compare() {
  const { data: c } = useFetch(() => api.evalCompare(), [])
  if (!c) return <Panel title="Rules vs DistilBERT vs hybrid"><div className="py-8 flex justify-center"><Spinner /></div></Panel>
  const tn = c.transformer
  const metrics = [
    ['detection_recall', 'Drug mentions found'], ['detection_precision', 'Precision'],
    ['normalised_correct', 'Mapped to the right drug'], ['unseen_brand_surfaced', 'Unseen brands surfaced'],
  ]
  const rows = metrics.map(([k, l]) => ({ name: l, ...Object.fromEntries(Object.entries(c.engines).map(([e, v]: any) => [e, v[k] == null ? 0 : +(v[k] * 100).toFixed(1)])) }))
  const engines = Object.keys(c.engines)
  return (
    <div className="grid grid-cols-12 gap-4">
      <Panel className="col-span-12 xl:col-span-8" title="Rules vs DistilBERT vs hybrid" sub={`Held-out set: ${c.sentences} dictations with unseen Indian brands and heavier ASR noise`}>
        <div className="h-[280px]">
          <ResponsiveContainer>
            <BarChart data={rows} margin={{ left: -14, right: 8, top: 8 }} barGap={3}>
              <CartesianGrid stroke={chartTheme.grid} vertical={false} />
              <XAxis dataKey="name" stroke={chartTheme.axis} tick={{ fontSize: 12, fill: '#c9d3d8' }} />
              <YAxis stroke={chartTheme.axis} tick={{ fontSize: 12 }} unit="%" domain={[0, 100]} />
              <Tooltip {...chartTheme.tooltip} cursor={{ fill: '#0c1013' }} formatter={(v: any) => `${v}%`} />
              <Legend wrapperStyle={{ fontSize: 12 }} formatter={(v: any) => ENG_LABEL[v] || v} />
              {engines.map(e => <Bar key={e} dataKey={e} name={e} fill={ENG_COLOR[e]} radius={[3, 3, 0, 0]} barSize={22} />)}
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="grid grid-cols-3 gap-2 mt-2 text-[13px]">
          {engines.map(e => (
            <div key={e} className="rounded-md border border-line bg-black px-3 py-2">
              <div className="font-medium" style={{ color: ENG_COLOR[e] }}>{ENG_LABEL[e]}</div>
              <div className="text-dim">F1 <span className="num text-ink text-[16px]">{(c.engines[e].detection_f1 * 100).toFixed(1)}%</span> · {c.engines[e].ms_per_dictation} ms · silent wrong <span className="num text-ink text-[16px]">{c.engines[e].silent_wrong}</span></div>
            </div>
          ))}
        </div>
        {!tn?.available && <p className="text-[13px] text-dim mt-3">Only the rule engine is shown. Train DistilBERT to add the other two bars: <span className="font-mono text-[12px] text-ink">python train_ner.py</span> in the backend folder (see README).</p>}
      </Panel>
      <Panel className="col-span-12 xl:col-span-4" title="DistilBERT model card" sub={tn?.available ? (tn.loaded ? 'Loaded and running alongside the rules' : 'Trained, loads on first use') : 'Not trained on this machine yet'}>
        {tn?.trained ? (
          <div className="space-y-2.5 text-[14px]">
            <dl className="grid grid-cols-[110px_1fr] gap-y-1">
              <dt className="text-dim">Base</dt><dd>{tn.base}</dd>
              <dt className="text-dim">Training</dt><dd>{tn.train_sentences} synthetic dictations · {tn.epochs} epochs</dd>
              <dt className="text-dim">Labels</dt><dd>DRUG, DOSE, UNIT, ROUTE, TIME, PROC, NEG (BIO)</dd>
            </dl>
            {tn.metrics && <div className="space-y-1.5 pt-1">
              {Object.entries(tn.metrics).filter(([k]) => k !== 'micro').map(([k, v]: any) => (
                <div key={k}>
                  <div className="flex justify-between text-[13px]"><span className="text-dim">{k}</span><span className="num text-[15px]">{(v.f1 * 100).toFixed(1)}%</span></div>
                  <div className="h-1.5 rounded-full bg-line"><div className="h-full rounded-full bg-spo2" style={{ width: `${v.f1 * 100}%` }} /></div>
                </div>
              ))}
              <div className="text-[13px] text-dim pt-1">Span micro-F1 on held-out set <span className="num text-ink text-[16px]">{(tn.metrics.micro.f1 * 100).toFixed(1)}%</span></div>
            </div>}
          </div>
        ) : (
          <ol className="text-[14px] text-dim space-y-1.5 list-decimal pl-5">
            <li><span className="font-mono text-[12px] text-ink">pip install -r requirements-ml.txt</span></li>
            <li><span className="font-mono text-[12px] text-ink">python train_ner.py</span> (10-25 min on CPU)</li>
            <li>Restart FieldScribe. The hybrid engine switches on automatically.</li>
          </ol>
        )}
        <p className="text-[12px] text-faint mt-3">Rules stay in charge of codes and doses. DistilBERT confirms rule hits and surfaces drug mentions the rules missed, always flagged for EMT review.</p>
      </Panel>
    </div>
  )
}

const LANG_ORDER = ['Hinglish', 'Hindi', 'Kanglish', 'Kannada']
const LANG_SUB: Record<string, string> = { Hinglish: 'Hindi in Latin letters', Hindi: 'Devanagari script', Kanglish: 'Kannada in Latin letters', Kannada: 'Kannada script' }

function Codemix() {
  const { data } = useFetch(() => api.evalCodemix(), [])
  const [set, setSet] = useState<'heldout' | 'development'>('heldout')
  const [onlyMiss, setOnlyMiss] = useState(false)
  if (!data) return <Panel title="Hindi and Kannada dictation"><div className="py-8 flex justify-center"><Spinner /></div></Panel>
  const d = data[set]
  const bars = LANG_ORDER.filter(l => d.with_indic.by_language[l]).map(l => ({
    name: l, with: +(d.with_indic.by_language[l].f1 * 100).toFixed(0), without: +(d.without_indic.by_language[l].f1 * 100).toFixed(0),
  }))
  const o = d.with_indic.overall, b = d.without_indic.overall
  const rows = d.rows.filter((r: any) => !onlyMiss || !r.ok)
  return (
    <div className="grid grid-cols-12 gap-4">
      <Panel className="col-span-12 xl:col-span-7" title="Hindi and Kannada dictation"
        sub={set === 'heldout' ? `${d.cases} sentences written after the language layer was finished, never used to tune it` : `${d.cases} sentences used while building the language layer`}
        actions={
          <div className="flex rounded-md border border-line2 p-0.5" role="tablist">
            {(['heldout', 'development'] as const).map(k => (
              <button key={k} role="tab" aria-selected={set === k} onClick={() => setSet(k)}
                className={'h-8 px-3 rounded text-[13px] ' + (set === k ? 'bg-raise text-ink' : 'text-dim')}>{k === 'heldout' ? 'Held-out' : 'Development'}</button>
            ))}
          </div>
        }>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5 mb-3">
          <Numeric size="md" label="Medication F1" value={(o.f1 * 100).toFixed(0)} unit="%" color="#3ee07f" hint={`was ${(b.f1 * 100).toFixed(0)}% English-only`} />
          <Numeric size="md" label="Drug found" value={(o.drug_accuracy * 100).toFixed(0)} unit="%" color="#35d0f0" hint={`was ${(b.drug_accuracy * 100).toFixed(0)}%`} />
          <Numeric size="md" label="Age & sex" value={(((o.age_accuracy ?? 1) + (o.sex_accuracy ?? 1)) * 50).toFixed(0)} unit="%" color="#c08bff" hint={`was ${(((b.age_accuracy ?? 0) + (b.sex_accuracy ?? 0)) * 50).toFixed(0)}%`} />
          <Numeric size="md" label="Fully correct" value={(o.cases_fully_correct * 100).toFixed(0)} unit="%" color="#f3cf3a" hint={`was ${(b.cases_fully_correct * 100).toFixed(0)}%`} />
        </div>
        <div className="h-[220px]">
          <ResponsiveContainer>
            <BarChart data={bars} margin={{ left: -14, right: 8, top: 6 }}>
              <CartesianGrid stroke={chartTheme.grid} vertical={false} />
              <XAxis dataKey="name" stroke={chartTheme.axis} tick={{ fontSize: 12 }} />
              <YAxis stroke={chartTheme.axis} tick={{ fontSize: 12 }} domain={[0, 100]} unit="%" />
              <Tooltip {...chartTheme.tooltip} formatter={(v: any) => `${v}%`} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="without" name="English-only engine" fill="#55626b" radius={[3, 3, 0, 0]} />
              <Bar dataKey="with" name="With Hindi + Kannada layer" fill="#3ee07f" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <p className="text-[12.5px] text-faint mt-2">Medication F1 counts a drug only when name, dose, unit and route are all right. {data.heldout.note}</p>
      </Panel>
      <Panel className="col-span-12 xl:col-span-5" title="Sentence by sentence" sub={`${rows.length} shown · ${LANG_ORDER.map(l => `${l}: ${LANG_SUB[l]}`).join(' · ')}`}
        actions={<label className="flex items-center gap-1.5 text-[13px] text-dim"><input type="checkbox" className="accent-[#3ee07f]" checked={onlyMiss} onChange={e => setOnlyMiss(e.target.checked)} />Misses only</label>}>
        <ul className="space-y-2 max-h-[372px] overflow-auto pr-1">
          {rows.map((r: any, i: number) => (
            <li key={i} className={'rounded-md border px-3 py-2 ' + (r.ok ? 'border-line' : 'border-warn/50 bg-warn/[.05]')}>
              <div className="flex items-center gap-2 text-[12px]"><span className="chip bg-raise text-dim">{r.lang}</span>{r.ok ? <span className="text-hr">Correct</span> : <span className="text-warn">Miss</span>}</div>
              <div className="text-[14px] mt-1">{r.text}</div>
              <div className="text-[12.5px] text-dim mt-0.5">Understood: {r.understood}</div>
              <div className="text-[12.5px] mt-0.5"><span className="text-faint">Expected</span> {r.expected.join('; ')} <span className="text-faint">· Got</span> {r.got.join('; ')}</div>
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  )
}
