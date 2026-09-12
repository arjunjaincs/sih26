import { NavLink, Link } from 'react-router-dom';
import { ArrowLeft, CheckCircle, AlertTriangle, ShieldCheck, FileText } from 'lucide-react';
import { cn } from '../lib/cn';

interface AssessmentSubNavProps {
  assessmentId: string;
  findingsCount?: number;
  evidenceCount?: number;
  chainValid?: boolean | null;
}

export function AssessmentSubNav({
  assessmentId,
  findingsCount,
  evidenceCount,
  chainValid,
}: AssessmentSubNavProps) {
  const tabs = [
    {
      to: `/assessments/${assessmentId}/result`,
      label: 'Results',
      icon: FileText,
      badge: null,
    },
    {
      to: `/assessments/${assessmentId}/findings`,
      label: 'Findings',
      icon: AlertTriangle,
      badge: findingsCount !== undefined ? findingsCount : null,
    },
    {
      to: `/assessments/${assessmentId}/evidence`,
      label: 'Evidence',
      icon: CheckCircle,
      badge: evidenceCount !== undefined ? evidenceCount : null,
    },
    {
      to: `/assessments/${assessmentId}/audit`,
      label: 'Audit Trail',
      icon: ShieldCheck,
      badge: chainValid === true ? 'Valid' : chainValid === false ? 'Invalid' : null,
    },
  ];

  return (
    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-[var(--border)] pb-3 mb-6">
      <Link
        to="/assessments"
        className="inline-flex items-center gap-1.5 text-xs text-3 hover:text-1 transition-colors w-fit focus-visible:ring-1"
      >
        <ArrowLeft className="w-3.5 h-3.5" />
        <span>Back to Assessments</span>
      </Link>

      <nav className="flex items-center gap-1.5 overflow-x-auto" aria-label="Assessment views">
        {tabs.map(tab => {
          const Icon = tab.icon;
          return (
            <NavLink
              key={tab.to}
              to={tab.to}
              className={({ isActive }) =>
                cn(
                  'inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-150 whitespace-nowrap',
                  isActive
                    ? 'bg-surface border border-accent/40 text-1 shadow-sm font-semibold'
                    : 'text-2 hover:text-1 hover:bg-surface-2 border border-transparent'
                )
              }
            >
              <Icon className="w-3.5 h-3.5 text-accent" />
              <span>{tab.label}</span>
              {tab.badge !== null && (
                <span
                  className={cn(
                    'px-1.5 py-0.2 rounded text-[10px] font-mono font-semibold',
                    typeof tab.badge === 'string'
                      ? tab.badge === 'Valid'
                        ? 'bg-[var(--green-bg)] text-[var(--green)]'
                        : 'bg-[var(--red-bg)] text-[var(--red)]'
                      : tab.badge > 0
                        ? 'bg-[var(--accent-bg)] text-accent'
                        : 'bg-surface-2 text-3'
                  )}
                >
                  {tab.badge}
                </span>
              )}
            </NavLink>
          );
        })}
      </nav>
    </div>
  );
}
