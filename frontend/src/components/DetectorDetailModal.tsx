import { useEffect, useRef } from 'react';
import {
  X,
  ShieldCheck,
  AlertTriangle,
  Layers,
  BookOpen,
  CheckCircle2,
  Info,
  Terminal
} from 'lucide-react';
import { cn } from '../lib/cn';
import { getDetectorDetail, type DetectorDetailSpec } from '../lib/detectorRegistry';
import type { DetectorCapabilitySchema } from '../types/api';

interface DetectorDetailModalProps {
  detectorIdOrCode: string | null;
  onClose: () => void;
  liveCapability?: DetectorCapabilitySchema | null;
}

export function DetectorDetailModal({
  detectorIdOrCode,
  onClose,
  liveCapability,
}: DetectorDetailModalProps) {
  const modalRef = useRef<HTMLDivElement>(null);

  // Close on ESC key
  useEffect(() => {
    if (!detectorIdOrCode) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [detectorIdOrCode, onClose]);

  // Lock body scroll when modal is open
  useEffect(() => {
    if (detectorIdOrCode) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [detectorIdOrCode]);

  if (!detectorIdOrCode) return null;

  const spec: DetectorDetailSpec = getDetectorDetail(detectorIdOrCode, liveCapability);
  const Icon = spec.icon;
  const isAvailable = spec.status === 'AVAILABLE';

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="detector-detail-title"
      className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 md:p-8 bg-black/60 backdrop-blur-sm animate-in fade-in duration-150"
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          onClose();
        }
      }}
    >
      <div
        ref={modalRef}
        className={cn(
          'w-full max-w-3xl max-h-[90vh] flex flex-col rounded-xl shadow-2xl',
          'bg-surface border border-[var(--border)] overflow-hidden transition-all'
        )}
      >
        {/* Header Bar */}
        <div className="flex items-start justify-between gap-4 px-5 py-4 border-b border-[var(--border)] bg-surface-2/60">
          <div className="flex items-center gap-3 min-w-0">
            <div className={cn('p-2.5 rounded-lg border flex-shrink-0', spec.bg)}>
              <Icon className={cn('w-5 h-5', spec.color)} />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-mono font-bold text-xs px-2 py-0.5 rounded bg-surface border border-[var(--border)] text-1">
                  {spec.code}
                </span>
                <span className="text-xs font-semibold px-2 py-0.5 rounded bg-surface-2 text-2 border border-[var(--border)]">
                  {spec.pillar}
                </span>
                <span
                  data-testid="detector-status-badge"
                  className={cn(
                    'text-[11px] font-mono font-semibold px-2 py-0.5 rounded-full border',
                    isAvailable
                      ? 'bg-[var(--green-bg)] text-[var(--green)] border-[var(--green)]/30'
                      : 'bg-[var(--amber-bg)] text-[var(--amber)] border-[var(--amber-border)]'
                  )}
                >
                  {spec.status}
                </span>
              </div>
              <h2
                id="detector-detail-title"
                className="text-base sm:text-lg font-bold text-1 mt-1 truncate"
                title={spec.name}
              >
                {spec.name}
              </h2>
            </div>
          </div>

          <button
            onClick={onClose}
            data-testid="close-detector-modal"
            aria-label="Close detector details"
            className="p-1.5 rounded-lg text-3 hover:text-1 hover:bg-surface-2 border border-transparent hover:border-[var(--border)] transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Scrollable Modal Content */}
        <div className="overflow-y-auto px-5 py-5 space-y-6 text-xs sm:text-sm">
          {/* Identity & Registry ID */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 p-3.5 rounded-lg bg-surface-2/40 border border-[var(--border)]">
            <div>
              <span className="text-[11px] font-mono text-3 block uppercase tracking-wider">
                Detector ID
              </span>
              <code className="text-xs font-mono font-semibold text-1 select-all break-all">
                {spec.id}
              </code>
            </div>
            <div>
              <span className="text-[11px] font-mono text-3 block uppercase tracking-wider">
                Specification Version
              </span>
              <span className="text-xs font-mono text-2">
                v{spec.version} (Authoritative)
              </span>
            </div>
          </div>

          {/* Purpose */}
          <div className="space-y-1.5">
            <h3 className="text-xs font-mono font-bold text-2 uppercase tracking-wider flex items-center gap-1.5">
              <Info className="w-3.5 h-3.5 text-accent" />
              Purpose & Objective
            </h3>
            <p className="text-1 leading-relaxed bg-surface-2/20 p-3 rounded-lg border border-[var(--border)]/70">
              {spec.purpose}
            </p>
          </div>

          {/* What it Analyzes */}
          <div className="space-y-1.5">
            <h3 className="text-xs font-mono font-bold text-2 uppercase tracking-wider flex items-center gap-1.5">
              <Layers className="w-3.5 h-3.5 text-accent" />
              What PRAMAAN Analyzes
            </h3>
            <div className="text-1 leading-relaxed bg-surface-2/20 p-3 rounded-lg border border-[var(--border)]/70">
              <p>{spec.whatItAnalyzes}</p>
            </div>
          </div>

          {/* Evidence Produced */}
          <div className="space-y-1.5">
            <h3 className="text-xs font-mono font-bold text-2 uppercase tracking-wider flex items-center gap-1.5">
              <Terminal className="w-3.5 h-3.5 text-accent" />
              Evidence Produced
            </h3>
            <ul className="space-y-1.5 bg-surface-2/20 p-3 rounded-lg border border-[var(--border)]/70">
              {spec.evidenceProduced.map((item, idx) => (
                <li key={idx} className="flex items-start gap-2 text-2">
                  <CheckCircle2 className="w-3.5 h-3.5 text-[var(--green)] flex-shrink-0 mt-0.5" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* Confidence Semantics (ADR-003 Decoupling) */}
          <div className="space-y-1.5">
            <h3 className="text-xs font-mono font-bold text-2 uppercase tracking-wider flex items-center gap-1.5">
              <ShieldCheck className="w-3.5 h-3.5 text-accent" />
              Confidence & Risk Semantics
            </h3>
            <div className="p-3 rounded-lg border border-[var(--border)]/80 bg-surface-2/30 text-2 leading-relaxed">
              <p>{spec.confidenceSemantics}</p>
            </div>
          </div>

          {/* Technical Scope Matrix: Access, Assets, Formats, Dependencies */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {/* Access Requirements */}
            <div className="p-3 rounded-lg border border-[var(--border)] bg-surface-2/30 space-y-1">
              <span className="text-[11px] font-mono text-3 block uppercase tracking-wider">
                Access Requirements
              </span>
              <span className="text-xs font-medium text-1">
                {spec.accessRequirements}
              </span>
            </div>

            {/* Applicable Asset Types */}
            <div className="p-3 rounded-lg border border-[var(--border)] bg-surface-2/30 space-y-1">
              <span className="text-[11px] font-mono text-3 block uppercase tracking-wider">
                Applicable Asset Types
              </span>
              <div className="flex items-center gap-1.5 flex-wrap">
                {spec.applicableAssetTypes.map((type, idx) => (
                  <span
                    key={idx}
                    className="text-[11px] font-mono px-2 py-0.5 rounded bg-surface border border-[var(--border)] text-1"
                  >
                    {type}
                  </span>
                ))}
              </div>
            </div>

            {/* Supported Formats */}
            <div className="p-3 rounded-lg border border-[var(--border)] bg-surface-2/30 space-y-1">
              <span className="text-[11px] font-mono text-3 block uppercase tracking-wider">
                Supported Formats
              </span>
              <div className="flex items-center gap-1.5 flex-wrap">
                {spec.supportedFormats.map((fmt, idx) => (
                  <span
                    key={idx}
                    className="text-[11px] font-mono px-2 py-0.5 rounded bg-surface border border-[var(--border)] text-2"
                  >
                    {fmt}
                  </span>
                ))}
              </div>
            </div>

            {/* Runtime Dependencies */}
            <div className="p-3 rounded-lg border border-[var(--border)] bg-surface-2/30 space-y-1">
              <span className="text-[11px] font-mono text-3 block uppercase tracking-wider">
                Runtime Dependencies
              </span>
              <div className="flex items-center gap-1.5 flex-wrap">
                {spec.dependencies.map((dep, idx) => (
                  <span
                    key={idx}
                    className="text-[11px] font-mono px-2 py-0.5 rounded bg-surface border border-[var(--border)] text-2"
                  >
                    {dep}
                  </span>
                ))}
              </div>
            </div>
          </div>

          {/* Known Limitations */}
          <div className="space-y-1.5">
            <h3 className="text-xs font-mono font-bold text-2 uppercase tracking-wider flex items-center gap-1.5">
              <AlertTriangle className="w-3.5 h-3.5 text-[var(--amber)]" />
              Known Limitations & Bounded Scope
            </h3>
            <ul className="space-y-1.5 bg-[var(--amber-bg)]/20 p-3 rounded-lg border border-[var(--amber-border)]/50 text-2">
              {spec.limitations.map((lim, idx) => (
                <li key={idx} className="flex items-start gap-2">
                  <span className="text-[var(--amber)] font-bold text-xs mt-0.5">•</span>
                  <span>{lim}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* Reference & Method Information */}
          <div className="space-y-1.5">
            <h3 className="text-xs font-mono font-bold text-2 uppercase tracking-wider flex items-center gap-1.5">
              <BookOpen className="w-3.5 h-3.5 text-accent" />
              Methodology & Scientific Reference
            </h3>
            <div className="p-3 rounded-lg border border-[var(--border)] bg-surface-2/30 text-2">
              <code className="text-xs font-mono text-1 block break-all">
                {spec.referenceMethod}
              </code>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-5 py-3 border-t border-[var(--border)] bg-surface-2/40 text-xs">
          <span className="text-3 font-mono">
            PRAMAAN Deterministic Assurance Engine
          </span>
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded-lg bg-surface border border-[var(--border)] text-1 font-medium hover:bg-surface-2 transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
