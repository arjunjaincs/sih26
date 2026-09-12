import { useEffect, useState } from 'react';
import { Sparkles, Check, ChevronRight, Loader2, Play } from 'lucide-react';
import type { DemoPresetSchema } from '../types/api';
import { getDemos } from '../api/client';
import { cn } from '../lib/cn';

interface DemoPresetsProps {
  onSelectPreset: (preset: DemoPresetSchema) => void;
  selectedPresetId?: string | null;
}

export function DemoPresets({ onSelectPreset, selectedPresetId }: DemoPresetsProps) {
  const [presets, setPresets] = useState<DemoPresetSchema[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getDemos()
      .then((res) => setPresets(res.demos))
      .catch((err) => console.error('Failed to load demo presets:', err))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="card p-4 border border-[var(--border)] bg-surface rounded-xl flex items-center justify-center gap-2 text-xs text-3 py-6">
        <Loader2 className="w-4 h-4 animate-spin text-accent" />
        <span>Loading SIH evaluation presets…</span>
      </div>
    );
  }

  if (presets.length === 0) return null;

  return (
    <div className="card p-5 border border-[var(--border)] bg-surface rounded-xl space-y-4 shadow-sm">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-md bg-[var(--accent-bg)] border border-accent/30 text-accent flex items-center justify-center">
            <Sparkles className="w-3.5 h-3.5" />
          </div>
          <div>
            <h2 className="text-xs font-mono font-bold text-1 uppercase tracking-wider">
              SIH Jury & Fast Evaluation Presets
            </h2>
            <p className="text-[11px] text-3">
              1-click execution against real deterministic offline corpus artifacts. Zero simulated findings.
            </p>
          </div>
        </div>

        <span className="font-mono text-[10px] text-3 px-2 py-0.5 rounded bg-surface-2 border border-[var(--border)]">
          {presets.length} VERIFIED PRESETS
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {presets.map((p) => {
          const isSelected = selectedPresetId === p.id;
          const isHighRisk = p.expected_risk === 'HIGH' || p.expected_risk === 'CRITICAL';

          return (
            <button
              key={p.id}
              type="button"
              onClick={() => onSelectPreset(p)}
              className={cn(
                'p-3.5 rounded-lg border text-left flex flex-col justify-between gap-3 transition-all duration-150',
                isSelected
                  ? 'border-accent bg-[var(--accent-bg)]/30 ring-1 ring-accent/40 shadow-sm'
                  : 'border-[var(--border)] bg-surface-2/40 hover:bg-surface-2 hover:border-[var(--border-strong)]'
              )}
            >
              <div className="space-y-1.5 w-full">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-[10px] font-semibold text-accent px-1.5 py-0.2 rounded bg-surface border border-[var(--border)]">
                    {p.category}
                  </span>
                  {isSelected ? (
                    <span className="inline-flex items-center gap-1 text-[10px] font-mono font-bold text-accent">
                      <Check className="w-3 h-3" />
                      LOADED
                    </span>
                  ) : (
                    <span
                      className={cn(
                        'text-[10px] font-mono font-bold px-1.5 py-0.2 rounded border',
                        isHighRisk
                          ? 'bg-[var(--red-bg)] text-[var(--red)] border-[var(--red)]/20'
                          : 'bg-[var(--green-bg)] text-[var(--green)] border-[var(--green)]/20'
                      )}
                    >
                      RISK: {p.expected_risk}
                    </span>
                  )}
                </div>

                <h3 className="text-xs font-bold text-1 leading-snug">{p.name}</h3>
                <p className="text-[11px] text-3 line-clamp-2 leading-relaxed">{p.description}</p>
              </div>

              <div className="flex items-center justify-between w-full pt-2 border-t border-[var(--border)]/60 text-[10px]">
                <div className="flex items-center gap-1 font-mono text-3">
                  <span>Targets:</span>
                  <span className="text-1 font-semibold">{p.detectors_targeted.join(', ')}</span>
                </div>

                <span className="inline-flex items-center gap-0.5 text-accent font-semibold group-hover:translate-x-0.5 transition-transform">
                  <span>Load</span>
                  <ChevronRight className="w-3 h-3" />
                </span>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
