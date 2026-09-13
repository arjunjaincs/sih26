import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowRight,
  AlertCircle,
  FileCheck2,
  SlidersHorizontal,
  CheckCircle2
} from 'lucide-react';
import type { CapabilitiesResponse } from '../types/api';
import { getCapabilities, NetworkError } from '../api/client';
import { ErrorState } from '../components/ErrorState';
import { StatusBadge } from '../components/StatusBadge';
import { cn } from '../lib/cn';
import {
  getDetectorDetail,
  normalizeDetectorCode,
  type DetectorDetailSpec
} from '../lib/detectorRegistry';
import { DetectorDetailModal } from '../components/DetectorDetailModal';

type LayerSpec = DetectorDetailSpec;

function resolveSpec(id: string, liveCap?: any): DetectorDetailSpec {
  return getDetectorDetail(id, liveCap);
}

interface MergedCapability {
  id: string;
  code: string;
  name: string;
  description: string;
  version: string;
  applicable_asset_types: string[];
  available: boolean;
  spec: LayerSpec;
}

export function Capabilities() {
  const [data, setData] = useState<CapabilitiesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [offline, setOffline] = useState(false);
  const [filter, setFilter] = useState<'all' | 'detector' | 'ledger'>('all');
  const [selectedDetector, setSelectedDetector] = useState<string | null>(null);

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

  if (loading) {
    return (
      <div className="max-w-6xl mx-auto px-6 py-10 space-y-6">
        <div className="h-10 bg-surface-2 rounded-lg animate-pulse w-1/3" />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-72 bg-surface-2 rounded-xl animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-6xl mx-auto px-6 py-10">
        <ErrorState
          title="Could not load capabilities specification"
          message={offline ? 'PRAMAAN backend is offline. Start the service and refresh.' : error}
        />
      </div>
    );
  }

  // Build merged capabilities: live backend detectors + AT-01 audit layer
  const detectorItems: MergedCapability[] = (data?.detectors ?? []).map(d => {
    const spec = resolveSpec(d.detector_id, d);
    return {
      id: d.detector_id,
      code: spec.code,
      name: d.name,
      description: d.description,
      version: d.version,
      applicable_asset_types: d.applicable_asset_types,
      available: d.available,
      spec,
    };
  });

  const at01Item: MergedCapability = {
    id: 'audit.ledger.at01_chain',
    code: 'AT-01',
    name: 'AT-01: Tamper-Evident Audit Trail',
    description: 'Append-only SHA-256 cryptographic hash chain verifying assessment provenance and event immutability.',
    version: data?.pramaan_version ?? '1.0.0',
    applicable_asset_types: ['audit_ledger', 'events'],
    available: true,
    spec: getDetectorDetail('AT-01'),
  };

  const allItems = [...detectorItems, at01Item];
  const displayedItems = allItems.filter(item => {
    if (filter === 'detector') return item.spec.category === 'detector';
    if (filter === 'ledger') return item.spec.category === 'ledger';
    return true;
  });

  return (
    <div className="max-w-6xl mx-auto px-6 py-8 space-y-8">
      {/* ── Page Header (Technical Analyst Workstation) ── */}
      <div className="border-b border-[var(--border)] pb-6 flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1.5">
            <span className="font-mono text-[11px] font-bold text-accent px-2 py-0.5 rounded bg-[var(--accent-bg)] border border-accent/20">
              SPECIFICATION v{data?.pramaan_version ?? '1.0.0'}
            </span>
            <span className="text-xs text-3 font-mono">PRAMAAN ASSURANCE ENGINE</span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-bold text-1 tracking-tight">
            Capabilities & Detector Specification
          </h1>
          <p className="mt-1 text-sm text-2 max-w-2xl leading-relaxed">
            Technical specification of offline assurance layers, automated computer vision detectors,
            evidence outputs, and boundary limitations.
          </p>
        </div>

        {/* Action button */}
        <div className="flex items-center gap-3">
          <Link
            to="/new"
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-accent text-white text-xs font-semibold hover:bg-[var(--accent-2)] transition-colors shadow-sm focus-visible:ring-1"
          >
            <span>Launch Assessment</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>
      </div>

      {/* ── Technical Summary Ribbon ── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="card p-3.5 flex flex-col gap-1">
          <span className="text-[10px] font-mono text-3 uppercase font-semibold">Assurance Stack</span>
          <p className="text-lg font-bold text-1">4 Layers</p>
          <span className="text-[11px] text-2">DI-01, MI-01, PI-01, AT-01</span>
        </div>

        <div className="card p-3.5 flex flex-col gap-1">
          <span className="text-[10px] font-mono text-3 uppercase font-semibold">Operational Mode</span>
          <p className="text-lg font-bold text-1">100% Offline</p>
          <span className="text-[11px] text-[var(--green)] font-medium">Air-Gapped Compatible</span>
        </div>

        <div className="card p-3.5 flex flex-col gap-1">
          <span className="text-[10px] font-mono text-3 uppercase font-semibold">Audit Integrity</span>
          <p className="text-lg font-bold text-1">SHA-256</p>
          <span className="text-[11px] text-2 font-mono">Append-Only Hash Chain</span>
        </div>

        <div className="card p-3.5 flex flex-col gap-1">
          <span className="text-[10px] font-mono text-3 uppercase font-semibold">Signatures</span>
          <p className="text-lg font-bold text-1">Ed25519</p>
          <span className="text-[11px] text-2 font-mono">Cryptographic Provenance</span>
        </div>
      </div>

      {/* ── Category Filter ── */}
      <div className="flex items-center justify-between gap-4 border-b border-[var(--border)] pb-2 flex-wrap">
        <div className="flex items-center gap-2">
          <SlidersHorizontal className="w-3.5 h-3.5 text-3 mr-1" />
          {[
            { id: 'all', label: `All Capabilities (${allItems.length})` },
            { id: 'detector', label: `Detectors (${detectorItems.length})` },
            { id: 'ledger', label: 'Audit Trail (1)' },
          ].map(tab => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setFilter(tab.id as any)}
              className={cn(
                'px-3 py-1 rounded-md text-xs font-medium transition-colors focus-visible:ring-1',
                filter === tab.id
                  ? 'bg-surface border border-accent/40 text-1 shadow-sm font-semibold'
                  : 'text-3 hover:text-1 hover:bg-surface-2'
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <span className="text-xs text-3 font-mono">
          System Registry: {allItems.filter(i => i.available).length} of {allItems.length} active
        </span>
      </div>

      {/* ── 4 Assurance Layer Specification Cards ── */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {displayedItems.map(item => {
          const { spec } = item;
          const Icon = spec.icon;

          return (
            <div
              key={item.id}
              className="card p-6 flex flex-col justify-between border border-[var(--border)] hover:border-[var(--border-strong)] transition-all duration-150"
            >
              {/* Header: Icon, Code, Title & Status */}
              <div>
                <div className="flex items-start justify-between gap-3 mb-3">
                  <div className="flex items-center gap-3">
                    <div className={cn('w-9 h-9 rounded-lg flex items-center justify-center border', spec.bg)}>
                      <Icon className={cn('w-4.5 h-4.5', spec.color)} />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs font-bold text-1 tracking-wide">
                          {spec.code}
                        </span>
                        <span className="text-[10px] font-mono text-3 uppercase tracking-wider">
                          // {spec.pillar}
                        </span>
                      </div>
                      <h3 className="text-sm font-semibold text-1 leading-snug mt-0.5">
                        {item.name}
                      </h3>
                    </div>
                  </div>

                  {/* Status & Availability Badges */}
                  <div className="flex flex-col items-end gap-1 flex-shrink-0">
                    <StatusBadge value={spec.statusBadge ?? 'implemented'} variant="availability" />
                    {/* Explicit Available / Unavailable text to ensure test contract & analyst clarity */}
                    <span className={cn(
                      'text-[10px] font-mono font-medium',
                      item.available ? 'text-[var(--green)]' : 'text-3'
                    )}>
                      {item.available ? 'Available' : 'Unavailable'}
                    </span>
                  </div>
                </div>

                {/* What it checks */}
                <div className="space-y-3.5 my-4 text-xs">
                  <div>
                    <p className="label text-3 mb-1">What It Checks</p>
                    <p className="text-2 leading-relaxed bg-surface-2/60 p-2.5 rounded border border-[var(--border)]">
                      {spec.whatItChecks}
                    </p>
                  </div>

                  {/* Evidence Produced */}
                  <div>
                    <p className="label text-3 mb-1">Evidence Produced</p>
                    <ul className="space-y-1 bg-surface-2/40 p-2.5 rounded border border-[var(--border)]">
                      {spec.evidenceProduced.map((ev, i) => (
                        <li key={i} className="flex items-start gap-2 text-2 text-[11px] leading-tight">
                          <CheckCircle2 className={cn('w-3 h-3 mt-0.5 flex-shrink-0', spec.color)} />
                          <span>{ev}</span>
                        </li>
                      ))}
                    </ul>
                  </div>

                  {/* Supported Access / Input */}
                  <div>
                    <p className="label text-3 mb-1">Supported Access / Input</p>
                    <div className="bg-surface-2/40 p-2 rounded border border-[var(--border)] text-[11px] text-2 font-mono">
                      {spec.supportedInput}
                    </div>
                  </div>

                  {/* Important Limitations */}
                  <div>
                    <p className="label text-amber mb-1 flex items-center gap-1">
                      <AlertCircle className="w-3 h-3 text-[var(--amber)]" />
                      Important Limitations
                    </p>
                    <p className="text-[11px] text-3 leading-relaxed pl-2 border-l-2 border-[var(--amber-border)]">
                      {Array.isArray(spec.limitations) ? spec.limitations.join(' ') : spec.limitations}
                    </p>
                  </div>
                </div>
              </div>

              {/* Card Footer: Version, Engine ID & Inspect Method Trigger */}
              <div className="pt-3 border-t border-[var(--border)] flex items-center justify-between text-[11px] font-mono text-3 mt-auto">
                <span className="truncate max-w-[200px]">
                  ID: <code className="text-2">{item.id}</code>
                </span>
                <button
                  type="button"
                  onClick={() => setSelectedDetector(item.code)}
                  data-testid={`inspect-detector-${item.code.toLowerCase()}`}
                  className="inline-flex items-center gap-1 text-xs font-semibold text-accent hover:underline focus:outline-none"
                >
                  <span>Inspect Method</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {/* ── Supported File Formats Reference ── */}
      {data && (
        <div className="card p-6 space-y-4">
          <div className="flex items-center justify-between border-b border-[var(--border)] pb-3">
            <div className="flex items-center gap-2">
              <FileCheck2 className="w-4 h-4 text-accent" />
              <h2 className="text-sm font-bold text-1 uppercase tracking-wider font-mono">
                Supported Ingestion & Model Formats
              </h2>
            </div>
            <span className="text-xs text-3 font-mono">Offline Air-Gapped Staging</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
            {/* Dataset Formats */}
            <div className="space-y-2">
              <p className="label text-3">Dataset Formats</p>
              <p className="text-xs text-3">
                Directories of images, ZIP archives, or standard annotation manifests:
              </p>
              <div className="flex flex-wrap gap-1.5 pt-1">
                {data.supported_dataset_formats.map(fmt => (
                  <span
                    key={fmt}
                    className="px-2.5 py-1 rounded bg-surface-2 border border-[var(--border)] text-xs font-mono font-medium text-1"
                  >
                    {fmt}
                  </span>
                ))}
              </div>
            </div>

            {/* Model Formats */}
            <div className="space-y-2">
              <p className="label text-3">Model Formats</p>
              <p className="text-xs text-3">
                Serialized models for structural fingerprinting and behavioral execution:
              </p>
              <div className="flex flex-wrap gap-1.5 pt-1">
                {data.supported_model_formats.map(fmt => (
                  <span
                    key={fmt}
                    className="px-2.5 py-1 rounded bg-surface-2 border border-[var(--border)] text-xs font-mono font-medium text-1"
                  >
                    {fmt}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Detector Method Detail Modal */}
      <DetectorDetailModal
        detectorIdOrCode={selectedDetector}
        onClose={() => setSelectedDetector(null)}
        liveCapability={
          selectedDetector && data?.detectors
            ? data.detectors.find(
                (d) =>
                  normalizeDetectorCode(d.detector_id) === selectedDetector ||
                  d.detector_id === selectedDetector
              )
            : null
        }
      />
    </div>
  );
}
