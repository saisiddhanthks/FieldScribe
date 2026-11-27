import { useState } from 'react'
import { Wifi, WifiOff, UploadCloud, GitMerge, Cpu, KeyRound, Database, RotateCcw, Loader2, Lock, Server } from 'lucide-react'
import clsx from 'clsx'
import { api } from '../lib/api'
import { Empty, Numeric, Panel, Spinner, useFetch, useToast } from '../components/ui'

export default function Device() {
  const toast = useToast()
  const { data: s, reload } = useFetch(api.sync, [], 4000)
  const { data: sys, reload: rs } = useFetch(api.system, [])
  const { data: incs } = useFetch(api.incidents, [])
  const [busy, setBusy] = useState('')
  const bump = () => { reload(); rs(); window.dispatchEvent(new Event('fs:refresh')) }
  const act = async (k: string, fn: () => Promise<any>, ok: (r: any) => string) => {
    setBusy(k)
    try { const r = await fn(); toast('ok', ok(r)) } catch (e: any) { toast('err', e.message) } finally { setBusy(''); bump() }
  }
  const live = (incs || []).find((i: any) => i.status !== 'handed_over')
  return (
    <div className="max-w-[1600px] mx-auto space-y-4">
      <div>
        <h1 className="font-num text-[34px] font-semibold leading-none">Sync & device</h1>
        <p className="text-dim mt-1.5">The ambulance keeps working in dead zones. Signed records wait in an outbox and merge with the ED hub when signal returns.</p>
      </div>
      {!s ? <Spinner /> : (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Numeric label="Connectivity" value={s.online ? 'Online' : 'Offline'} color={s.online ? '#3ee07f' : '#ffa733'} hint={s.last_sync ? `last sync ${new Date(s.last_sync).toLocaleTimeString('en-GB')}` : 'never synced'} />
          <Numeric label="Queued" value={s.queued} color={s.queued ? '#ffa733' : '#3ee07f'} hint={`${(s.queued_bytes / 1024).toFixed(1)} KB waiting`} />
          <Numeric label="Synced" value={s.synced} color="#35d0f0" hint="items accepted by ED hub" />
          <Numeric label="Conflicts" value={s.conflicts} color={s.conflicts ? '#c08bff' : '#55626b'} hint="resolved, kept for audit" />
        </div>
      )}
      <div className="grid grid-cols-12 gap-4">
        <Panel className="col-span-12 lg:col-span-5" title="Dead-zone drill" sub="Walk judges through an offline run">
          <ol className="space-y-3 text-[14px]">
            <Step n={1} t="Cut the signal" d="Switch the device offline. Capture and signing keep working.">
              <button className={clsx(s?.online ? 'btn-sec' : 'btn-pri')} onClick={() => act('net', () => api.setOnline(!s?.online), r => r.online ? `Online · ${r.sync?.synced_now ?? 0} synced` : 'Offline · outbox buffering')}>
                {s?.online ? <WifiOff size={15} /> : <Wifi size={15} />}{s?.online ? 'Go offline' : 'Restore signal'}
              </button>
            </Step>
            <Step n={2} t="Create a conflict" d="The ED edits this incident on the hub while the ambulance is offline.">
              <button className="btn-sec" disabled={!live || busy === 'hub'} onClick={() => act('hub', () => api.hubEdit(live.id), r => `Hub now at v${r.hub_version} for ${live.vehicle}`)}><GitMerge size={15} />Simulate ED edit</button>
            </Step>
            <Step n={3} t="Reconnect and sync" d="Clinical entries are append-only so they always merge. Header conflicts follow the hub and are logged.">
              <button className="btn-pri" disabled={!s?.online || busy === 'sync'} onClick={() => act('sync', api.runSync, r => `${r.synced_now} synced, ${r.conflicts_now} conflict${r.conflicts_now === 1 ? '' : 's'} resolved`)}>
                {busy === 'sync' ? <Loader2 size={15} className="animate-spin" /> : <UploadCloud size={15} />}Sync now
              </button>
            </Step>
          </ol>
        </Panel>
        <Panel className="col-span-12 lg:col-span-7" title="Outbox" sub="Most recent 60 items">
          {!s?.items?.length ? <Empty title="Outbox empty" /> : (
            <div className="overflow-auto max-h-[420px] -mx-4">
              <table className="tbl w-full">
                <thead className="sticky top-0 bg-panel"><tr><th>#</th><th>Kind</th><th>Incident</th><th>Size</th><th>Created</th><th>Status</th></tr></thead>
                <tbody>{s.items.map((i: any) => (
                  <tr key={i.id}>
                    <td className="num text-[15px] text-dim">{i.id}</td><td>{i.kind}</td><td className="text-dim">{i.incident_id}</td>
                    <td className="num text-[15px] text-dim">{i.bytes} B</td><td className="text-dim">{new Date(i.created_at).toLocaleTimeString('en-GB')}</td>
                    <td title={i.note || ''}>
                      <span className={clsx('chip', i.status === 'queued' ? 'bg-warn/15 text-warn' : i.status === 'conflict' ? 'bg-co2/15 text-co2' : 'bg-hr/10 text-hr')}>{i.status}</span>
                      {i.note && <div className="text-[11px] text-faint mt-0.5 max-w-[240px]">{i.note}</div>}
                    </td>
                  </tr>))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      </div>
      {sys && (
        <div className="grid grid-cols-12 gap-4">
          <Panel className="col-span-12 md:col-span-6" title={<span className="flex items-center gap-2"><Lock size={16} />Device database</span>}
            sub="Lives on this laptop or tablet; works with no network">
            <dl className="text-[14px] space-y-1.5">
              <Row k="Engine" v={<span className={sys.database.encrypted ? 'text-hr' : 'text-warn'}>{sys.database.engine}</span>} />
              <Row k="File" v={`${sys.database.file} · ${sys.database.size_kb} KB`} />
            </dl>
            {!sys.database.encrypted && <p className="text-[12px] text-warn mt-2">Not encrypted. Run <span className="font-mono">pip install sqlcipher3-wheels</span> and restart; the existing file is converted automatically.</p>}
            {sys.database.encrypted && <p className="text-[12px] text-faint mt-2">AES-256 at rest. A copied database file is unreadable without the device key in backend/.env.</p>}
          </Panel>
          <Panel className="col-span-12 md:col-span-6" title={<span className="flex items-center gap-2"><Server size={16} />ED / state hub</span>}
            sub="Where ambulances sync when signal returns">
            <dl className="text-[14px] space-y-1.5">
              <Row k="Engine" v={sys.hub.engine === 'postgresql' ? <span className="text-hr">PostgreSQL</span> : <span className="text-warn">Simulated (inside this device)</span>} />
              {sys.hub.url && <Row k="Server" v={<span className="font-mono text-[12px]">{sys.hub.url}</span>} />}
              <Row k="Status" v={sys.hub.ok ? <span className="text-hr">Connected</span> : <span className="text-alarm">{sys.hub.error || 'Unreachable'}</span>} />
              {sys.hub.ok && <Row k="Holds" v={`${sys.hub.incidents} incidents · ${sys.hub.items} items`} />}
            </dl>
            {sys.hub.engine !== 'postgresql' && <p className="text-[12px] text-faint mt-2">Set FIELDSCRIBE_HUB_URL in backend/.env to sync to a real PostgreSQL hub (see README).</p>}
          </Panel>
          <Panel className="col-span-12 md:col-span-4" title={<span className="flex items-center gap-2"><Cpu size={16} />Speech engine</span>}>
            <dl className="text-[14px] space-y-1.5">
              <Row k="Engine" v={sys.asr.engine || 'Not installed'} /><Row k="Model" v={`whisper-${sys.asr.model} · ${sys.asr.compute_type} · ${sys.asr.device}`} />
              <Row k="Status" v={sys.asr.available ? (sys.asr.loaded ? 'Loaded in memory' : 'Ready, loads on first use') : 'pip install faster-whisper'} />
            </dl>
            {sys.asr.available && !sys.asr.loaded && <button className="btn-sec mt-3" disabled={busy === 'warm'} onClick={() => act('warm', api.asrWarmup, r => `Model loaded in ${r.seconds}s`)}>{busy === 'warm' ? <Loader2 size={15} className="animate-spin" /> : <Cpu size={15} />}Load model now</button>}
          </Panel>
          <Panel className="col-span-12 md:col-span-4" title={<span className="flex items-center gap-2"><KeyRound size={16} />Device signing key</span>}>
            <dl className="text-[14px] space-y-1.5"><Row k="Algorithm" v={sys.device_key.algorithm} /><Row k="Key id" v={sys.device_key.key_id} /></dl>
            <div className="font-mono text-[11px] text-dim break-all mt-2 bg-black border border-line rounded p-2">{sys.device_key.public_key}</div>
            <p className="text-[12px] text-faint mt-2">The private key never leaves this device. The ED verifies blocks with this public key.</p>
          </Panel>
          <Panel className="col-span-12 md:col-span-4" title={<span className="flex items-center gap-2"><Database size={16} />Local store</span>}>
            <div className="grid grid-cols-3 gap-2">{Object.entries(sys.counts).map(([k, v]: any) => <div key={k} className="rounded border border-line bg-black px-2 py-1.5"><div className="num text-[22px] font-semibold leading-none">{v}</div><div className="text-[12px] text-dim">{k}</div></div>)}</div>
            <p className="text-[12px] text-faint mt-2">{sys.privacy}</p>
            <button className="btn-ghost mt-2 text-warn" disabled={busy === 'seed'} onClick={() => { if (confirm('Delete all local data and reload the demo incidents?')) act('seed', api.reseed, () => 'Demo data reloaded') }}><RotateCcw size={15} />Reset demo data</button>
          </Panel>
        </div>
      )}
    </div>
  )
}

function Step({ n, t, d, children }: any) {
  return (
    <li className="flex gap-3">
      <span className="num text-[22px] font-semibold text-faint w-5">{n}</span>
      <div className="flex-1"><div className="font-medium">{t}</div><div className="text-dim text-[13px] mb-2">{d}</div>{children}</div>
    </li>
  )
}
function Row({ k, v }: { k: string; v: any }) {
  return <div className="grid grid-cols-[90px_1fr]"><dt className="text-dim">{k}</dt><dd>{v}</dd></div>
}
