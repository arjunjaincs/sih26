import { Link } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { ArrowRight, Shield, Database, Cpu, GitBranch } from 'lucide-react';
import { getHealth, getCapabilities } from '../api/client';
import type { HealthResponse, CapabilitiesResponse } from '../types/api';
import { HeroComposition } from '../components/HeroComposition';

const SIGNALS = [
  {
    icon: Database,
    label: 'Dataset Integrity',
    desc: 'Detect duplicate images, near-duplicates, and dataset format anomalies.',
  },
  {
    icon: Cpu,
    label: 'Model Integrity',
    desc: 'Cryptographic fingerprinting detects substitution or tampering.',
  },
  {
    icon: GitBranch,
    label: 'Provenance',
    desc: 'Cryptographically signed manifests link inputs to outputs.',
  },
];

function PillFeature({ label }: { label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium
      border border-[var(--border)] text-2 hover:border-accent hover:text-accent
      transition-colors duration-150 cursor-default select-none">
      {label}
    </span>
  );
}

export function Overview() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [caps, setCaps] = useState<CapabilitiesResponse | null>(null);

  useEffect(() => {
    let m = true;
    Promise.all([getHealth().catch(() => null), getCapabilities().catch(() => null)])
      .then(([h, c]) => { if (m) { setHealth(h); setCaps(c); } });
    return () => { m = false; };
  }, []);

  const available = caps?.detectors.filter(d => d.available).length ?? 0;
  const total = caps?.detectors.length ?? 0;

  return (
    <div className="min-h-[calc(100vh-3rem)] flex flex-col">
      {/* ── Hero ── */}
      <section className="flex-1 max-w-7xl mx-auto w-full px-6 py-16 md:py-24
        grid grid-cols-1 md:grid-cols-2 gap-12 items-center">

        {/* Left: Copy */}
        <div className="flex flex-col gap-6">
          {/* Eyebrow */}
          <div className="flex items-center gap-2">
            <Shield className="w-4 h-4 text-accent" />
            <span className="label text-accent tracking-widest">PRAMAAN</span>
          </div>

          {/* Display headline */}
          <div>
            <h1 className="text-4xl md:text-5xl font-bold leading-[1.05] tracking-tight text-1">
              Trust AI
            </h1>
            <h1 className="text-4xl md:text-5xl font-bold leading-[1.05] tracking-tight">
              with{' '}
              <span className="text-accent">Evidence</span>
            </h1>
          </div>

          {/* Description */}
          <p className="text-sm text-2 leading-relaxed max-w-sm">
            PRAMAAN provides independent, evidence-based integrity assessment
            for AI models, datasets, and inference outputs.
          </p>

          {/* Feature pills */}
          <div className="flex flex-wrap gap-2">
            <PillFeature label="Detect Risks" />
            <PillFeature label="Generate Evidence" />
            <PillFeature label="Build Trust" />
          </div>

          {/* CTAs */}
          <div className="flex items-center gap-3 flex-wrap">
            <Link
              to="/new"
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded
                bg-accent text-white text-sm font-semibold
                hover:bg-[var(--accent-2)] transition-colors duration-150
                active:scale-[0.97]"
            >
              Start an Assessment
              <ArrowRight className="w-4 h-4" />
            </Link>
            <Link
              to="/capabilities"
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded
                border border-[var(--border)] text-1 text-sm font-medium
                hover:bg-surface-2 transition-colors duration-150"
            >
              View Capabilities
            </Link>
          </div>

          {/* Tagline */}
          <p className="text-xs text-3">
            Transparent AI. Safer Tomorrow.
          </p>
        </div>

        {/* Right: Technical Composition */}
        <div className="relative flex items-center justify-center w-full">
          <HeroComposition />
        </div>
      </section>

      {/* ── Product signals ── */}
      <section className="border-t border-[var(--border)] bg-surface/50">
        <div className="max-w-7xl mx-auto px-6 py-10 grid grid-cols-1 sm:grid-cols-3 gap-8">
          {SIGNALS.map(({ icon: Icon, label, desc }) => (
            <div key={label} className="flex items-start gap-4">
              <div className="flex-shrink-0 w-8 h-8 rounded flex items-center justify-center
                bg-[var(--accent-bg)] text-accent">
                <Icon className="w-4 h-4" />
              </div>
              <div>
                <p className="text-sm font-semibold text-1">{label}</p>
                <p className="mt-0.5 text-xs text-3 leading-relaxed">{desc}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Status strip ── */}
      {(health || caps) && (
        <div className="border-t border-[var(--border)] bg-surface/30">
          <div className="max-w-7xl mx-auto px-6 py-2.5 flex items-center gap-6 text-xs text-3 flex-wrap">
            {health && (
              <>
                <span className="flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-[var(--green)] inline-block" />
                  Service online
                </span>
                <span>v{health.version}</span>
              </>
            )}
            {caps && (
              <span>{available}/{total} detectors available</span>
            )}
            {caps && (
              <span>{caps.supported_dataset_formats.join(' · ')}</span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
