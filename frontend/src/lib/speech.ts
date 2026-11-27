import { api, ROUTE_LABEL } from './api'

/** Spoken read-back with the operating system's built-in (offline) voices, plus a short
 *  voice-confirm capture transcribed by the on-device Whisper. */
const KEY = 'fs_readback'
export const readbackOn = () => { try { return localStorage.getItem(KEY) === '1' } catch { return false } }
export const setReadback = (on: boolean) => { try { localStorage.setItem(KEY, on ? '1' : '0') } catch { /* noop */ } window.dispatchEvent(new Event('fs:readback')) }

const UNIT_SAY: Record<string, string> = { mg: 'milligrams', mcg: 'micrograms', g: 'grams', mL: 'millilitres', L: 'litres', 'L/min': 'litres per minute', units: 'units', tab: 'tablets', puffs: 'puffs' }

export function sayable(text: string) {
  return text
    .replace(/(\d+(?:\.\d+)?)\s*(mcg|mg|mL|L\/min|g|L)\b/g, (_, n, u) => `${n} ${UNIT_SAY[u] || u}`)
    .replace(/\bSpO₂|\bspo2\b/gi, 'S P O 2').replace(/\bGCS\b/g, 'G C S').replace(/\bECG\b/g, 'E C G')
    .replace(/[•·→]/g, ', ').replace(/\s+/g, ' ').trim()
}

let voice: SpeechSynthesisVoice | null = null
function pickVoice() {
  const vs = window.speechSynthesis?.getVoices() || []
  voice = vs.find(v => /en-IN/i.test(v.lang) && v.localService) || vs.find(v => /en-(GB|US)/i.test(v.lang) && v.localService) || vs.find(v => /^en/i.test(v.lang)) || null
}
if (typeof window !== 'undefined' && window.speechSynthesis) { pickVoice(); window.speechSynthesis.onvoiceschanged = pickVoice }

export function speak(text: string, force = false): Promise<void> {
  return new Promise(res => {
    if ((!force && !readbackOn()) || !window.speechSynthesis) return res()
    window.speechSynthesis.cancel()
    const u = new SpeechSynthesisUtterance(sayable(text))
    if (voice) u.voice = voice
    u.rate = 1.05
    u.onend = () => res(); u.onerror = () => res()
    window.speechSynthesis.speak(u)
  })
}

export function entrySentence(e: any): string {
  const f = e.fields ? Object.fromEntries(Object.entries(e.fields).map(([k, v]: any) => [k, v?.value])) : (e.payload || e)
  if (e.kind === 'procedure') return `${f.procedure}${f.time ? ` at ${f.time}` : ''}`
  const dose = f.rate ? f.rate : f.dose != null ? `${f.dose} ${f.unit || ''}` : 'dose not stated'
  const held = e.status === 'withheld' || e.negated
  return `${f.drug}, ${dose}, ${ROUTE_LABEL[f.route] || f.route || 'route not stated'}${f.time ? `, at ${f.time}` : ''}${held ? ', withheld' : ''}`
}

/** Record a few seconds and decide confirm / cancel / unclear. */
export async function listenConfirm(seconds = 4): Promise<'confirm' | 'cancel' | null> {
  let stream: MediaStream
  try { stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } }) } catch { return null }
  const mr = new MediaRecorder(stream)
  const chunks: BlobPart[] = []
  mr.ondataavailable = e => chunks.push(e.data)
  const done = new Promise<void>(r => { mr.onstop = () => r() })
  mr.start(); beep(880, 0.08)
  await new Promise(r => setTimeout(r, seconds * 1000))
  mr.stop(); stream.getTracks().forEach(t => t.stop())
  await done
  try {
    const r: any = await api.asr(new Blob(chunks, { type: mr.mimeType || 'audio/webm' }))
    const t = (r.text || '').toLowerCase()
    if (/\b(cancel|no|stop|wait|don'?t|nahi|nahin|beda)\b/.test(t)) return 'cancel'
    if (/\b(confirm|confirmed|yes|yeah|sign|ok|okay|correct|haan|ha|houdu|sari)\b/.test(t)) return 'confirm'
    return null
  } catch { return null }
}

let ac: AudioContext | null = null
export function beep(freq = 660, dur = 0.15, times = 1) {
  try {
    ac = ac || new AudioContext()
    for (let i = 0; i < times; i++) {
      const o = ac.createOscillator(), g = ac.createGain()
      o.frequency.value = freq; o.type = 'sine'
      const t0 = ac.currentTime + i * (dur + 0.08)
      g.gain.setValueAtTime(0.0001, t0); g.gain.exponentialRampToValueAtTime(0.25, t0 + 0.01); g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur)
      o.connect(g).connect(ac.destination); o.start(t0); o.stop(t0 + dur + 0.02)
    }
  } catch { /* audio unavailable */ }
}
