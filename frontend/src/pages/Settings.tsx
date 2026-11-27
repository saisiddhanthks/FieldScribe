import { useEffect, useState } from 'react'
import { Cpu, Play, Brain, CloudOff, CheckCircle2, AlertTriangle, XCircle, Copy, RefreshCw, UserPlus, KeyRound, Power, Volume2, Download, Keyboard, Compass, MonitorSmartphone, ShieldCheck } from 'lucide-react'
import clsx from 'clsx'
import { api } from '../lib/api'
import { Panel, Modal, Spinner, useFetch, useToast } from '../components/ui'
import { useAuth } from '../components/Auth'
import { canInstall, installApp, useCommandUI } from '../components/Command'
import { readbackOn, setReadback, speak } from '../lib/speech'
import { ASR_LANGS, asrLang, setAsrLang } from '../lib/lang'

const ROLE: Record<string, string> = { emt: 'Ambulance crew', ed: 'Emergency dept', admin: 'Supervisor' }
const RIGHT: Record<string, string> = {
  read: 'View records', capture: 'Capture care', sign: 'Sign records', amend: 'Amend and void entries', copilot: 'Copilot can log care',
  copilot_read: 'Ask Copilot', sync: 'Sync to hub', handover: 'Accept handovers', admin: 'Manage users and drills',
}

export default function Settings() {
  const { user, can, authOn } = useAuth()
  const tabs = [
    { k: 'account', label: 'My account', show: authOn },
    { k: 'users', label: 'Users', show: authOn && can('admin') },
    { k: 'ai', label: 'Offline AI', show: true },
    { k: 'ready', label: 'Readiness check', show: true },
    { k: 'prefs', label: 'Preferences & app', show: true },
  ].filter(t => t.show)
  const [tab, setTab] = useState(() => (typeof location !== 'undefined' && location.hash.slice(1)) || tabs[0].k)
  useEffect(() => { history.replaceState(null, '', `#${tab}`) }, [tab])
  const cur = tabs.find(t => t.k === tab) ? tab : tabs[0].k
  return (
    <div className="max-w-[1100px] space-y-4">
      <div>
        <h1 className="font-num text-[34px] font-semibold leading-none">Settings</h1>
        <p className="text-dim mt-1.5">Your PIN, the people who can sign in, whether this device is ready, and how the app behaves.</p>
      </div>
      <div role="tablist" className="flex gap-1 border-b border-line overflow-x-auto">
        {tabs.map(t => (
          <button key={t.k} role="tab" aria-selected={cur === t.k} onClick={() => setTab(t.k)}
            className={clsx('h-10 px-4 text-[15px] -mb-px border-b-2 transition-colors whitespace-nowrap shrink-0', cur === t.k ? 'border-hr text-ink' : 'border-transparent text-dim hover:text-ink')}>
            {t.label}
          </button>
        ))}
      </div>
      {cur === 'account' && user && <Account user={user} />}
      {cur === 'users' && <Users me={user?.id} />}
      {cur === 'ai' && <OfflineAI />}
      {cur === 'ready' && <Readiness />}
      {cur === 'prefs' && <Prefs />}
    </div>
  )
}

function PinField({ label, value, onChange, auto }: { label: string; value: string; onChange: (v: string) => void; auto?: boolean }) {
  return (
    <label className="block">
      <span className="text-[13px] text-dim">{label}</span>
      <input className="input mt-1 h-10 text-[18px] tracking-[0.4em] font-mono" type="password" inputMode="numeric" autoComplete="off" maxLength={8}
        autoFocus={auto} value={value} onChange={e => onChange(e.target.value.replace(/\D/g, ''))} />
    </label>
  )
}

function Account({ user }: { user: any }) {
  const toast = useToast()
  const [old, setOld] = useState(''); const [pin, setPin] = useState(''); const [pin2, setPin2] = useState('')
  const [busy, setBusy] = useState(false); const [err, setErr] = useState('')
  const mismatch = pin2.length >= pin.length && pin2 !== pin && pin2.length > 0
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setErr('')
    if (pin !== pin2) { setErr('The new PINs don’t match'); return }
    setBusy(true)
    try { await api.changePin(old, pin); toast('ok', 'PIN changed. Use it next time you sign in.'); setOld(''); setPin(''); setPin2('') }
    catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }
  return (
    <div className="grid lg:grid-cols-2 gap-4">
      <Panel title={user.name} sub={`${ROLE[user.role]} · ID ${user.id}`}>
        <p className="text-[14px] text-dim mb-2">What this account can do on this device:</p>
        <ul className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1.5">
          {user.rights.map((r: string) => <li key={r} className="flex items-center gap-2 text-[14px]"><CheckCircle2 size={15} className="text-hr" />{RIGHT[r] || r}</li>)}
        </ul>
        <p className="text-[13px] text-faint mt-4">Everything you sign, amend or accept carries this name in the audit ledger.</p>
      </Panel>
      <Panel title="Change PIN" sub="4 to 8 digits. Avoid birthdays and repeated digits.">
        <form onSubmit={submit} className="space-y-3 max-w-[340px]">
          <PinField label="Current PIN" value={old} onChange={setOld} />
          <PinField label="New PIN" value={pin} onChange={setPin} />
          <PinField label="New PIN again" value={pin2} onChange={setPin2} />
          {(err || mismatch) && <p className="text-[13px] text-alarm" role="alert">{err || 'The new PINs don’t match yet'}</p>}
          <button className="btn-pri h-10" disabled={busy || old.length < 4 || pin.length < 4 || pin !== pin2}>{busy ? <Spinner /> : <KeyRound size={15} />}Change PIN</button>
        </form>
      </Panel>
    </div>
  )
}

function ago(t?: number) {
  if (!t) return 'Never'
  const s = Date.now() / 1000 - t
  return s < 60 ? 'Just now' : s < 3600 ? `${Math.round(s / 60)} min ago` : s < 86400 ? `${Math.round(s / 3600)} h ago` : `${Math.round(s / 86400)} d ago`
}

function Users({ me }: { me?: string }) {
  const toast = useToast()
  const { data, reload, loading } = useFetch(() => api.adminUsers(), [])
  const [add, setAdd] = useState(false)
  const [reset, setReset] = useState<any>(null)
  const demo = (data || []).filter((u: any) => u.active && u.pin_default).length
  const toggle = async (u: any) => {
    try { await api.adminPatch(u.id, { active: !u.active }); toast('ok', `${u.name} ${u.active ? 'disabled' : 'enabled'}`); reload() } catch (e: any) { toast('err', e.message) }
  }
  return (
    <>
      {demo > 0 && (
        <div className="flex items-start gap-3 rounded-lg border border-warn/40 bg-warn/10 px-4 py-3 text-[14px]">
          <AlertTriangle size={18} className="text-warn shrink-0 mt-0.5" />
          <div><b className="text-warn">{demo} account{demo > 1 ? 's' : ''} still use{demo === 1 ? 's' : ''} a demo PIN.</b> <span className="text-dim">Anyone who has seen the demo can sign in as them. Use Reset PIN to give each one its own.</span></div>
        </div>
      )}
      <Panel title="People on this device" sub="Disabled accounts can’t sign in. Their past signatures stay in the ledger."
        actions={<button className="btn-pri h-9" onClick={() => setAdd(true)}><UserPlus size={15} />Add user</button>} bodyClass="px-0">
        {loading && !data ? <div className="p-6"><Spinner /></div> : (
          <div className="overflow-x-auto">
            <table className="w-full text-[14px]">
              <thead><tr className="text-left text-[12.5px] text-faint border-b border-line">
                <th className="font-normal px-4 h-9">Name</th><th className="font-normal">Role</th><th className="font-normal">PIN</th><th className="font-normal">Last active</th><th className="font-normal px-4 text-right">Actions</th>
              </tr></thead>
              <tbody>
                {(data || []).map((u: any) => (
                  <tr key={u.id} className={clsx('border-b border-line/70 h-12', !u.active && 'opacity-50')}>
                    <td className="px-4"><div className="flex items-center gap-2">
                      <span className={clsx('w-2 h-2 rounded-full', u.online ? 'bg-hr' : 'bg-line2')} title={u.online ? 'Signed in' : 'Not signed in'} />
                      <span className="font-medium">{u.name}</span><span className="text-faint font-mono text-[12px]">{u.id}</span>
                      {u.id === me && <span className="chip bg-raise text-dim">You</span>}
                    </div></td>
                    <td className="text-dim">{ROLE[u.role]}</td>
                    <td>{u.pin_default ? <span className="chip text-warn bg-warn/10">Demo PIN</span> : <span className="chip text-hr bg-hr/10">Own PIN</span>}{u.locked && <span className="chip text-alarm bg-alarm/10 ml-1">Locked</span>}</td>
                    <td className="text-dim">{u.active ? ago(u.last_seen) : 'Disabled'}</td>
                    <td className="px-4"><div className="flex justify-end gap-1.5">
                      <button className="btn-sec h-8" onClick={() => setReset(u)}><KeyRound size={14} />Reset PIN</button>
                      {u.id !== me && <button className={clsx('h-8', u.active ? 'btn-danger' : 'btn-sec')} onClick={() => toggle(u)}><Power size={14} />{u.active ? 'Disable' : 'Enable'}</button>}
                    </div></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
      <AddUser open={add} onClose={() => setAdd(false)} onDone={() => { setAdd(false); reload() }} />
      <ResetPin u={reset} onClose={() => setReset(null)} onDone={() => { setReset(null); reload() }} />
    </>
  )
}

function AddUser({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone: () => void }) {
  const toast = useToast()
  const [f, setF] = useState({ id: '', name: '', role: 'emt', pin: '' })
  const [err, setErr] = useState(''); const [busy, setBusy] = useState(false)
  useEffect(() => { if (open) { setF({ id: '', name: '', role: 'emt', pin: '' }); setErr('') } }, [open])
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setBusy(true); setErr('')
    try { await api.adminCreate(f); toast('ok', `${f.name} can now sign in`); onDone() } catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }
  return (
    <Modal open={open} onClose={onClose} title="Add user">
      <form onSubmit={submit} className="space-y-3">
        <div className="grid grid-cols-3 gap-1 p-1 rounded-lg bg-raise border border-line2" role="radiogroup" aria-label="Role">
          {Object.entries(ROLE).map(([k, v]) => (
            <button type="button" key={k} role="radio" aria-checked={f.role === k} onClick={() => setF({ ...f, role: k })}
              className={clsx('h-9 rounded-md text-[14px]', f.role === k ? 'bg-black text-ink border border-line2' : 'text-dim')}>{v}</button>
          ))}
        </div>
        <label className="block"><span className="text-[13px] text-dim">Full name as it should appear on records</span>
          <input className="input mt-1 h-10" value={f.name} onChange={e => setF({ ...f, name: e.target.value })} placeholder="EMT-22 K. Shetty" autoFocus /></label>
        <label className="block"><span className="text-[13px] text-dim">User ID</span>
          <input className="input mt-1 h-10 font-mono" value={f.id} onChange={e => setF({ ...f, id: e.target.value.toLowerCase().replace(/[^a-z0-9_.-]/g, '') })} placeholder="emt22" /></label>
        <PinField label="Starting PIN (they can change it later)" value={f.pin} onChange={pin => setF({ ...f, pin })} />
        {err && <p className="text-[13px] text-alarm" role="alert">{err}</p>}
        <div className="flex justify-end gap-2 pt-1">
          <button type="button" className="btn-ghost h-10" onClick={onClose}>Cancel</button>
          <button className="btn-pri h-10" disabled={busy || !f.id || !f.name || f.pin.length < 4}>{busy ? <Spinner /> : <UserPlus size={15} />}Add user</button>
        </div>
      </form>
    </Modal>
  )
}

function ResetPin({ u, onClose, onDone }: { u: any; onClose: () => void; onDone: () => void }) {
  const toast = useToast()
  const [pin, setPin] = useState(''); const [err, setErr] = useState(''); const [busy, setBusy] = useState(false)
  useEffect(() => { setPin(''); setErr('') }, [u?.id])
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setBusy(true); setErr('')
    try { await api.adminPatch(u.id, { pin }); toast('ok', `New PIN set for ${u.name}. They’ve been signed out everywhere.`); onDone() } catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }
  return (
    <Modal open={!!u} onClose={onClose} title={u ? `Reset PIN for ${u.name}` : ''}>
      <form onSubmit={submit} className="space-y-3">
        <PinField label="New PIN" value={pin} onChange={setPin} auto />
        <p className="text-[13px] text-faint">Tell them in person. This also unlocks the account and signs it out of every device.</p>
        {err && <p className="text-[13px] text-alarm" role="alert">{err}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" className="btn-ghost h-10" onClick={onClose}>Cancel</button>
          <button className="btn-pri h-10" disabled={busy || pin.length < 4}>{busy ? <Spinner /> : <KeyRound size={15} />}Set PIN</button>
        </div>
      </form>
    </Modal>
  )
}

const ICON = { ok: CheckCircle2, warn: AlertTriangle, fail: XCircle } as const
const TONE = { ok: 'text-hr', warn: 'text-warn', fail: 'text-alarm' } as const

function Readiness() {
  const toast = useToast()
  const { data, loading, reload } = useFetch(() => api.healthChecks(), [])
  const [spin, setSpin] = useState(false)
  const groups: Record<string, any[]> = {}
  for (const i of data?.items || []) (groups[i.group] ||= []).push(i)
  const copy = (t: string) => navigator.clipboard?.writeText(t).then(() => toast('ok', 'Command copied. Paste it in PowerShell in the fieldscribe folder.'))
  const pct = data ? Math.round((data.ok / data.total) * 100) : 0
  return (
    <div className="space-y-4">
      <Panel>
        <div className="flex items-center gap-5 pt-4">
          <div className="relative w-[84px] h-[84px] shrink-0">
            <svg viewBox="0 0 36 36" className="w-full h-full -rotate-90">
              <circle cx="18" cy="18" r="15.5" fill="none" stroke="#182027" strokeWidth="3" />
              <circle cx="18" cy="18" r="15.5" fill="none" stroke={data?.ready ? '#3ee07f' : '#ffa733'} strokeWidth="3" strokeLinecap="round"
                strokeDasharray={`${pct * 0.974} 100`} style={{ transition: 'stroke-dasharray .6s' }} />
            </svg>
            <div className="absolute inset-0 flex items-center justify-center num text-[24px] font-semibold">{data ? `${data.ok}/${data.total}` : '–'}</div>
          </div>
          <div className="min-w-0">
            <h2 className="font-num text-[26px] font-semibold leading-tight">{!data ? 'Checking this device…' : data.ready ? (data.ok === data.total ? 'Everything is ready' : 'Ready for the road') : 'Something needs fixing'}</h2>
            <p className="text-[14px] text-dim">{data && (data.ready ? 'Nothing is broken. Amber items are optional upgrades or security steps.' : 'Fix the red items before using this device on a call.')}</p>
          </div>
          <button className="btn-sec h-9 ml-auto" onClick={async () => { setSpin(true); await reload(); setSpin(false) }}>
            <RefreshCw size={15} className={clsx((spin || loading) && 'animate-spin')} />Check again
          </button>
        </div>
      </Panel>
      {Object.entries(groups).map(([g, items]) => (
        <Panel key={g} title={g} bodyClass="px-0 pb-1">
          {items.map(i => {
            const I = ICON[i.status as keyof typeof ICON]
            return (
              <div key={i.key} className="flex items-start gap-3 px-4 py-3 border-t border-line/70 first:border-t-0">
                <I size={19} className={clsx('shrink-0 mt-0.5', TONE[i.status as keyof typeof TONE])} />
                <div className="min-w-0 flex-1">
                  <div className="text-[15px] font-medium">{i.label}</div>
                  <div className="text-[13.5px] text-dim">{i.detail}</div>
                  {i.fix && i.status !== 'ok' && (/pip |python |npm |ollama |winget |\.bat|^cd /.test(i.fix) ? (
                    <div className="mt-2 flex items-center gap-2 rounded-md border border-line2 bg-black px-3 py-2">
                      <code className="text-[12.5px] font-mono text-ink break-all flex-1">{i.fix}</code>
                      <button className="btn-ghost h-7 px-2 shrink-0" onClick={() => copy(i.fix)} aria-label="Copy command"><Copy size={14} /></button>
                    </div>
                  ) : <div className="mt-1 text-[13.5px] text-ink"><span className="text-faint">Fix: </span>{i.fix}</div>)}
                </div>
              </div>
            )
          })}
        </Panel>
      ))}
    </div>
  )
}

function Prefs() {
  const ui = useCommandUI()
  const [rb, setRb] = useState(readbackOn())
  const [lang, setLang] = useState(asrLang())
  const [installable, setInstallable] = useState(canInstall())
  const standalone = typeof window !== 'undefined' && window.matchMedia?.('(display-mode: standalone)').matches
  useEffect(() => {
    const h = () => { setRb(readbackOn()); setInstallable(canInstall()) }
    window.addEventListener('fs:readback', h); window.addEventListener('fs:installable', h)
    return () => { window.removeEventListener('fs:readback', h); window.removeEventListener('fs:installable', h) }
  }, [])
  const host = typeof location !== 'undefined' ? location.host : ''
  return (
    <div className="grid lg:grid-cols-2 gap-4">
      <Panel title="Spoken read-back" sub="Before signing, the record is read aloud and you say “confirm”.">
        <div className="flex items-center gap-3">
          <button role="switch" aria-checked={rb} onClick={() => { const v = !rb; setReadback(v); setRb(v); if (v) speak('Read back on', true) }}
            className={clsx('relative w-12 h-7 rounded-full transition-colors', rb ? 'bg-hr' : 'bg-line2')}>
            <span className={clsx('absolute top-1 w-5 h-5 rounded-full bg-black transition-all', rb ? 'left-6' : 'left-1')} />
          </button>
          <span className="text-[15px]">{rb ? 'On' : 'Off'}</span>
          <button className="btn-sec h-9 ml-auto" onClick={() => speak('Aspirin, 300 milligrams, oral, at 10 42. Say confirm to sign.', true)}><Volume2 size={15} />Test voice</button>
        </div>
        <p className="text-[13px] text-faint mt-3">Uses the voices built into Windows, so it works offline. An Indian English voice is used when one is installed (Windows Settings → Time & language → Speech).</p>
      </Panel>
      <Panel title="Dictation language" sub="What the on-device Whisper listens for. Drug names and numbers can stay in English.">
        <div className="grid grid-cols-2 gap-1.5" role="radiogroup" aria-label="Dictation language">
          {ASR_LANGS.map(o => (
            <button key={o.k} role="radio" aria-checked={lang === o.k} onClick={() => { setAsrLang(o.k); setLang(o.k) }}
              className={clsx('rounded-md border px-3 py-2 text-left', lang === o.k ? 'border-hr/60 bg-hr/[.06]' : 'border-line2 hover:border-faint')}>
              <div className="text-[15px]">{o.label}</div><div className="text-[12.5px] text-dim">{o.hint}</div>
            </button>
          ))}
        </div>
        <p className="text-[13px] text-faint mt-3">Hindi and Kannada are read on the device, in either script or typed in English letters, and mapped to clinical English before extraction. Accuracy is measured in Model lab.</p>
      </Panel>
      <Panel title="Install as an app" sub="Own window, desktop icon, opens without the browser bar.">
        {standalone ? <p className="text-[14px] text-hr flex items-center gap-2"><CheckCircle2 size={16} />You’re using the installed app.</p>
          : installable ? <button className="btn-pri h-10" onClick={installApp}><Download size={15} />Install FieldScribe</button>
            : <p className="text-[14px] text-dim">In Chrome or Edge, click the install icon at the right of the address bar, or open the browser menu → <b className="text-ink">Install FieldScribe</b>.</p>}
        <p className="text-[13px] text-faint mt-3">The installed app keeps its screens on the device, so it opens even with no network. Records still live in the local backend.</p>
      </Panel>
      <Panel title="Work faster" sub="Search everything and move without the mouse.">
        <div className="flex flex-wrap gap-2">
          <button className="btn-sec h-10" onClick={ui.openPalette}><span className="kbd">Ctrl K</span>Command bar</button>
          <button className="btn-sec h-10" onClick={ui.openHelp}><Keyboard size={15} />All shortcuts</button>
          <button className="btn-sec h-10" onClick={ui.openTour}><Compass size={15} />Take the tour</button>
        </div>
      </Panel>
      <PhonePanel />
    </div>
  )
}

function OfflineAI() {
  const toast = useToast()
  const { can } = useAuth()
  const { data: st, reload } = useFetch(() => api.localai(), [])
  const [prog, setProg] = useState<any>(null)
  const [test, setTest] = useState<any>(null)
  const [testing, setTesting] = useState(false)
  const pulling = prog && !['idle', 'success', 'error'].includes(prog.status)
  useEffect(() => { if (st?.pull && !['idle'].includes(st.pull.status)) setProg(st.pull) }, [st])
  useEffect(() => {
    if (!pulling) return
    const t = setInterval(async () => {
      const p: any = await api.localaiProgress(); setProg(p)
      if (p.status === 'success') { toast('ok', `${p.model} is on this laptop. Copilot now works with no internet.`); reload() }
      if (p.status === 'error') toast('err', p.error)
    }, 700)
    return () => clearInterval(t)
  }, [pulling])
  if (!st) return <div className="py-16 flex justify-center"><Spinner /></div>
  const have = new Set(st.models.map((m: any) => m.name))
  const pull = async (m: string) => { try { setProg(await api.localaiPull(m)) } catch (e: any) { toast('err', e.message) } }
  const start = async () => { const r: any = await api.localaiStart(); r.ok ? toast('ok', 'Local AI started') : toast('err', r.error); reload() }
  const runTest = async () => { setTesting(true); setTest(null); try { setTest(await api.localaiTest()) } finally { setTesting(false) } }
  const state = st.model ? 'ready' : st.running ? 'nomodel' : st.installed ? 'stopped' : 'missing'
  return (
    <div className="space-y-4">
      <Panel>
        <div className="flex flex-wrap items-center gap-4 pt-4">
          <div className={clsx('w-14 h-14 rounded-xl flex items-center justify-center shrink-0', state === 'ready' ? 'bg-hr/15 text-hr' : 'bg-warn/15 text-warn')}><Brain size={28} /></div>
          <div className="min-w-0 flex-1">
            <h2 className="font-num text-[26px] font-semibold leading-tight">
              {state === 'ready' ? 'Copilot works with no internet' : state === 'nomodel' ? 'Download a model to finish' : state === 'stopped' ? 'Local AI is installed but stopped' : 'Local AI is not installed'}
            </h2>
            <p className="text-[14px] text-dim">
              {state === 'ready' ? <>Using <b className="text-ink">{st.model}</b> on this laptop. In a dead zone, Copilot switches to it automatically and still gives first-aid steps and logs care.</>
                : state === 'missing' ? <>Install Ollama, the free engine that runs AI models on this laptop. The FieldScribe installer does this for you, or run the command below.</>
                  : state === 'stopped' ? 'Start it here. FieldScribe also starts it automatically when it opens.'
                    : <>Pick a model below. It downloads once ({st.recommended.size_gb} GB for the recommended one) and then needs no internet.</>}
            </p>
          </div>
          {state === 'stopped' && can('admin') && <button className="btn-pri h-10" onClick={start}><Play size={15} />Start local AI</button>}
          {state === 'ready' && <button className="btn-sec h-10" onClick={runTest} disabled={testing}>{testing ? <Spinner /> : <Play size={15} />}Test it</button>}
        </div>
        {state === 'missing' && (
          <div className="mt-3 flex items-center gap-2 rounded-md border border-line2 bg-black px-3 py-2">
            <code className="text-[13px] font-mono flex-1">winget install Ollama.Ollama</code>
            <button className="btn-ghost h-7 px-2" onClick={() => navigator.clipboard?.writeText('winget install Ollama.Ollama').then(() => toast('ok', 'Copied. Paste it in PowerShell, then come back and press Check again.'))}><Copy size={14} /></button>
          </div>
        )}
        {test && (
          <div className={clsx('mt-3 rounded-md border px-3 py-2 text-[14px]', test.ok ? 'border-hr/40 bg-hr/[.05]' : 'border-alarm/40 bg-alarm/[.05]')}>
            {test.ok ? <><span className="text-dim">{test.model} answered in {test.seconds} s, offline:</span> {test.reply}</> : <span className="text-alarm">{test.error}</span>}
          </div>
        )}
        <div className="flex flex-wrap items-center gap-x-5 gap-y-1 mt-4 text-[13px] text-dim">
          <span className="flex items-center gap-1.5"><Cpu size={14} />{st.ram_gb} GB memory</span>
          <span>Engine: {st.running ? <span className="text-hr">running</span> : st.installed ? 'installed, stopped' : 'not installed'}</span>
          <button className="btn-ghost h-7 px-2 ml-auto" onClick={reload}><RefreshCw size={13} />Check again</button>
        </div>
      </Panel>

      <Panel title="Models" sub="Qwen 2.5: understands English and Hindi, and can call FieldScribe’s tools to look up protocols and log care">
        <div className="grid md:grid-cols-3 gap-3">
          {st.catalog.map((m: any) => {
            const rec = m.name === st.recommended.name, got = have.has(m.name), active = st.model === m.name
            const mine = prog?.model === m.name
            const tooBig = st.ram_gb < m.min_ram_gb
            return (
              <div key={m.name} className={clsx('rounded-lg border p-4 flex flex-col', active ? 'border-hr/60 bg-hr/[.05]' : rec ? 'border-spo2/40' : 'border-line')}>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-num text-[20px] font-semibold">{m.label}</span>
                  {rec && <span className="chip bg-spo2/10 text-spo2">Best for this laptop</span>}
                  {active && <span className="chip bg-hr/15 text-hr">In use</span>}
                </div>
                <div className="text-[13.5px] text-dim mt-1 flex-1">{m.note}</div>
                <div className="text-[12.5px] text-faint mt-2">{m.size_gb} GB download · needs about {Math.max(m.min_ram_gb, 4)} GB memory</div>
                {mine && pulling && (
                  <div className="mt-3">
                    <div className="h-2 rounded-full bg-line2 overflow-hidden"><div className="h-full bg-hr transition-all" style={{ width: `${prog.percent ?? 2}%` }} /></div>
                    <div className="text-[12.5px] text-dim mt-1 num">{prog.percent != null ? `${prog.percent}% · ${(prog.completed / 1e9).toFixed(2)} of ${(prog.total / 1e9).toFixed(2)} GB` : prog.status}</div>
                  </div>
                )}
                {mine && prog?.status === 'error' && <p className="text-[13px] text-alarm mt-2">{prog.error}</p>}
                <div className="mt-3">
                  {got ? <span className="text-[14px] text-hr flex items-center gap-1.5"><CheckCircle2 size={15} />On this laptop</span>
                    : can('admin') ? <button className="btn-sec h-9 w-full" disabled={!st.running || pulling} onClick={() => pull(m.name)}><Download size={15} />{tooBig ? 'Download anyway (may be slow)' : 'Download'}</button>
                      : <span className="text-[13px] text-faint">A supervisor can download it</span>}
                </div>
              </div>
            )
          })}
        </div>
      </Panel>

      <Panel title="When to use the local AI" sub="Cloud AI (Gemini) gives the best answers when there is signal">
        <div className="flex items-start gap-3">
          <button role="switch" aria-checked={st.prefer_offline} disabled={!can('admin')}
            onClick={async () => { await api.localaiPrefer(!st.prefer_offline); reload() }}
            className={clsx('relative w-12 h-7 rounded-full transition-colors shrink-0 mt-0.5', st.prefer_offline ? 'bg-hr' : 'bg-line2')}>
            <span className={clsx('absolute top-1 w-5 h-5 rounded-full bg-black transition-all', st.prefer_offline ? 'left-6' : 'left-1')} />
          </button>
          <div className="text-[14px]">
            <div className="font-medium">Always use the local AI, even with internet</div>
            <div className="text-dim">Off: Gemini when online, local AI in dead zones, protocol engine if both are unavailable. On: patient details never leave the laptop for AI.</div>
          </div>
        </div>
        <div className="flex items-center gap-2 mt-4 text-[13px] text-faint"><CloudOff size={14} />Order when offline: local AI → built-in protocol engine. Nothing is logged without the crew’s confirmation.</div>
      </Panel>
    </div>
  )
}

function PhonePanel() {
  const { data: t } = useFetch(() => api.tlsStatus(), [])
  const secure = typeof window !== 'undefined' && window.isSecureContext && location.hostname !== 'localhost' && location.hostname !== '127.0.0.1'
  return (
    <Panel title="Use it on phones and tablets" sub="Phones on the same Wi-Fi or hotspot use this laptop">
      {secure ? (
        <p className="text-[14px] text-hr flex items-center gap-2"><ShieldCheck size={16} />This device is connected securely. Dictation and Add to Home screen work here.</p>
      ) : t?.tablet_mode && t.qr_svg ? (
        <div className="flex gap-4 items-start flex-wrap">
          <div className="w-[148px] h-[148px] rounded-lg bg-white p-1.5 shrink-0 [&_svg]:w-full [&_svg]:h-full" aria-label="QR code for phone set-up" dangerouslySetInnerHTML={{ __html: t.qr_svg }} />
          <div className="text-[14px] min-w-[220px] flex-1">
            <p className="font-medium">Scan with the phone’s camera</p>
            <p className="text-dim mt-1">It opens <span className="font-mono text-ink">{t.setup_url}</span>: download the laptop’s certificate, trust it once, then open FieldScribe securely and add it to the home screen.</p>
            <p className="text-faint text-[12.5px] mt-2">Secure address: <span className="font-mono">{t.https_urls.join(', ')}</span> · fingerprint {t.fingerprint}</p>
          </div>
        </div>
      ) : (
        <div className="flex items-start gap-3 text-[14px] text-dim">
          <MonitorSmartphone size={18} className="text-spo2 shrink-0 mt-0.5" />
          <div>Start <b className="text-ink">FieldScribe (tablet mode)</b> from the Start menu (or <code className="font-mono text-ink">start_tablet_mode.bat</code>). This panel then shows a QR code that phones scan to set up. Phones get the microphone and a home-screen icon over the laptop’s own secure connection.</div>
        </div>
      )}
      <div className="flex items-start gap-2 mt-3 text-[13px] text-faint"><ShieldCheck size={15} className="shrink-0 mt-0.5" />Each person signs in with their own PIN. Use only on the ambulance’s own Wi-Fi or hotspot.</div>
    </Panel>
  )
}
