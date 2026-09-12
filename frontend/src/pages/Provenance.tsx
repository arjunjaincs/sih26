import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { 
  KeyRound, 
  ShieldCheck, 
  ShieldAlert, 
  CheckCircle2, 
  XCircle, 
  Copy, 
  Check, 
  Clock, 
  FileText, 
  Cpu, 
  Database,
  ArrowRight,
  AlertTriangle
} from 'lucide-react';
import type { ProvenanceResponse } from '../types/api';
import { getProvenance } from '../api/client';
import { formatDatetime } from '../lib/format';
import { ErrorState } from '../components/ErrorState';
import { cn } from '../lib/cn';

function CopyMiniBtn({ value, label }: { value: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={() => {
        navigator.clipboard.writeText(value).then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 1400);
        });
      }}
      className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono text-3 hover:text-1 hover:bg-surface-2 transition-colors border border-[var(--border)]"
      title={`Copy ${label ?? 'value'}`}
    >
      {copied ? <Check className="w-3 h-3 text-[var(--green)]" /> : <Copy className="w-3 h-3" />}
      <span>{copied ? 'Copied' : 'Copy'}</span>
    </button>
  );
}

function TruncatedHash({ hash, label }: { hash: string; label?: string }) {
  const short = hash.length > 20 ? `${hash.slice(0, 10)}…${hash.slice(-8)}` : hash;
  return (
    <div className="flex items-center gap-2">
      <code className="text-xs font-mono text-2 px-1.5 py-0.5 rounded bg-surface-2 border border-[var(--border)]" title={hash}>
        {short}
      </code>
      <CopyMiniBtn value={hash} label={label} />
    </div>
  );
}

export function Provenance() {
  const { id } = useParams<{ id: string }>();
  const [prov, setProv] = useState<ProvenanceResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showRaw, setShowRaw] = useState(false);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    getProvenance(id)
      .then((data) => {
        setProv(data);
        setError(null);
      })
      .catch((err) => {
        console.error('Failed to load provenance:', err);
        setError(err instanceof Error ? err.message : 'Failed to load provenance data.');
      })
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="h-28 rounded-xl bg-surface-2 animate-pulse" />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="h-44 rounded-xl bg-surface-2 animate-pulse" />
          <div className="h-44 rounded-xl bg-surface-2 animate-pulse" />
        </div>
      </div>
    );
  }

  if (error || !prov) {
    return (
      <ErrorState
        title="Could not load provenance assurance"
        message={error || 'No provenance data available.'}
        action={{ label: 'Back to Overview', to: `/assessments/${id}/result` }}
      />
    );
  }

  if (!prov.has_provenance || !prov.manifest) {
    return (
      <div className="card p-8 border border-[var(--border)] bg-surface rounded-xl space-y-4 text-center max-w-2xl mx-auto my-8">
        <div className="w-12 h-12 rounded-full bg-surface-2 border border-[var(--border)] flex items-center justify-center mx-auto text-3">
          <KeyRound className="w-6 h-6" />
        </div>
        <div className="space-y-1">
          <h2 className="text-base font-bold text-1">No Inference Provenance Manifest Provided</h2>
          <p className="text-xs text-3 max-w-md mx-auto leading-relaxed">
            This assessment was executed without an accompanying signed inference manifest.
            PI-01 output binding and cryptographic attestation were marked not applicable.
          </p>
        </div>

        {prov.anomalies && prov.anomalies.length > 0 && (
          <div className="p-4 rounded-lg bg-[var(--amber-bg)]/20 border border-[var(--amber-border)] text-left text-xs space-y-1.5 mt-4">
            <span className="font-mono font-bold text-[var(--amber)] uppercase">Related Observations:</span>
            <ul className="list-disc list-inside text-2 space-y-0.5">
              {prov.anomalies.map((a, i) => (
                <li key={i}>{a}</li>
              ))}
            </ul>
          </div>
        )}

        <div className="pt-2">
          <Link
            to="/new"
            className="inline-flex items-center gap-1.5 text-xs text-accent hover:underline font-semibold"
          >
            <span>Run Assessment with Signed Provenance Manifest</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>
      </div>
    );
  }

  const m = prov.manifest;
  const isSigValid = m.status === 'VERIFIED';
  const isReplayClean = m.replay_status === 'CLEAN';
  const isBindingValid = m.binding_status === 'BOUND';

  return (
    <div className="space-y-6">
      {/* Header Banner */}
      <div className="card p-5 border border-[var(--border)] bg-surface rounded-xl flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <KeyRound className="w-4 h-4 text-accent" />
            <h2 className="text-sm font-bold text-1 tracking-tight">
              Inference Provenance Attestation (PI-01)
            </h2>
            <span
              className={cn(
                'font-mono text-[10px] font-bold px-2 py-0.5 rounded border',
                isSigValid && isReplayClean && isBindingValid
                  ? 'bg-[var(--green-bg)] text-[var(--green)] border-[var(--green)]/30'
                  : 'bg-[var(--red-bg)] text-[var(--red)] border-[var(--red)]/30'
              )}
            >
              {isSigValid && isReplayClean && isBindingValid ? 'FULLY ATTESTED' : 'ANOMALIES DETECTED'}
            </span>
          </div>
          <p className="text-xs text-3">
            Manifest ID: <code className="font-mono text-1">{m.manifest_id}</code>
          </p>
        </div>

        <button
          type="button"
          onClick={() => setShowRaw(!showRaw)}
          className="text-xs font-mono text-accent hover:underline self-start sm:self-auto"
        >
          {showRaw ? 'Hide Raw Manifest' : 'View Raw JSON Manifest'}
        </button>
      </div>

      {/* Raw JSON Manifest Viewer */}
      {showRaw && (
        <div className="card p-4 border border-[var(--border)] bg-surface-2/40 rounded-xl space-y-2">
          <div className="flex items-center justify-between">
            <span className="font-mono text-xs font-bold text-2">RAW PROVENANCE MANIFEST</span>
            <CopyMiniBtn value={JSON.stringify(m, null, 2)} label="Manifest JSON" />
          </div>
          <pre className="p-3 rounded-lg bg-surface border border-[var(--border)] font-mono text-[11px] text-1 overflow-x-auto max-h-72">
            {JSON.stringify(m, null, 2)}
          </pre>
        </div>
      )}

      {/* Primary Attestation Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Card 1: Ed25519 Signature */}
        <div className="card p-5 border border-[var(--border)] bg-surface rounded-xl space-y-4 flex flex-col justify-between">
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-mono text-xs font-bold text-3 uppercase">Digital Signature</span>
              <span
                className={cn(
                  'font-mono text-[10px] font-bold px-2 py-0.5 rounded border',
                  isSigValid
                    ? 'bg-[var(--green-bg)] text-[var(--green)] border-[var(--green)]/30'
                    : 'bg-[var(--red-bg)] text-[var(--red)] border-[var(--red)]/30'
                )}
              >
                {m.status}
              </span>
            </div>
            <p className="text-xs text-2 leading-relaxed">
              Cryptographic signature evaluated using Ed25519 PureEdDSA (RFC 8032) over canonical digest.
            </p>
          </div>

          <div className="space-y-2 pt-2 border-t border-[var(--border)] text-xs">
            <div className="space-y-0.5">
              <span className="text-3 font-mono text-[10px] uppercase">Signature Digest</span>
              {m.signature ? (
                <TruncatedHash hash={m.signature} label="Signature" />
              ) : (
                <span className="text-3 font-mono">—</span>
              )}
            </div>
            <div className="space-y-0.5">
              <span className="text-3 font-mono text-[10px] uppercase">Signer Public Key</span>
              {m.public_key_hex ? (
                <TruncatedHash hash={m.public_key_hex} label="Public Key" />
              ) : (
                <span className="text-3 font-mono">Bound to Assessment</span>
              )}
            </div>
          </div>
        </div>

        {/* Card 2: Replay Protection & Sequence */}
        <div className="card p-5 border border-[var(--border)] bg-surface rounded-xl space-y-4 flex flex-col justify-between">
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-mono text-xs font-bold text-3 uppercase">Replay Protection</span>
              <span
                className={cn(
                  'font-mono text-[10px] font-bold px-2 py-0.5 rounded border',
                  isReplayClean
                    ? 'bg-[var(--green-bg)] text-[var(--green)] border-[var(--green)]/30'
                    : 'bg-[var(--red-bg)] text-[var(--red)] border-[var(--red)]/30'
                )}
              >
                {m.replay_status}
              </span>
            </div>
            <p className="text-xs text-2 leading-relaxed">
              Monotonic sequence ordering and cryptographic nonce evaluated against persisted ledger index.
            </p>
          </div>

          <div className="space-y-2 pt-2 border-t border-[var(--border)] text-xs">
            <div className="flex items-center justify-between">
              <span className="text-3 font-mono text-[10px] uppercase">Sequence Number</span>
              <code className="font-mono text-1 font-bold">#{m.sequence}</code>
            </div>
            <div className="space-y-0.5">
              <span className="text-3 font-mono text-[10px] uppercase">Cryptographic Nonce</span>
              <TruncatedHash hash={m.nonce} label="Nonce" />
            </div>
            <div className="flex items-center justify-between">
              <span className="text-3 font-mono text-[10px] uppercase">Timestamp UTC</span>
              <span className="font-mono text-[11px] text-2">{formatDatetime(m.timestamp_utc)}</span>
            </div>
          </div>
        </div>

        {/* Card 3: Cryptographic Bindings */}
        <div className="card p-5 border border-[var(--border)] bg-surface rounded-xl space-y-4 flex flex-col justify-between">
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-mono text-xs font-bold text-3 uppercase">Asset Bindings</span>
              <span
                className={cn(
                  'font-mono text-[10px] font-bold px-2 py-0.5 rounded border',
                  isBindingValid
                    ? 'bg-[var(--green-bg)] text-[var(--green)] border-[var(--green)]/30'
                    : 'bg-[var(--red-bg)] text-[var(--red)] border-[var(--red)]/30'
                )}
              >
                {m.binding_status}
              </span>
            </div>
            <p className="text-xs text-2 leading-relaxed">
              Strict byte-level cryptographic linkage between candidate input, model graph, and output tensors.
            </p>
          </div>

          <div className="space-y-2 pt-2 border-t border-[var(--border)] text-xs">
            <div className="space-y-0.5">
              <span className="text-3 font-mono text-[10px] uppercase">Input SHA-256</span>
              <TruncatedHash hash={m.input_sha256} label="Input SHA-256" />
            </div>
            <div className="space-y-0.5">
              <span className="text-3 font-mono text-[10px] uppercase">Model SHA-256</span>
              <TruncatedHash hash={m.model_sha256} label="Model SHA-256" />
            </div>
            <div className="space-y-0.5">
              <span className="text-3 font-mono text-[10px] uppercase">Output SHA-256</span>
              <TruncatedHash hash={m.output_sha256} label="Output SHA-256" />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
