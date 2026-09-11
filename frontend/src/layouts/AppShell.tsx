import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { useEffect, useState } from 'react';
import {
  LayoutDashboard,
  Plus,
  ClipboardList,
  AlertTriangle,
  ShieldCheck,
  Cpu,
  Moon,
  Sun,
  Globe,
  Wifi,
  WifiOff,
} from 'lucide-react';
import { motion } from 'framer-motion';
import { useTheme } from '../hooks/useTheme';
import { getHealth } from '../api/client';
import { NetworkError } from '../api/client';
import { cn } from '../lib/cn';

interface NavItem {
  to: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  end?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { to: '/',             label: 'Overview',       icon: LayoutDashboard, end: true },
  { to: '/new',          label: 'New Assessment', icon: Plus },
  { to: '/assessments',  label: 'Assessments',    icon: ClipboardList },
  { to: '/findings',     label: 'Findings',       icon: AlertTriangle },
  { to: '/audit',        label: 'Audit Trail',    icon: ShieldCheck },
  { to: '/capabilities', label: 'Capabilities',   icon: Cpu },
];

function SidebarNavItem({ item }: { item: NavItem }) {
  const Icon = item.icon;
  return (
    <NavLink
      to={item.to}
      end={item.end}
      className={({ isActive }) =>
        cn(
          'flex items-center gap-2.5 px-3 py-2 rounded text-sm transition-all duration-150',
          'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[var(--accent)]',
          isActive
            ? 'bg-[var(--accent-light)] text-[var(--accent)] font-medium'
            : 'text-[var(--text-secondary)] hover:bg-[var(--surface-2)] hover:text-[var(--text-primary)]',
        )
      }
    >
      <Icon className="w-4 h-4 flex-shrink-0" />
      <span>{item.label}</span>
    </NavLink>
  );
}

type BackendStatus = 'checking' | 'connected' | 'unavailable';

export function AppShell() {
  const { theme, toggle } = useTheme();
  const [backendStatus, setBackendStatus] = useState<BackendStatus>('checking');
  const location = useLocation();

  // Poll backend health
  useEffect(() => {
    let mounted = true;
    const check = async () => {
      try {
        await getHealth();
        if (mounted) setBackendStatus('connected');
      } catch (err) {
        if (mounted) setBackendStatus(err instanceof NetworkError ? 'unavailable' : 'connected');
      }
    };
    check();
    const id = setInterval(check, 30_000);
    return () => { mounted = false; clearInterval(id); };
  }, []);

  return (
    <div className="flex h-screen overflow-hidden bg-[var(--surface-0)]">
      {/* Sidebar */}
      <aside
        className="flex flex-col w-[224px] flex-shrink-0 border-r border-[var(--border)] bg-[var(--surface-1)]"
        aria-label="Main navigation"
      >
        {/* Brand */}
        <div className="px-4 pt-5 pb-4 border-b border-[var(--border)]">
          <div className="flex items-center gap-2">
            <div className="flex items-center justify-center w-7 h-7 rounded bg-[var(--accent)] flex-shrink-0">
              <ShieldCheck className="w-4 h-4 text-white" />
            </div>
            <div>
              <p className="text-sm font-bold text-[var(--text-primary)] leading-tight tracking-tight">
                PRAMAAN
              </p>
              <p className="text-[10px] text-[var(--text-muted)] leading-tight">
                Evidence Before Trust
              </p>
            </div>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-2 py-3 space-y-0.5 overflow-y-auto">
          {NAV_ITEMS.map((item) => (
            <SidebarNavItem key={item.to} item={item} />
          ))}
        </nav>

        {/* Bottom utility area */}
        <div className="px-3 py-3 border-t border-[var(--border)] space-y-1.5">
          {/* Backend status */}
          <div className="flex items-center gap-2 px-1 py-1">
            {backendStatus === 'checking' && (
              <div className="w-2 h-2 rounded-full bg-[var(--text-muted)] animate-pulse" />
            )}
            {backendStatus === 'connected' && (
              <Wifi className="w-3.5 h-3.5 text-[var(--risk-none)]" />
            )}
            {backendStatus === 'unavailable' && (
              <WifiOff className="w-3.5 h-3.5 text-[var(--risk-critical)]" />
            )}
            <span className="text-xs text-[var(--text-muted)]">
              {backendStatus === 'checking' && 'Connecting…'}
              {backendStatus === 'connected' && 'Backend connected'}
              {backendStatus === 'unavailable' && 'Backend unavailable'}
            </span>
          </div>

          {/* Theme toggle */}
          <button
            onClick={toggle}
            className="flex items-center gap-2 w-full px-1 py-1 rounded text-xs text-[var(--text-secondary)] hover:bg-[var(--surface-2)] hover:text-[var(--text-primary)] transition-colors duration-150"
            aria-label={`Switch to ${theme === 'light' ? 'dark' : 'light'} mode`}
          >
            <motion.span
              key={theme}
              initial={{ opacity: 0, rotate: -30 }}
              animate={{ opacity: 1, rotate: 0 }}
              transition={{ duration: 0.2 }}
              className="flex-shrink-0"
            >
              {theme === 'light' ? <Moon className="w-3.5 h-3.5" /> : <Sun className="w-3.5 h-3.5" />}
            </motion.span>
            <span>{theme === 'light' ? 'Dark mode' : 'Light mode'}</span>
          </button>

          {/* Language selector — visual only, translation deferred */}
          <button
            className="flex items-center gap-2 w-full px-1 py-1 rounded text-xs text-[var(--text-muted)] hover:bg-[var(--surface-2)] transition-colors duration-150 cursor-default"
            aria-label="Language selector — English (additional languages coming soon)"
            title="Additional languages will be available in a future update"
            onClick={(e) => e.preventDefault()}
          >
            <Globe className="w-3.5 h-3.5 flex-shrink-0" />
            <span>EN · English</span>
          </button>
        </div>
      </aside>

      {/* Main content area */}
      <main className="flex-1 overflow-y-auto" id="main-content">
        <motion.div
          key={location.pathname}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.2 }}
          className="min-h-full"
        >
          <Outlet />
        </motion.div>
      </main>
    </div>
  );
}
