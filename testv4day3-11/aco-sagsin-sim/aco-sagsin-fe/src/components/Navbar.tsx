import { Link, useLocation } from 'react-router-dom'

export default function Navbar() {
  const loc = useLocation()
  const active = (p: string) => (loc.pathname.startsWith(p) ? 'text-white' : 'text-slate-400 hover:text-white')
  return (
    <nav className="sticky top-0 z-10 w-full bg-slate-900/80 backdrop-blur border-b border-slate-800">
      <div className="max-w-7xl mx-auto px-4 py-3 flex items-center gap-6">
        <div className="font-bold">SAGSIN ACO</div>
        <Link className={active('/data')} to="/data">Data</Link>
        <Link className={active('/route')} to="/route">Route</Link>
        <Link className={active('/packet')} to="/packet">Packet</Link>
      </div>
    </nav>
  )
}
