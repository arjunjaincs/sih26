import { useEffect, useState } from 'react';
import { Database, Cpu, GitBranch, ChevronDown, ChevronUp } from 'lucide-react';
import type { CapabilitiesResponse, DetectorCapabilitySchema } from '../types/api';
import { getCapabilities, NetworkError } from '../api/client';
import { ErrorState } from '../components/ErrorState';
import { cn } from '../lib/cn';

const DETECTOR_META: Record<string, { icon: typeof Database; color: string; bg: string }> = {
  'DI-01': { icon: Database,  color: 'text-blue-400',   bg: 'bg-blue-500/10' },
  'MI-01': { icon: Cpu,       color: 'text-purple-400', bg: 'bg-purple-500/10' },
  'PI-01': { icon: GitBranch, color: 'text-amber-400',  bg: 'bg-amber-500/10' },
};

function DetectorCard({ d }: { d: DetectorCapabilitySchema }) {
  const [expanded, setExpanded] = useState(false);
  const meta = DETECTOR_META[d.detector_id] ?? { icon: Database, color: 'text-accent', bg: 'bg-[var(--accent-bg)]' };
  const Icon = meta.icon;

  return (
    <div className={cn(
      'card flex flex-col gap-4 p-6 transition-shadow duration-150',
      'hover:shadow-[0_0_0_1px_var(--accent)]',
    )}>
      {/* Icon + ID */}
      <div className="flex items-start justify-between gap-3">
        <div className={cn('w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0', meta.bg)}>
          <Icon className={cn('w-4.5 h-4.5', meta.color)} />
        </div>
        <code className="text-[10px] font-mono font-bold text-accent">{d.detector_id}</code>
      </div>

      {/* Name + description */}
      <div>
        <h3 className="text-sm font-semibold text-1 leading-snug">{d.name}</h3>
        <p className="mt-1.5 text-xs text-3 leading-relaxed">
          {expanded ? d.description : d.description.slice(0, 120) + (d.description.length > 120 ? '…' : '')}
        </p>
      </div>

      {/* Metadata */}
      <div className="space-y-2 text-xs">
        <div>
          <p className="label mb-1">Version</p>
          <code className="font-mono text-2">{d.version}</code>
        </div>

        <div>
          <p className="label mb-1">Supported Formats</p>
          <div className="flex flex-wrap gap-1">
            {d.applicable_asset_types.map(t => (
              <span key={t} className="px-1.5 py-0.5 rounded bg-surface-2 border border-[var(--border)]
                text-[10px] font-mono text-2">
                {t.toUpperCase()}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* Expandable details */}
      {d.description.length > 120 && (
        <button
          onClick={() => setExpanded(o => !o)}
          className="flex items-center gap-1 text-[10px] text-3 hover:text-1 transition-colors mt-auto"
        >
          {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          {expanded ? 'Show less' : 'Show more'}
        </button>
      )}

      {/* Availability badge */}
      <div className={cn(
        'mt-auto flex items-center gap-1.5 text-xs font-semibold',
        d.available ? 'text-[var(--green)]' : 'text-3',
      )}>
        <div className={cn(
          'w-1.5 h-1.5 rounded-full',
          d.available ? 'bg-[var(--green)]' : 'bg-[var(--border-strong)]',
        )} />
        {d.available ? 'Available' : 'Unavailable'}
      </div>
    </div>
  );
}

export function Capabilities() {
  const [data, setData] = useState<CapabilitiesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    let m = true;
    getCapabilities()
      .then(d => { if (m) { setData(d); setLoading(false); } })
      .catch(err => {
        if (m) {
          setOffline(err instanceof NetworkError);
          setError(err.message);
          setLoading(false);
        }
      });
    return () => { m = false; };
  }, []);

  if (loading) return (
    <div className="max-w-5xl mx-auto px-6 py-10">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-6 animate-pulse">
        {[...Array(3)].map((_, i) => <div key={i} className="h-64 bg-surface-2 rounded-lg" />)}
      </div>
    </div>
  );

  if (error) return (
    <div className="max-w-5xl mx-auto px-6 py-10">
      <ErrorState
        title="Could not load capabilities"
        message={offline
          ? 'The PRAMAAN backend is not running. Start it and refresh.'
          : error}
      />
    </div>
  );

  const detectors = data?.detectors ?? [];

  return (
    <div className="max-w-5xl mx-auto px-6 py-10 space-y-8">
      {/* Header */}
      <div>
        <p className="label text-accent mb-1">PRAMAAN · System</p>
        <h1 className="text-2xl font-bold text-1">Capabilities</h1>
        <p className="mt-0.5 text-sm text-3">Supported detectors and file formats.</p>
      </div>

      {/* Detector grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
        {detectors.map(d => <DetectorCard key={d.detector_id} d={d} />)}
      </div>

      {/* Formats reference */}
      {data && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 pt-4 border-t border-[var(--border)]">
          {[
            { label: 'Dataset Formats', items: data.supported_dataset_formats },
            { label: 'Model Formats', items: data.supported_model_formats },
          ].map(({ label, items }) => (
            <div key={label}>
              <p className="label mb-2">{label}</p>
              <div className="flex flex-wrap gap-1.5">
                {items.map(f => (
                  <code key={f} className="px-2 py-1 rounded bg-surface-2 border border-[var(--border)]
                    text-[11px] font-mono text-2">
                    {f}
                  </code>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Version */}
      {data?.pramaan_version && (
        <p className="text-xs text-3">
          PRAMAAN v{data.pramaan_version}
        </p>
      )}
    </div>
  );
}
