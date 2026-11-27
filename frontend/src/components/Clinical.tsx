import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Timer, BellRing, CheckCircle2, Circle, AlertTriangle } from 'lucide-react'
import clsx from 'clsx'
import { api } from '../lib/api'
import { beep, speak } from '../lib/speech'
import { Empty, useToast } from './ui'

const SEV = { critical: '#ff4b4b', warning: '#ffa733', info: '#35d0f0' } as Record<string, string>

export function ClockRow({ t }: { t: any }) {
  const c = SEV[t.severity]
  const due = t.due_in_min
  return (
    <div className={clsx('rounded-md border px-3 py-2', t.severity === 'critical' ? 'border-alarm/60 bg-alarm/[.06]' : t.severity === 'warning' ? 'border-warn/50 bg-warn/[.05]' : 'border-line bg-black')}>
      <div className="flex items-center justify-between gap-2">
        <span className="text-[14px] font-medium flex items-center gap-1.5" style={{ color: t.severity === 'info' ? undefined : c }}>
          {t.severity !== 'info' && <span className="w-1.5 h-1.5 rounded-full blink" style={{ background: c }} />}{t.label}
        </span>
        <span className="num text-[18px] font-semibold" style={{ color: c }}>
          {due != null ? (due > 0 ? `${Math.ceil(due)}′` : `+${Math.ceil(-due)}′`) : `${Math.round(t.elapsed_min)}′`}
        </span>
      </div>
      <div className="text-[12px] text-dim mt-0.5">since {t.started} · {Math.round(t.elapsed_min)} min · {t.message}</div>
    </div>
  )
}

export function ClockPanel({ timers, compact }: { timers: any[]; compact?: boolean }) {
  if (!timers?.length) return <Empty title="No timers running">Timers start from what you log: vitals, adrenaline, analgesia, tourniquet, CPR.</Empty>
  return <div className={clsx('space-y-2', compact && 'max-h-[260px] overflow-auto')}>{timers.map(t => <ClockRow key={t.id} t={t} />)}</div>
}

/** Top-bar bell: polls every active incident's clock and alerts once when a timer falls due. */
export function ClockBell() {
  const toast = useToast()
  const [timers, setTimers] = useState<any[]>([])
  const [open, setOpen] = useState(false)
  const seen = useRef<Record<string, string>>({})
  const init = useRef(false)
  useEffect(() => {
    let alive = true
    const load = async () => {
      try {
        const r: any = await api.clockAll()
        if (!alive) return
        setTimers(r.timers)
        const firstLoad = !init.current
        init.current = true
        for (const t of r.timers) {
          const prev = seen.current[t.id]
          seen.current[t.id] = t.status
          if (firstLoad || t.status === 'running' || prev === t.status) continue   // no alarm burst on page load
          beep(t.severity === 'critical' ? 980 : 760, 0.14, t.severity === 'critical' ? 3 : 2)
          toast(t.severity === 'critical' ? 'err' : 'info', `${t.vehicle}: ${t.label}. ${t.message}`)
          speak(`${t.label}. ${t.message}`)
        }
      } catch { /* offline or logged out */ }
    }
    load()
    const id = setInterval(load, 15000)
    return () => { alive = false; clearInterval(id) }
  }, [])
  const due = timers.filter(t => t.status !== 'running')
  const crit = due.some(t => t.severity === 'critical')
  return (
    <div className="relative">
      <button onClick={() => setOpen(o => !o)} title="Clinical clock"
        className={clsx('chip h-8 px-2.5 sm:px-3 text-[13px] border whitespace-nowrap', crit ? 'text-alarm border-alarm/50 bg-alarm/10' : due.length ? 'text-warn border-warn/50 bg-warn/10' : 'text-dim border-line2')}>
        {due.length ? <BellRing size={14} className={crit ? 'blink' : ''} /> : <Timer size={14} />}
        {due.length ? `${due.length} due` : `${timers.length} timers`}
      </button>
      {open && (
        <div className="absolute right-0 top-10 z-50 w-[min(380px,calc(100vw-24px))] panel p-3 shadow-2xl" onMouseLeave={() => setOpen(false)}>
          <div className="text-[13px] text-dim mb-2">Clinical clock · all active units</div>
          <ClockPanel timers={timers} compact />
          {timers.length > 0 && <div className="text-[12px] text-faint mt-2">Open a unit from <Link to="/incidents" className="text-spo2">Incidents</Link> to act on its timers.</div>}
        </div>
      )}
    </div>
  )
}

export function Readiness({ c, compact }: { c: any; compact?: boolean }) {
  if (!c) return null
  const col = c.score >= 90 ? '#3ee07f' : c.score >= 70 ? '#ffa733' : '#ff4b4b'
  const R = 30, C = 2 * Math.PI * R
  const show = compact ? c.missing : c.items
  return (
    <div className="flex gap-4 items-start">
      <svg width="76" height="76" viewBox="0 0 76 76" className="shrink-0" role="img" aria-label={`Handover readiness ${c.score}%`}>
        <circle cx="38" cy="38" r={R} fill="none" stroke="#182027" strokeWidth="7" />
        <circle cx="38" cy="38" r={R} fill="none" stroke={col} strokeWidth="7" strokeLinecap="round" strokeDasharray={`${(c.score / 100) * C} ${C}`} transform="rotate(-90 38 38)" />
        <text x="38" y="44" textAnchor="middle" fill={col} style={{ font: '600 20px "Barlow Condensed"' }}>{c.score}%</text>
      </svg>
      <div className="flex-1 min-w-0">
        <div className="text-[13px] text-dim mb-1.5">{c.ready ? 'Ready for handover' : 'Missing before handover'}{c.condition ? ` · ${c.condition} checks` : ''}</div>
        {show.length === 0 ? <div className="text-[14px] text-hr flex items-center gap-1.5"><CheckCircle2 size={15} />Everything the ED needs is recorded</div> : (
          <ul className="space-y-1">
            {show.map((i: any) => (
              <li key={i.key} className="text-[13px] flex items-start gap-1.5">
                {i.ok ? <CheckCircle2 size={14} className="text-hr mt-0.5 shrink-0" /> : i.severity === 'required' ? <AlertTriangle size={14} className="text-alarm mt-0.5 shrink-0" /> : <Circle size={14} className="text-warn mt-0.5 shrink-0" />}
                <span className={i.ok ? 'text-dim' : ''}>{i.label}{!i.ok && i.hint ? <span className="text-faint"> · {i.hint}</span> : null}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
