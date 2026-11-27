import { ReactNode, useEffect, useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { ShieldCheck, Wifi, WifiOff, Menu, X, Lock, LogOut, Volume2, VolumeX, Search, Keyboard } from 'lucide-react'
import { NAV_GROUPS, pageFor } from '../lib/nav'
import { useCommandUI } from './Command'
import { useAuth } from './Auth'
import { ClockBell } from './Clinical'
import { readbackOn, setReadback, speak } from '../lib/speech'
import clsx from 'clsx'
import { api } from '../lib/api'
import { useToast } from './ui'


export function Shell({ children }: { children: ReactNode }) {
  const [clock, setClock] = useState(new Date())
  const [state, setState] = useState<any>(null)
  const [open, setOpen] = useState(false)
  const toast = useToast()
  const loc = useLocation()
  const { user, can, lock, logout, authOn } = useAuth()
  const ui = useCommandUI()
  const page = pageFor(loc.pathname)
  useEffect(() => { document.title = `${page?.label || 'FieldScribe'} · FieldScribe` }, [page?.label])
  const [rb, setRb] = useState(readbackOn())
  useEffect(() => { const h = () => setRb(readbackOn()); window.addEventListener('fs:readback', h); return () => window.removeEventListener('fs:readback', h) }, [])
  useEffect(() => setOpen(false), [loc.pathname])
  useEffect(() => { const t = setInterval(() => setClock(new Date()), 1000); return () => clearInterval(t) }, [])
  const refresh = async () => {
    try {
      const [s, v] = await Promise.all([api.sync(), api.verify()])
      setState({ ...s, chain: v })
    } catch { setState((x: any) => ({ ...(x || {}), down: true })) }
  }
  useEffect(() => {
    refresh()
    const t = setInterval(refresh, 5000)
    const h = () => refresh()
    window.addEventListener('fs:refresh', h)
    return () => { clearInterval(t); window.removeEventListener('fs:refresh', h) }
  }, [])
  const toggle = async () => {
    const next = !state?.online
    const r: any = await api.setOnline(next)
    toast(next ? 'ok' : 'info', next ? `Back online · ${r.sync?.synced_now ?? 0} items synced to ED hub` : 'Offline mode · records stay signed and queued on this device')
    refresh(); window.dispatchEvent(new Event('fs:refresh'))
  }
  const online = state?.online
  return (
    <div className="h-full flex">
      <aside className={clsx('fixed lg:static inset-y-0 left-0 z-40 w-[232px] shrink-0 bg-black border-r border-line flex flex-col transition-transform',
        open ? 'translate-x-0' : '-translate-x-full lg:translate-x-0')}>
        <div className="h-16 flex items-center gap-2.5 px-4 border-b border-line">
          <svg viewBox="0 0 32 32" className="w-8 h-8"><rect width="32" height="32" rx="7" fill="#06080a" stroke="#182027" /><path d="M3 18h7l3-8 4 14 3-9 2 3h7" fill="none" stroke="#3ee07f" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" /></svg>
          <div>
            <div className="font-num text-[22px] font-semibold leading-none tracking-wide">FieldScribe</div>
            <div className="text-[12px] text-dim leading-tight mt-0.5">EMS clinical record</div>
          </div>
          <button className="lg:hidden ml-auto btn-ghost h-8 px-2" onClick={() => setOpen(false)} aria-label="Close menu"><X size={16} /></button>
        </div>
        <div className="px-2.5 pt-2.5">
          <button onClick={ui.openPalette} className="w-full flex items-center gap-2 h-9 px-3 rounded-md border border-line2 bg-raise/60 text-dim hover:text-ink hover:border-faint text-[14px]">
            <Search size={15} className="shrink-0" /><span className="truncate">Search or jump</span><kbd className="kbd ml-auto whitespace-nowrap">Ctrl K</kbd>
          </button>
        </div>
        <nav className="flex-1 p-2.5 overflow-auto" aria-label="Main">
          {NAV_GROUPS.map(g => {
            const items = g.items.filter(n => !n.right || can(n.right))
            if (!items.length) return null
            return (
              <div key={g.title} className="mb-3">
                <div className="px-3 pb-1 text-[12px] text-faint">{g.title}</div>
                <div className="space-y-0.5">
                  {items.map(n => (
                    <NavLink key={n.to} to={n.to} end={n.end} title={`${n.hint}  (G then ${n.key.toUpperCase()})`}
                      className={({ isActive }) => clsx('group flex items-center gap-3 rounded-md px-3 h-10 text-[15px] transition-colors',
                        isActive ? 'bg-raise text-ink shadow-[inset_2px_0_0_#3ee07f]' : 'text-dim hover:text-ink hover:bg-raise/60')}>
                      <n.icon size={17} strokeWidth={1.9} />{n.label}
                      <kbd className="kbd ml-auto opacity-0 group-hover:opacity-100 transition-opacity">{n.key.toUpperCase()}</kbd>
                    </NavLink>
                  ))}
                </div>
              </div>
            )
          })}
        </nav>
        <div className="p-3 border-t border-line text-[12px] text-faint leading-relaxed">
          Team RCB · Virtusa hackathon<br />Synthetic data only · no real PHI
        </div>
      </aside>
      {open && <div className="fixed inset-0 z-30 bg-black/60 lg:hidden" onClick={() => setOpen(false)} />}
      <div className="flex-1 min-w-0 flex flex-col">
        <header className="h-16 shrink-0 min-w-0 border-b border-line bg-black/90 backdrop-blur flex items-center gap-3 px-4 lg:px-6 sticky top-0 z-20">
          <button className="lg:hidden btn-ghost h-9 px-2" onClick={() => setOpen(true)} aria-label="Open menu"><Menu size={18} /></button>
          <nav aria-label="Breadcrumb" className="min-w-0 flex items-center gap-2 text-[14px] whitespace-nowrap">
            <span className="hidden md:inline text-dim">108 Bengaluru Urban</span>
            <span className="hidden md:inline text-faint">/</span>
            {page && <page.icon size={15} className="text-hr shrink-0" />}
            <span className="hidden sm:inline font-medium truncate">{page?.label}</span>
          </nav>
          <button onClick={ui.openPalette} className="hidden sm:flex lg:hidden btn-ghost h-8 px-2" aria-label="Search"><Search size={16} /></button>
          <div className="ml-auto flex items-center gap-1.5 sm:gap-2.5 min-w-0">
            <button onClick={ui.openHelp} className="hidden xl:flex btn-ghost h-8 px-2" title="Keyboard shortcuts (?)" aria-label="Keyboard shortcuts"><Keyboard size={16} /></button>
            <ClockBell />
            <button className={clsx('chip h-8 px-2.5 border', rb ? 'text-hr border-hr/40 bg-hr/10' : 'text-dim border-line2')}
              title={rb ? 'Spoken read-back on' : 'Spoken read-back off'} aria-label="Toggle spoken read-back"
              onClick={() => { const v = !rb; setReadback(v); if (v) speak('Read back on', true) }}>
              {rb ? <Volume2 size={15} /> : <VolumeX size={15} />}
            </button>
            <button onClick={toggle} className={clsx('chip h-8 px-2.5 sm:px-3 text-[13px] border transition-colors whitespace-nowrap',
              online ? 'text-hr border-hr/40 bg-hr/10' : 'text-warn border-warn/50 bg-warn/10')}
              title="Toggle connectivity to simulate a dead zone">
              {online ? <Wifi size={14} /> : <WifiOff size={14} />}
              <span className="hidden sm:inline">{state?.down ? 'API unreachable' : online ? 'Online' : 'Offline'}</span>
              {state?.queued ? <span className="num ml-1 px-1.5 rounded bg-black/40">{state.queued}<span className="hidden sm:inline"> queued</span></span> : null}
            </button>
            <NavLink to="/audit" className={clsx('hidden md:inline-flex chip h-8 px-3 text-[13px] border whitespace-nowrap',
              state?.chain?.valid === false ? 'text-alarm border-alarm/50 bg-alarm/10' : 'text-ink border-line2')}>
              <ShieldCheck size={14} className={state?.chain?.valid === false ? 'text-alarm' : 'text-hr'} />
              {state?.chain ? (state.chain.valid ? `Chain intact · ${state.chain.blocks}` : `Break at #${state.chain.first_bad_seq}`) : 'Chain …'}
            </NavLink>
            <div className="hidden sm:block num text-[22px] font-semibold text-ink tabular-nums w-[92px] text-right">
              {clock.toLocaleTimeString('en-GB')}
            </div>
            {authOn && user && (
              <div className="flex items-center gap-1 pl-2 border-l border-line">
                <div className="hidden md:block text-right leading-tight mr-1">
                  <div className="text-[13px] font-medium">{user.name}</div>
                  <div className="text-[11px] text-dim">{user.role === 'emt' ? 'Ambulance crew' : user.role === 'ed' ? 'Emergency dept' : 'Supervisor'}</div>
                </div>
                <button className="btn-ghost h-8 px-2" onClick={lock} title="Lock now" aria-label="Lock"><Lock size={15} /></button>
                <button className="btn-ghost h-8 px-2" onClick={logout} title="Sign out" aria-label="Sign out"><LogOut size={15} /></button>
              </div>
            )}
          </div>
        </header>
        <main className="flex-1 overflow-auto p-4 lg:p-6">{children}</main>
      </div>
    </div>
  )
}
