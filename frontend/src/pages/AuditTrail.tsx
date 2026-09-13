import { useParams, useOutletContext } from 'react-router-dom';
import { useEffect, useState } from 'react';
import type { AssessmentWorkspaceContext } from '../layouts/AssessmentWorkspaceLayout';
import { 
  ShieldCheck, 
  ShieldAlert, 
  Check, 
  Copy, 
  RefreshCw, 
  CheckCircle2,
  Download,
  FileCheck
} from 'lucide-react';
import type { AuditResponse, AuditEventSchema } from '../types/api';
import { getAudit, exportAuditJson } from '../api/client';
import { ErrorState } from '../components/ErrorState';
import { AssessmentSubNav } from '../components/AssessmentSubNav';
import { formatDatetime } from '../lib/format';
import { cn } from '../lib/cn';

function TruncatedHash({ hash, label }: { hash: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  const isZero = hash === '0' || hash === '0000000000000000000000000000000000000000000000000000000000000000';
  const short = hash.length > 20 ? `${hash.slice(0, 10)}…${hash.slice(-8)}` : hash;

  if (isZero) {
    return (
      <span className="text-[11px] font-mono text-3 italic">
        00000000 (Genesis Block)
      </span>
    );
  }

  return (
    <div className="flex items-center gap-1.5">
      <code className="text-[11px] font-mono text-2 px-1.5 py-0.5 rounded bg-surface-2 border border-[var(--border)]" title={hash}>
        {short}
      </code>
      <button
        type="button"
        onClick={() => {
          navigator.clipboard.writeText(hash).then(() => {
            setCopied(true);
            setTimeout(() => setCopied(false), 1400);
          });
        }}
        className="p-1 rounded text-3 hover:text-1 hover:bg-surface-2 transition-colors"
        title={`Copy full ${label ?? 'hash'}`}
      >
        {copied ? <Check className="w-3 h-3 text-[var(--green)]" /> : <Copy className="w-3 h-3" />}
      </button>
    </div>
  );
}

function TimelineEvent({
  event,
  index,
  isLast,
}: {
  event: AuditEventSchema;
  index: number;
  isLast: boolean;
}) {
  return (
    <div className="flex gap-4">
      {/* Timeline Indicator Column */}
      <div className="flex flex-col items-center flex-shrink-0">
        <div className="w-6 h-6 rounded-full bg-[var(--accent-bg)] border border-accent/30 text-accent flex items-center justify-center text-[10px] font-mono font-bold z-10">
          {index + 1}
        </div>
        {!isLast && (
          <div className="w-px flex-1 bg-[var(--border)] my-1" style={{ minHeight: '36px' }} />
        )}
      </div>

      {/* Event Details Card */}
      <div className={cn('flex-1 pb-6', isLast && 'pb-0')}>
        <div className="card p-4 border border-[var(--border)] hover:border-[var(--border-strong)] transition-all">
          <div className="flex items-start justify-between gap-4 flex-wrap pb-2 border-b border-[var(--border)]">
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-mono font-bold text-accent uppercase">
                  {event.event_type.replace(/_/g, ' ')}
                </span>
                <span className="text-[10px] font-mono text-3 px-1.5 py-0.2 rounded bg-surface-2">
                  Actor: {event.actor || 'system'}
                </span>
              </div>
              <code className="text-[11px] font-mono text-3 block mt-0.5">
                Block Event: {event.event_id || `EVT-${index + 1}`}
              </code>
            </div>

            <span className="text-xs text-3 font-mono">
              {event.timestamp_utc ? formatDatetime(event.timestamp_utc) : '—'}
            </span>
          </div>

          {/* SHA-256 Hash Chain Linkage */}
          <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
            {event.current_hash && (
              <div>
                <p className="label text-3 mb-1">Block Hash (SHA-256)</p>
                <TruncatedHash hash={event.current_hash} label="Current Hash" />
              </div>
            )}

            {event.previous_hash && (
              <div>
                <p className="label text-3 mb-1">Previous Linkage Hash</p>
                <TruncatedHash hash={event.previous_hash} label="Previous Hash" />
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ────────────────────────────────────────────────────────────
   AuditTrail Page Component
──────────────────────────────────────────────────────────── */
export function AuditTrail() {
  const { id } = useParams<{ id?: string }>();
  const [data, setData] = useState<AuditResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [verifying, setVerifying] = useState(false);
  const [verifiedNotice, setVerifiedNotice] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportSuccessNotice, setExportSuccessNotice] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const outletCtx = useOutletContext<AssessmentWorkspaceContext | undefined>();

  function load() {
    if (!id) { setLoading(false); return; }
    setLoading(true);
    setError(null);
    getAudit(id)
      .then(d => { setData(d); setLoading(false); })
      .catch(err => { setError(err.message); setLoading(false); });
  }

  useEffect(() => { load(); }, [id]);

  function handleVerify() {
    if (!id) return;
    setVerifying(true);
    getAudit(id)
      .then(d => {
        setData(d);
        setVerifying(false);
        setVerifiedNotice(true);
        setTimeout(() => setVerifiedNotice(false), 3500);
        if (outletCtx?.reloadAssessment) {
          outletCtx.reloadAssessment();
        }
      })
      .catch(err => {
        setError(err.message);
        setVerifying(false);
      });
  }

  async function handleExportAudit() {
    if (!id) return;
    setExporting(true);
    setExportError(null);
    try {
      const safeShortId = id.slice(0, 8);
      await exportAuditJson(id, `pramaan_audit_export_${safeShortId}.json`);
      setExporting(false);
      setExportSuccessNotice(true);
      setTimeout(() => setExportSuccessNotice(false), 4500);
    } catch (err: unknown) {
      setExporting(false);
      setExportError(err instanceof Error ? err.message : 'Failed to export verified audit trail.');
      setTimeout(() => setExportError(null), 5000);
    }
  }

  if (loading) {
    return (
      <div className={outletCtx ? "space-y-4 animate-pulse" : "max-w-5xl mx-auto px-6 py-8 space-y-4 animate-pulse"}>
        <div className="h-10 bg-surface-2 rounded w-1/3" />
        {[...Array(4)].map((_, i) => (
          <div key={i} className="h-20 bg-surface-2 rounded-xl" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className={outletCtx ? "" : "max-w-5xl mx-auto px-6 py-8"}>
        <ErrorState title="Could not load audit trail" message={error} />
      </div>
    );
  }

  const events = data?.events ?? [];
  const chainValid = data?.chain_valid;

  return (
    <div className={outletCtx ? "space-y-6" : "max-w-5xl mx-auto px-6 py-8 space-y-6"}>
      {/* Sub-navigation only if accessed outside master workspace */}
      {!outletCtx && id && (
        <AssessmentSubNav 
          assessmentId={id} 
          chainValid={chainValid} 
        />
      )}

      {/* Header */}
      <div className="border-b border-[var(--border)] pb-6 flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-2 mb-1.5">
            <span className="font-mono text-[11px] font-bold text-accent px-2 py-0.5 rounded bg-[var(--accent-bg)] border border-accent/20">
              TAMPER-EVIDENT LEDGER
            </span>
            <span className="text-xs text-3 font-mono">AT-01 SPECIFICATION</span>
            <span className="text-[11px] font-mono text-2 px-2 py-0.5 rounded bg-surface-2 border border-[var(--border)]" title="All exports are structured verification artifacts">
              VERIFICATION ARTIFACT
            </span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-bold text-1 tracking-tight">
            Audit Trail
          </h1>
          <p className="mt-1 text-sm text-2 max-w-2xl leading-relaxed">
            Cryptographically verifiable append-only hash chain linking all assessment lifecycle events back to genesis.
          </p>
        </div>

        {/* Chain Validation Badge & Actions */}
        <div className="flex items-center gap-2.5 flex-shrink-0">
          {chainValid !== undefined && (
            <div className={cn(
              'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border font-mono text-xs font-semibold',
              chainValid
                ? 'bg-[var(--green-bg)] border-[var(--green)]/30 text-[var(--green)]'
                : 'bg-[var(--red-bg)] border-[var(--red)]/30 text-[var(--red)]'
            )}>
              {chainValid ? <ShieldCheck className="w-4 h-4" /> : <ShieldAlert className="w-4 h-4" />}
              <span>{chainValid ? 'Chain Valid' : 'Invalid Linkage'}</span>
            </div>
          )}

          <button
            type="button"
            onClick={handleVerify}
            disabled={verifying}
            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg border border-[var(--border)] text-xs font-semibold text-1 hover:bg-surface-2 transition-colors disabled:opacity-50"
            title="Re-verify cryptographic hash chain"
          >
            <RefreshCw className={cn('w-3.5 h-3.5', verifying && 'animate-spin text-accent')} />
            <span>{verifying ? 'Verifying…' : 'Verify Chain'}</span>
          </button>

          <button
            type="button"
            id="export-audit-btn"
            onClick={handleExportAudit}
            disabled={exporting}
            className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg border border-accent/40 bg-accent/10 hover:bg-accent/20 text-xs font-semibold text-accent transition-colors disabled:opacity-50"
            title="Export verified audit trail as structured JSON (Verification Artifact)"
          >
            <Download className={cn('w-3.5 h-3.5', exporting && 'animate-bounce')} />
            <span>{exporting ? 'Exporting…' : 'Export Audit'}</span>
          </button>
        </div>
      </div>

      {/* Live Verification Notice Banner */}
      {verifiedNotice && (
        <div className="card p-3 rounded-lg border border-[var(--green)]/30 bg-[var(--green-bg)] flex items-center justify-between text-xs text-[var(--green)]">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
            <span className="font-medium">
              Hash chain verification passed: all {events.length} event hashes are mathematically linked and unhampered.
            </span>
          </div>
        </div>
      )}

      {/* Live Export Notice Banner */}
      {exportSuccessNotice && (
        <div className="card p-3 rounded-lg border border-accent/30 bg-[var(--accent-bg)] flex items-center justify-between text-xs text-accent">
          <div className="flex items-center gap-2">
            <FileCheck className="w-4 h-4 flex-shrink-0" />
            <span className="font-medium">
              Verification Artifact downloaded: structured JSON audit trail containing hashes, sequence, and verification results.
            </span>
          </div>
        </div>
      )}

      {/* Export Error Banner */}
      {exportError && (
        <div className="card p-3 rounded-lg border border-[var(--red)]/30 bg-[var(--red-bg)] flex items-center justify-between text-xs text-[var(--red)]">
          <div className="flex items-center gap-2">
            <ShieldAlert className="w-4 h-4 flex-shrink-0" />
            <span className="font-medium">{exportError}</span>
          </div>
        </div>
      )}

      {/* Timeline Section */}
      {events.length === 0 ? (
        <div className="card p-12 text-center space-y-3 border border-dashed border-[var(--border)]">
          <p className="text-sm font-semibold text-1">No Audit Events Recorded</p>
          <p className="text-xs text-3">No lifecycle events were found for this assessment record.</p>
        </div>
      ) : (
        <div className="space-y-0 pt-2">
          {events.map((ev, i) => (
            <TimelineEvent
              key={ev.event_id ?? i}
              event={ev}
              index={i}
              isLast={i === events.length - 1}
            />
          ))}
        </div>
      )}

      {/* Technical Footnote (Honest claims - no blockchain, no absolute immutability claims) */}
      <div className="card p-4 border border-[var(--border)] bg-surface-2/40 rounded-xl space-y-1 text-xs text-3 leading-relaxed">
        <p className="font-semibold text-2 font-mono text-[11px] uppercase">
          Tamper-Evident Ledger Mechanics
        </p>
        <p>
          Each record incorporates the SHA-256 digest of the immediately preceding event, establishing an append-only cryptographic sequence.
          Any retroactive alteration to prior event payloads breaks subsequent hash links, rendering tampering immediately detectable upon verification.
        </p>
      </div>
    </div>
  );
}
