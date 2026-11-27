import { useEffect, useRef } from 'react'

/** Sweep-style monitor trace (the signature element). Pure canvas, respects reduced motion. */
export function EcgTrace({ bpm = 78, color = '#3ee07f', height = 64, kind = 'ecg', className = '' }: {
  bpm?: number; color?: string; height?: number; kind?: 'ecg' | 'pleth' | 'resp'; className?: string
}) {
  const ref = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    const cv = ref.current!
    const ctx = cv.getContext('2d')!
    let raf = 0, x = 0, last = performance.now(), phase = 0
    const dpr = window.devicePixelRatio || 1
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const resize = () => {
      cv.width = cv.clientWidth * dpr; cv.height = height * dpr
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.fillStyle = '#000'; ctx.fillRect(0, 0, cv.clientWidth, height)
    }
    resize()
    const ro = new ResizeObserver(resize); ro.observe(cv)
    const wave = (p: number) => {
      // p in [0,1) of a cardiac cycle
      if (kind === 'pleth') return -(Math.max(0, Math.sin(p * Math.PI * 2 - .4)) ** 1.6) * .8 + (p > .45 && p < .6 ? -.12 * Math.sin((p - .45) / .15 * Math.PI) : 0)
      if (kind === 'resp') return -Math.sin(p * Math.PI * 2) * .55
      const g = (c: number, w: number, a: number) => a * Math.exp(-((p - c) ** 2) / (2 * w * w))
      return -(g(.12, .025, .12) - g(.2, .008, .1) + g(.225, .01, 1) - g(.25, .01, .25) + g(.45, .045, .22))
    }
    let prevY = height / 2
    const step = (now: number) => {
      const w = cv.clientWidth
      const dt = Math.min(64, now - last); last = now
      const pxPerMs = 0.085
      const cycleMs = kind === 'resp' ? 4200 : 60000 / bpm
      const n = Math.max(1, Math.round(dt * pxPerMs))
      for (let i = 0; i < n; i++) {
        phase = (phase + (1 / pxPerMs) / cycleMs) % 1
        const y = height / 2 + wave(phase) * height * 0.42
        ctx.fillStyle = '#000'
        ctx.fillRect(x + 1, 0, 14, height)
        ctx.strokeStyle = color; ctx.lineWidth = 1.8; ctx.lineJoin = 'round'
        ctx.shadowColor = color; ctx.shadowBlur = 6
        ctx.beginPath(); ctx.moveTo(x, prevY); ctx.lineTo(x + 1, y); ctx.stroke()
        ctx.shadowBlur = 0
        prevY = y; x += 1
        if (x > w) { x = 0 }
      }
      raf = requestAnimationFrame(step)
    }
    if (reduce) {
      ctx.strokeStyle = color; ctx.lineWidth = 1.6; ctx.beginPath()
      const w = cv.clientWidth
      for (let i = 0; i < w; i++) { const y = height / 2 + wave((i / 90) % 1) * height * .42; i ? ctx.lineTo(i, y) : ctx.moveTo(i, y) }
      ctx.stroke()
    } else raf = requestAnimationFrame(step)
    return () => { cancelAnimationFrame(raf); ro.disconnect() }
  }, [bpm, color, height, kind])
  return <canvas ref={ref} className={`w-full block ${className}`} style={{ height }} aria-hidden />
}
