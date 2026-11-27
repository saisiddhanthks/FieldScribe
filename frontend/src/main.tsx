import React, { lazy, Suspense } from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import './index.css'
import { Shell } from './components/Shell'
import { ToastHost } from './components/ui'
import { AuthGate } from './components/Auth'
import { CommandHost } from './components/Command'
import { Spinner } from './components/ui'

const Command = lazy(() => import('./pages/Command'))
const Capture = lazy(() => import('./pages/Capture'))
const Incidents = lazy(() => import('./pages/Incidents'))
const IncidentDetail = lazy(() => import('./pages/IncidentDetail'))
const Handover = lazy(() => import('./pages/Handover'))
const Audit = lazy(() => import('./pages/Audit'))
const Lab = lazy(() => import('./pages/Lab'))
const Lexicon = lazy(() => import('./pages/Lexicon'))
const Device = lazy(() => import('./pages/Device'))
const Copilot = lazy(() => import('./pages/Copilot'))
const Settings = lazy(() => import('./pages/Settings'))
const Mci = lazy(() => import('./pages/Mci'))

// Installable app: keep the browser's install prompt so Settings and the command bar can offer it
window.addEventListener('beforeinstallprompt', (e: any) => {
  e.preventDefault()
  ;(window as any).__fsInstallReady = true
  ;(window as any).__fsInstall = async () => { e.prompt(); await e.userChoice; (window as any).__fsInstallReady = false; window.dispatchEvent(new Event('fs:installable')) }
  window.dispatchEvent(new Event('fs:installable'))
})
if ('serviceWorker' in navigator && location.protocol !== 'file:' && !(import.meta as any).env?.DEV) {
  window.addEventListener('load', () => navigator.serviceWorker.register('/sw.js').catch(() => {}))
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <ToastHost>
        <AuthGate>
        <CommandHost>
        <Shell>
          <Suspense fallback={<div className="h-[60vh] flex items-center justify-center text-dim gap-2"><Spinner />Loading…</div>}>
          <Routes>
            <Route path="/" element={<Command />} />
            <Route path="/capture" element={<Capture />} />
            <Route path="/copilot" element={<Copilot />} />
            <Route path="/incidents" element={<Incidents />} />
            <Route path="/incidents/:id" element={<IncidentDetail />} />
            <Route path="/handover" element={<Handover />} />
            <Route path="/audit" element={<Audit />} />
            <Route path="/lab" element={<Lab />} />
            <Route path="/lexicon" element={<Lexicon />} />
            <Route path="/device" element={<Device />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="/mci" element={<Mci />} />
            <Route path="*" element={<Command />} />
          </Routes>
          </Suspense>
        </Shell>
        </CommandHost>
        </AuthGate>
      </ToastHost>
    </BrowserRouter>
  </React.StrictMode>,
)
