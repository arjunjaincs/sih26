import { useEffect, useState } from 'react';
import { useParams, useLocation, Outlet } from 'react-router-dom';
import type { AssessmentResultSchema, AICopilotScope } from '../types/api';
import { getAssessment } from '../api/client';
import { AssessmentHeader } from '../components/AssessmentHeader';
import { AssessmentSubNav } from '../components/AssessmentSubNav';
import { AnalystCopilot } from '../components/AnalystCopilot';
import { ErrorState } from '../components/ErrorState';

export interface AssessmentWorkspaceContext {
  result: AssessmentResultSchema | null;
  reloadAssessment: () => Promise<void>;
  openCopilot: (scope?: AICopilotScope, findingId?: string | null) => void;
}

export function AssessmentWorkspaceLayout() {
  const { id } = useParams<{ id: string }>();
  const location = useLocation();

  const stateResult = (location.state as { result?: AssessmentResultSchema })?.result ?? null;
  const [result, setResult] = useState<AssessmentResultSchema | null>(stateResult);
  const [loading, setLoading] = useState<boolean>(!stateResult);
  const [error, setError] = useState<string | null>(null);

  // Copilot drawer state
  const [copilotOpen, setCopilotOpen] = useState<boolean>(false);
  const [copilotScope, setCopilotScope] = useState<AICopilotScope>('assessment');
  const [copilotFindingId, setCopilotFindingId] = useState<string | null>(null);

  const openCopilot = (scope: AICopilotScope = 'assessment', findingId: string | null = null) => {
    setCopilotScope(scope);
    setCopilotFindingId(findingId);
    setCopilotOpen(true);
  };

  const fetchAssessment = async () => {
    if (!id) {
      setError('No assessment ID specified.');
      setLoading(false);
      return;
    }
    try {
      setError(null);
      const data = await getAssessment(id);
      setResult(data);
    } catch (err) {
      console.error('Failed to load assessment:', err);
      setError(err instanceof Error ? err.message : 'Assessment not found.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!result || result.assessment_id !== id) {
      setLoading(true);
      fetchAssessment();
    }
  }, [id]);

  if (loading && !result) {
    return (
      <div className="max-w-6xl mx-auto px-6 py-12 space-y-6">
        <div className="h-28 rounded-xl bg-surface-2 animate-pulse" />
        <div className="h-10 rounded-lg bg-surface-2/60 animate-pulse" />
        <div className="h-64 rounded-xl bg-surface-2/40 animate-pulse" />
      </div>
    );
  }

  if (error && !result) {
    return (
      <div className="max-w-4xl mx-auto px-6 py-12">
        <ErrorState
          title="Could not load assessment workspace"
          message={error}
          action={{ label: 'Back to Assessments', to: '/assessments' }}
        />
      </div>
    );
  }

  if (!result) return null;

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 py-6 sm:py-8 space-y-6">
      {/* Unified Master Header */}
      <AssessmentHeader
        assessmentId={result.assessment_id}
        title={result.title}
        status={result.status}
        startedAt={result.started_at}
        completedAt={result.completed_at}
        overallRisk={result.overall_risk}
        overallConfidence={result.overall_confidence}
        coverageFraction={result.coverage_fraction}
        softwareVersion={result.software_version}
      />

      {/* Unified Sub-navigation with Copilot Trigger */}
      <AssessmentSubNav
        assessmentId={result.assessment_id}
        findingsCount={result.findings_count}
        evidenceCount={result.evidence_count}
        chainValid={result.audit_chain_valid}
        coverageGapsCount={result.coverage_gaps?.length ?? 0}
        onOpenCopilot={() => openCopilot('assessment')}
      />

      {/* Active Tab View */}
      <div id="assessment-workspace-content">
        <Outlet
          context={{
            result,
            reloadAssessment: fetchAssessment,
            openCopilot,
          } satisfies AssessmentWorkspaceContext}
        />
      </div>

      {/* Analyst Copilot Drawer */}
      <AnalystCopilot
        assessmentId={result.assessment_id}
        isOpen={copilotOpen}
        onClose={() => setCopilotOpen(false)}
        initialScope={copilotScope}
        initialFindingId={copilotFindingId}
      />
    </div>
  );
}
