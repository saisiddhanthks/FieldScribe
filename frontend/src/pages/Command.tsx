import { Link } from 'react-router-dom'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Mic } from 'lucide-react'
import { api, ROUTE_LABEL, TRIAGE_COLOR } from '../lib/api'
import { chartTheme, Empty, Numeric, Panel, Spinner, Status, Triage, useFetch } from '../components/ui'
import { FleetMap } from '../components/FleetMap'
import { RoadMap } from '../components/RoadMap'
import { useEffect, useState } from 'react'
import { EcgTrace } from '../components/Ecg'

const ROUTE_COLORS = ['#3ee07f', '#35d0f0', '#f3cf3a', '#c08bff', '#ffa733', '#ff6b9a', '#f2f4f5', '#8a979f']

export default function Command() {
  const { data: a } = useFetch(api.analytics, [], 8000)
  const { data: incs } = useFetch(api.incidents, [], 8000)
  const { data: rt } = useFetch(api.routes, [], 15000)
  const [mapMode, setMapMode] = useState<'street' | 'plot'>('street')
  const [tilesFailed, setTilesFailed] = useState(false)
  const [netUp, setNetUp] = useState(typeof navigator === 'undefined' ? true : navigator.onLine)
  useEffect(() => {
    const on = () => { setNetUp(true); setTilesFailed(false) }
    const off = () => setNetUp(false)
    window.addEventListener('online', on); window.addEventListener('offline', off)
    return () => { window.removeEventListener('online', on); window.removeEventListener('offline', off) }
  }, [])
  // while tiles are failing, probe every 20 s and switch back to the live map as soon as they load
  useEffect(() => {
    if (!tilesFailed) return
    const t = setInterval(() => {
      const img = new Image()
      img.onload = () => setTilesFailed(false)
      img.src = `https://tile.openstreetmap.org/11/1463/949.png?probe=${Date.now()}`
    }, 20000)
    return () => clearInterval(t)
  }, [tilesFailed])
  const { data: ms } = useFetch(api.mapStatus, [])
  const { data: offMap } = useFetch(() => ms?.available ? api.mapData() : Promise.resolve(null), [ms?.available])
  if (!a || !incs) return <div className="flex justify-center py-24"><Spinner size={24} /></div>
  const k = a.kpi
  const live = k.online && netUp && !tilesFailed   // live tiles + live routing; otherwise fall back automatically
  const active = incs.filter((i: any) => i.status !== 'handed_over' && i.status !== 'closed')
  return (
    <div className="space-y-4 max-w-[1600px] mx-auto">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-num text-[34px] font-semibold leading-none">Command centre</h1>
          <p className="text-dim mt-1.5">Every ambulance, every dose, signed on the device and visible to the ED before arrival.</p>
        </div>
        <Link to="/capture" className="btn-pri"><Mic size={16} />Start a dictation</Link>
      </div>

      <div className="grid grid-cols-12 gap-4">
        <Panel className="col-span-12 xl:col-span-8" title="Fleet" bodyClass="px-0 pb-0"
          sub={(() => {
            const base = `${k.active} active · ${a.hospitals.length} receiving hospitals · `
            if (mapMode === 'plot') return base + 'offline plot, true to scale'
            if (live) return base + 'live map, live road routes'
            if (offMap) return base + `offline street map, routes computed on this device (${!k.online ? 'device offline' : !netUp ? 'no internet' : 'map server unreachable'})`
            return base + 'offline plot, true to scale. Download the offline street map for dead zones (README)'
          })()}
          actions={
            <div className="flex items-center gap-2">
              {mapMode === 'street' && <span className={`chip h-7 px-2.5 ${live ? 'bg-hr/10 text-hr' : 'bg-warn/10 text-warn'}`}>
                <span className={`w-1.5 h-1.5 rounded-full ${live ? 'bg-hr' : 'bg-warn'}`} />{live ? 'Live' : offMap ? 'Offline map' : 'Offline plot'}</span>}
              <div className="flex rounded-md border border-line2 p-0.5">
                {(['street', 'plot'] as const).map(m => (
                  <button key={m} onClick={() => { setMapMode(m); if (m === 'street') setTilesFailed(false) }}
                    className={`h-7 px-2.5 rounded text-[13px] ${mapMode === m ? 'bg-raise text-ink' : 'text-dim'}`}>{m === 'street' ? 'Map' : 'Offline plot'}</button>
                ))}
              </div>
            </div>}>
          {mapMode === 'street' && live
            ? <RoadMap key="live" fleet={a.fleet} hospitals={a.hospitals} routes={rt?.routes || []} height={400} onTilesFailed={() => setTilesFailed(true)} />
            : mapMode === 'street' && offMap
            ? <RoadMap key="offline" fleet={a.fleet} hospitals={a.hospitals} routes={rt?.routes || []} height={400} onTilesFailed={() => {}} offlineMap={offMap} />
            : <FleetMap fleet={a.fleet} hospitals={a.hospitals} height={400} />}
        </Panel>
        <div className="col-span-12 xl:col-span-4 grid grid-cols-2 gap-3 content-start">
          <Numeric label="Active units" value={k.active} color="#ffa733" hint={`${k.incidents} incidents in 24 h`} />
          <Numeric label="Doses logged" value={k.meds} color="#3ee07f" hint={`${k.procedures} procedures`} />
          <Numeric label="Capture time" value={k.avg_capture_s} unit="s" color="#35d0f0" hint={`vs ~${k.manual_baseline_s}s manual entry (est.)`} />
          <Numeric label="Time returned" value={k.time_saved_min} unit="min" color="#35d0f0" hint="to patient care, 24 h" />
          <Numeric label="Needs review" value={k.flagged} color={k.flagged ? '#ffa733' : '#3ee07f'} hint={`${(k.edit_rate * 100).toFixed(0)}% of fields edited by EMTs`} />
          <Numeric label="Mean confidence" value={(k.mean_confidence * 100).toFixed(0)} unit="%" color="#c08bff" hint={k.field_wer != null ? `field WER ${(k.field_wer * 100).toFixed(1)}%` : 'no voice records yet'} />
          <Link to="/audit" className="col-span-2">
            <Numeric label="Audit chain" value={k.chain_valid ? 'Intact' : 'Broken'} color={k.chain_valid ? '#3ee07f' : '#ff4b4b'} alarm={!k.chain_valid}
              size="md" hint={`${k.blocks} signed blocks · Ed25519 · ${k.queued} queued for sync${k.online ? '' : ' · device offline'}`} />
          </Link>
        </div>
      </div>

      <Panel title="On the road now" sub="Trace speed follows each patient's last recorded heart rate">
        {active.length === 0 ? <Empty title="No active incidents">Open a new incident from Capture.</Empty> : (
          <div className="grid gap-3 grid-cols-1 md:grid-cols-2 2xl:grid-cols-3">
            {active.map((i: any) => <ActiveCard key={i.id} inc={i} route={(rt?.routes || []).find((r: any) => r.incident_id === i.id)} />)}
          </div>
        )}
      </Panel>

      <div className="grid grid-cols-12 gap-4">
        <Panel className="col-span-12 xl:col-span-8" title="Documentation activity" sub="Signed records and clinical entries per hour, last 24 h">
          <div className="h-[240px]">
            <ResponsiveContainer>
              <AreaChart data={a.hourly} margin={{ left: -18, right: 8, top: 8 }}>
                <defs>
                  <linearGradient id="gm" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#3ee07f" stopOpacity=".45" /><stop offset="1" stopColor="#3ee07f" stopOpacity="0" /></linearGradient>
                  <linearGradient id="gp" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#35d0f0" stopOpacity=".4" /><stop offset="1" stopColor="#35d0f0" stopOpacity="0" /></linearGradient>
                </defs>
                <CartesianGrid stroke={chartTheme.grid} vertical={false} />
                <XAxis dataKey="hour" stroke={chartTheme.axis} tick={{ fontSize: 12 }} interval={2} />
                <YAxis stroke={chartTheme.axis} tick={{ fontSize: 12 }} allowDecimals={false} />
                <Tooltip {...chartTheme.tooltip} />
                <Area type="monotone" dataKey="meds" name="Medications" stroke="#3ee07f" fill="url(#gm)" strokeWidth={2} />
                <Area type="monotone" dataKey="procs" name="Procedures" stroke="#35d0f0" fill="url(#gp)" strokeWidth={2} />
                <Area type="step" dataKey="records" name="Signed records" stroke="#f3cf3a" fill="none" strokeWidth={1.5} strokeDasharray="4 3" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Panel>
        <Panel className="col-span-12 xl:col-span-4" title="Safety flags raised" sub="Shown to the EMT before signing">
          {a.flags.length === 0 ? <Empty title="No flags yet" /> : (
            <div className="space-y-2.5 pt-1">
              {a.flags.map((f: any) => {
                const max = a.flags[0].count
                const crit = ['ALLERGY_CONFLICT', 'UNIT_IMPLAUSIBLE', 'AMBIGUOUS_DRUG'].includes(f.code)
                return (
                  <div key={f.code}>
                    <div className="flex justify-between text-[13px] mb-1"><span className="text-dim">{f.code.replace(/_/g, ' ').toLowerCase()}</span><span className="num">{f.count}</span></div>
                    <div className="h-1.5 rounded-full bg-line"><div className="h-full rounded-full" style={{ width: `${(f.count / max) * 100}%`, background: crit ? '#ff4b4b' : '#ffa733' }} /></div>
                  </div>
                )
              })}
            </div>
          )}
        </Panel>
      </div>

      <div className="grid grid-cols-12 gap-4">
        <Panel className="col-span-12 md:col-span-6 xl:col-span-4" title="Most administered" sub="Confirmed doses, 24 h">
          <div className="h-[240px]">
            <ResponsiveContainer>
              <BarChart data={a.drugs} layout="vertical" margin={{ left: 10, right: 16 }}>
                <XAxis type="number" hide allowDecimals={false} />
                <YAxis type="category" dataKey="name" width={110} stroke={chartTheme.axis} tick={{ fontSize: 12, fill: '#c9d3d8' }} />
                <Tooltip {...chartTheme.tooltip} cursor={{ fill: '#0c1013' }} />
                <Bar dataKey="count" name="Doses" fill="#3ee07f" radius={[0, 3, 3, 0]} barSize={12} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Panel>
        <Panel className="col-span-12 md:col-span-6 xl:col-span-4" title="Routes" sub="How medications were given">
          <div className="h-[240px] flex items-center">
            <ResponsiveContainer width="55%">
              <PieChart>
                <Pie data={a.routes} dataKey="count" nameKey="name" innerRadius={52} outerRadius={84} paddingAngle={2} stroke="#000">
                  {a.routes.map((_: any, i: number) => <Cell key={i} fill={ROUTE_COLORS[i % ROUTE_COLORS.length]} />)}
                </Pie>
                <Tooltip {...chartTheme.tooltip} />
              </PieChart>
            </ResponsiveContainer>
            <ul className="flex-1 space-y-1.5 text-[13px]">
              {a.routes.map((r: any, i: number) => (
                <li key={r.name} className="flex items-center gap-2"><span className="w-2.5 h-2.5 rounded-sm" style={{ background: ROUTE_COLORS[i % ROUTE_COLORS.length] }} />
                  <span className="text-dim flex-1">{ROUTE_LABEL[r.name] || r.name}</span><span className="num">{r.count}</span></li>
              ))}
            </ul>
          </div>
        </Panel>
        <Panel className="col-span-12 xl:col-span-4" title="Extraction confidence" sub="Distribution across signed entries">
          <div className="h-[170px]">
            <ResponsiveContainer>
              <BarChart data={a.confidence} margin={{ left: -24, right: 4, top: 6 }}>
                <CartesianGrid stroke={chartTheme.grid} vertical={false} />
                <XAxis dataKey="bin" stroke={chartTheme.axis} tick={{ fontSize: 11 }} />
                <YAxis stroke={chartTheme.axis} tick={{ fontSize: 11 }} allowDecimals={false} />
                <Tooltip {...chartTheme.tooltip} cursor={{ fill: '#0c1013' }} />
                <Bar dataKey="count" name="Entries" radius={[3, 3, 0, 0]}>
                  {a.confidence.map((c: any, i: number) => <Cell key={i} fill={i < 3 ? '#ffa733' : '#c08bff'} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="flex gap-2 flex-wrap mt-2">
            {a.triage.map((t: any) => (
              <span key={t.name} className="chip bg-raise text-dim"><span className="w-2 h-2 rounded-full" style={{ background: TRIAGE_COLOR[t.name] }} />{t.name.toLowerCase()} <span className="num text-ink">{t.count}</span></span>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  )
}

function ActiveCard({ inc, route }: { inc: any; route?: any }) {
  const { data } = useFetch(() => api.incident(inc.id), [inc.id, inc.updated_at])
  const vit = data?.vitals || []
  const last = (n: string) => [...vit].reverse().find((v: any) => v.name === n)?.value
  const hr = Number(last('hr')) || 0
  const spo2 = last('spo2'), bp = last('bp')
  return (
    <Link to={`/incidents/${inc.id}`} className="block rounded-lg border border-line bg-black hover:border-line2 transition-colors overflow-hidden">
      <div className="flex items-start justify-between gap-2 px-3.5 pt-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2"><Triage t={inc.triage} /><Status s={inc.status} /></div>
          <div className="mt-1.5 font-medium truncate">{inc.complaint || 'Assessment in progress'}</div>
          <div className="text-[13px] text-dim truncate">{inc.vehicle} · {inc.place}</div>
        </div>
        {inc.status === 'transporting' && (route || inc.eta_min) ? (
          <div className="text-right shrink-0"><div className="num text-[30px] font-semibold text-spo2 leading-none">{route ? Math.max(1, Math.round(route.remaining_s / 60)) : inc.eta_min}</div>
            <div className="text-[12px] text-dim">min ETA{route ? ` · ${(route.distance_m / 1000).toFixed(1)} km` : ''}</div></div>
        ) : null}
      </div>
      <div className="mt-2 border-y border-line">
        {hr ? <EcgTrace bpm={hr} height={48} /> : <div className="h-12 flex items-center px-3.5 text-[13px] text-faint">No heart rate recorded yet</div>}
      </div>
      <div className="grid grid-cols-4 divide-x divide-line text-center py-2">
        <MiniNum l="HR" v={hr || '—'} c="#3ee07f" />
        <MiniNum l="SpO₂" v={spo2 ?? '—'} c="#35d0f0" />
        <MiniNum l="NIBP" v={bp ?? '—'} c="#f2f4f5" />
        <MiniNum l="Doses" v={inc.counts.meds} c="#f3cf3a" />
      </div>
    </Link>
  )
}

function MiniNum({ l, v, c }: { l: string; v: any; c: string }) {
  return <div><div className="text-[11px]" style={{ color: c }}>{l}</div><div className="num text-[20px] font-semibold leading-tight" style={{ color: c }}>{v}</div></div>
}
