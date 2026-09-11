import { useParams, Link } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { ShieldCheck, ShieldAlert, AlertCircle } from 'lucide-react';
import type { AuditResponse } from '../types/api';
import { getAudit } from '../api/client';
import { Panel } from '../components/Panel';
import { AuditEventRow } from '../components/AuditEventRow';
import { EmptyState } from '../components/EmptyState';
import { ErrorState } from '../components/ErrorState';
import { cn } from '../lib/cn';

export function AuditTrail() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<AuditResponse | null>(null);
  const [error, setError] = useState<{ message: string; isNetwork: boolean } | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) { setLoading(false); return; }
    getAudit(id)
      .then((r) => { setData(r); setLoading(false); })
      .catch((err) => { setError({ message: err.message, isNetwork: err.name === 'NetworkError' }); setLoading(false); });
  }, [id]);

  if (!id) {
    return (
      <div className="max-w-4xl mx-auto px-6 py-8">
        <div>
          <h1 className="text-xl font-bold text-[var(--text-primary)] tracking-tight mb-2">Audit Trail</h1>
        </div>
        <Panel>
          <EmptyState
            icon={<ShieldCheck className="w-8 h-8" />}
            title="No assessment selected"
            description="Open an assessment result to view its tamper-evident audit chain."
            action={<Link to="/new" className="text-xs text-[var(--accent)] hover:underline">Run Assessment →</Link>}
          />
        </Panel>
      </div>
    );
  }

  const invalidEventIds = new Set(
    data?.first_invalid_event_id ? [data.first_invalid_event_id] : [],
  );

  return (
    <div className="max-w-4xl mx-auto px-6 py-8 space-y-5">
      <div>
        <h1 className="text-xl font-bold text-[var(--text-primary)] tracking-tight">Audit Trail</h1>
        <p className="mt-0.5 text-xs text-[var(--text-muted)] font-mono">{id}</p>
      </div>

      {loading && (
        <div className="animate-pulse space-y-3">
          <div className="h-14 rounded-lg bg-[var(--surface-2)]" />
          <div className="h-48 rounded-lg bg-[var(--surface-2)]" />
        </div>
      )}

      {error && !loading && (
        <Panel>
          <ErrorState message={error.message} isNetwork={error.isNetwork} onRetry={() => window.location.reload()} />
        </Panel>
      )}

      {!loading && !error && data && (
        <>
          {/* Chain validity banner */}
          <div
            className={cn(
              'flex items-start gap-3 px-4 py-3 rounded-lg border',
              data.chain_valid
                ? 'bg-[var(--risk-none-bg)] border-[var(--risk-none)]'
                : 'bg-[var(--risk-critical-bg)] border-[var(--risk-critical)]',
            )}
            role="status"
          >
            {data.chain_valid ? (
              <ShieldCheck className="w-5 h-5 text-[var(--risk-none)] flex-shrink-0 mt-0.5" />
            ) : (
              <ShieldAlert className="w-5 h-5 text-[var(--risk-critical)] flex-shrink-0 mt-0.5" />
            )}
            <div>
              <p className={cn(
                'text-sm font-bold tracking-wide',
                data.chain_valid ? 'text-[var(--risk-none)]' : 'text-[var(--risk-critical)]',
              )}>
                {data.chain_valid ? 'AUDIT CHAIN VALID' : 'AUDIT CHAIN INVALID'}
              </p>
              <p className="text-xs text-[var(--text-secondary)] mt-0.5">
                {data.events_checked} event{data.events_checked !== 1 ? 's' : ''} verified
                {!data.chain_valid && data.first_invalid_event_id && (
                  <> · First failure at event <code className="font-mono">{data.first_invalid_event_id}</code></>
                )}
              </p>
            </div>
          </div>

          {/* Chain integrity explanation */}
          <div className="text-xs text-[var(--text-muted)] px-0.5 space-y-1">
            <p>
              Each event's <code className="font-mono text-[10px]">current_hash</code> is computed from
              the previous hash, event ID, timestamp, and payload digest (SHA-256).
              Any modification to any event breaks the chain at that point.
            </p>
          </div>

          {/* Failures */}
          {data.failures.length > 0 && (
            <div className="rounded-lg border border-[var(--risk-critical)] bg-[var(--risk-critical-bg)] p-3">
              <div className="flex items-center gap-2 mb-2">
                <AlertCircle className="w-4 h-4 text-[var(--risk-critical)]" />
                <p className="text-xs font-semibold text-[var(--risk-critical)]">Chain Failures</p>
              </div>
              <ul className="space-y-1">
                {data.failures.map((f, i) => (
                  <li key={i} className="text-xs text-[var(--text-secondary)]">{f}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Events table */}
          {data.events.length === 0 ? (
            <Panel><EmptyState title="No audit events" description="No events were recorded for this assessment." /></Panel>
          ) : (
            <Panel title="Event Chain" noPadding>
              <div className="overflow-x-auto">
                <table className="w-full text-xs min-w-[700px]">
                  <thead>
                    <tr className="border-b border-[var(--border)] bg-[var(--surface-1)]">
                      {['#', 'Event Type', 'Timestamp (UTC)', 'Actor', 'Hash Link', 'Event ID'].map((h) => (
                        <th key={h} className="text-left py-2.5 px-3 text-[var(--text-muted)] font-semibold uppercase tracking-wide text-[10px]">
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--border-subtle)]">
                    {data.events.map((event, i) => (
                      <AuditEventRow
                        key={event.event_id}
                        event={event}
                        index={i}
                        isFirst={i === 0}
                        isInvalid={invalidEventIds.has(event.event_id)}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>
          )}

          <div className="text-xs text-[var(--text-muted)] px-1">
            <Link to={`/assessments/${id}/result`} className="text-[var(--accent)] hover:underline">
              ← Back to assessment result
            </Link>
          </div>
        </>
      )}
    </div>
  );
}
