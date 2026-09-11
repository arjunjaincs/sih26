import { useEffect, useState } from 'react';
import { Cpu, CheckCircle, XCircle } from 'lucide-react';
import type { CapabilitiesResponse } from '../types/api';
import { getCapabilities } from '../api/client';
import { Panel } from '../components/Panel';
import { ErrorState } from '../components/ErrorState';
import { cn } from '../lib/cn';

export function Capabilities() {
  const [data, setData] = useState<CapabilitiesResponse | null>(null);
  const [error, setError] = useState<{ message: string; isNetwork: boolean } | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getCapabilities()
      .then((r) => { setData(r); setLoading(false); })
      .catch((err) => { setError({ message: err.message, isNetwork: err.name === 'NetworkError' }); setLoading(false); });
  }, []);

  const available = data?.detectors.filter((d) => d.available).length ?? 0;
  const total = data?.detectors.length ?? 0;

  return (
    <div className="max-w-3xl mx-auto px-6 py-8 space-y-5">
      <div>
        <h1 className="text-xl font-bold text-[var(--text-primary)] tracking-tight">Capabilities</h1>
        <p className="mt-1 text-sm text-[var(--text-muted)]">
          What PRAMAAN can establish in this environment. Availability depends on installed dependencies and asset access.
        </p>
      </div>

      {loading && (
        <div className="space-y-3 animate-pulse">
          {[1, 2, 3].map((i) => <div key={i} className="h-28 rounded-lg bg-[var(--surface-2)]" />)}
        </div>
      )}

      {error && !loading && (
        <Panel>
          <ErrorState message={error.message} isNetwork={error.isNetwork} onRetry={() => window.location.reload()} />
        </Panel>
      )}

      {!loading && !error && data && (
        <>
          {/* Summary */}
          <div className="grid grid-cols-3 gap-4">
            <div className="p-4 rounded-lg border border-[var(--border)] bg-[var(--surface-1)]">
              <p className="text-[10px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">Detectors</p>
              <p className="text-2xl font-bold text-[var(--text-primary)] mt-1">
                {available}<span className="text-[var(--text-muted)] text-base font-normal">/{total}</span>
              </p>
              <p className="text-[10px] text-[var(--text-muted)] mt-0.5">available</p>
            </div>
            <div className="p-4 rounded-lg border border-[var(--border)] bg-[var(--surface-1)]">
              <p className="text-[10px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">Dataset Formats</p>
              <div className="mt-1.5 flex flex-wrap gap-1">
                {data.supported_dataset_formats.map((f) => (
                  <code key={f} className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--surface-2)] font-mono text-[var(--text-secondary)]">
                    {f}
                  </code>
                ))}
              </div>
            </div>
            <div className="p-4 rounded-lg border border-[var(--border)] bg-[var(--surface-1)]">
              <p className="text-[10px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">Model Formats</p>
              <div className="mt-1.5 flex flex-wrap gap-1">
                {data.supported_model_formats.map((f) => (
                  <code key={f} className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--surface-2)] font-mono text-[var(--text-secondary)]">
                    {f}
                  </code>
                ))}
              </div>
            </div>
          </div>

          {/* Detector cards */}
          <Panel title="Detectors" description={`PRAMAAN v${data.pramaan_version}`}>
            <div className="space-y-3">
              {data.detectors.map((d) => (
                <div
                  key={d.detector_id}
                  className={cn(
                    'rounded-lg border p-4 transition-colors duration-150',
                    d.available
                      ? 'border-[var(--border)] bg-[var(--surface-1)]'
                      : 'border-[var(--border-subtle)] bg-[var(--surface-0)] opacity-75',
                  )}
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex items-start gap-3 min-w-0">
                      <div className="flex items-center justify-center w-8 h-8 rounded bg-[var(--surface-2)] flex-shrink-0 mt-0.5">
                        <Cpu className="w-4 h-4 text-[var(--text-muted)]" />
                      </div>
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <code className="text-xs font-mono font-semibold text-[var(--accent)]">
                            {d.detector_id}
                          </code>
                          <span className="text-[10px] text-[var(--text-muted)]">v{d.version}</span>
                        </div>
                        <p className="text-sm font-semibold text-[var(--text-primary)] mt-0.5">{d.name}</p>
                        <p className="text-xs text-[var(--text-muted)] mt-1 leading-relaxed">{d.description}</p>
                      </div>
                    </div>
                    <div className="flex-shrink-0 flex items-center gap-1.5">
                      {d.available ? (
                        <CheckCircle className="w-4 h-4 text-[var(--risk-none)]" />
                      ) : (
                        <XCircle className="w-4 h-4 text-[var(--text-muted)]" />
                      )}
                      <span className={cn(
                        'text-xs font-semibold',
                        d.available ? 'text-[var(--risk-none)]' : 'text-[var(--text-muted)]',
                      )}>
                        {d.available ? 'Available' : 'Unavailable'}
                      </span>
                    </div>
                  </div>

                  {/* Asset types */}
                  <div className="mt-3 flex flex-wrap gap-1.5 pl-11">
                    {d.applicable_asset_types.map((t) => (
                      <span
                        key={t}
                        className="text-[10px] px-2 py-0.5 rounded-full border border-[var(--border)] text-[var(--text-muted)] bg-[var(--surface-2)]"
                      >
                        {t}
                      </span>
                    ))}
                  </div>

                  {/* Unavailability notice */}
                  {!d.available && (
                    <div className="mt-3 pl-11">
                      <p className="text-[10px] text-[var(--text-muted)] italic">
                        This detector's runtime dependencies are not satisfied in the current environment.
                        Install the optional <code className="font-mono">[models]</code> extras to enable it.
                      </p>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </Panel>
        </>
      )}
    </div>
  );
}
