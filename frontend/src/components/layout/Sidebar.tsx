import { Link, useLocation } from 'react-router-dom'
import { 
  LayoutDashboard, 
  FileText, 
  Link2, 
  MessageSquareCode, 
  Lock,
  type LucideIcon
} from 'lucide-react'

interface NavItem {
  id: string
  label: string
  path: string
  icon: LucideIcon
  badge?: string
}

const NAV_ITEMS: NavItem[] = [
  { id: 'dashboard', label: 'Dashboard', path: '/dashboard', icon: LayoutDashboard },
  { id: 'report', label: 'Assurance Report', path: '/report', icon: FileText },
  { id: 'audit', label: 'Audit Chain', path: '/audit-chain', icon: Link2 },
  { id: 'copilot', label: 'PRAMAAN Copilot', path: '/copilot', icon: MessageSquareCode, badge: 'AI' },
]

export const Sidebar: React.FC = () => {
  const location = useLocation()

  return (
    <aside className="w-16 md:w-18 flex-shrink-0 h-screen bg-[#0B1F3A]/90 backdrop-blur-xl border-r border-[#4F81BD]/20 flex flex-col items-center py-5 justify-between z-30 select-none">
      {/* Brand Wordmark — clickable home link */}
      <div className="flex flex-col items-center gap-6">
        <Link
          to="/"
          title="PRAMAAN — Back to home"
          className="group relative flex flex-col items-center gap-0.5 px-1 py-2 rounded-xl hover:bg-[#1F497D]/20 transition-all duration-200"
        >
          <span className="text-[11px] font-header font-black tracking-[0.18em] text-[#C9A24B] group-hover:text-[#d6b059] transition-colors leading-none">
            PR
          </span>
          <span className="text-[11px] font-header font-black tracking-[0.18em] text-[#C9A24B] group-hover:text-[#d6b059] transition-colors leading-none">
            AM
          </span>
          <span className="text-[11px] font-header font-black tracking-[0.18em] text-[#C9A24B] group-hover:text-[#d6b059] transition-colors leading-none">
            AN
          </span>
          {/* Tooltip */}
          <div className="absolute left-full ml-3 top-1/2 -translate-y-1/2 px-2.5 py-1 bg-[#0B1F3A]/95 backdrop-blur-md border border-[#4F81BD]/30 rounded-md text-[11px] font-medium text-[#F4F6F9] whitespace-nowrap opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity z-50 shadow-xl">
            Home
          </div>
        </Link>

        {/* Divider */}
        <div className="w-8 h-[1px] bg-[#4F81BD]/20" />

        {/* Primary Navigation Icons */}
        <nav className="flex flex-col items-center gap-3">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon
            const isActive = location.pathname === item.path || (item.id === 'dashboard' && location.pathname === '/')

            return (
              <div key={item.id} className="relative group">
                <Link
                  to={item.path}
                  aria-label={item.label}
                  className={`relative flex items-center justify-center w-11 h-11 rounded-xl transition-all duration-200 ${
                    isActive
                      ? 'bg-[#1F497D]/50 text-[#C9A24B] border border-[#C9A24B]/60 shadow-[0_0_14px_rgba(201,162,75,0.25)]'
                      : 'text-[#F4F6F9]/60 hover:text-[#F4F6F9] hover:bg-[#1F497D]/30 border border-transparent hover:border-[#4F81BD]/30'
                  }`}
                >
                  <Icon className="w-5 h-5" />

                  {/* Active Indicator Bar */}
                  {isActive && (
                    <span className="absolute -left-[18px] top-1/2 -translate-y-1/2 w-1 h-5 rounded-r bg-[#C9A24B] shadow-[0_0_8px_#C9A24B]" />
                  )}

                  {/* Optional Mini Badge */}
                  {item.badge && (
                    <span className="absolute -top-1 -right-1 px-1 text-[8px] font-mono font-bold bg-[#1F497D] text-[#4F81BD] border border-[#4F81BD]/40 rounded-full">
                      {item.badge}
                    </span>
                  )}
                </Link>

                {/* Tooltip */}
                <div className="absolute left-full ml-3 top-1/2 -translate-y-1/2 px-2.5 py-1 bg-[#0B1F3A]/95 backdrop-blur-md border border-[#4F81BD]/30 rounded-md text-[11px] font-medium text-[#F4F6F9] whitespace-nowrap opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity z-50 shadow-xl">
                  {item.label}
                  {isActive && <span className="ml-1.5 text-[9px] font-mono text-[#C9A24B]">(ACTIVE)</span>}
                </div>
              </div>
            )
          })}
        </nav>
      </div>

      {/* Bottom: Air-gap status lock only */}
      <div className="flex flex-col items-center gap-3">
        <div
          className="p-2 rounded-lg bg-[#0B1F3A] border border-[#4F81BD]/20 text-[#4F81BD]/70"
          title="Air-gapped verification node — no external network calls"
        >
          <Lock className="w-3.5 h-3.5 text-[#3F7D4F]" />
        </div>
      </div>
    </aside>
  )
}

export default Sidebar
