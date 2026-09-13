import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, Clock, Copy, Check } from 'lucide-react';
import { StatusBadge } from './StatusBadge';
import { ReportDownloadButton } from './ReportDownloadButton';
import { ExportJsonButton } from './ExportJsonButton';
import { MetricTriad } from './MetricTriad';
import { formatDatetime, formatDuration } from '../lib/format';

interface AssessmentHeaderProps {
  assessmentId: string;
  title: string;
  status: string;
  startedAt?: string | null;
  completedAt?: string | null;
  overallRisk?: string;
  overallConfidence?: string;
  coverageFraction?: number;
  softwareVersion?: string;
}

export function AssessmentHeader({
  assessmentId,
  title,
  status,
  startedAt,
  completedAt,
  overallRisk,
  overallConfidence,
  coverageFraction,
  softwareVersion = '1.0.0',
}: AssessmentHeaderProps) {
  const [copied, setCopied] = useState(false);

  const handleCopyId = () => {
    navigator.clipboard.writeText(assessmentId).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    });
  };

  return (
    <div className="border-b border-[var(--border)] pb-5 space-y-4">
      {/* Top utility row */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <Link
          to="/assessments"
          className="inline-flex items-center gap-1.5 text-xs text-3 hover:text-1 transition-colors w-fit focus-visible:ring-1"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span>Back to Assessments</span>
        </Link>

        <div className="flex items-center gap-2">
          <span className="font-mono text-[10px] font-bold text-accent px-2 py-0.5 rounded bg-[var(--accent-bg)] border border-accent/20 tracking-wider">
            OPERATIONAL ASSURANCE
          </span>
          <span className="font-mono text-[10px] text-3 px-2 py-0.5 rounded bg-surface-2 border border-[var(--border)]">
            v{softwareVersion} · AIR-GAPPED
          </span>
        </div>
      </div>

      {/* Main title & action row */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
        <div className="space-y-2">
          <h1 className="text-2xl sm:text-3xl font-extrabold text-1 tracking-tight">
            {title}
          </h1>

          <div className="flex items-center flex-wrap gap-x-4 gap-y-2 text-xs text-3">
            {/* ID & Copy */}
            <div className="flex items-center gap-1.5 bg-surface-2/60 px-2 py-0.5 rounded border border-[var(--border)]">
              <span className="text-3 font-mono">ID:</span>
              <code className="font-mono text-1">{assessmentId}</code>
              <button
                type="button"
                onClick={handleCopyId}
                className="p-0.5 rounded text-3 hover:text-1 hover:bg-surface transition-colors"
                title="Copy Assessment ID"
                aria-label="Copy Assessment ID"
              >
                {copied ? (
                  <Check className="w-3 h-3 text-[var(--green)]" />
                ) : (
                  <Copy className="w-3 h-3" />
                )}
              </button>
            </div>

            {/* Execution timestamp */}
            {startedAt && (
              <span>Executed: {formatDatetime(startedAt)}</span>
            )}

            {/* Duration */}
            {startedAt && completedAt && (
              <span className="flex items-center gap-1 text-3 font-mono">
                <Clock className="w-3 h-3" />
                {formatDuration(startedAt, completedAt)}
              </span>
            )}

            {/* Status */}
            <StatusBadge value={status} variant="status" />
          </div>
        </div>

        {/* Action buttons: PDF report & JSON export */}
        <div className="flex items-center gap-2.5 flex-shrink-0 flex-wrap">
          <ReportDownloadButton assessmentId={assessmentId} />
          <ExportJsonButton assessmentId={assessmentId} variant="outline" />
        </div>
      </div>

      {/* Metric Triad Badges in header if available */}
      {overallRisk && overallConfidence && coverageFraction !== undefined && (
        <div className="pt-1">
          <MetricTriad
            overallRisk={overallRisk}
            overallConfidence={overallConfidence}
            coverageFraction={coverageFraction}
            compact
          />
        </div>
      )}
    </div>
  );
}
