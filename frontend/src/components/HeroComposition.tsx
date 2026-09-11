import { useState } from 'react';
import { 
  Database, 
  Cpu, 
  GitBranch, 
  ShieldCheck, 
  Lock, 
  Hash, 
  CheckCircle2, 
  ArrowUpRight 
} from 'lucide-react';

interface LayerItem {
  id: string;
  code: string;
  name: string;
  icon: typeof Database;
  category: string;
  status: string;
  summary: string;
  hash: string;
  features: string[];
}

const LAYERS: LayerItem[] = [
  {
    id: 'datasets',
    code: 'DI-01',
    name: 'Dataset Integrity',
    icon: Database,
    category: 'Ingestion & Hygiene',
    status: 'AVAILABLE',
    summary: 'Detects exact duplicates, near-duplicates, and dataset format anomalies.',
    hash: 'sha256:4a8f9b...12c8',
    features: ['Duplicate hashing', 'Near-duplicate detection', 'Dataset validation'],
  },
  {
    id: 'models',
    code: 'MI-01',
    name: 'Model Architecture',
    icon: Cpu,
    category: 'Structural Fingerprint',
    status: 'AVAILABLE',
    summary: 'Cryptographic weight & topology digest prevents model substitution.',
    hash: 'sha256:9e14a2...770b',
    features: ['Weight AST digest', 'Layer invariant checks', 'Format compliance'],
  },
  {
    id: 'provenance',
    code: 'PI-01',
    name: 'Provenance Attestation',
    icon: GitBranch,
    category: 'Cryptographic Lineage',
    status: 'AVAILABLE',
    summary: 'Cryptographically signed manifests link inputs directly to inferences.',
    hash: 'sig:ed25519:7b0f...3d9a',
    features: ['Lineage manifest', 'Digital signature', 'Replay protection'],
  },
  {
    id: 'audit',
    code: 'AT-01',
    name: 'Tamper-Evident Audit Trail',
    icon: ShieldCheck,
    category: 'Tamper-Evident Ledger',
    status: 'AVAILABLE',
    summary: 'Append-only SHA-256 hash chain verifiable by independent external auditors.',
    hash: 'sha256:chain:d51c...884f',
    features: ['SHA-256 Hash Chain', 'Event timestamps', 'Hash-linked verification'],
  },
];

export function HeroComposition() {
  const [selectedLayer, setSelectedLayer] = useState<string>('models');
  const active = LAYERS.find(l => l.id === selectedLayer) || LAYERS[1];

  return (
    <div className="relative w-full max-w-xl mx-auto select-none">
      {/* Main Container */}
      <div className="relative rounded-2xl border border-[var(--border-strong)] bg-surface shadow-lg overflow-hidden">
        
        {/* Technical Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-[var(--border)] bg-surface-2/60 text-xs">
          <div className="flex items-center gap-2">
            <span className="inline-block w-2 h-2 rounded-full bg-accent" />
            <span className="font-mono font-medium text-1 tracking-wider text-[11px] uppercase">
              PRAMAAN CORE // ASSURANCE STACK
            </span>
          </div>
          <div className="flex items-center gap-3 font-mono text-[10px] text-3">
            <span className="hidden sm:inline-flex items-center gap-1">
              <Lock className="w-3 h-3 text-accent" />
              SHA-256 HASH CHAIN
            </span>
            <span className="px-2 py-0.5 rounded bg-surface-3 border border-[var(--border)] text-2 font-semibold">
              v1.0.4
            </span>
          </div>
        </div>

        {/* Central Composition */}
        <div className="p-5 sm:p-6 flex flex-col gap-5">
          
          {/* Schematic & Active Capability Box */}
          <div className="relative rounded-xl border border-[var(--border)] bg-surface-2/40 p-4 overflow-hidden">
            <div className="relative flex flex-col sm:flex-row items-center justify-between gap-4">
              
              {/* Central Geometric Emblem */}
              <div className="relative flex items-center justify-center w-24 h-24 sm:w-28 sm:h-28 flex-shrink-0">
                {/* SVG Technical Rings */}
                <svg className="absolute inset-0 w-full h-full text-accent" viewBox="0 0 100 100">
                  <circle 
                    cx="50" 
                    cy="50" 
                    r="46" 
                    fill="none" 
                    stroke="currentColor" 
                    strokeWidth="1" 
                    strokeDasharray="4 4" 
                    className="opacity-25" 
                  />
                  <circle 
                    cx="50" 
                    cy="50" 
                    r="36" 
                    fill="none" 
                    stroke="currentColor" 
                    strokeWidth="1" 
                    strokeDasharray="2 4" 
                    className="opacity-35" 
                  />
                  <polygon 
                    points="50,14 82,32 82,68 50,86 18,68 18,32" 
                    fill="currentColor" 
                    fillOpacity="0.04" 
                    stroke="currentColor" 
                    strokeWidth="1.25" 
                    className="text-accent opacity-60" 
                  />
                </svg>

                {/* Inner Seal */}
                <div className="relative z-10 flex flex-col items-center justify-center p-3 rounded-full bg-surface border border-[var(--border-strong)] shadow-sm">
                  <ShieldCheck className="w-8 h-8 text-accent" />
                </div>
              </div>

              {/* Active Layer Detail Card */}
              <div className="flex-1 w-full flex flex-col justify-between pl-0 sm:pl-2">
                <div className="flex items-center justify-between gap-2 mb-1.5">
                  <div className="flex items-center gap-1.5">
                    <span className="font-mono text-[10px] text-accent font-semibold px-1.5 py-0.5 rounded bg-accent-bg border border-accent/20">
                      {active.code}
                    </span>
                    <h3 className="text-sm font-semibold text-1">{active.name}</h3>
                  </div>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-surface border border-[var(--border)] text-2 font-medium">
                    {active.status}
                  </span>
                </div>

                <p className="text-xs text-2 leading-relaxed mb-3">
                  {active.summary}
                </p>

                {/* Feature Chips */}
                <div className="flex flex-wrap gap-1.5">
                  {active.features.map(f => (
                    <span 
                      key={f} 
                      className="text-[10px] font-mono px-2 py-0.5 rounded bg-surface border border-[var(--border)] text-3 flex items-center gap-1"
                    >
                      <CheckCircle2 className="w-2.5 h-2.5 text-accent" />
                      {f}
                    </span>
                  ))}
                </div>
              </div>
            </div>

            {/* Active Layer Hash Footer */}
            <div className="mt-3 pt-2.5 border-t border-[var(--border)] flex items-center justify-between text-[10px] font-mono text-3">
              <span className="flex items-center gap-1 text-2 truncate max-w-[280px]">
                <Hash className="w-3 h-3 text-accent flex-shrink-0" />
                {active.hash}
              </span>
              <span className="text-[9px] uppercase tracking-wider text-accent font-semibold flex items-center gap-0.5">
                ASSURANCE SPEC
                <ArrowUpRight className="w-3 h-3" />
              </span>
            </div>
          </div>

          {/* 4 Architectural Tier Selectors */}
          <div className="grid grid-cols-2 gap-2.5">
            {LAYERS.map((layer) => {
              const Icon = layer.icon;
              const isSelected = layer.id === selectedLayer;

              return (
                <button
                  key={layer.id}
                  type="button"
                  onClick={() => setSelectedLayer(layer.id)}
                  className={`flex flex-col text-left p-3 rounded-xl border transition-all duration-150 cursor-pointer ${
                    isSelected
                      ? 'border-accent bg-accent-bg ring-1 ring-accent/30'
                      : 'border-[var(--border)] bg-surface-2/40 hover:bg-surface-2 hover:border-[var(--border-strong)]'
                  }`}
                >
                  <div className="flex items-center justify-between w-full mb-1.5">
                    <div className="flex items-center gap-2">
                      <div className={`p-1.5 rounded-md ${isSelected ? 'bg-accent text-white' : 'bg-surface text-3'}`}>
                        <Icon className="w-3.5 h-3.5" />
                      </div>
                      <span className="font-mono text-[10px] font-semibold text-accent">
                        {layer.code}
                      </span>
                    </div>
                    <span className="w-1.5 h-1.5 rounded-full bg-[var(--border-strong)]" />
                  </div>
                  <span className="text-xs font-semibold text-1 truncate">
                    {layer.name}
                  </span>
                  <span className="text-[10px] text-3 font-mono truncate mt-0.5">
                    {layer.category}
                  </span>
                </button>
              );
            })}
          </div>

          {/* Bottom Capability Strip */}
          <div className="px-3.5 py-2.5 rounded-lg border border-[var(--border)] bg-surface-2/50 flex items-center justify-between text-[10px] font-mono text-3 flex-wrap gap-2">
            <div className="flex items-center gap-1.5 text-1 font-medium">
              <ShieldCheck className="w-3.5 h-3.5 text-accent" />
              <span>4 ASSURANCE LAYERS</span>
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              <span className="px-1.5 py-0.5 rounded bg-surface border border-[var(--border)] text-3">
                OFFLINE EXECUTION
              </span>
              <span className="px-1.5 py-0.5 rounded bg-surface border border-[var(--border)] text-3">
                CRYPTOGRAPHIC PROVENANCE
              </span>
              <span className="hidden sm:inline-block px-1.5 py-0.5 rounded bg-surface border border-[var(--border)] text-3">
                EVIDENCE-BACKED FINDINGS
              </span>
            </div>
          </div>

        </div>

      </div>
    </div>
  );
}
