import { NavLink, Outlet, useLocation, Link } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Moon, Sun, ShieldCheck, Search } from 'lucide-react';
import { useTheme } from '../hooks/useTheme';
import { getHealth, NetworkError } from '../api/client';
import { GlobalSearchModal } from '../components/GlobalSearchModal';
import { cn } from '../lib/cn';

const NAV_LINKS = [
  { to: '/', label: 'Home', end: true },
  { to: '/new', label: 'Assess' },
  { to: '/assessments', label: 'History' },
  { to: '/capabilities', label: 'Capabilities' },
  { to: '/settings', label: 'Settings' },
];

type BackendStatus = 'checking' | 'ok' | 'down';

function PramaanShield({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 28" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path
        d="M12 1L2 5.5V13.5C2 19.3 6.4 24.7 12 26.5C17.6 24.7 22 19.3 22 13.5V5.5L12 1Z"
        stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" fill="none"
      />
      <path d="M8 13.5L10.5 16L16 10.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  );
}

export function AppShell() {
  const { theme, toggle } = useTheme();
  const [status, setStatus] = useState<BackendStatus>('checking');
  const [searchOpen, setSearchOpen] = useState(false);
  const location = useLocation();

  useEffect(() => {
    let mounted = true;
    const check = async () => {
      try {
        await getHealth();
        if (mounted) setStatus('ok');
      } catch (err) {
        if (mounted) setStatus(err instanceof NetworkError ? 'down' : 'ok');
      }
    };
    check();
    const id = setInterval(check, 30_000);
    return () => { mounted = false; clearInterval(id); };
  }, []);

  // Global keyboard shortcuts (Ctrl+K and / when outside text inputs)
  useEffect(() => {
    function handleGlobalKeyDown(e: KeyboardEvent) {
      // Ctrl/Cmd + K
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setSearchOpen((prev) => !prev);
        return;
      }

      // '/' shortcut to open search if user is not currently in an input/textarea
      if (e.key === '/' && !e.ctrlKey && !e.metaKey && !e.altKey) {
        const target = e.target as HTMLElement | null;
        if (target && target.tagName) {
          const tag = target.tagName.toLowerCase();
          if (tag === 'input' || tag === 'textarea' || tag === 'select' || target.isContentEditable) {
            return; // Preserve browser-native typing in inputs
          }
        }
        e.preventDefault();
        setSearchOpen(true);
      }
    }

    window.addEventListener('keydown', handleGlobalKeyDown);
    return () => window.removeEventListener('keydown', handleGlobalKeyDown);
  }, []);

  // Route change focus management: scroll top and focus main content landmark to avoid focus loss
  useEffect(() => {
    window.scrollTo(0, 0);
    const mainEl = document.getElementById('main-content');
    if (mainEl) {
      mainEl.setAttribute('tabindex', '-1');
      mainEl.focus({ preventScroll: true });
    }
  }, [location.pathname]);

  return (
    <div className="min-h-screen bg-bg flex flex-col">
      {/* Accessible skip link */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[100] px-3 py-1.5 rounded-lg bg-accent text-white font-semibold text-xs shadow-lg focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-accent"
      >
        Skip to main content
      </a>
      {/* Top navigation */}
      <header className="fixed top-0 inset-x-0 z-50 h-12 border-b border-[var(--border)] bg-surface nav-blur">
        <div className="max-w-7xl mx-auto h-full px-6 flex items-center justify-between gap-8">
          {/* Brand */}
          <Link to="/" className="flex items-center gap-2 flex-shrink-0 group">
            <PramaanShield className="w-5 h-6 text-accent group-hover:text-accent transition-colors" />
            <span className="text-sm font-bold tracking-tight text-1">PRAMAAN</span>
          </Link>

          {/* Nav links */}
          <nav className="flex items-center gap-1" aria-label="Primary navigation">
            {NAV_LINKS.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                end={link.end}
                className={({ isActive }) =>
                  cn(
                    'px-3 py-1.5 rounded-lg text-xs sm:text-sm font-medium transition-all duration-150',
                    isActive
                      ? 'bg-surface-2/80 text-accent font-semibold border border-[var(--border)] shadow-sm'
                      : 'text-2 hover:text-1 hover:bg-surface-2/50 border border-transparent',
                  )
                }
              >
                {link.label}
              </NavLink>
            ))}
          </nav>

          {/* Right controls */}
          <div className="flex items-center gap-2.5 sm:gap-3 flex-shrink-0">
            {/* Global Search Trigger */}
            <button
              type="button"
              id="global-search-btn"
              onClick={() => setSearchOpen(true)}
              aria-label="Open global search (Ctrl+K)"
              className="flex items-center gap-2 px-2.5 py-1 rounded-lg bg-surface-2/80 hover:bg-surface-2 border border-[var(--border)] text-xs text-3 hover:text-1 transition-colors group"
            >
              <Search className="w-3.5 h-3.5 text-3 group-hover:text-accent transition-colors" />
              <span className="hidden md:inline">Search PRAMAAN…</span>
              <kbd className="hidden sm:inline-flex items-center gap-0.5 font-mono text-[10px] text-3 px-1.5 py-0.2 rounded bg-surface border border-[var(--border)]">
                Ctrl K
              </kbd>
            </button>

            {/* Backend status */}
            <div className="flex items-center gap-1.5" title={
              status === 'ok' ? 'Backend connected' :
              status === 'down' ? 'Backend unavailable' : 'Connecting…'
            }>
              <div className={cn(
                'w-1.5 h-1.5 rounded-full transition-colors duration-300',
                status === 'ok' ? 'bg-[var(--green)]' :
                status === 'down' ? 'bg-[var(--red)]' :
                'bg-text4 animate-pulse',
              )} />
              <span className="text-xs text-3 hidden sm:block">
                {status === 'ok' ? 'Live' : status === 'down' ? 'Offline' : '…'}
              </span>
            </div>

            {/* Air-Gapped Mode Badge */}
            <div
              className="flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-mono font-medium bg-surface-2 border border-[var(--border)] text-2 select-none"
              title="Air-Gapped: Fully offline operation with zero outbound network calls"
            >
              <ShieldCheck className="w-3.5 h-3.5 text-accent" />
              <span className="hidden sm:inline">Air-Gapped</span>
            </div>

            {/* Theme toggle */}
            <button
              onClick={toggle}
              aria-label={`Switch to ${theme === 'light' ? 'dark' : 'light'} mode`}
              className="flex items-center justify-center w-7 h-7 rounded hover:bg-surface-2 text-3 hover:text-1 transition-colors"
            >
              <motion.span
                key={theme}
                initial={{ opacity: 0, rotate: -20 }}
                animate={{ opacity: 1, rotate: 0 }}
                transition={{ duration: 0.18 }}
              >
                {theme === 'light' ? <Moon className="w-4 h-4" /> : <Sun className="w-4 h-4" />}
              </motion.span>
            </button>
          </div>
        </div>
      </header>

      {/* Page content */}
      <main className="flex-1 pt-12" id="main-content">
        <motion.div
          key={location.pathname}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.18, ease: 'easeOut' }}
          className="min-h-[calc(100vh-3rem)]"
        >
          <Outlet />
        </motion.div>
      </main>

      {/* Global Search Dialog */}
      <GlobalSearchModal isOpen={searchOpen} onClose={() => setSearchOpen(false)} />
    </div>
  );
}
