import { asrLang } from './lang'

const BASE = (import.meta as any).env?.VITE_API_BASE || ''

async function req<T = any>(path: string, opts: RequestInit = {}): Promise<T> {
  const r = await fetch(BASE + path, {
    credentials: 'same-origin',
    ...opts,
    headers: opts.body instanceof FormData ? opts.headers : { 'Content-Type': 'application/json', ...(opts.headers || {}) },
  })
  if (r.status === 401 && !path.startsWith('/api/auth/')) window.dispatchEvent(new Event('fs:auth'))
  if (!r.ok) {
    let msg = r.statusText
    try { const j = await r.json(); msg = j.detail || JSON.stringify(j) } catch { /* noop */ }
    throw new Error(msg)
  }
  const ct = r.headers.get('content-type') || ''
  return (ct.includes('json') ? r.json() : r.blob()) as Promise<T>
}

export const api = {
  authUsers: () => req('/api/auth/users'),
  login: (user_id: string, pin: string) => req('/api/auth/login', { method: 'POST', body: JSON.stringify({ user_id, pin }) }),
  logout: () => req('/api/auth/logout', { method: 'POST' }),
  me: () => req('/api/auth/me'),
  changePin: (old: string, pin: string) => req('/api/auth/pin', { method: 'POST', body: JSON.stringify({ old, new: pin }) }),
  adminUsers: () => req<any[]>('/api/admin/users'),
  adminCreate: (b: { id: string; name: string; role: string; pin: string }) => req('/api/admin/users', { method: 'POST', body: JSON.stringify(b) }),
  adminPatch: (id: string, b: any) => req(`/api/admin/users/${id}`, { method: 'PATCH', body: JSON.stringify(b) }),
  healthChecks: () => req('/api/health/checks'),
  destinations: (id: string) => req(`/api/incidents/${id}/destinations`),
  setPatient: (id: string, b: any) => req(`/api/incidents/${id}/patient`, { method: 'POST', body: JSON.stringify(b) }),
  setMlc: (id: string, b: any) => req(`/api/incidents/${id}/mlc`, { method: 'POST', body: JSON.stringify(b) }),
  setRefusal: (id: string, b: any) => req(`/api/incidents/${id}/refusal`, { method: 'POST', body: JSON.stringify(b) }),
  access: (id: string) => req<any[]>(`/api/incidents/${id}/access`),
  mci: () => req('/api/mci'),
  mciStart: (b: any) => req('/api/mci', { method: 'POST', body: JSON.stringify(b) }),
  mciAdd: (eid: string, b: any) => req(`/api/mci/${eid}/casualty`, { method: 'POST', body: JSON.stringify(b) }),
  mciRetriage: (iid: string, triage: string) => req(`/api/mci/retriage/${iid}`, { method: 'POST', body: JSON.stringify({ triage }) }),
  mciClose: (eid: string) => req(`/api/mci/${eid}/close`, { method: 'POST' }),
  amend: (eid: string, fields: any, reason: string) => req(`/api/entries/${eid}/amend`, { method: 'POST', body: JSON.stringify({ fields, reason }) }),
  voidEntry: (eid: string, reason: string) => req(`/api/entries/${eid}/void`, { method: 'POST', body: JSON.stringify({ reason }) }),
  completeness: (id: string) => req(`/api/incidents/${id}/completeness`),
  clock: (id: string) => req(`/api/incidents/${id}/clock`),
  clockAll: () => req('/api/clock'),
  system: () => req('/api/system'),
  analytics: () => req('/api/analytics'),
  incidents: () => req<any[]>('/api/incidents'),
  incident: (id: string) => req(`/api/incidents/${id}`),
  createIncident: (b: any) => req('/api/incidents', { method: 'POST', body: JSON.stringify(b) }),
  patchIncident: (id: string, b: any) => req(`/api/incidents/${id}`, { method: 'PATCH', body: JSON.stringify(b) }),
  extract: (text: string, incident_id?: string) => req('/api/extract', { method: 'POST', body: JSON.stringify({ text, incident_id }) }),
  asr: (blob: Blob, language: string = asrLang()) => {
    const fd = new FormData()
    fd.append('file', blob, 'dictation.webm')
    fd.append('language', language)
    return req('/api/asr', { method: 'POST', body: fd })
  },
  asrWarmup: () => req('/api/asr/warmup', { method: 'POST' }),
  sign: (id: string, b: any) => req(`/api/incidents/${id}/records`, { method: 'POST', body: JSON.stringify(b) }),
  handover: (id: string, received_by: string) => req(`/api/incidents/${id}/handover`, { method: 'POST', body: JSON.stringify({ received_by }) }),
  fhir: (id: string) => req(`/api/incidents/${id}/fhir`),
  fhirLite: (id: string) => req(`/api/incidents/${id}/fhir-lite`),
  pdfUrl: (id: string) => `${BASE}/api/incidents/${id}/pdf`,
  hubEdit: (id: string) => req(`/api/incidents/${id}/hub-edit`, { method: 'POST' }),
  ledger: (incident_id?: string) => req<any[]>(`/api/ledger${incident_id ? `?incident_id=${incident_id}` : ''}`),
  verify: () => req('/api/ledger/verify'),
  tamper: () => req('/api/ledger/tamper', { method: 'POST' }),
  restore: () => req('/api/ledger/restore', { method: 'POST' }),
  sync: () => req('/api/sync'),
  runSync: () => req('/api/sync/run', { method: 'POST' }),
  setOnline: (online: boolean) => req('/api/settings/online', { method: 'POST', body: JSON.stringify({ online }) }),
  evalCodemix: () => req('/api/eval/codemix'),
  tlsStatus: () => req('/api/tls/status'),
  localai: () => req('/api/localai'),
  localaiStart: () => req('/api/localai/start', { method: 'POST' }),
  localaiPull: (model: string) => req('/api/localai/pull', { method: 'POST', body: JSON.stringify({ model }) }),
  localaiProgress: () => req('/api/localai/progress'),
  localaiTest: () => req('/api/localai/test', { method: 'POST' }),
  localaiPrefer: (on: boolean) => req('/api/localai/prefer', { method: 'POST', body: JSON.stringify({ on }) }),
  evalCompare: (refresh = false) => req(`/api/eval/compare${refresh ? '?refresh=true' : ''}`),
  eval: (refresh = false) => req(`/api/eval${refresh ? '?refresh=true' : ''}`),
  wer: (reference: string, hypothesis: string) => req('/api/wer', { method: 'POST', body: JSON.stringify({ reference, hypothesis }) }),
  lexicon: () => req('/api/lexicon'),
  reference: () => req('/api/reference'),
  routes: () => req('/api/routes'),
  mapStatus: () => req('/api/map/status'),
  mapData: () => req('/api/map/data'),
  reseed: () => req('/api/admin/reseed', { method: 'POST' }),
  agentStatus: () => req('/api/agent/status'),
  agentChat: (messages: any[], incident_id?: string, signer?: string, prefer?: string) =>
    req('/api/agent/chat', { method: 'POST', body: JSON.stringify({ messages, incident_id, signer, prefer }) }),
  agentConfirm: (pending: any, signer?: string) => req('/api/agent/confirm', { method: 'POST', body: JSON.stringify({ pending, signer }) }),
}

export function download(name: string, data: any) {
  const blob = new Blob([typeof data === 'string' ? data : JSON.stringify(data, null, 2)], { type: 'application/json' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = name
  a.click()
  setTimeout(() => URL.revokeObjectURL(a.href), 2000)
}

export const STATUS_LABEL: Record<string, string> = {
  on_scene: 'On scene', transporting: 'Transporting', handed_over: 'Handed over', closed: 'Closed',
}
export const TRIAGE_COLOR: Record<string, string> = {
  RED: '#ff4b4b', YELLOW: '#f3cf3a', GREEN: '#3ee07f', BLACK: '#8a979f', UNTRIAGED: '#55626b',
}
export const ROUTE_LABEL: Record<string, string> = {
  PO: 'Oral', IV: 'Intravenous', IM: 'Intramuscular', SL: 'Sublingual', SC: 'Subcutaneous', IO: 'Intraosseous',
  NEB: 'Nebulised', INH: 'Inhaled', IN: 'Intranasal', PR: 'Rectal', TOP: 'Topical',
}
export const VITAL_COLOR: Record<string, string> = {
  hr: '#3ee07f', spo2: '#35d0f0', bp: '#f2f4f5', rr: '#f3cf3a', gcs: '#c08bff', glucose: '#ffa733', temp: '#ff8f6b', pain: '#ff6b9a', pupils: '#8a979f',
}
export const VITAL_LABEL: Record<string, string> = {
  hr: 'HR', spo2: 'SpO₂', bp: 'NIBP', rr: 'Resp', gcs: 'GCS', glucose: 'GRBS', temp: 'Temp', pain: 'Pain', pupils: 'Pupils',
}
