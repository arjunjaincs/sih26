import { useEffect, useState } from 'react';
import {
  Sparkles,
  Check,
  ChevronRight,
  Loader2,
  ShieldCheck,
  Layers,
  Play,
  RotateCcw,
  Cpu,
  Database,
  KeyRound,
  FileCheck
} from 'lucide-react';
import type { DemoPresetSchema } from '../types/api';
import { getDemos } from '../api/client';
import { cn } from '../lib/cn';

interface DemoPresetsProps {
  onSelectPreset: (preset: DemoPresetSchema) => void;
  selectedPresetId?: string | null;
  onExecute?: () => void;
  onClearPreset?: () => void;
  isExecuting?: boolean;
  className?: string;
}

export function DemoPresets({
  onSelectPreset,
  selectedPresetId,
  onExecute,
  onClearPreset,
  isExecuting = false,
  className,
}: DemoPresetsProps) {
  const [presets, setPresets] = useState<DemoPresetSchema[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getDemos()
      .then((res) => setPresets(res.demos))
      .catch((err) => console.error('Failed to load demo presets:', err))
      .finally(() => setLoading(false));
  }, []);

  const selectedPreset = presets.find((p) => p.id === selectedPresetId) || null;

  if (loading) {
    return (
      <div className="card p-6 border border-[var(--border)] bg-surface rounded-xl flex flex-col items-center justify-center gap-2 text-xs text-3 py-10 shadow-sm">
        <Loader2 className="w-5 h-5 animate-spin text-accent" />
        <span className="font-mono">Loading deterministic corpus presets…</span>
      </div>
    );
  }

  if (presets.length === 0) return null;

  const getLayerIcon = (layer?: string) => {
    if (layer?.includes('Dataset')) return <Database className="w-3.5 h-3.5" />;
    if (layer?.includes('Provenance')) return <KeyRound className="w-3.5 h-3.5" />;
    return <Cpu className="w-3.5 h-3.5" />;
  };

  return (
    <div className={cn('space-y-4', className)}>
      {/* ── Demo Mode Banner & Header ── */}
      <div className="card p-5 border border-accent/25 bg-gradient-to-r from-[var(--accent-bg)]/50 via-surface to-surface-2/40 rounded-xl space-y-3 shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-accent/15 border border-accent/30 text-accent flex items-center justify-center shadow-inner">
              <Sparkles className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <h2 className="text-sm font-extrabold text-1 tracking-tight">
                  Deterministic Offline Corpus Scenarios
                </h2>
                <span className="px-2 py-0.5 rounded font-mono text-[9px] font-bold uppercase tracking-wider bg-accent text-white">
                  DEMO MODE
                </span>
                <span className="px-2 py-0.5 rounded font-mono text-[9px] text-3 bg-surface border border-[var(--border)]">
                  AIR-GAPPED
                </span>
              </div>
              <p className="text-xs text-3 mt-0.5">
                Authentic test scenarios running against real local corpus artifacts. Zero simulated findings or mocked data.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 self-start sm:self-auto font-mono text-xs">
            <span className="text-[11px] text-3 bg-surface px-2.5 py-1 rounded-md border border-[var(--border)] flex items-center gap-1.5">
              <ShieldCheck className="w-3.5 h-3.5 text-accent" />
              <span>{presets.length} Curated Scenarios</span>
            </span>
          </div>
        </div>
      </div>

      {/* ── Active Preset Quick-Action Bar ── */}
      {selectedPreset && (
        <div className="p-4 rounded-xl border border-accent/40 bg-[var(--accent-bg)]/25 flex flex-col md:flex-row md:items-center justify-between gap-3 transition-all duration-200 shadow-sm animate-in fade-in">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-accent text-white flex items-center justify-center shrink-0 shadow-sm">
              <Check className="w-4 h-4" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-xs font-mono font-bold text-accent uppercase tracking-wider">
                  Scenario Loaded:
                </span>
                <span className="text-xs font-bold text-1 truncate">{selectedPreset.name}</span>
                {selectedPreset.expected_layer && (
                  <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-surface border border-[var(--border)] text-2">
                    {selectedPreset.expected_layer}
                  </span>
                )}
              </div>
              <p className="text-[11px] text-3 truncate max-w-xl">
                Expected outcome: {selectedPreset.expected_finding_type || `Risk ${selectedPreset.expected_risk}`}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 self-end md:self-auto shrink-0">
            {onClearPreset && (
              <button
                type="button"
                onClick={onClearPreset}
                className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg border border-[var(--border)] bg-surface hover:bg-surface-2 text-xs text-3 hover:text-1 transition-colors"
                title="Clear loaded demo and reset form"
              >
                <RotateCcw className="w-3 h-3" />
                <span>Clear Selection</span>
              </button>
            )}

            {onExecute && (
              <button
                type="button"
                onClick={onExecute}
                disabled={isExecuting}
                className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-accent text-white text-xs font-semibold hover:bg-[var(--accent-2)] transition-all shadow-sm active:scale-95 disabled:opacity-50"
              >
                {isExecuting ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>Executing Battery…</span>
                  </>
                ) : (
                  <>
                    <Play className="w-3.5 h-3.5 fill-current" />
                    <span>Execute Demo Assessment</span>
                  </>
                )}
              </button>
            )}
          </div>
        </div>
      )}

      {/* ── Preset Cards Grid ── */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {presets.map((p) => {
          const isSelected = selectedPresetId === p.id;
          const isHighRisk = p.expected_risk === 'HIGH' || p.expected_risk === 'CRITICAL';
          const isClean = p.expected_risk === 'NONE';

          return (
            <div
              key={p.id}
              className={cn(
                'rounded-xl border p-4 flex flex-col justify-between gap-3.5 transition-all duration-150',
                isSelected
                  ? 'border-accent bg-[var(--accent-bg)]/20 ring-2 ring-accent/50 shadow-md'
                  : 'border-[var(--border)] bg-surface hover:border-[var(--border-strong)] hover:shadow-sm'
              )}
            >
              {/* Top metadata tags */}
              <div className="space-y-2.5">
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <div className="flex items-center gap-1 text-[11px] font-mono font-medium text-accent px-2 py-0.5 rounded bg-surface-2 border border-[var(--border)]">
                    {getLayerIcon(p.expected_layer || p.category)}
                    <span>{p.expected_layer || p.category}</span>
                  </div>

                  {/* Complexity indicator */}
                  {p.complexity && (
                    <span className="font-mono text-[9px] px-1.5 py-0.5 rounded bg-surface-2 border border-[var(--border)] text-3 font-semibold">
                      {p.complexity}
                    </span>
                  )}
                </div>

                {/* Scenario Title & Description */}
                <div>
                  <h3 className="text-sm font-bold text-1 leading-snug">{p.name}</h3>
                  <p className="text-xs text-3 mt-1 leading-relaxed line-clamp-2">{p.description}</p>
                </div>

                {/* Expected Finding Box */}
                {p.expected_finding_type && (
                  <div className="p-2.5 rounded-lg bg-surface-2/70 border border-[var(--border)] text-[11px] space-y-0.5">
                    <span className="font-mono text-[10px] text-3 uppercase tracking-wider block font-semibold">
                      Expected Detection:
                    </span>
                    <span className="text-1 font-medium leading-tight block">
                      {p.expected_finding_type}
                    </span>
                  </div>
                )}
              </div>

              {/* Bottom targets and action */}
              <div className="pt-3 border-t border-[var(--border)]/70 space-y-2.5">
                <div className="flex items-center justify-between text-[11px]">
                  {/* Expected Risk */}
                  <span
                    className={cn(
                      'text-[10px] font-mono font-bold px-2 py-0.5 rounded border',
                      isClean
                        ? 'bg-[var(--green-bg)] text-[var(--green)] border-[var(--green)]/30'
                        : isHighRisk
                        ? 'bg-[var(--red-bg)] text-[var(--red)] border-[var(--red)]/30'
                        : 'bg-[var(--amber-bg)] text-[var(--amber)] border-[var(--amber-border)]'
                    )}
                  >
                    EXPECTED RISK: {p.expected_risk}
                  </span>

                  {/* Detectors targeted */}
                  <div className="flex items-center gap-1 font-mono text-[10px] text-3">
                    <Layers className="w-3 h-3" />
                    <span>{p.detectors_targeted.join(', ')}</span>
                  </div>
                </div>

                {/* Load button */}
                <button
                  type="button"
                  onClick={() => onSelectPreset(p)}
                  className={cn(
                    'w-full py-2 px-3 rounded-lg text-xs font-semibold flex items-center justify-center gap-1.5 transition-all select-none',
                    isSelected
                      ? 'bg-accent text-white shadow-sm'
                      : 'border border-[var(--border)] bg-surface-2 hover:bg-surface text-1 hover:border-accent/40'
                  )}
                >
                  {isSelected ? (
                    <>
                      <Check className="w-3.5 h-3.5" />
                      <span>Preset Loaded in Engine</span>
                    </>
                  ) : (
                    <>
                      <FileCheck className="w-3.5 h-3.5" />
                      <span>Load Scenario</span>
                      <ChevronRight className="w-3.5 h-3.5 ml-auto text-3" />
                    </>
                  )}
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
