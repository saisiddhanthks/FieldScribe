import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { TRIAGE_COLOR } from '../lib/api'

const CENTRE = { lat: 12.9716, lng: 77.5946 } // MG Road
const KM_LAT = 110.574, KM_LNG = 111.32 * Math.cos(CENTRE.lat * Math.PI / 180)

/** Offline fleet plot: no map tiles needed. Distances are true to scale around the city centre. */
export function FleetMap({ fleet, hospitals, height = 380 }: { fleet: any[]; hospitals: any[]; height?: number }) {
  const nav = useNavigate()
  const [hover, setHover] = useState<any>(null)
  const W = 1060, H = 420, scale = 16.5 // px per km
  const p = (lat: number, lng: number) => ({ x: W / 2 + (lng - CENTRE.lng) * KM_LNG * scale, y: H / 2 - (lat - CENTRE.lat) * KM_LAT * scale })
  const hosp = useMemo(() => Object.fromEntries(hospitals.map(h => [h.name, h])), [hospitals])
  return (
    <div className="relative overflow-hidden bg-black">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full block overflow-hidden" style={{ height }} role="img" aria-label="Ambulance fleet and receiving hospitals around Bengaluru">
        <defs>
          <radialGradient id="rg" cx="50%" cy="50%" r="55%">
            <stop offset="0%" stopColor="#0b1a12" /><stop offset="100%" stopColor="#000" />
          </radialGradient>
          <pattern id="dots" width="17.5" height="17.5" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r=".8" fill="#182027" /></pattern>
        </defs>
        <rect width={W} height={H} fill="url(#rg)" />
        <rect width={W} height={H} fill="url(#dots)" />
        {[5, 10, 15, 20].map(km => (
          <g key={km}>
            <circle cx={W / 2} cy={H / 2} r={km * scale} fill="none" stroke="#182027" strokeDasharray={km % 10 ? '2 5' : undefined} />
            <text x={W / 2 + km * scale * .707 + 4} y={H / 2 - km * scale * .707} fill="#55626b" fontSize="11">{km} km</text>
          </g>
        ))}
        <line x1={W / 2} y1={0} x2={W / 2} y2={H} stroke="#11181d" /><line x1={0} y1={H / 2} x2={W} y2={H / 2} stroke="#11181d" />
        <text x={W / 2 + 6} y={H / 2 - 6} fill="#55626b" fontSize="11">MG Road</text>
        {fleet.filter(f => f.status !== 'handed_over' && f.destination && hosp[f.destination]).map(f => {
          const a = p(f.lat, f.lng), b = p(hosp[f.destination].lat, hosp[f.destination].lng)
          const c = TRIAGE_COLOR[f.triage || 'UNTRIAGED']
          return (
            <g key={'r' + f.id}>
              <path d={`M${a.x},${a.y} Q${(a.x + b.x) / 2 + (b.y - a.y) * .18},${(a.y + b.y) / 2 - (b.x - a.x) * .18} ${b.x},${b.y}`}
                fill="none" stroke={c} strokeOpacity=".55" strokeWidth="1.6" strokeDasharray="5 6">
                <animate attributeName="stroke-dashoffset" from="22" to="0" dur="1.2s" repeatCount="indefinite" />
              </path>
            </g>
          )
        })}
        {hospitals.map(h => {
          const q = p(h.lat, h.lng)
          return (
            <g key={h.id} transform={`translate(${q.x},${q.y})`}>
              <rect x="-9" y="-9" width="18" height="18" rx="4" fill="#06080a" stroke="#f2f4f5" strokeOpacity=".7" />
              <path d="M0,-5V5M-5,0H5" stroke="#ff4b4b" strokeWidth="2.4" />
              <text x="13" y="4" fill="#c9d3d8" fontSize="12">{h.name.replace(' Institute of Cardiology', '').replace(' Medical College Hospital', '')}</text>
            </g>
          )
        })}
        {fleet.map(f => {
          const q = p(f.lat, f.lng)
          const c = f.status === 'handed_over' ? '#55626b' : TRIAGE_COLOR[f.triage || 'UNTRIAGED']
          const live = f.status !== 'handed_over'
          return (
            <g key={f.id} transform={`translate(${q.x},${q.y})`} className="cursor-pointer"
              onMouseEnter={() => setHover({ ...f, ...q })} onMouseLeave={() => setHover(null)} onClick={() => nav(`/incidents/${f.id}`)}>
              {live && <circle r="7" fill={c} className="ping-soft" />}
              <circle r={live ? 6.5 : 4.5} fill={live ? c : '#000'} stroke={c} strokeWidth="2" />
            </g>
          )
        })}
      </svg>
      {hover && (
        <div className="absolute pointer-events-none panel px-3 py-2 text-[13px] shadow-xl"
          style={{ left: `calc(${(hover.x / W) * 100}% + 12px)`, top: `calc(${(hover.y / H) * 100}% - 8px)` }}>
          <div className="font-medium">{hover.vehicle}</div>
          <div className="text-dim">{hover.complaint || 'Assessment pending'}</div>
          {hover.status !== 'handed_over' && hover.destination && <div className="text-spo2">→ {hover.destination}{hover.eta_min ? ` · ETA ${hover.eta_min} min` : ''}</div>}
        </div>
      )}
      <div className="absolute left-3 bottom-3 flex flex-wrap gap-3 text-[12px] text-dim bg-black/70 rounded px-2.5 py-1.5">
        {['RED', 'YELLOW', 'GREEN'].map(t => <span key={t} className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full" style={{ background: TRIAGE_COLOR[t] }} />{t[0] + t.slice(1).toLowerCase()}</span>)}
        <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full border border-faint" />Completed</span>
        <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-sm border border-bp/70" />Hospital</span>
      </div>
    </div>
  )
}
