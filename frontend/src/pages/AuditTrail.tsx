import { useParams, Link } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { ArrowLeft, ShieldCheck, ShieldAlert, Check, Copy } from 'lucide-react';
import type { AuditResponse, AuditEventSchema } from '../types/api';
import { getAudit } from '../api/client';
import { ErrorState } from '../components/ErrorState';
import { formatDatetime } from '../lib/format';
import { cn } from '../lib/cn';

function TruncatedHash({ hash, full }: { hash: string; full?: string }) {
  const [copied, setCopied] = useState(false);
  const display = full ?? hash;
  const short = hash.length > 16 ? `${hash.slice(0, 8)}…${hash.slice(-6)}` : hash;

  return (
    <div className="flex items-center gap-1.5">
      <code className="text-[11px] font-mono text-3">{short}</code>
      <button
        onClick={() => { navigator.clipboard.writeText(display).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1400); }); }}
        className="p-0.5 rounded text-4 hover:text-2 transition-colors"
        title="Copy full hash"
      >
        {copied ? <Check className="w-3 h-3 text-[var(--green)]" /> : <Copy className="w-3 h-3" />}
      </button>
    </div>
  );
}

function TimelineEvent({
  event,
  isLast,
}: {
  event: AuditEventSchema;
  isLast: boolean;
}) {
  return (
    <div className="flex gap-4">
      {/* Timeline indicator */}
      <div className="flex flex-col items-center flex-shrink-0">
        <div className="w-5 h-5 rounded-full bg-[var(--green)] flex items-center justify-center z-10">
          <svg className="w-3 h-3 text-white" viewBox="0 0 12 12" fill="none">
            <path d="M2 6l3 3 5-5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </div>
        {!isLast && (
          <div className="w-px flex-1 bg-[var(--border)] mt-1" style={{ minHeight: '20px' }} />
        )}
      </div>

      {/* Event content */}
      <div className={cn('flex-1 pb-5', isLast && 'pb-0')}>
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <p className="text-sm font-medium text-1 leading-tight">
              {event.event_type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
            </p>
            <p className="text-xs text-3 mt-0.5">{event.actor ?? 'system'}</p>
          </div>
          <span className="text-xs text-3 font-mono flex-shrink-0">
            {event.timestamp_utc ? formatDatetime(event.timestamp_utc) : '—'}
          </span>
        </div>

        {/* Hash chain */}
        <div className="mt-2 flex flex-wrap gap-x-6 gap-y-1">
          {event.current_hash && (
            <div>
              <p className="label mb-0.5">Current</p>
              <TruncatedHash hash={event.current_hash} />
            </div>
          )}
          {event.previous_hash && event.previous_hash !== '0' && (
            <div>
              <p className="label mb-0.5">Previous</p>
              <TruncatedHash hash={event.previous_hash} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export function AuditTrail() {
  const { id } = useParams<{ id?: string }>();
  const [data, setData] = useState<AuditResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) { setLoading(false); return; }
    getAudit(id)
      .then(d => { setData(d); setLoading(false); })
      .catch(err => { setError(err.message); setLoading(false); });
  }, [id]);

  if (loading) return (
    <div className="max-w-3xl mx-auto px-6 py-10 space-y-4 animate-pulse">
      {[...Array(5)].map((_, i) => <div key={i} className="h-14 bg-surface-2 rounded" />)}
    </div>
  );
  if (error) return (
    <div className="max-w-3xl mx-auto px-6 py-10">
      <ErrorState title="Could not load audit trail" message={error} />
    </div>
  );

  const events = data?.events ?? [];
  const chainValid = data?.chain_valid;

  return (
    <div className="max-w-3xl mx-auto px-6 py-10 space-y-8">
      {/* Back */}
      {id && (
        <Link to={`/assessments/${id}/result`}
          className="flex items-center gap-1.5 text-xs text-3 hover:text-1 transition-colors">
          <ArrowLeft className="w-3.5 h-3.5" />
          Back to Results
        </Link>
      )}

      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="label text-accent mb-1">PRAMAAN · Audit</p>
          <h1 className="text-2xl font-bold text-1">Audit Trail</h1>
          <p className="mt-0.5 text-sm text-3">
            Cryptographically verifiable record of this assessment.
          </p>
        </div>

        {/* Chain valid badge */}
        {chainValid !== undefined && (
          <div className={cn(
            'flex items-center gap-2 px-3 py-2 rounded border flex-shrink-0',
            chainValid
              ? 'bg-[var(--risk-none-bg)] border-[var(--risk-none)]/30 text-[var(--risk-none)]'
              : 'bg-[var(--risk-critical-bg)] border-[var(--risk-critical)]/30 text-[var(--risk-critical)]',
          )}>
            {chainValid
              ? <ShieldCheck className="w-4 h-4" />
              : <ShieldAlert className="w-4 h-4" />
            }
            <span className="text-xs font-bold">
              {chainValid ? 'Chain Valid' : 'Chain Invalid'}
            </span>
          </div>
        )}
      </div>

      {/* Event count */}
      {events.length > 0 && (
        <p className="text-xs text-3">{events.length} event{events.length !== 1 ? 's' : ''}</p>
      )}

      {/* Timeline */}
      {events.length === 0 ? (
        <div className="card p-10 text-center">
          <p className="text-sm text-3">No audit events recorded.</p>
        </div>
      ) : (
        <div className="space-y-0">
          {events.map((ev, i) => (
            <TimelineEvent
              key={ev.event_id ?? i}
              event={ev}
              isLast={i === events.length - 1}
            />
          ))}
        </div>
      )}

      {/* Verify footer */}
      {events.length > 0 && (
        <div className="pt-4 border-t border-[var(--border)] flex items-center gap-4">
          <button className="px-4 py-2 rounded border border-[var(--border)] text-xs font-semibold text-1
            hover:bg-surface-2 transition-colors">
            Verify Chain
          </button>
          <p className="text-xs text-3">
            All events are cryptographically linked using SHA-256.
          </p>
        </div>
      )}
    </div>
  );
}
