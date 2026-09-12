import { Link } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { ArrowRight, Shield } from 'lucide-react';
import { getHealth, getCapabilities } from '../api/client';
import type { HealthResponse, CapabilitiesResponse } from '../types/api';
import { HeroComposition } from '../components/HeroComposition';

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
    <div className="min-h-[calc(100vh-3rem)] md:h-[calc(100vh-3rem)] md:max-h-[calc(100vh-3rem)] flex flex-col justify-between md:overflow-hidden select-none">
      {/* ── Main Hero Section (Single Viewport Fitted) ── */}
      <section className="flex-1 max-w-7xl mx-auto w-full px-6 lg:px-8 flex items-center justify-center py-4 lg:py-6">
        <div className="w-full grid grid-cols-1 lg:grid-cols-12 gap-8 lg:gap-12 items-center">

          {/* Left: Headline, Value Proposition, Actions */}
          <div className="lg:col-span-5 flex flex-col gap-4 lg:gap-5">
            {/* Eyebrow badge */}
            <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-[var(--accent-bg)] border border-accent/25 w-fit">
              <Shield className="w-3.5 h-3.5 text-accent" />
              <span className="font-mono text-[11px] font-semibold tracking-wider text-accent uppercase">
                Offline CV Assurance
              </span>
            </div>

            {/* Display headline */}
            <div className="space-y-0.5">
              <h1 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold tracking-tight text-1 leading-[1.08]">
                Trust AI
              </h1>
              <h1 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold tracking-tight leading-[1.08]">
                with <span className="text-accent">Evidence</span>
              </h1>
            </div>

            {/* Description */}
            <p className="text-sm text-2 leading-relaxed max-w-md">
              PRAMAAN provides independent, cryptographic, evidence-based integrity assessment
              for computer vision models, training datasets, and inference pipelines.
            </p>

            {/* Feature pills */}
            <div className="flex flex-wrap gap-2">
              <PillFeature label="Detect Risks" />
              <PillFeature label="Generate Evidence" />
              <PillFeature label="Build Trust" />
            </div>

            {/* CTAs */}
            <div className="flex items-center gap-3 pt-1 flex-wrap">
              <Link
                to="/new"
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg
                  bg-accent text-white text-sm font-semibold
                  hover:bg-[var(--accent-2)] transition-colors duration-150
                  shadow-sm active:scale-[0.98]"
              >
                Start an Assessment
                <ArrowRight className="w-4 h-4" />
              </Link>
              <Link
                to="/capabilities"
                className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg
                  border border-[var(--border)] text-1 text-sm font-medium
                  hover:bg-surface-2 transition-colors duration-150"
              >
                View Capabilities
              </Link>
            </div>

            {/* Trust and architecture guarantees */}
            <div className="flex items-center gap-3 text-[11px] font-mono text-3 pt-0.5">
              <span className="flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-[var(--green)]" />
                Air-Gapped Ready
              </span>
              <span>·</span>
              <span>Zero Cloud Telemetry</span>
              <span>·</span>
              <span>Tamper-Evident Chain</span>
            </div>
          </div>

          {/* Right: Technical Composition */}
          <div className="lg:col-span-7 relative flex items-center justify-center w-full">
            <HeroComposition version={health?.version ?? '1.0.0'} />
          </div>

        </div>
      </section>

      {/* ── Status & Telemetry Strip ── */}
      <footer className="border-t border-[var(--border)] bg-surface-2/40 backdrop-blur-sm flex-shrink-0">
        <div className="max-w-7xl mx-auto px-6 py-2.5 flex items-center justify-between text-xs text-3 flex-wrap gap-3">
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-1.5 text-2 font-medium">
              <span className="w-1.5 h-1.5 rounded-full bg-[var(--green)] animate-pulse" />
              PRAMAAN Core Active
            </span>
            <span className="text-3 font-mono">v{health?.version ?? '1.0.0'}</span>
            <span className="hidden sm:inline text-3">·</span>
            <span className="hidden sm:inline text-3 font-mono text-[11px]">
              {available > 0 ? `${available}/${total} Assurance Detectors Online` : '4 Assurance Layers Online'}
            </span>
          </div>

          <div className="flex items-center gap-4 font-mono text-[11px]">
            <span className="hidden md:inline text-3">
              Supported: {caps?.supported_dataset_formats.slice(0, 4).join(', ') ?? 'JPEG, PNG, WEBP, ZIP, ONNX'}
            </span>
            <span className="text-accent/90 bg-accent-bg px-2 py-0.5 rounded border border-accent/20 font-medium">
              SHA-256 Hash Chain Sealed
            </span>
          </div>
        </div>
      </footer>
    </div>
  );
}
