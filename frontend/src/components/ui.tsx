import { ReactNode, createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { X, AlertTriangle, AlertOctagon, Info, CheckCircle2 } from 'lucide-react'
import clsx from 'clsx'
import { STATUS_LABEL, TRIAGE_COLOR } from '../lib/api'

export function useFetch<T = any>(fn: () => Promise<T>, deps: any[] = [], intervalMs?: number) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const fnRef = useRef(fn)
  fnRef.current = fn
  const load = useCallback(async () => {
    try {
      const d = await fnRef.current()
      setData(d); setError(null)
    } catch (e: any) { setError(e.message) } finally { setLoading(false) }
  }, [])
  useEffect(() => {
    setLoading(true); load()
    if (intervalMs) { const t = setInterval(load, intervalMs); return () => clearInterval(t) }
  }, deps) // eslint-disable-line
  return { data, error, loading, reload: load, setData }
}

export function Panel({ title, sub, actions, children, className, bodyClass }: {
  title?: ReactNode; sub?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; bodyClass?: string
}) {
  return (
    <section className={clsx('panel flex flex-col min-w-0', className)}>
      {(title || actions) && (
        <header className="panel-h">
          <div className="min-w-0">
            {title && <h2 className="panel-t truncate">{title}</h2>}
            {sub && <p className="panel-s truncate">{sub}</p>}
          </div>
          {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
        </header>
      )}
      <div className={clsx('px-4 pb-4 min-h-0 flex-1', bodyClass)}>{children}</div>
    </section>
  )
}

/** Patient-monitor style numeric: parameter colour, big condensed digits, small unit. */
export function Numeric({ label, value, unit, color = '#e4ebee', hint, alarm, size = 'lg' }: {
  label: string; value: ReactNode; unit?: string; color?: string; hint?: ReactNode; alarm?: boolean; size?: 'md' | 'lg' | 'xl'
}) {
  return (
    <div className={clsx('relative rounded-lg border px-3.5 py-2.5 bg-black', alarm ? 'border-alarm/60' : 'border-line')}>
      <div className="flex items-center justify-between">
        <span className="text-[13px] font-semibold" style={{ color }}>{label}</span>
        {alarm && <span className="w-2 h-2 rounded-full bg-alarm blink" aria-label="alarm" />}
      </div>
      <div className="flex items-baseline gap-1.5" style={{ color }}>
        <span className={clsx('num font-semibold leading-none', size === 'xl' ? 'text-[56px]' : size === 'lg' ? 'text-[40px]' : 'text-[30px]')}>{value}</span>
        {unit && <span className="text-[13px] opacity-70">{unit}</span>}
      </div>
      {hint && <div className="text-[12px] text-dim mt-1 truncate">{hint}</div>}
    </div>
  )
}

export function Triage({ t }: { t?: string | null }) {
  const k = (t || 'UNTRIAGED').toUpperCase()
  const c = TRIAGE_COLOR[k] || '#55626b'
  return (
    <span className="chip border" style={{ color: c, borderColor: c + '66', background: c + '14' }}>
      <span className="w-1.5 h-1.5 rounded-full" style={{ background: c }} />
      {k === 'UNTRIAGED' ? 'Untriaged' : k[0] + k.slice(1).toLowerCase()}
    </span>
  )
}

export function Status({ s }: { s: string }) {
  const map: Record<string, string> = { on_scene: '#ffa733', transporting: '#35d0f0', handed_over: '#3ee07f', closed: '#8a979f' }
  const c = map[s] || '#8a979f'
  return (
    <span className="chip" style={{ color: c, background: c + '18' }}>
      {s === 'transporting' && <span className="w-1.5 h-1.5 rounded-full blink" style={{ background: c }} />}
      {STATUS_LABEL[s] || s}
    </span>
  )
}

export function FlagLine({ f }: { f: { level: string; code: string; message: string } }) {
  const Icon = f.level === 'critical' ? AlertOctagon : f.level === 'warning' ? AlertTriangle : Info
  const c = f.level === 'critical' ? 'text-alarm' : f.level === 'warning' ? 'text-warn' : 'text-dim'
  return (
    <div className="flex items-start gap-2 text-[13px] leading-snug">
      <Icon size={14} className={clsx('mt-0.5 shrink-0', c)} />
      <span><span className={clsx('font-semibold mr-1', c)}>{f.code.replace(/_/g, ' ').toLowerCase()}</span><span className="text-dim">{f.message}</span></span>
    </div>
  )
}

export function ConfBar({ v }: { v: number }) {
  const c = v >= 0.85 ? '#3ee07f' : v >= 0.7 ? '#ffa733' : '#ff4b4b'
  return (
    <div className="flex items-center gap-2" title={`confidence ${(v * 100).toFixed(0)}%`}>
      <div className="h-1.5 w-16 rounded-full bg-line overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${Math.max(4, v * 100)}%`, background: c }} />
      </div>
      <span className="num text-[13px]" style={{ color: c }}>{(v * 100).toFixed(0)}%</span>
    </div>
  )
}

export function Modal({ open, onClose, title, children, wide }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; wide?: boolean }) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', k); return () => window.removeEventListener('keydown', k)
  }, [onClose])
  return (
    <AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}>
          <motion.div role="dialog" aria-modal className={clsx('panel w-full max-h-[86vh] flex flex-col', wide ? 'max-w-5xl' : 'max-w-2xl')}
            initial={{ y: 12, scale: .98 }} animate={{ y: 0, scale: 1 }} exit={{ y: 8, opacity: 0 }} onClick={e => e.stopPropagation()}>
            <div className="panel-h border-b border-line">
              <h3 className="panel-t">{title}</h3>
              <button className="btn-ghost h-8 px-2" onClick={onClose} aria-label="Close"><X size={16} /></button>
            </div>
            <div className="p-4 overflow-auto">{children}</div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

export function JsonView({ data, max = '60vh' }: { data: any; max?: string }) {
  const txt = JSON.stringify(data, null, 2)
  const html = txt
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g, m => {
      let c = '#f3cf3a'
      if (/^"/.test(m)) c = /:$/.test(m) ? '#35d0f0' : '#cfe8d8'
      else if (/true|false/.test(m)) c = '#c08bff'
      else if (/null/.test(m)) c = '#55626b'
      return `<span style="color:${c}">${m}</span>`
    })
  return <pre className="font-mono text-[12px] leading-[1.55] bg-black border border-line rounded-md p-3 overflow-auto" style={{ maxHeight: max }} dangerouslySetInnerHTML={{ __html: html }} />
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center text-center py-10 text-dim">
      <div className="text-ink font-medium mb-1">{title}</div>
      <div className="text-sm max-w-sm">{children}</div>
    </div>
  )
}

export function Spinner({ size = 16 }: { size?: number }) {
  return <span className="inline-block rounded-full border-2 border-line2 border-t-spo2 animate-spin" style={{ width: size, height: size }} />
}

export function Hash({ h, n = 10 }: { h?: string; n?: number }) {
  if (!h) return null
  return <span className="font-mono text-[12px] text-dim" title={h}>{h.slice(0, n)}…{h.slice(-4)}</span>
}

// --------------------------------------------------------------- toasts

type Toast = { id: number; kind: 'ok' | 'err' | 'info'; text: string }
const ToastCtx = createContext<(kind: Toast['kind'], text: string) => void>(() => {})
export const useToast = () => useContext(ToastCtx)

export function ToastHost({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([])
  const push = useCallback((kind: Toast['kind'], text: string) => {
    const id = Date.now() + Math.random()
    setItems(x => [...x, { id, kind, text }])
    setTimeout(() => setItems(x => x.filter(t => t.id !== id)), 4200)
  }, [])
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="fixed bottom-4 right-4 z-[60] flex flex-col gap-2 w-[360px] max-w-[calc(100vw-2rem)]" aria-live="polite">
        <AnimatePresence>
          {items.map(t => (
            <motion.div key={t.id} initial={{ x: 30, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={{ x: 30, opacity: 0 }}
              className={clsx('panel px-3.5 py-3 flex items-start gap-2.5 text-sm shadow-2xl',
                t.kind === 'ok' && 'border-hr/50', t.kind === 'err' && 'border-alarm/60')}>
              {t.kind === 'ok' ? <CheckCircle2 size={16} className="text-hr mt-0.5" /> : t.kind === 'err' ? <AlertOctagon size={16} className="text-alarm mt-0.5" /> : <Info size={16} className="text-spo2 mt-0.5" />}
              <span>{t.text}</span>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </ToastCtx.Provider>
  )
}

export const chartTheme = {
  grid: '#182027', axis: '#55626b',
  tooltip: { contentStyle: { background: '#000', border: '1px solid #242e36', borderRadius: 8, fontSize: 13, color: '#e4ebee' }, labelStyle: { color: '#8a979f' }, itemStyle: { color: '#e4ebee' } },
}
