import { Siren, Activity, Mic, Bot, Ambulance, Hospital, ShieldCheck, FlaskConical, BookOpen, RadioTower, Settings as Cog } from 'lucide-react'

export type NavItem = { to: string; label: string; icon: any; end?: boolean; right?: string; key: string; hint: string }

/** Sidebar groups. `key` is the second key of the "g then x" shortcut. */
export const NAV_GROUPS: { title: string; items: NavItem[] }[] = [
  {
    title: 'On the road',
    items: [
      { to: '/', label: 'Command centre', icon: Activity, end: true, key: 'h', hint: 'Live fleet, map, timers and alerts' },
      { to: '/capture', label: 'Capture', icon: Mic, right: 'capture', key: 'c', hint: 'Speak or type care, review, sign' },
      { to: '/copilot', label: 'Copilot', icon: Bot, key: 'a', hint: 'First-aid guidance that logs care' },
      { to: '/mci', label: 'Mass casualty', icon: Siren, key: 'x', hint: 'START triage tags and a live casualty board' },
    ],
  },
  {
    title: 'Hospital',
    items: [
      { to: '/incidents', label: 'Incidents', icon: Ambulance, key: 'i', hint: 'Every patient record on this device' },
      { to: '/handover', label: 'ED handover', icon: Hospital, key: 'e', hint: 'Inbound units, readiness, accept' },
    ],
  },
  {
    title: 'Records & safety',
    items: [
      { to: '/audit', label: 'Audit ledger', icon: ShieldCheck, key: 'l', hint: 'Signed, hash-chained history' },
      { to: '/lab', label: 'Model lab', icon: FlaskConical, key: 'm', hint: 'Accuracy of speech and extraction' },
      { to: '/lexicon', label: 'Drug lexicon', icon: BookOpen, key: 'd', hint: 'Drugs, doses and spoken aliases' },
    ],
  },
  {
    title: 'System',
    items: [
      { to: '/device', label: 'Sync & device', icon: RadioTower, key: 's', hint: 'Queue, hub, database, keys' },
      { to: '/settings', label: 'Settings', icon: Cog, key: 'p', hint: 'PIN, users, readiness, preferences' },
    ],
  },
]

export const NAV: NavItem[] = NAV_GROUPS.flatMap(g => g.items)

export function pageFor(path: string): NavItem | undefined {
  if (path.startsWith('/incidents/')) return NAV.find(n => n.to === '/incidents')
  return NAV.find(n => (n.end ? path === n.to : path.startsWith(n.to))) || NAV[0]
}
