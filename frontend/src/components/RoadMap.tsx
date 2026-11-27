import { useEffect, useMemo, useRef, useState } from 'react'
import { MapContainer, TileLayer, Polyline, Polygon, Marker, Tooltip, useMap, useMapEvents, LayersControl } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { useNavigate } from 'react-router-dom'
import { TRIAGE_COLOR } from '../lib/api'

const CENTRE: [number, number] = [12.9716, 77.5946]

const hospitalIcon = L.divIcon({
  className: '', iconSize: [22, 22], iconAnchor: [11, 11],
  html: `<div style="width:22px;height:22px;border-radius:5px;background:#06080a;border:1.5px solid rgba(242,244,245,.8);display:flex;align-items:center;justify-content:center;box-shadow:0 0 0 3px rgba(0,0,0,.5)">
    <svg width="12" height="12" viewBox="0 0 12 12"><path d="M6 1v10M1 6h10" stroke="#ff4b4b" stroke-width="2.6"/></svg></div>`,
})
const unitIcon = (c: string, live: boolean) => L.divIcon({
  className: '', iconSize: [30, 30], iconAnchor: [15, 15],
  html: live
    ? `<div class="fs-unit" style="--c:${c}"><span></span><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#000" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M10 10H6M8 8v4M3 17h1m16 0h1M2 13V7a1 1 0 0 1 1-1h11l3 4h3a1 1 0 0 1 1 1v6H2z"/><circle cx="7" cy="17" r="2"/><circle cx="17" cy="17" r="2"/></svg></div>`
    : `<div style="width:12px;height:12px;margin:9px;border-radius:50%;background:#000;border:2px solid #55626b"></div>`,
})
const sceneIcon = (c: string) => L.divIcon({
  className: '', iconSize: [14, 14], iconAnchor: [7, 7],
  html: `<div style="width:14px;height:14px;border-radius:50%;border:2px dashed ${c};background:rgba(0,0,0,.6)"></div>`,
})

function Fit({ pts }: { pts: [number, number][] }) {
  const map = useMap()
  const done = useRef(false)
  useEffect(() => {
    if (done.current || pts.length < 2) return
    map.fitBounds(L.latLngBounds(pts).pad(0.12), { animate: false })
    done.current = true
  }, [pts, map])
  return null
}

// ---------------------------------------------------------------- live layers (online)

const OSM_ATTR = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors · routing OSRM'
const LIVE_LAYERS = [
  // Dark = the free OpenStreetMap tiles with a CSS night filter (no API key needed)
  { name: 'Dark', url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png', subdomains: 'abc', className: 'fs-dark-tiles', attribution: OSM_ATTR },
  { name: 'Streets', url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png', subdomains: 'abc', className: '', attribution: OSM_ATTR },
  { name: 'Satellite', url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', subdomains: 'abc', className: '',
    attribution: 'Imagery &copy; Esri, Maxar, Earthstar Geographics · routing OSRM' },
]

// ---------------------------------------------------------------- offline vector basemap

const ROAD_STYLE: Record<number, { color: string; weight: number; minZoom: number }> = {
  1: { color: '#4a5866', weight: 3.4, minZoom: 0 }, 2: { color: '#3a4650', weight: 2.6, minZoom: 0 },
  3: { color: '#2e3840', weight: 2.0, minZoom: 11 }, 4: { color: '#252e35', weight: 1.4, minZoom: 12 },
  5: { color: '#1e262c', weight: 1.1, minZoom: 13 }, 6: { color: '#192025', weight: 0.9, minZoom: 14 },
}
const placeIcon = (n: string) => L.divIcon({ className: '', iconSize: [0, 0],
  html: `<div style="transform:translate(-50%,-50%);white-space:nowrap;font:500 11px Barlow,sans-serif;color:#55626b;letter-spacing:.02em;text-shadow:0 0 3px #000,0 0 3px #000">${n.replace(/[<>&]/g, '')}</div>` })

function OfflineBase({ map }: { map: any }) {
  const [zoom, setZoom] = useState(11)
  useMapEvents({ zoomend: e => setZoom(e.target.getZoom()) })
  const grouped = useMemo(() => {
    const g: Record<number, [number, number][][]> = {}
    for (const r of map.roads) (g[r.c] ||= []).push(r.g)
    return g
  }, [map])
  return (
    <>
      {map.parks.map((p: any, i: number) => <Polygon key={'p' + i} positions={p.g} interactive={false} pathOptions={{ stroke: false, fillColor: '#0b1d12', fillOpacity: 1 }} />)}
      {map.water.map((p: any, i: number) => <Polygon key={'w' + i} positions={p.g} interactive={false} pathOptions={{ stroke: false, fillColor: '#0b2433', fillOpacity: 1 }} />)}
      {[6, 5, 4, 3, 2, 1].filter(c => grouped[c] && zoom >= ROAD_STYLE[c].minZoom).map(c => (
        <Polyline key={'r' + c} positions={grouped[c]} interactive={false}
          pathOptions={{ color: ROAD_STYLE[c].color, weight: ROAD_STYLE[c].weight * (zoom >= 14 ? 1.6 : zoom >= 13 ? 1.25 : 1), lineCap: 'round', lineJoin: 'round' }} />
      ))}
      {zoom >= 12 && map.places.filter((p: any) => zoom >= 13 || p.k === 'suburb' || p.k === 'town').map((p: any, i: number) => (
        <Marker key={'pl' + i} position={p.p} icon={placeIcon(p.n)} interactive={false} />
      ))}
    </>
  )
}

export function RoadMap({ fleet, hospitals, routes, height = 400, onTilesFailed, offlineMap }: {
  fleet: any[]; hospitals: any[]; routes: any[]; height?: number; onTilesFailed: () => void; offlineMap?: any
}) {
  const nav = useNavigate()
  const [, setTick] = useState(0)
  const fails = useRef(0)
  const byInc = useMemo(() => Object.fromEntries(routes.map(r => [r.incident_id, r])), [routes])
  useEffect(() => { const t = setInterval(() => setTick(x => x + 1), 15000); return () => clearInterval(t) }, [])
  const pts: [number, number][] = [...hospitals.map(h => [h.lat, h.lng] as [number, number]), ...fleet.filter(f => f.lat).map(f => [f.lat, f.lng] as [number, number])]
  return (
    <div className="fs-map relative" style={{ height }}>
      <MapContainer center={CENTRE} zoom={11} zoomControl={true} attributionControl={true} preferCanvas={true} style={{ height: '100%', width: '100%', background: '#000' }} scrollWheelZoom={false}>
        {offlineMap ? <OfflineBase map={offlineMap} /> : (
          <LayersControl position="topright">
            {LIVE_LAYERS.map((l, i) => (
              <LayersControl.BaseLayer key={l.name} name={l.name} checked={i === 0}>
                <TileLayer url={l.url} attribution={l.attribution} subdomains={l.subdomains || 'abc'} maxZoom={19} className={l.className}
                  eventHandlers={{ tileerror: () => { fails.current += 1; if (fails.current === 6) onTilesFailed() },
                                   tileload: () => { fails.current = 0 } }} />
              </LayersControl.BaseLayer>
            ))}
          </LayersControl>
        )}
        {offlineMap && <AttributionText text={`© OpenStreetMap contributors · offline copy ${offlineMap.fetched || ''} · on-device routing`} />}
        <Fit pts={pts} />
        {routes.map(r => {
          const c = TRIAGE_COLOR[r.triage || 'UNTRIAGED']
          const solid = r.source === 'osrm' || r.source === 'offline-roads'
          const done = r.coords.slice(0, Math.max(1, Math.round(r.coords.length * r.progress)))
          return (
            <span key={'r' + r.incident_id}>
              <Polyline positions={r.coords} pathOptions={{ color: c, weight: 4, opacity: .3, dashArray: solid ? undefined : '6 8' }} />
              {r.status === 'transporting' && done.length > 1 && <Polyline positions={[...done, r.position]} pathOptions={{ color: c, weight: 4, opacity: .9 }} />}
            </span>
          )
        })}
        {hospitals.map(h => (
          <Marker key={h.id} position={[h.lat, h.lng]} icon={hospitalIcon}>
            <Tooltip direction="right" offset={[12, 0]} className="fs-tip">{h.name}<br /><span style={{ opacity: .6 }}>{h.type} · {h.beds_ed} ED beds</span></Tooltip>
          </Marker>
        ))}
        {fleet.filter(f => f.lat).map(f => {
          const r = byInc[f.id]
          const live = f.status !== 'handed_over'
          const c = live ? TRIAGE_COLOR[f.triage || 'UNTRIAGED'] : '#55626b'
          const pos: [number, number] = r ? r.position : [f.lat, f.lng]
          return (
            <span key={f.id}>
              {r && f.status === 'transporting' && <Marker position={r.scene} icon={sceneIcon(c)} />}
              <Marker position={pos} icon={unitIcon(c, live)} eventHandlers={{ click: () => nav(`/incidents/${f.id}`) }}>
                <Tooltip direction="top" offset={[0, -14]} className="fs-tip">
                  <b>{f.vehicle}</b> · {f.complaint || 'assessment pending'}<br />
                  {r ? <>→ {r.destination} · {(r.distance_m / 1000).toFixed(1)} km · {Math.max(1, Math.round((f.status === 'transporting' ? r.remaining_s : r.duration_s) / 60))} min
                    <br /><span style={{ opacity: .6 }}>{r.source === 'offline-roads' ? 'road route, computed on this device' : r.source === 'osrm' ? `live road route${r.cached ? ' (saved)' : ''}` : 'straight-line estimate'}</span></>
                    : <span style={{ opacity: .6 }}>{live ? 'no destination set' : 'handed over'}</span>}
                </Tooltip>
              </Marker>
            </span>
          )
        })}
      </MapContainer>
      <div className="absolute left-3 bottom-3 z-[500] flex flex-wrap gap-3 text-[12px] text-dim bg-black/75 rounded px-2.5 py-1.5 pointer-events-none">
        {['RED', 'YELLOW', 'GREEN'].map(t => <span key={t} className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full" style={{ background: TRIAGE_COLOR[t] }} />{t[0] + t.slice(1).toLowerCase()}</span>)}
        <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full border border-faint" />Completed</span>
        <span className="flex items-center gap-1.5"><span className="w-3 h-0.5 bg-alarm" />Driven</span>
        <span className="flex items-center gap-1.5"><span className="w-3 h-0.5 bg-alarm/30" />Remaining road route</span>
      </div>
    </div>
  )
}


function AttributionText({ text }: { text: string }) {
  const map = useMap()
  useEffect(() => {
    map.attributionControl.setPrefix(false)
    map.attributionControl.addAttribution(text)
    return () => { map.attributionControl.removeAttribution(text) }
  }, [map, text])
  return null
}
