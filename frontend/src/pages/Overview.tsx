import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Plus, Cpu, ShieldCheck, AlertCircle } from 'lucide-react';
import { getHealth, getCapabilities, NetworkError } from '../api/client';
import type { HealthResponse, CapabilitiesResponse } from '../types/api';
import { Panel } from '../components/Panel';
import { ErrorState } from '../components/ErrorState';

export function Overview() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [caps, setCaps] = useState<CapabilitiesResponse | null>(null);
  const [error, setError] = useState<{ message: string; isNetwork: boolean } | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    Promise.all([getHealth(), getCapabilities()])
      .then(([h, c]) => {
        if (!mounted) return;
        setHealth(h);
        setCaps(c);
        setLoading(false);
      })
      .catch((err) => {
        if (!mounted) return;
        setError({ message: err.message, isNetwork: err instanceof NetworkError });
        setLoading(false);
      });
    return () => { mounted = false; };
  }, []);

  const availableDetectors = caps?.detectors.filter((d) => d.available).length ?? 0;
  const totalDetectors = caps?.detectors.length ?? 0;

  return (
    <div className="max-w-4xl mx-auto px-6 py-8 space-y-6">
      {/* Page header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-[var(--text-primary)] tracking-tight">
            PRAMAAN Assurance Overview
          </h1>
          <p className="mt-1 text-sm text-[var(--text-muted)]">
            Offline integrity assurance for computer vision data, models and inference outputs.
          </p>
        </div>
        <Link
          to="/new"
          className="inline-flex items-center gap-2 px-4 py-2 rounded bg-[var(--accent)] text-white text-sm font-medium hover:bg-[var(--accent-hover)] transition-colors duration-150"
        >
          <Plus className="w-4 h-4" />
          New Assessment
        </Link>
      </div>

      {/* Error state */}
      {error && !loading && (
        <Panel>
          <ErrorState
            message={error.message}
            isNetwork={error.isNetwork}
            onRetry={() => window.location.reload()}
          />
        </Panel>
      )}

      {/* Loading skeleton */}
      {loading && (
        <div className="space-y-4 animate-pulse">
          <div className="h-28 rounded-lg bg-[var(--surface-2)]" />
          <div className="h-40 rounded-lg bg-[var(--surface-2)]" />
        </div>
      )}

      {/* Content */}
      {!loading && !error && (
        <>
          {/* System status */}
          <Panel title="System Status">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              <div className="flex flex-col gap-1">
                <span className="text-[10px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">Service</span>
                <div className="flex items-center gap-1.5">
                  <div className="w-2 h-2 rounded-full bg-[var(--risk-none)]" />
                  <span className="text-sm font-semibold text-[var(--text-primary)] capitalize">
                    {health?.status ?? '—'}
                  </span>
                </div>
              </div>
              <div className="flex flex-col gap-1">
                <span className="text-[10px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">Version</span>
                <span className="text-sm font-semibold text-[var(--text-primary)]">
                  v{health?.version ?? '—'}
                </span>
              </div>
              <div className="flex flex-col gap-1">
                <span className="text-[10px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">Detectors</span>
                <span className="text-sm font-semibold text-[var(--text-primary)]">
                  {availableDetectors}/{totalDetectors} available
                </span>
              </div>
              <div className="flex flex-col gap-1">
                <span className="text-[10px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">Formats</span>
                <span className="text-sm font-semibold text-[var(--text-primary)]">
                  {caps?.supported_dataset_formats.join(', ') ?? '—'}
                </span>
              </div>
            </div>
          </Panel>

          {/* What PRAMAAN assures */}
          <Panel title="Assurance Coverage">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              {[
                {
                  icon: <AlertCircle className="w-5 h-5" />,
                  label: 'Data Integrity',
                  description: 'Detects duplicates, near-duplicates, and data quality issues in CV datasets.',
                },
                {
                  icon: <Cpu className="w-5 h-5" />,
                  label: 'Model Integrity',
                  description: 'Cryptographic fingerprinting of model artifacts to detect substitution or tampering.',
                },
                {
                  icon: <ShieldCheck className="w-5 h-5" />,
                  label: 'Inference Provenance',
                  description: 'Cryptographically signed manifests linking inputs, models, and outputs.',
                },
              ].map((item) => (
                <div key={item.label} className="p-4 rounded-lg bg-[var(--surface-1)] border border-[var(--border)]">
                  <div className="text-[var(--accent)] mb-2">{item.icon}</div>
                  <p className="text-sm font-semibold text-[var(--text-primary)]">{item.label}</p>
                  <p className="mt-1 text-xs text-[var(--text-muted)] leading-relaxed">{item.description}</p>
                </div>
              ))}
            </div>
          </Panel>

          {/* Available detectors */}
          {caps && (
            <Panel
              title="Active Detectors"
              description={`${availableDetectors} of ${totalDetectors} available in this environment`}
              actions={
                <Link to="/capabilities" className="text-xs text-[var(--accent)] hover:underline">
                  View all →
                </Link>
              }
            >
              <div className="space-y-1.5">
                {caps.detectors.map((d) => (
                  <div
                    key={d.detector_id}
                    className="flex items-center gap-3 py-1.5 px-2 rounded hover:bg-[var(--surface-2)] transition-colors duration-150"
                  >
                    <div
                      className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                        d.available ? 'bg-[var(--risk-none)]' : 'bg-[var(--text-muted)]'
                      }`}
                    />
                    <code className="text-[10px] font-mono text-[var(--text-muted)] w-16 flex-shrink-0">
                      {d.detector_id}
                    </code>
                    <span className="text-xs text-[var(--text-primary)] flex-1 truncate">{d.name}</span>
                    <span className="text-[10px] text-[var(--text-muted)] flex-shrink-0">
                      {d.available ? 'Available' : 'Unavailable'}
                    </span>
                  </div>
                ))}
              </div>
            </Panel>
          )}

          {/* Assessment history — no list endpoint exists */}
          <Panel
            title="Recent Assessments"
            description="Assessment history is not yet available in this view."
          >
            <div className="py-8 flex flex-col items-center gap-2 text-center">
              <p className="text-sm text-[var(--text-muted)]">No assessment history available.</p>
              <p className="text-xs text-[var(--text-muted)] max-w-sm">
                Run an assessment to generate findings. Results are accessible immediately after completion.
              </p>
              <Link
                to="/new"
                className="mt-2 inline-flex items-center gap-1.5 text-xs text-[var(--accent)] hover:underline"
              >
                <Plus className="w-3.5 h-3.5" />
                Run your first assessment
              </Link>
            </div>
          </Panel>
        </>
      )}
    </div>
  );
}
