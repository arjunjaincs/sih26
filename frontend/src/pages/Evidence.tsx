import { useParams, Link } from 'react-router-dom';
import { useEffect, useState } from 'react';
import type { EvidenceResponse } from '../types/api';
import { getEvidence } from '../api/client';
import { Panel } from '../components/Panel';
import { EvidenceRow } from '../components/EvidenceRow';
import { EmptyState } from '../components/EmptyState';
import { ErrorState } from '../components/ErrorState';

export function Evidence() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<EvidenceResponse | null>(null);
  const [error, setError] = useState<{ message: string; isNetwork: boolean } | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) { setLoading(false); return; }
    getEvidence(id)
      .then((r) => { setData(r); setLoading(false); })
      .catch((err) => { setError({ message: err.message, isNetwork: err.name === 'NetworkError' }); setLoading(false); });
  }, [id]);

  if (!id) {
    return (
      <div className="max-w-3xl mx-auto px-6 py-8">
        <Panel>
          <EmptyState
            title="No assessment selected"
            description="Navigate here from an assessment result page."
            action={<Link to="/new" className="text-xs text-[var(--accent)] hover:underline">New Assessment →</Link>}
          />
        </Panel>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto px-6 py-8 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-[var(--text-primary)] tracking-tight">Evidence</h1>
          <p className="mt-0.5 text-xs text-[var(--text-muted)] font-mono">{id}</p>
        </div>
        {data && (
          <span className="text-sm font-semibold text-[var(--text-primary)]">
            {data.count} item{data.count !== 1 ? 's' : ''}
          </span>
        )}
      </div>

      <p className="text-xs text-[var(--text-muted)] px-0.5">
        Evidence items contain structured forensic measurements collected during analysis.
        Artifact filesystem paths are intentionally omitted from API responses.
      </p>

      {loading && (
        <div className="space-y-2 animate-pulse">
          {[1, 2, 3, 4].map((i) => <div key={i} className="h-12 rounded bg-[var(--surface-2)]" />)}
        </div>
      )}

      {error && !loading && (
        <Panel>
          <ErrorState message={error.message} isNetwork={error.isNetwork} onRetry={() => window.location.reload()} />
        </Panel>
      )}

      {!loading && !error && data && (
        <>
          {data.count === 0 ? (
            <Panel>
              <EmptyState title="No evidence items" description="No evidence was recorded for this assessment." />
            </Panel>
          ) : (
            <Panel title="Evidence Items" noPadding>
              <div className="p-4 space-y-2">
                {data.evidence.map((e) => (
                  <EvidenceRow key={e.evidence_id} evidence={e} />
                ))}
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
