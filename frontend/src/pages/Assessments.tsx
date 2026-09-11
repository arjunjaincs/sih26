import { Link } from 'react-router-dom';
import { Plus, ClipboardList } from 'lucide-react';
import { Panel } from '../components/Panel';
import { EmptyState } from '../components/EmptyState';
import { Button } from '../components/Button';

/**
 * Assessments list page.
 * No GET /api/v1/assessments list endpoint exists in the backend.
 * This page displays an honest empty state and links to the last-run assessment
 * stored in sessionStorage (if any).
 */
export function Assessments() {
  const lastId = sessionStorage.getItem('pramaan_last_assessment_id');

  return (
    <div className="max-w-3xl mx-auto px-6 py-8 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-[var(--text-primary)] tracking-tight">Assessments</h1>
          <p className="mt-1 text-sm text-[var(--text-muted)]">
            History of assurance assessments run on this workstation.
          </p>
        </div>
        <Link to="/new">
          <Button leftIcon={<Plus className="w-4 h-4" />} size="sm">New Assessment</Button>
        </Link>
      </div>

      {lastId && (
        <Panel title="Last Assessment">
          <div className="flex items-center justify-between gap-4">
            <code className="text-xs font-mono text-[var(--text-secondary)] truncate">{lastId}</code>
            <Link
              to={`/assessments/${lastId}/result`}
              className="text-xs text-[var(--accent)] hover:underline flex-shrink-0"
            >
              View result →
            </Link>
          </div>
        </Panel>
      )}

      <Panel>
        <EmptyState
          icon={<ClipboardList className="w-8 h-8" />}
          title="No assessment history available"
          description="Assessment list retrieval is not yet supported by the backend API. Run an assessment to see its result immediately after completion."
          action={
            <Link to="/new">
              <Button size="sm" leftIcon={<Plus className="w-4 h-4" />}>Run Assessment</Button>
            </Link>
          }
        />
      </Panel>
    </div>
  );
}
