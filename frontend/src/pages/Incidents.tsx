import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Search } from 'lucide-react'
import { api, STATUS_LABEL } from '../lib/api'
import { Panel, Spinner, Status, Triage, useFetch } from '../components/ui'

export default function Incidents() {
  const { data } = useFetch(api.incidents, [], 8000)
  const [q, setQ] = useState('')
  const [st, setSt] = useState('all')
  const rows = useMemo(() => (data || []).filter((i: any) =>
    (st === 'all' || i.status === st) &&
    (!q || [i.dispatch_id, i.vehicle, i.complaint, i.place, i.crew].join(' ').toLowerCase().includes(q.toLowerCase()))), [data, q, st])
  return (
    <div className="max-w-[1600px] mx-auto space-y-4">
      <div>
        <h1 className="font-num text-[34px] font-semibold leading-none">Incidents</h1>
        <p className="text-dim mt-1.5">Electronic patient care records, newest first.</p>
      </div>
      <Panel title={`${rows.length} incidents`} actions={
        <div className="flex gap-2">
          <div className="relative"><Search size={15} className="absolute left-2.5 top-2.5 text-faint" />
            <input className="input pl-8 w-64" placeholder="Search dispatch, vehicle, complaint" value={q} onChange={e => setQ(e.target.value)} /></div>
          <select className="input w-40" value={st} onChange={e => setSt(e.target.value)}>
            <option value="all">All statuses</option>{Object.entries(STATUS_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </div>}>
        {!data ? <div className="py-10 flex justify-center"><Spinner /></div> : (
          <div className="overflow-x-auto -mx-4">
            <table className="tbl w-full min-w-[900px]">
              <thead><tr><th>Dispatch</th><th>Triage</th><th>Complaint</th><th>Scene</th><th>Crew</th><th>Destination</th><th>Doses</th><th>Flags</th><th>Status</th></tr></thead>
              <tbody>
                {rows.map((i: any) => (
                  <tr key={i.id} className="cursor-pointer" onClick={() => (location.href = `/incidents/${i.id}`)}>
                    <td><Link to={`/incidents/${i.id}`} className="font-medium hover:text-spo2">{i.dispatch_id}</Link><div className="text-[12px] text-faint">{new Date(i.created_at).toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })} · {i.vehicle}</div></td>
                    <td><Triage t={i.triage} /></td>
                    <td>{i.complaint || <span className="text-faint">Pending</span>}<div className="text-[12px] text-faint">{i.patient?.age != null ? `${i.patient.age} y ${i.patient.sex || ''}` : ''}</div></td>
                    <td className="text-dim">{i.place}</td>
                    <td className="text-dim">{i.crew}</td>
                    <td className="text-dim">{i.destination || '—'}</td>
                    <td className="num text-[16px]">{i.counts.meds}<span className="text-faint"> / {i.counts.procs}</span></td>
                    <td className="num text-[16px]" style={{ color: i.counts.flagged ? '#ffa733' : '#55626b' }}>{i.counts.flagged}</td>
                    <td><Status s={i.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  )
}
