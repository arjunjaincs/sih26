import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Database, 
  Cpu, 
  GitBranch, 
  ShieldCheck, 
  Lock, 
  ChevronDown, 
  ChevronUp, 
  CheckCircle2, 
  ArrowRight,
  Layers,
  Sparkles,
  FileCheck,
  Hash
} from 'lucide-react';
import type { CapabilitiesResponse, DetectorCapabilitySchema } from '../types/api';
import { getCapabilities, NetworkError } from '../api/client';
import { ErrorState } from '../components/ErrorState';
import { cn } from '../lib/cn';

interface LayerMeta {
  code: string;
  pillar: string;
  category: 'detector' | 'ledger';
  icon: typeof Database;
  color: string;
  bg: string;
  badgeBg: string;
  borderHover: string;
  glowColor: string;
  features: string[];
  techSpec: string;
  guarantee: string;
}

const LAYER_REGISTRY: Record<string, LayerMeta> = {
  'DI-01': {
    code: 'DI-01',
    pillar: 'Dataset Hygiene & Integrity',
    category: 'detector',
    icon: Database,
    color: 'text-blue-400',
    bg: 'bg-blue-500/10',
    badgeBg: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
    borderHover: 'hover:border-blue-500/50',
    glowColor: 'rgba(59, 130, 246, 0.12)',
    features: [
      'Exact SHA-256 Byte Deduplication',
      'Perceptual pHash Near-Duplicates (Hamming ≤10)',
      'Corrupt & Truncated Image Detection',
      'Dataset Hygiene & Format Validation',
    ],
    techSpec: 'Offline dual-phase hashing engine combining full-content SHA-256 and 64-bit DCT perceptual hash (pHash) clustering.',
    guarantee: 'Identifies image redundancy and integrity flaws before training or evaluation pipelines run.',
  },
  'MI-01': {
    code: 'MI-01',
    pillar: 'Model Architecture & Weights',
    category: 'detector',
    icon: Cpu,
    color: 'text-purple-400',
    bg: 'bg-purple-500/10',
    badgeBg: 'bg-purple-500/15 text-purple-400 border-purple-500/30',
    borderHover: 'hover:border-purple-500/50',
    glowColor: 'rgba(168, 85, 247, 0.12)',
    features: [
      'Layer 1: SHA-256 Raw Byte Fingerprint',
      'Layer 2: Structural AST & Topology Digest',
      'Layer 3: Invariant Behavioral Test Battery',
      'Layer 4: Zero-Knowledge Reference Comparison',
    ],
    techSpec: 'Multi-layer structural AST digest and deterministic behavioral activation profiling against a reference baseline.',
    guarantee: 'Guarantees the deployed model has not been substituted, modified, or altered in storage.',
  },
  'PI-01': {
    code: 'PI-01',
    pillar: 'Cryptographic Provenance',
    category: 'detector',
    icon: GitBranch,
    color: 'text-amber-400',
    bg: 'bg-amber-500/10',
    badgeBg: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
    borderHover: 'hover:border-amber-500/50',
    glowColor: 'rgba(245, 158, 11, 0.12)',
    features: [
      'Ed25519 Cryptographic Signature Checks',
      'Input-to-Inference Hash Binding',
      'Immutable Provenance Manifest Validation',
      'Timestamp & Replay Protection Verification',
    ],
    techSpec: 'Cryptographically binds model weights, dataset version, and runtime inference parameters into signed manifests.',
    guarantee: 'Ensures untampered lineage and chain of custody from training inputs to predictions.',
  },
  'AT-01': {
    code: 'AT-01',
    pillar: 'Tamper-Evident Ledger',
    category: 'ledger',
    icon: ShieldCheck,
    color: 'text-emerald-400',
    bg: 'bg-emerald-500/10',
    badgeBg: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
    borderHover: 'hover:border-emerald-500/50',
    glowColor: 'rgba(16, 185, 129, 0.12)',
    features: [
      'Append-Only SHA-256 Hash Chain',
      'Genesis Block Anchor & Link Verification',
      'Instant Tamper & Break Localization',
      'Exportable Proof for External Auditors',
    ],
    techSpec: 'Cryptographic append-only hash chain where every event hash is cryptographically linked to previous block hashes.',
    guarantee: 'Any retroactive tampering or event deletion mathematically invalidates the entire chain.',
  },
};

function resolveLayerMeta(id: string): LayerMeta {
  const lower = id.toLowerCase();
  if (lower.includes('di01') || id === 'DI-01') return LAYER_REGISTRY['DI-01'];
  if (lower.includes('mi01') || id === 'MI-01') return LAYER_REGISTRY['MI-01'];
  if (lower.includes('pi01') || id === 'PI-01') return LAYER_REGISTRY['PI-01'];
  if (lower.includes('at01') || id === 'AT-01') return LAYER_REGISTRY['AT-01'];
  return LAYER_REGISTRY['DI-01'];
}

interface CapabilityItem {
  id: string;
  code: string;
  name: string;
  description: string;
  version: string;
  applicable_asset_types: string[];
  available: boolean;
  meta: LayerMeta;
}

function CapabilityCard({ item }: { item: CapabilityItem }) {
  const [expanded, setExpanded] = useState(false);
  const { meta } = item;
  const Icon = meta.icon;

  return (
    <motion.div 
      layout
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.98 }}
      transition={{ duration: 0.25, ease: 'easeOut' }}
      whileHover={{ y: -3, transition: { duration: 0.15 } }}
      className={cn(
        'group relative rounded-2xl border border-[var(--border)] bg-surface p-6 flex flex-col justify-between transition-all duration-200',
        'shadow-sm hover:shadow-xl',
        meta.borderHover,
      )}
      style={{
        boxShadow: `0 4px 20px -2px ${meta.glowColor}`,
      }}
    >
      {/* Top row: Icon, Badge, and Code */}
      <div className="flex items-start justify-between gap-3 mb-4">
        <div className="flex items-center gap-3">
          <div className={cn('w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 border border-white/5 transition-transform group-hover:scale-105', meta.bg)}>
            <Icon className={cn('w-5 h-5', meta.color)} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className={cn('font-mono text-[11px] font-bold px-2 py-0.5 rounded border', meta.badgeBg)}>
                {meta.code}
              </span>
              <span className="text-[10px] font-mono text-3 uppercase tracking-wider">
                {meta.pillar}
              </span>
            </div>
            <h3 className="text-base font-semibold text-1 leading-snug mt-1">{item.name}</h3>
          </div>
        </div>

        {/* Status indicator */}
        <div 
          className={cn(
            'flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border flex-shrink-0',
            item.available
              ? 'bg-[var(--green-bg)] text-[var(--green)] border-[var(--green)]/30'
              : 'bg-surface-2 text-3 border-[var(--border)]'
          )}
        >
          <span 
            className={cn(
              'w-1.5 h-1.5 rounded-full',
              item.available ? 'bg-[var(--green)] animate-pulse' : 'bg-text4'
            )} 
          />
          <span>{item.available ? 'Available' : 'Unavailable'}</span>
        </div>
      </div>

      {/* Description */}
      <p className="text-xs text-2 leading-relaxed mb-4">
        {item.description}
      </p>

      {/* Feature chips list */}
      <div className="space-y-1.5 mb-4">
        <p className="text-[10px] font-mono text-3 uppercase tracking-wider font-semibold">Core Guarantees</p>
        <div className="grid grid-cols-1 gap-1.5">
          {meta.features.slice(0, expanded ? undefined : 2).map((feature, i) => (
            <div key={i} className="flex items-center gap-2 text-xs text-2 bg-surface-2/60 px-2.5 py-1.5 rounded-lg border border-[var(--border)]">
              <CheckCircle2 className={cn('w-3.5 h-3.5 flex-shrink-0', meta.color)} />
              <span className="truncate">{feature}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Expandable Technical Specification */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden border-t border-[var(--border)] pt-3.5 mt-1 mb-4 space-y-3"
          >
            <div>
              <p className="text-[10px] font-mono text-3 uppercase tracking-wider mb-1 font-semibold">Technical Implementation</p>
              <p className="text-xs text-2 leading-relaxed bg-surface-2/40 p-2.5 rounded-lg border border-[var(--border)]">
                {meta.techSpec}
              </p>
            </div>

            <div>
              <p className="text-[10px] font-mono text-3 uppercase tracking-wider mb-1 font-semibold">Assurance Impact</p>
              <p className="text-xs text-accent/90 bg-[var(--accent-bg)] p-2.5 rounded-lg border border-accent/20">
                {meta.guarantee}
              </p>
            </div>

            <div className="flex items-center justify-between text-[11px] font-mono text-3 pt-1">
              <span>Engine Version: <strong className="text-1 font-semibold">v{item.version}</strong></span>
              <span className="text-accent flex items-center gap-1 font-medium">
                <Lock className="w-3 h-3" />
                Air-Gapped Compatible
              </span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Card Footer: Formats & Expand toggle */}
      <div className="pt-3 border-t border-[var(--border)] flex items-center justify-between mt-auto">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-[10px] font-mono text-3">Targets:</span>
          {item.applicable_asset_types.map(t => (
            <span 
              key={t} 
              className="px-2 py-0.5 rounded bg-surface-2 border border-[var(--border)] text-[10px] font-mono font-medium text-2 uppercase"
            >
              {t}
            </span>
          ))}
        </div>

        <button
          type="button"
          onClick={() => setExpanded(prev => !prev)}
          className="inline-flex items-center gap-1 text-xs text-accent font-medium hover:text-[var(--accent-2)] transition-colors py-1 cursor-pointer"
        >
          <span>{expanded ? 'Show less' : 'Show details'}</span>
          {expanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
        </button>
      </div>
    </motion.div>
  );
}

export function Capabilities() {
  const [data, setData] = useState<CapabilitiesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [offline, setOffline] = useState(false);
  const [activeTab, setActiveTab] = useState<'all' | 'detectors' | 'ledger'>('all');

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
        <div className="h-14 bg-surface-2 rounded-xl animate-pulse w-1/3" />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-64 bg-surface-2 rounded-2xl animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-6xl mx-auto px-6 py-10">
        <ErrorState
          title="Could not load capabilities"
          message={offline
            ? 'The PRAMAAN backend is not running. Start it and refresh.'
            : error}
        />
      </div>
    );
  }

  // Build the complete 4-pillar list:
  // Detectors from backend (DI-01, MI-01, PI-01) + the Core Tamper-Evident Audit Trail (AT-01)
  const detectorItems: CapabilityItem[] = (data?.detectors ?? []).map(d => {
    const meta = resolveLayerMeta(d.detector_id);
    return {
      id: d.detector_id,
      code: meta.code,
      name: d.name,
      description: d.description,
      version: d.version,
      applicable_asset_types: d.applicable_asset_types,
      available: d.available,
      meta,
    };
  });

  // Ensure AT-01 (Tamper-Evident Audit Trail) is always represented in the full assurance stack
  const at01Item: CapabilityItem = {
    id: 'audit.ledger.at01_chain',
    code: 'AT-01',
    name: 'AT-01: Tamper-Evident Audit Trail',
    description: 'Cryptographic append-only hash chain linking every assessment event, finding, and evidence record back to the genesis block for independent auditing.',
    version: data?.pramaan_version ?? '1.0.0',
    applicable_asset_types: ['AUDIT_LEDGER', 'EVENTS'],
    available: true,
    meta: LAYER_REGISTRY['AT-01'],
  };

  const allCapabilities: CapabilityItem[] = [...detectorItems, at01Item];

  const filteredItems = allCapabilities.filter(item => {
    if (activeTab === 'detectors') return item.meta.category === 'detector';
    if (activeTab === 'ledger') return item.meta.category === 'ledger';
    return true;
  });

  const availableCount = allCapabilities.filter(c => c.available).length;

  return (
    <div className="max-w-6xl mx-auto px-6 py-10 space-y-8">
      {/* ── Top Header ── */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 border-b border-[var(--border)] pb-6">
        <div>
          <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-[var(--accent-bg)] border border-accent/20 mb-2">
            <Sparkles className="w-3.5 h-3.5 text-accent" />
            <span className="font-mono text-[11px] font-semibold text-accent uppercase tracking-wider">
              PRAMAAN v{data?.pramaan_version ?? '1.0.0'} // Assurance Architecture
            </span>
          </div>
          <h1 className="text-3xl font-extrabold text-1 tracking-tight">System Capabilities</h1>
          <p className="mt-1 text-sm text-2 max-w-xl">
            Offline-first computer vision integrity assurance engine featuring 4 cryptographic layers, automated anomaly detectors, and tamper-evident audit trails.
          </p>
        </div>

        {/* Quick actions */}
        <div className="flex items-center gap-3">
          <Link
            to="/new"
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-accent text-white text-xs font-semibold hover:bg-[var(--accent-2)] transition-colors shadow-sm active:scale-[0.98]"
          >
            <span>Start Assessment</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>
          <Link
            to="/assessments"
            className="inline-flex items-center gap-2 px-3.5 py-2 rounded-lg border border-[var(--border)] text-1 text-xs font-medium hover:bg-surface-2 transition-colors"
          >
            <span>View History</span>
          </Link>
        </div>
      </div>

      {/* ── Key Metrics Ribbon ── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3.5">
        <div className="p-3.5 rounded-xl border border-[var(--border)] bg-surface flex flex-col gap-1">
          <div className="flex items-center justify-between text-3">
            <span className="text-[11px] font-mono uppercase">Assurance Layers</span>
            <Layers className="w-3.5 h-3.5 text-accent" />
          </div>
          <p className="text-xl font-bold text-1">4 Layers</p>
          <span className="text-[10px] text-[var(--green)] font-medium">100% Offline Capable</span>
        </div>

        <div className="p-3.5 rounded-xl border border-[var(--border)] bg-surface flex flex-col gap-1">
          <div className="flex items-center justify-between text-3">
            <span className="text-[11px] font-mono uppercase">Engine Status</span>
            <span className="w-2 h-2 rounded-full bg-[var(--green)] animate-pulse" />
          </div>
          <p className="text-xl font-bold text-1">{availableCount} / {allCapabilities.length}</p>
          <span className="text-[10px] text-2 font-medium">Operational & Ready</span>
        </div>

        <div className="p-3.5 rounded-xl border border-[var(--border)] bg-surface flex flex-col gap-1">
          <div className="flex items-center justify-between text-3">
            <span className="text-[11px] font-mono uppercase">Audit Chain</span>
            <Hash className="w-3.5 h-3.5 text-emerald-400" />
          </div>
          <p className="text-xl font-bold text-1">SHA-256</p>
          <span className="text-[10px] text-emerald-400 font-medium">Tamper-Evident Ledger</span>
        </div>

        <div className="p-3.5 rounded-xl border border-[var(--border)] bg-surface flex flex-col gap-1">
          <div className="flex items-center justify-between text-3">
            <span className="text-[11px] font-mono uppercase">Signatures</span>
            <Lock className="w-3.5 h-3.5 text-amber-400" />
          </div>
          <p className="text-xl font-bold text-1">Ed25519</p>
          <span className="text-[10px] text-amber-400 font-medium">Provenance Attestation</span>
        </div>
      </div>

      {/* ── Category Filter Tabs ── */}
      <div className="flex items-center gap-2 border-b border-[var(--border)] pb-3">
        {[
          { id: 'all', label: `All Capabilities (${allCapabilities.length})` },
          { id: 'detectors', label: `Automated Detectors (${detectorItems.length})` },
          { id: 'ledger', label: 'Audit Trail & Ledger (1)' },
        ].map(tab => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setActiveTab(tab.id as any)}
            className={cn(
              'px-3.5 py-1.5 rounded-lg text-xs font-medium transition-all duration-150 cursor-pointer',
              activeTab === tab.id
                ? 'bg-accent text-white shadow-sm'
                : 'text-2 hover:text-1 hover:bg-surface-2'
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* ── Capabilities Grid ── */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <AnimatePresence mode="popLayout">
          {filteredItems.map(item => (
            <CapabilityCard key={item.id} item={item} />
          ))}
        </AnimatePresence>
      </div>

      {/* ── Supported Formats & Architecture Reference ── */}
      {data && (
        <div className="rounded-2xl border border-[var(--border)] bg-surface p-6 space-y-5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <FileCheck className="w-4 h-4 text-accent" />
              <h2 className="text-sm font-bold text-1 uppercase tracking-wider">
                Supported File Formats & Runtime Environments
              </h2>
            </div>
            <span className="text-[10px] font-mono text-3">PRAMAAN v{data.pramaan_version}</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
            {/* Dataset formats */}
            <div className="p-4 rounded-xl border border-[var(--border)] bg-surface-2/40">
              <p className="text-xs font-semibold text-1 mb-1.5 flex items-center gap-2">
                <Database className="w-3.5 h-3.5 text-blue-400" />
                Dataset Ingestion Formats
              </p>
              <p className="text-[11px] text-3 mb-3 leading-relaxed">
                Raw image directories, compressed ZIP archives, and annotated dataset schemas:
              </p>
              <div className="flex flex-wrap gap-1.5">
                {data.supported_dataset_formats.map(f => (
                  <span
                    key={f}
                    className="px-2.5 py-1 rounded-md bg-surface border border-[var(--border)] text-xs font-mono font-medium text-1"
                  >
                    {f}
                  </span>
                ))}
              </div>
            </div>

            {/* Model formats */}
            <div className="p-4 rounded-xl border border-[var(--border)] bg-surface-2/40">
              <p className="text-xs font-semibold text-1 mb-1.5 flex items-center gap-2">
                <Cpu className="w-3.5 h-3.5 text-purple-400" />
                Model Serialization Formats
              </p>
              <p className="text-[11px] text-3 mb-3 leading-relaxed">
                Supported graph and weights formats for structural and behavioral fingerprinting:
              </p>
              <div className="flex flex-wrap gap-1.5">
                {data.supported_model_formats.map(f => (
                  <span
                    key={f}
                    className="px-2.5 py-1 rounded-md bg-surface border border-[var(--border)] text-xs font-mono font-medium text-1"
                  >
                    {f}
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
