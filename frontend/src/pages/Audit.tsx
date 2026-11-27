import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { ShieldCheck, ShieldAlert, RotateCcw, Skull, RefreshCw, Link2 } from 'lucide-react'
import clsx from 'clsx'
import { api } from '../lib/api'
import { Hash, JsonView, Panel, Spinner, useFetch, useToast } from '../components/ui'

const EVENT_COLOR: Record<string, string> = { INCIDENT_OPENED: '#ffa733', RECORD_SIGNED: '#3ee07f', INCIDENT_UPDATED: '#35d0f0', HANDOVER_ACK: '#c08bff' }

export default function Audit() {
  const toast = useToast()
  const { data: blocks, reload } = useFetch(() => api.ledger(), [])
  const { data: v, reload: rv } = useFetch(api.verify, [])
  const [sel, setSel] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const bad = new Set((v?.problems || []).map((p: any) => p.seq))
  useEffect(() => { if (blocks) setSel((s: any) => blocks.find((b: any) => b.seq === s?.seq) || blocks[0]) }, [blocks])
  const refresh = async () => { await Promise.all([reload(), rv()]); window.dispatchEvent(new Event('fs:refresh')) }
  const tamper = async () => {
    setBusy(true)
    const r: any = await api.tamper()
    toast('err', `Block #${r.tamper.seq} edited directly in the database (${r.tamper.change}). Verification now fails.`)
    await refresh(); setBusy(false)
  }
  const restore = async () => { setBusy(true); await api.restore(); toast('ok', 'Original payload restored. Chain verifies again.'); await refresh(); setBusy(false) }
  const asc = [...(blocks || [])].reverse()
  return (
    <div className="max-w-[1600px] mx-auto space-y-4">
      <div>
        <h1 className="font-num text-[34px] font-semibold leading-none">Audit ledger</h1>
        <p className="text-dim mt-1.5">Every open, signature and handover is a block. Change one byte of history and verification says exactly where.</p>
      </div>

      <div className="grid grid-cols-12 gap-4">
        <div className={clsx('col-span-12 lg:col-span-5 rounded-[10px] border p-5 flex items-center gap-5',
          v?.valid === false ? 'border-alarm/60 bg-alarm/[.06]' : 'border-hr/40 bg-hr/[.04]')}>
          {!v ? <Spinner /> : <>
            <motion.div key={String(v.valid)} initial={{ scale: .7, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}>
              {v.valid ? <ShieldCheck size={64} className="text-hr" strokeWidth={1.5} /> : <ShieldAlert size={64} className="text-alarm" strokeWidth={1.5} />}
            </motion.div>
            <div>
              <div className={clsx('font-num text-[38px] font-semibold leading-none', v.valid ? 'text-hr' : 'text-alarm')}>{v.valid ? 'Chain verified' : `Tampering at block #${v.first_bad_seq}`}</div>
              <div className="text-dim mt-1.5 text-[14px]">{v.blocks} blocks replayed · {v.algorithm}</div>
              <div className="text-[13px] text-faint mt-0.5">Device key {v.key_id} · checked {new Date(v.verified_at).toLocaleTimeString('en-GB')}</div>
              {!v.valid && v.problems.map((p: any) => <div key={p.seq} className="text-[13px] text-alarm mt-1">#{p.seq} {p.event_type.toLowerCase().replace('_', ' ')}: {p.issues.join('; ')}</div>)}
            </div>
          </>}
        </div>
        <Panel className="col-span-12 lg:col-span-7" title="Tamper drill" sub="Simulates an insider editing a signed dose straight in SQLite, bypassing the app">
          <ol className="text-[14px] text-dim space-y-1 mb-3 list-decimal pl-5">
            <li>Pick the newest signed record and multiply its first dose by ten.</li>
            <li>Re-run verification: the payload hash no longer matches, so the block is rejected.</li>
            <li>Restore the original bytes and watch the chain go green again.</li>
          </ol>
          <div className="flex flex-wrap gap-2">
            <button className="btn-danger" disabled={busy || v?.valid === false} onClick={tamper}><Skull size={15} />Tamper with a dose</button>
            <button className="btn-sec" disabled={busy || v?.valid !== false} onClick={restore}><RotateCcw size={15} />Restore original</button>
            <button className="btn-ghost" onClick={refresh}><RefreshCw size={15} />Re-verify</button>
          </div>
        </Panel>
      </div>

      <Panel title="Chain" sub="Oldest on the left. Each block stores the hash of the one before it.">
        {!blocks ? <Spinner /> : (
          <div className="overflow-x-auto pb-2">
            <div className="flex items-center gap-0 min-w-max py-2">
              {asc.map((b: any, i: number) => {
                const isBad = bad.has(b.seq)
                const afterBad = [...bad].some((s: any) => s < b.seq)
                const c = isBad ? '#ff4b4b' : EVENT_COLOR[b.event_type] || '#8a979f'
                return (
                  <div key={b.seq} className="flex items-center">
                    {i > 0 && <div className="w-6 h-px" style={{ background: isBad ? '#ff4b4b' : '#242e36' }} />}
                    <button onClick={() => setSel(b)} title={`#${b.seq} ${b.event_type}`}
                      className={clsx('w-[86px] rounded-md border p-2 text-left transition-colors', sel?.seq === b.seq ? 'bg-raise' : 'bg-black', afterBad && !isBad && 'opacity-60')}
                      style={{ borderColor: isBad ? '#ff4b4b' : sel?.seq === b.seq ? c : '#182027' }}>
                      <div className="flex items-center justify-between"><span className="num text-[18px] font-semibold" style={{ color: c }}>#{b.seq}</span>{isBad && <ShieldAlert size={13} className="text-alarm" />}</div>
                      <div className="font-mono text-[10px] text-faint truncate">{b.hash.slice(0, 8)}</div>
                      <div className="h-1 rounded-full mt-1.5" style={{ background: c, opacity: .7 }} />
                    </button>
                  </div>
                )
              })}
            </div>
          </div>
        )}
        <div className="flex flex-wrap gap-3 text-[12px] text-dim mt-1">
          {Object.entries(EVENT_COLOR).map(([k, c]) => <span key={k} className="flex items-center gap-1.5"><span className="w-2.5 h-1 rounded-full" style={{ background: c }} />{k.toLowerCase().replace('_', ' ')}</span>)}
        </div>
      </Panel>

      {sel && (
        <div className="grid grid-cols-12 gap-4">
          <Panel className="col-span-12 lg:col-span-5" title={`Block #${sel.seq}`} sub={`${sel.event_type.toLowerCase().replace('_', ' ')} · ${new Date(sel.ts).toLocaleString('en-GB')}`}>
            <dl className="space-y-2.5 text-[13px]">
              {[['Incident', sel.incident_id], ['Signer', sel.signer], ['Key id', sel.key_id]].map(([k, val]) => (
                <div key={k} className="grid grid-cols-[110px_1fr]"><dt className="text-dim">{k}</dt><dd>{val}</dd></div>
              ))}
              {[['Payload hash', sel.payload_hash], ['Previous hash', sel.prev_hash], ['Block hash', sel.hash]].map(([k, val]) => (
                <div key={k} className="grid grid-cols-[110px_1fr]"><dt className="text-dim">{k}</dt><dd className="font-mono text-[11px] break-all text-ink/80">{val}</dd></div>
              ))}
              <div className="grid grid-cols-[110px_1fr]"><dt className="text-dim">Signature</dt><dd className="font-mono text-[11px] break-all text-ink/60">{sel.signature}</dd></div>
            </dl>
            <div className={clsx('mt-3 rounded-md px-3 py-2 text-[13px] flex items-center gap-2', bad.has(sel.seq) ? 'bg-alarm/10 text-alarm' : 'bg-hr/10 text-hr')}>
              {bad.has(sel.seq) ? <ShieldAlert size={15} /> : <Link2 size={15} />}
              {bad.has(sel.seq) ? 'This block fails verification' : 'Hash, link and Ed25519 signature verified'}
            </div>
          </Panel>
          <Panel className="col-span-12 lg:col-span-7" title="Signed payload" sub="Canonical JSON (sorted keys) that the payload hash commits to">
            <JsonView data={sel.payload} max="420px" />
          </Panel>
        </div>
      )}
    </div>
  )
}
