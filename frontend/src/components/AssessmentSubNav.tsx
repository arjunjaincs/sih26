import { NavLink } from 'react-router-dom';
import { 
  FileText, 
  AlertTriangle, 
  FileSearch, 
  ShieldCheck, 
  KeyRound, 
  SlidersHorizontal 
} from 'lucide-react';
import { cn } from '../lib/cn';

interface AssessmentSubNavProps {
  assessmentId: string;
  findingsCount?: number;
  evidenceCount?: number;
  chainValid?: boolean | null;
  provenanceValid?: boolean | null;
  coverageGapsCount?: number;
}

export function AssessmentSubNav({
  assessmentId,
  findingsCount,
  evidenceCount,
  chainValid,
  provenanceValid,
  coverageGapsCount,
}: AssessmentSubNavProps) {
  const tabs = [
    {
      to: `/assessments/${assessmentId}/result`,
      label: 'Results Overview',
      icon: FileText,
      badge: null,
    },
    {
      to: `/assessments/${assessmentId}/findings`,
      label: 'Findings',
      icon: AlertTriangle,
      badge: findingsCount !== undefined ? findingsCount : null,
      badgeType: findingsCount && findingsCount > 0 ? 'warning' : 'neutral',
    },
    {
      to: `/assessments/${assessmentId}/evidence`,
      label: 'Evidence',
      icon: FileSearch,
      badge: evidenceCount !== undefined ? evidenceCount : null,
      badgeType: 'neutral',
    },
    {
      to: `/assessments/${assessmentId}/provenance`,
      label: 'Provenance',
      icon: KeyRound,
      badge:
        provenanceValid === true
          ? 'Verified'
          : provenanceValid === false
          ? 'Failed'
          : null,
      badgeType: provenanceValid === true ? 'success' : 'danger',
    },
    {
      to: `/assessments/${assessmentId}/audit`,
      label: 'Audit Trail',
      icon: ShieldCheck,
      badge:
        chainValid === true
          ? 'Valid'
          : chainValid === false
          ? 'Tampered'
          : null,
      badgeType: chainValid === true ? 'success' : 'danger',
    },
    {
      to: `/assessments/${assessmentId}/limitations`,
      label: 'Limitations',
      icon: SlidersHorizontal,
      badge: coverageGapsCount !== undefined && coverageGapsCount > 0 ? coverageGapsCount : null,
      badgeType: 'warning',
    },
  ];

  return (
    <div className="border-b border-[var(--border)] mb-6 overflow-x-auto">
      <nav className="flex items-center gap-1.5 min-w-max pb-3" aria-label="Assessment views">
        {tabs.map((tab) => {
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
              <Icon className="w-3.5 h-3.5 text-accent flex-shrink-0" />
              <span>{tab.label}</span>
              {tab.badge !== null && (
                <span
                  className={cn(
                    'px-1.5 py-0.2 rounded text-[10px] font-mono font-semibold',
                    tab.badgeType === 'success'
                      ? 'bg-[var(--green-bg)] text-[var(--green)] border border-[var(--green)]/30'
                      : tab.badgeType === 'danger'
                      ? 'bg-[var(--red-bg)] text-[var(--red)] border border-[var(--red)]/30'
                      : tab.badgeType === 'warning'
                      ? 'bg-[var(--amber-bg)] text-[var(--amber)] border border-[var(--amber-border)]'
                      : 'bg-surface-2 text-3 border border-[var(--border)]'
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
