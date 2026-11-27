import { ReactNode, createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { Lock, Delete, ShieldCheck, UserRound, Stethoscope, KeyRound, Loader2 } from 'lucide-react'
import clsx from 'clsx'
import { api } from '../lib/api'

type User = { id: string; name: string; role: 'emt' | 'ed' | 'admin'; rights: string[] }
const Ctx = createContext<{ user: User | null; can: (r: string) => boolean; lock: () => void; logout: () => void; authOn: boolean }>({
  user: null, can: () => true, lock: () => {}, logout: () => {}, authOn: false,
})
export const useAuth = () => useContext(Ctx)

const IDLE_MS = 5 * 60 * 1000
const ROLE_LABEL: Record<string, string> = { emt: 'Ambulance crew', ed: 'Emergency department', admin: 'Supervisor' }

export function AuthGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<'loading' | 'login' | 'ok'>('loading')
  const [user, setUser] = useState<User | null>(null)
  const [authOn, setAuthOn] = useState(true)
  const [locked, setLocked] = useState(false)
  const last = useRef(Date.now())

  const check = useCallback(async () => {
    try {
      const r: any = await api.me()
      setAuthOn(r.enabled)
      if (!r.user) { setState('login'); return }
      setUser(r.user); setState('ok')
    } catch { setState('login') }
  }, [])
  useEffect(() => { check() }, [check])
  useEffect(() => {
    const h = () => { setUser(null); setState('login') }
    window.addEventListener('fs:auth', h)
    return () => window.removeEventListener('fs:auth', h)
  }, [])
  // idle auto-lock
  useEffect(() => {
    if (state !== 'ok' || !authOn) return
    const bump = () => { last.current = Date.now() }
    const evs = ['mousemove', 'keydown', 'pointerdown', 'touchstart', 'wheel']
    evs.forEach(e => window.addEventListener(e, bump, { passive: true }))
    const t = setInterval(() => { if (Date.now() - last.current > IDLE_MS) setLocked(true) }, 5000)
    return () => { evs.forEach(e => window.removeEventListener(e, bump)); clearInterval(t) }
  }, [state, authOn])

  const logout = async () => { try { await api.logout() } catch { /* noop */ } setUser(null); setLocked(false); setState('login') }
  const can = (r: string) => !authOn || !!user?.rights.includes(r)

  if (state === 'loading') return <div className="h-full flex items-center justify-center"><Loader2 className="animate-spin text-dim" /></div>
  if (state === 'login') return <Login onDone={(u) => { setUser(u); setState('ok'); last.current = Date.now() }} />
  return (
    <Ctx.Provider value={{ user, can, lock: () => setLocked(true), logout, authOn }}>
      {children}
      {locked && user && <LockScreen user={user} onUnlock={() => { setLocked(false); last.current = Date.now() }} onSwitch={logout} />}
    </Ctx.Provider>
  )
}

function Login({ onDone }: { onDone: (u: User) => void }) {
  const [users, setUsers] = useState<User[]>([])
  const [demo, setDemo] = useState(false)
  const [sel, setSel] = useState<User | null>(null)
  useEffect(() => { api.authUsers().then((r: any) => { setUsers(r.users); setDemo(!!r.demo_pins) }).catch(() => {}) }, [])
  const groups = ['emt', 'ed', 'admin'].map(r => [r, users.filter(u => u.role === r)] as const)
  return (
    <div className="min-h-full flex items-center justify-center p-6 grid-bg">
      <div className="w-full max-w-4xl grid md:grid-cols-[1fr_340px] gap-6 items-start">
        <div>
          <div className="flex items-center gap-3 mb-6">
            <svg viewBox="0 0 32 32" className="w-11 h-11"><rect width="32" height="32" rx="7" fill="#06080a" stroke="#182027" /><path d="M3 18h7l3-8 4 14 3-9 2 3h7" fill="none" stroke="#3ee07f" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" /></svg>
            <div><div className="font-num text-[34px] font-semibold leading-none">FieldScribe</div><div className="text-dim">Sign in to this device</div></div>
          </div>
          {groups.map(([role, list]) => list.length > 0 && (
            <div key={role} className="mb-4">
              <div className="text-[13px] text-dim mb-2">{ROLE_LABEL[role]}</div>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                {list.map(u => (
                  <button key={u.id} onClick={() => setSel(u)}
                    className={clsx('panel px-3 py-2.5 text-left flex items-center gap-2.5 transition-colors', sel?.id === u.id ? 'border-hr/70 bg-hr/[.06]' : 'hover:border-line2')}>
                    {role === 'ed' ? <Stethoscope size={16} className="text-spo2" /> : role === 'admin' ? <KeyRound size={16} className="text-co2" /> : <UserRound size={16} className="text-hr" />}
                    <span className="text-[14px] truncate">{u.name}</span>
                  </button>
                ))}
              </div>
            </div>
          ))}
          {demo && <p className="text-[12px] text-faint mt-4">Demo PINs: crew 1080 · ED 2020 · supervisor 9090. Change them in Settings before real use.</p>}
        </div>
        <div className="panel p-5">
          {sel ? <PinPad title={sel.name} sub={ROLE_LABEL[sel.role]} onSubmit={async pin => { const r: any = await api.login(sel.id, pin); onDone(r.user) }} />
            : <div className="h-[380px] flex flex-col items-center justify-center text-center text-dim"><ShieldCheck size={36} className="text-faint mb-3" />Choose your name to sign in.<br />Every record you sign carries your name.</div>}
        </div>
      </div>
    </div>
  )
}

function PinPad({ title, sub, onSubmit }: { title: string; sub: string; onSubmit: (pin: string) => Promise<void> }) {
  const [pin, setPin] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const go = async (p = pin) => {
    if (p.length < 4 || busy) return
    setBusy(true); setErr('')
    try { await onSubmit(p) } catch (e: any) { setErr(e.message); setPin('') } finally { setBusy(false) }
  }
  const press = (d: string) => { if (busy) return; const p = (pin + d).slice(0, 8); setPin(p); if (p.length === 4) setTimeout(() => go(p), 80) }
  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if (/^\d$/.test(e.key)) press(e.key)
      else if (e.key === 'Backspace') setPin(p => p.slice(0, -1))
      else if (e.key === 'Enter') go()
    }
    window.addEventListener('keydown', k); return () => window.removeEventListener('keydown', k)
  })
  return (
    <div>
      <div className="text-center">
        <div className="font-medium">{title}</div>
        <div className="text-[13px] text-dim">{sub}</div>
        <motion.div key={err} animate={err ? { x: [0, -8, 8, -5, 5, 0] } : {}} className="flex justify-center gap-3 my-5">
          {[0, 1, 2, 3].map(i => <span key={i} className={clsx('w-3.5 h-3.5 rounded-full border', i < pin.length ? 'bg-hr border-hr' : 'border-line2')} />)}
        </motion.div>
        <div className={clsx('text-[13px] h-5', err ? 'text-alarm' : 'text-faint')}>{busy ? 'Checking…' : err || 'Enter your 4-digit PIN'}</div>
      </div>
      <div className="grid grid-cols-3 gap-2 mt-3">
        {['1', '2', '3', '4', '5', '6', '7', '8', '9'].map(d => <Key key={d} onClick={() => press(d)}>{d}</Key>)}
        <span />
        <Key onClick={() => press('0')}>0</Key>
        <Key onClick={() => setPin(p => p.slice(0, -1))} label="Delete"><Delete size={20} /></Key>
      </div>
    </div>
  )
}

function Key({ children, onClick, label }: any) {
  return <button aria-label={label} onClick={onClick} className="h-14 rounded-lg bg-black border border-line hover:border-line2 active:bg-raise num text-[26px] font-semibold flex items-center justify-center">{children}</button>
}

function LockScreen({ user, onUnlock, onSwitch }: { user: User; onUnlock: () => void; onSwitch: () => void }) {
  return (
    <div className="fixed inset-0 z-[80] bg-black/95 backdrop-blur flex items-center justify-center p-6">
      <div className="panel p-6 w-full max-w-[360px]">
        <div className="flex items-center justify-center gap-2 text-warn mb-1"><Lock size={16} />Locked after 5 minutes idle</div>
        <PinPad title={user.name} sub="Enter your PIN to continue" onSubmit={async pin => { await api.login(user.id, pin); onUnlock() }} />
        <button className="btn-ghost w-full justify-center mt-3" onClick={onSwitch}>Switch user</button>
      </div>
    </div>
  )
}
