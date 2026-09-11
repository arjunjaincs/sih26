import { NavLink, Outlet, useLocation, Link } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Moon, Sun, Globe } from 'lucide-react';
import { useTheme } from '../hooks/useTheme';
import { getHealth, NetworkError } from '../api/client';
import { cn } from '../lib/cn';

const NAV_LINKS = [
  { to: '/', label: 'Home', end: true },
  { to: '/new', label: 'Assess' },
  { to: '/capabilities', label: 'Capabilities' },
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

  return (
    <div className="min-h-screen bg-bg flex flex-col">
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
                    'px-3 py-1.5 rounded text-sm transition-colors duration-150',
                    isActive
                      ? 'text-accent font-medium'
                      : 'text-2 hover:text-1',
                  )
                }
              >
                {link.label}
              </NavLink>
            ))}
          </nav>

          {/* Right controls */}
          <div className="flex items-center gap-3 flex-shrink-0">
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

            {/* Lang */}
            <button
              className="flex items-center gap-1 text-xs text-3 hover:text-1 transition-colors"
              title="Language (additional languages coming soon)"
            >
              <Globe className="w-3.5 h-3.5" />
              <span>EN</span>
            </button>

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

            {/* CTA */}
            <Link
              to="/new"
              className="px-3.5 py-1.5 rounded bg-accent text-white text-xs font-semibold hover:bg-[var(--accent-2)] transition-colors"
            >
              Get Started
            </Link>
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
    </div>
  );
}
