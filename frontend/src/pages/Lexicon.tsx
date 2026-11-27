import { useMemo, useState } from 'react'
import { Search, AlertTriangle } from 'lucide-react'
import { api, ROUTE_LABEL } from '../lib/api'
import { Panel, Spinner, useFetch } from '../components/ui'

export default function Lexicon() {
  const { data } = useFetch(api.lexicon, [])
  const [q, setQ] = useState('')
  const [tab, setTab] = useState<'drugs' | 'procedures' | 'language'>('drugs')
  const drugs = useMemo(() => (data?.drugs || []).filter((d: any) => !q || [d.name, d.class, ...d.aliases].join(' ').toLowerCase().includes(q.toLowerCase())), [data, q])
  if (!data) return <div className="py-24 flex justify-center"><Spinner size={24} /></div>
  return (
    <div className="max-w-[1600px] mx-auto space-y-4">
      <div>
        <h1 className="font-num text-[34px] font-semibold leading-none">Drug lexicon</h1>
        <p className="text-dim mt-1.5">Indian brand names, abbreviations and mis-hearings mapped to one generic, one code and one protocol default.</p>
      </div>
      <div className="flex flex-wrap gap-2 items-center">
        <div className="flex rounded-md border border-line2 p-0.5">
          {(['drugs', 'procedures', 'language'] as const).map(t => <button key={t} onClick={() => setTab(t)} className={`h-8 px-3 rounded text-[14px] ${tab === t ? 'bg-raise text-ink' : 'text-dim'}`}>{t === 'drugs' ? `Medications (${data.drugs.length})` : t === 'procedures' ? `Procedures (${data.procedures.length})` : 'Routes, units & code-mix'}</button>)}
        </div>
        {tab === 'drugs' && <div className="relative ml-auto"><Search size={15} className="absolute left-2.5 top-2.5 text-faint" /><input className="input pl-8 w-72" placeholder="Search brand, generic or class" value={q} onChange={e => setQ(e.target.value)} /></div>}
      </div>
      {tab === 'drugs' && (
        <Panel title={`${drugs.length} medications`} sub="Reference ranges are demo values used only to raise review flags. Load your state 108 protocol before clinical use.">
          <div className="overflow-x-auto -mx-4">
            <table className="tbl w-full min-w-[980px]">
              <thead><tr><th>Generic</th><th>Class</th><th>Heard as</th><th>RxNorm</th><th>Default route</th><th>Ref. range</th><th>Safety</th></tr></thead>
              <tbody>{drugs.map((d: any) => (
                <tr key={d.name}>
                  <td className="font-medium">{d.name}</td>
                  <td className="text-dim">{d.class}</td>
                  <td><div className="flex flex-wrap gap-1 max-w-[380px]">{d.aliases.map((a: string) => <span key={a} className={`chip ${data.ambiguous[a] ? 'bg-warn/15 text-warn' : 'bg-raise text-dim'}`}>{a}</span>)}</div></td>
                  <td className="num text-[16px]">{d.rxnorm || <span className="text-warn text-[13px] font-sans">verify</span>}</td>
                  <td className="text-dim">{ROUTE_LABEL[d.default_route] || d.default_route}</td>
                  <td className="num text-[16px]">{d.range ? `${d.range[0]}–${d.range[1]}` : '—'} <span className="text-faint text-[13px]">{d.default_unit}</span></td>
                  <td><div className="flex gap-1">{d.high_alert && <span className="chip bg-alarm/15 text-alarm">High alert</span>}{d.controlled && <span className="chip bg-co2/15 text-co2">Controlled</span>}</div></td>
                </tr>))}
              </tbody>
            </table>
          </div>
          <p className="text-[13px] text-dim mt-3 flex items-center gap-2"><AlertTriangle size={14} className="text-warn" />Amber aliases are ambiguous. FieldScribe never resolves them silently and asks the EMT to confirm.</p>
        </Panel>
      )}
      {tab === 'procedures' && (
        <Panel title="Procedures" sub="SNOMED CT where the concept is well established; local FS codes map through the terminology service">
          <div className="overflow-x-auto -mx-4">
            <table className="tbl w-full"><thead><tr><th>Procedure</th><th>Code</th><th>Heard as</th></tr></thead>
              <tbody>{data.procedures.map((p: any) => (
                <tr key={p.name}><td className="font-medium">{p.name}</td><td className="num text-[16px]">{p.snomed}</td>
                  <td><div className="flex flex-wrap gap-1">{p.aliases.map((a: string) => <span key={a} className="chip bg-raise text-dim">{a}</span>)}</div></td></tr>))}
              </tbody></table>
          </div>
        </Panel>
      )}
      {tab === 'language' && (
        <div className="grid grid-cols-12 gap-4">
          <Panel className="col-span-12 lg:col-span-6" title="Routes">
            <div className="space-y-2">{Object.entries(data.routes).map(([k, v]: any) => (
              <div key={k} className="grid grid-cols-[120px_1fr] gap-2 text-[14px]"><span className="font-medium">{k} <span className="text-dim font-normal">{ROUTE_LABEL[k]}</span></span>
                <div className="flex flex-wrap gap-1">{v.map((a: string) => <span key={a} className="chip bg-raise text-dim">{a}</span>)}</div></div>))}</div>
          </Panel>
          <Panel className="col-span-12 lg:col-span-6" title="Code-mixed phrases" sub="Hindi and Kannada verbs normalised before extraction">
            <div className="grid grid-cols-2 gap-1.5">{Object.entries(data.code_mix).filter(([, v]) => v).map(([k, v]: any) => (
              <div key={k} className="flex items-center justify-between rounded border border-line px-2.5 py-1.5 text-[14px]"><span>{k}</span><span className="text-spo2">{v}</span></div>))}</div>
          </Panel>
          <Panel className="col-span-12" title="Units">
            <div className="flex flex-wrap gap-3">{Object.entries(data.units).map(([k, v]: any) => (
              <div key={k} className="rounded border border-line px-3 py-2"><div className="num text-[20px] font-semibold">{k}</div><div className="text-[12px] text-dim">{v.join(', ')}</div></div>))}</div>
          </Panel>
        </div>
      )}
    </div>
  )
}
