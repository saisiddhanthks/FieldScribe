import { createContext, ReactNode, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { Search, CornerDownLeft, Plus, Wifi, WifiOff, Lock, LogOut, Volume2, RefreshCw, Keyboard, Compass, Download, Ambulance } from 'lucide-react'
import clsx from 'clsx'
import { api, TRIAGE_COLOR } from '../lib/api'
import { NAV, NAV_GROUPS } from '../lib/nav'
import { readbackOn, setReadback, speak } from '../lib/speech'
import { useAuth } from './Auth'
import { useToast } from './ui'

type Cmd = { id: string; group: string; label: string; hint?: string; icon: any; keys?: string; color?: string; run: () => void }

const UI = createContext<{ openPalette: () => void; openHelp: () => void; openTour: () => void }>({ openPalette() {}, openHelp() {}, openTour() {} })
export const useCommandUI = () => useContext(UI)

/** Installable-app prompt captured in main.tsx. */
export const installApp = () => (window as any).__fsInstall?.()
export const canInstall = () => !!(window as any).__fsInstallReady

function typing(e: KeyboardEvent) {
  const t = e.target as HTMLElement | null
  return !!t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable)
}

export function CommandHost({ children }: { children: ReactNode }) {
  const [palette, setPalette] = useState(false)
  const [help, setHelp] = useState(false)
  const [tour, setTour] = useState(false)
  const nav = useNavigate()
  const { can, user } = useAuth()
  const gPending = useRef(0)

  // first sign-in on this device for this user → show the tour once
  useEffect(() => {
    if (!user) return
    const k = `fs_tour_${user.id}`
    try { if (!localStorage.getItem(k)) { setTour(true); localStorage.setItem(k, '1') } } catch { /* storage blocked */ }
  }, [user?.id])

  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setPalette(p => !p); return }
      if (e.key === 'Escape') { setHelp(false) }
      if (typing(e) || e.ctrlKey || e.metaKey || e.altKey) return
      if (e.key === '/') { e.preventDefault(); setPalette(true); return }
      if (e.key === '?') { e.preventDefault(); setHelp(h => !h); return }
      if (e.key === 'g') { gPending.current = Date.now(); return }
      if (gPending.current && Date.now() - gPending.current < 1200) {
        gPending.current = 0
        const item = NAV.find(n => n.key === e.key.toLowerCase() && (!n.right || can(n.right)))
        if (item) { e.preventDefault(); nav(item.to) }
        return
      }
      if (e.key === 'n' && can('capture')) { e.preventDefault(); nav('/capture') }
    }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [can, nav])

  const ctx = useMemo(() => ({ openPalette: () => setPalette(true), openHelp: () => setHelp(true), openTour: () => setTour(true) }), [])
  return (
    <UI.Provider value={ctx}>
      {children}
      <Palette open={palette} onClose={() => setPalette(false)} onHelp={() => setHelp(true)} onTour={() => setTour(true)} />
      <Shortcuts open={help} onClose={() => setHelp(false)} />
      <Tour open={tour} onClose={() => setTour(false)} />
    </UI.Provider>
  )
}

function Palette({ open, onClose, onHelp, onTour }: { open: boolean; onClose: () => void; onHelp: () => void; onTour: () => void }) {
  const [q, setQ] = useState('')
  const [sel, setSel] = useState(0)
  const [incs, setIncs] = useState<any[]>([])
  const [online, setOnline] = useState<boolean | null>(null)
  const nav = useNavigate()
  const toast = useToast()
  const { can, lock, logout, authOn } = useAuth()
  const input = useRef<HTMLInputElement>(null)
  const list = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    setQ(''); setSel(0)
    setTimeout(() => input.current?.focus(), 20)
    api.incidents().then(setIncs).catch(() => {})
    api.sync().then((s: any) => setOnline(!!s.online)).catch(() => {})
  }, [open])

  const go = (to: string) => () => nav(to)
  const cmds: Cmd[] = useMemo(() => {
    const out: Cmd[] = []
    if (can('capture')) out.push({ id: 'new', group: 'Actions', label: 'New incident', hint: 'Start capturing care', icon: Plus, keys: 'N', run: go('/capture') })
    if (can('sync')) {
      out.push({ id: 'online', group: 'Actions', label: online ? 'Go offline (dead-zone drill)' : 'Go online and sync', icon: online ? WifiOff : Wifi, run: async () => {
        const r: any = await api.setOnline(!online)
        toast(online ? 'info' : 'ok', online ? 'Offline · records stay signed and queued' : `Online · ${r.sync?.synced_now ?? 0} items synced`)
        window.dispatchEvent(new Event('fs:refresh'))
      } })
      out.push({ id: 'sync', group: 'Actions', label: 'Sync now', hint: 'Push queued records to the ED hub', icon: RefreshCw, run: async () => {
        try { const r: any = await api.runSync(); toast('ok', `Synced ${r.synced_now ?? 0} · ${r.queued ?? 0} still queued`) } catch (e: any) { toast('err', e.message) }
        window.dispatchEvent(new Event('fs:refresh'))
      } })
    }
    out.push({ id: 'rb', group: 'Actions', label: readbackOn() ? 'Turn spoken read-back off' : 'Turn spoken read-back on', icon: Volume2, run: () => { const v = !readbackOn(); setReadback(v); if (v) speak('Read back on', true) } })
    if (authOn) {
      out.push({ id: 'lock', group: 'Actions', label: 'Lock screen', icon: Lock, run: lock })
      out.push({ id: 'out', group: 'Actions', label: 'Sign out', icon: LogOut, run: logout })
    }
    if (canInstall()) out.push({ id: 'install', group: 'Actions', label: 'Install FieldScribe as an app', icon: Download, run: installApp })
    out.push({ id: 'keys', group: 'Help', label: 'Keyboard shortcuts', icon: Keyboard, keys: '?', run: onHelp })
    out.push({ id: 'tour', group: 'Help', label: 'Take the tour again', icon: Compass, run: onTour })
    for (const g of NAV_GROUPS) for (const n of g.items) {
      if (n.right && !can(n.right)) continue
      out.push({ id: 'p' + n.to, group: 'Go to', label: n.label, hint: n.hint, icon: n.icon, keys: `G ${n.key.toUpperCase()}`, run: go(n.to) })
    }
    for (const i of incs) {
      const p = i.patient || {}
      out.push({
        id: 'i' + i.id, group: 'Incidents', icon: Ambulance, color: TRIAGE_COLOR[i.triage || 'UNTRIAGED'],
        label: `${i.dispatch_id || i.id} · ${i.complaint || 'No complaint yet'}`,
        hint: [p.age && `${p.age}${p.sex ? p.sex[0].toUpperCase() : ''}`, i.vehicle, i.place, i.status].filter(Boolean).join(' · '),
        run: go(`/incidents/${i.id}`),
      })
    }
    return out
  }, [incs, online, can, authOn]) // eslint-disable-line

  const shown = useMemo(() => {
    const words = q.toLowerCase().split(/\s+/).filter(Boolean)
    const hit = (c: Cmd) => words.every(w => `${c.label} ${c.hint || ''} ${c.group}`.toLowerCase().includes(w))
    const r = cmds.filter(hit)
    if (!words.length) return r.filter(c => c.group !== 'Incidents' || r.filter(x => x.group === 'Incidents').indexOf(c) < 6)
    return r.slice(0, 40)
  }, [q, cmds])
  useEffect(() => setSel(0), [q])
  useEffect(() => { list.current?.querySelector(`[data-i="${sel}"]`)?.scrollIntoView({ block: 'nearest' }) }, [sel])

  const run = (c?: Cmd) => { if (!c) return; onClose(); setTimeout(c.run, 0) }
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setSel(s => Math.min(s + 1, shown.length - 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setSel(s => Math.max(s - 1, 0)) }
    else if (e.key === 'Enter') { e.preventDefault(); run(shown[sel]) }
    else if (e.key === 'Escape') onClose()
  }

  let last = ''
  return (
    <AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-[70] bg-black/70 backdrop-blur-[2px] flex items-start justify-center pt-[12vh] px-4"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.12 }} onMouseDown={onClose}>
          <motion.div role="dialog" aria-label="Command bar" onMouseDown={e => e.stopPropagation()}
            initial={{ y: -8, scale: 0.985 }} animate={{ y: 0, scale: 1 }} exit={{ y: -8, scale: 0.985 }} transition={{ duration: 0.14 }}
            className="w-full max-w-[640px] rounded-xl border border-line2 bg-panel shadow-[0_24px_80px_rgba(0,0,0,.8)] overflow-hidden">
            <div className="flex items-center gap-3 px-4 h-14 border-b border-line">
              <Search size={18} className="text-dim" />
              <input ref={input} value={q} onChange={e => setQ(e.target.value)} onKeyDown={onKey}
                placeholder="Search incidents, pages and actions…" aria-label="Search"
                className="flex-1 bg-transparent outline-none focus-visible:outline-none text-[16px] placeholder:text-faint" style={{ outline: "none" }} />
              <kbd className="kbd">Esc</kbd>
            </div>
            <div ref={list} className="max-h-[52vh] overflow-auto py-1.5" role="listbox">
              {shown.length === 0 && <div className="px-4 py-8 text-center text-dim text-[14px]">No match for “{q}”. Try a dispatch ID, a complaint like “chest pain”, or a page name.</div>}
              {shown.map((c, i) => {
                const head = c.group !== last ? (last = c.group) : null
                return (
                  <div key={c.id}>
                    {head && <div className="px-4 pt-2.5 pb-1 text-[12px] text-faint">{head}</div>}
                    <button data-i={i} role="option" aria-selected={i === sel} onMouseMove={() => setSel(i)} onClick={() => run(c)}
                      className={clsx('w-full flex items-center gap-3 px-4 h-11 text-left', i === sel ? 'bg-raise' : '')}>
                      <c.icon size={16} className="shrink-0" style={{ color: c.color || (i === sel ? '#3ee07f' : '#8a979f') }} />
                      <span className="text-[14.5px] truncate">{c.label}</span>
                      {c.hint && <span className="text-[13px] text-faint truncate">{c.hint}</span>}
                      <span className="ml-auto flex items-center gap-1 shrink-0">
                        {c.keys && <kbd className="kbd">{c.keys}</kbd>}
                        {i === sel && <CornerDownLeft size={14} className="text-dim" />}
                      </span>
                    </button>
                  </div>
                )
              })}
            </div>
            <div className="flex items-center gap-4 px-4 h-10 border-t border-line text-[12px] text-faint">
              <span><kbd className="kbd">↑</kbd> <kbd className="kbd">↓</kbd> move</span>
              <span><kbd className="kbd">Enter</kbd> open</span>
              <span className="ml-auto"><kbd className="kbd">?</kbd> all shortcuts</span>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

function Shortcuts({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { can } = useAuth()
  const rows: [string[], string][] = [
    [['Ctrl', 'K', 'or', '/'], 'Open the command bar'],
    [['?'], 'Show or hide this list'],
    ...(can('capture') ? [[['N'], 'New incident (Capture)'] as [string[], string]] : []),
    ...NAV.filter(n => !n.right || can(n.right)).map(n => [['G', 'then', n.key.toUpperCase()], n.label] as [string[], string]),
    [['Esc'], 'Close any window'],
  ]
  return (
    <AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-[70] bg-black/70 flex items-center justify-center p-4" onMouseDown={onClose}
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.12 }}>
          <div role="dialog" aria-label="Keyboard shortcuts" onMouseDown={e => e.stopPropagation()} className="w-full max-w-[460px] rounded-xl border border-line2 bg-panel p-5">
            <h2 className="font-num text-[24px] font-semibold">Keyboard shortcuts</h2>
            <p className="text-[13px] text-dim mb-3">Work without the mouse. Shortcuts pause while you type in a field.</p>
            <div className="divide-y divide-line">
              {rows.map(([k, v]) => (
                <div key={v} className="flex items-center justify-between h-9 text-[14px]">
                  <span className="text-dim">{v}</span>
                  <span className="flex gap-1">{k.map((p, i) => p === 'then' || p === 'or' ? <span key={i} className="text-faint text-[12px] self-center px-0.5">{p}</span> : <kbd key={i} className="kbd">{p}</kbd>)}</span>
                </div>
              ))}
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

const TOUR = [
  { title: 'Welcome to FieldScribe', body: 'The patient record writes itself while you work. Everything runs on this device, so it keeps working in dead zones and syncs to the hospital when signal returns.', to: null },
  { title: 'Capture care by voice', body: 'Say what you did: “aspirin 300 mg oral at 10:42, BP 130 over 80”. FieldScribe turns it into drugs, doses, routes and vitals. You check it, it reads it back, you say “confirm”, and it’s signed.', to: '/capture', right: 'capture' },
  { title: 'Ask Copilot when unsure', body: 'Describe the patient and Copilot gives step-by-step first aid from 108 protocols. Tell it what you gave and it logs it for you after you confirm.', to: '/copilot' },
  { title: 'Watch the clock', body: 'The bell at the top counts the things that are due: repeat vitals, adrenaline windows, tourniquet time, the golden hour. It beeps when one falls due.', to: '/' },
  { title: 'Hand over without retelling', body: 'The emergency team sees each inbound patient, a readiness score of what’s missing, and the full signed record before you arrive.', to: '/handover' },
  { title: 'Find anything fast', body: 'Press Ctrl K (or /) to search incidents, jump to pages or run actions. Press ? for every shortcut. You can replay this tour from the command bar.', to: null },
]

function Tour({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [i, setI] = useState(0)
  const nav = useNavigate()
  const { can } = useAuth()
  const steps = TOUR.filter(s => !s.right || can(s.right))
  useEffect(() => { if (open) setI(0) }, [open])
  if (!open) return null
  const s = steps[Math.min(i, steps.length - 1)]
  const last = i >= steps.length - 1
  const next = () => { if (last) { onClose(); return } const n = steps[i + 1]; if (n.to) nav(n.to); setI(i + 1) }
  return (
    <div className="fixed z-[65] bottom-5 right-5 left-5 sm:left-auto sm:w-[400px]" role="dialog" aria-label="Guided tour">
      <motion.div key={i} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.18 }}
        className="rounded-xl border border-hr/40 bg-panel shadow-[0_20px_60px_rgba(0,0,0,.85)] p-5">
        <div className="flex items-center gap-1.5 mb-3" aria-hidden>
          {steps.map((_, k) => <span key={k} className={clsx('h-1 rounded-full transition-all', k === i ? 'w-6 bg-hr' : 'w-2 bg-line2')} />)}
          <span className="ml-auto text-[12px] text-faint">{i + 1} of {steps.length}</span>
        </div>
        <h3 className="font-num text-[24px] font-semibold leading-tight">{s.title}</h3>
        <p className="text-[14.5px] text-dim mt-1.5 leading-relaxed">{s.body}</p>
        <div className="flex items-center gap-2 mt-4">
          <button className="btn-ghost h-9" onClick={onClose}>Skip tour</button>
          {i > 0 && <button className="btn-sec h-9 ml-auto" onClick={() => { const p = steps[i - 1]; if (p.to) nav(p.to); setI(i - 1) }}>Back</button>}
          <button className={clsx('btn-pri h-9', i === 0 && 'ml-auto')} onClick={next}>{last ? 'Start working' : 'Next'}</button>
        </div>
      </motion.div>
    </div>
  )
}
