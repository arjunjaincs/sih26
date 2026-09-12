import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { 
  Database, 
  Cpu, 
  GitBranch, 
  ShieldCheck, 
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

interface LayerSpec {
  code: string;
  pillar: string;
  category: 'detector' | 'ledger';
  icon: typeof Database;
  color: string;
  bg: string;
  statusBadge: 'implemented' | 'limited' | 'not_applicable' | 'unavailable';
  statusLabel: string;
  whatItChecks: string;
  evidenceProduced: string[];
  supportedInput: string;
  limitations: string;
  version: string;
}

const STATIC_LAYER_SPECS: Record<string, LayerSpec> = {
  'DI-01': {
    code: 'DI-01',
    pillar: 'Dataset Integrity',
    category: 'detector',
    icon: Database,
    color: 'text-blue-500',
    bg: 'bg-blue-500/10 border-blue-500/20',
    statusBadge: 'implemented',
    statusLabel: 'IMPLEMENTED',
    whatItChecks: 'Exact byte duplicates (SHA-256) and perceptual near-duplicate images via DCT pHash Hamming distance clustering (Hamming ≤ 10). Detects image truncation, decode errors, and format non-conformance.',
    evidenceProduced: [
      'Duplicate image cluster manifests with member counts',
      'Normalized Hamming distance metrics (0–64)',
      'SHA-256 byte collision matching records',
      'Corrupt and unreadable image file list',
    ],
    supportedInput: 'Directory of images, compressed ZIP archives, COCO annotation schemas. Formats: JPEG, PNG, WEBP.',
    limitations: 'Pixel & perceptual space analysis only. Does not infer semantic equivalence or identify adversarial perturbations.',
    version: '1.0.0',
  },
  'MI-01': {
    code: 'MI-01',
    pillar: 'Model Integrity',
    category: 'detector',
    icon: Cpu,
    color: 'text-purple-500',
    bg: 'bg-purple-500/10 border-purple-500/20',
    statusBadge: 'limited',
    statusLabel: 'LIMITED',
    whatItChecks: 'Multi-layer structural AST and weight fingerprinting: Layer 1 (raw byte SHA-256), Layer 2 (graph topology, operator counts, input/output tensors), Layer 3 (deterministic behavioral execution battery on ONNX), Layer 4 (reference baseline comparison).',
    evidenceProduced: [
      'Structural topology digest and operator frequency table',
      'Input/output tensor shape and dtype compliance records',
      'Deterministic output deviation statistics (mean, std, min, max)',
      'Reference baseline delta finding (observed vs expected)',
    ],
    supportedInput: 'Serialized models: .onnx, .pt, .pth, .ts.',
    limitations: 'Behavioral battery supported on ONNX runtime. PyTorch state-dicts without executable architecture class are marked unavailable for execution. Identifies material structural drift; does not classify changes as malicious.',
    version: '1.0.0',
  },
  'PI-01': {
    code: 'PI-01',
    pillar: 'Provenance / Output Integrity',
    category: 'detector',
    icon: GitBranch,
    color: 'text-amber-500',
    bg: 'bg-amber-500/10 border-amber-500/20',
    statusBadge: 'implemented',
    statusLabel: 'IMPLEMENTED',
    whatItChecks: 'Cryptographic authenticity and integrity of signed ProvenanceManifest. Verifies Ed25519 digital signatures binding input dataset hash, model weight hash, and inference output digests.',
    evidenceProduced: [
      'Ed25519 signature verification statement',
      'Input-model-output cryptographic digest match records',
      'Manifest schema and timestamp replay verification',
      'Missing or tampered asset reference alerts',
    ],
    supportedInput: 'Inference bundle with signed provenance_manifest.json and Ed25519 public key.',
    limitations: 'Validates cryptographic authenticity and unhampered transmission; cannot verify initial training provenance if manifest was signed dishonestly prior to ingestion.',
    version: '1.0.0',
  },
  'AT-01': {
    code: 'AT-01',
    pillar: 'Tamper-Evident Audit Trail',
    category: 'ledger',
    icon: ShieldCheck,
    color: 'text-emerald-500',
    bg: 'bg-emerald-500/10 border-emerald-500/20',
    statusBadge: 'implemented',
    statusLabel: 'IMPLEMENTED',
    whatItChecks: 'Cryptographic append-only hash chain linking all assessment events, findings, and evidence sequentially back to the genesis block. Guarantees event immutability across the audit lifecycle.',
    evidenceProduced: [
      'Sequential block hash links (current_hash and previous_hash)',
      'Chain verification result (valid vs broken linkage)',
      'Tamper and event break point localization',
      'Exportable verification payload for third-party auditing',
    ],
    supportedInput: 'System-wide assessment lifecycle events and evidence records.',
    limitations: 'Tamper-evident ledger detects and pinpoints modification/deletion; relies on local node SQLite storage and requires external hash chain export for cross-node multi-party verification.',
    version: '1.0.0',
  },
};

function resolveSpec(id: string): LayerSpec {
  const lower = id.toLowerCase();
  if (lower.includes('di01') || id === 'DI-01') return STATIC_LAYER_SPECS['DI-01'];
  if (lower.includes('mi01') || id === 'MI-01') return STATIC_LAYER_SPECS['MI-01'];
  if (lower.includes('pi01') || id === 'PI-01') return STATIC_LAYER_SPECS['PI-01'];
  if (lower.includes('at01') || id === 'AT-01') return STATIC_LAYER_SPECS['AT-01'];
  return STATIC_LAYER_SPECS['DI-01'];
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
    const spec = resolveSpec(d.detector_id);
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
    spec: STATIC_LAYER_SPECS['AT-01'],
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
                    <StatusBadge value={spec.statusBadge} variant="availability" />
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
                      {spec.limitations}
                    </p>
                  </div>
                </div>
              </div>

              {/* Card Footer: Version & Raw Engine ID */}
              <div className="pt-3 border-t border-[var(--border)] flex items-center justify-between text-[11px] font-mono text-3 mt-auto">
                <span className="truncate max-w-[240px]">
                  ID: <code className="text-2">{item.id}</code>
                </span>
                <span>Engine v{item.version}</span>
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
    </div>
  );
}
