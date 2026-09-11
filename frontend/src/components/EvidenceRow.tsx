import { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import type { EvidenceSchema } from '../types/api';
import { EVIDENCE_TYPE_LABELS, truncateHash } from '../lib/format';
import { CopyButton } from './CopyButton';
import { cn } from '../lib/cn';

interface EvidenceRowProps {
  evidence: EvidenceSchema;
}

const TYPE_CLASSES: Record<string, string> = {
  measurement:     'bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-300',
  comparison:      'bg-purple-50 text-purple-700 dark:bg-purple-950 dark:text-purple-300',
  anomaly:         'bg-orange-50 text-orange-700 dark:bg-orange-950 dark:text-orange-300',
  hash_mismatch:   'bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300',
  hash_match:      'bg-green-50 text-green-700 dark:bg-green-950 dark:text-green-300',
  statistical_test:'bg-cyan-50 text-cyan-700 dark:bg-cyan-950 dark:text-cyan-300',
  cluster:         'bg-violet-50 text-violet-700 dark:bg-violet-950 dark:text-violet-300',
};

export function EvidenceRow({ evidence }: EvidenceRowProps) {
  const [expanded, setExpanded] = useState(false);
  const typeLabel = EVIDENCE_TYPE_LABELS[evidence.evidence_type] ?? evidence.evidence_type;
  const typeClass = TYPE_CLASSES[evidence.evidence_type] ?? 'bg-gray-100 text-gray-600';

  return (
    <div className="rounded border border-[var(--border)] bg-[var(--surface-1)]">
      <button
        onClick={() => setExpanded((e) => !e)}
        className="w-full flex items-start gap-3 p-3 text-left hover:bg-[var(--surface-2)] rounded transition-colors duration-150"
        aria-expanded={expanded}
      >
        <span className="mt-0.5 text-[var(--text-muted)]">
          {expanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5">
            <span className={cn('text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded', typeClass)}>
              {typeLabel}
            </span>
            <span className="text-[10px] text-[var(--text-muted)] font-mono">{evidence.detector_id}</span>
          </div>
          <p className="text-xs text-[var(--text-secondary)]">{evidence.description}</p>
        </div>
      </button>

      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.16 }}
            className="overflow-hidden"
          >
            <div className="border-t border-[var(--border)] px-3 pb-3 pt-2 space-y-2">
              {/* SHA-256 */}
              {evidence.artifact_sha256 && (
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-[var(--text-muted)] font-semibold uppercase tracking-wide w-20 flex-shrink-0">
                    SHA-256
                  </span>
                  <code
                    className="text-[10px] font-mono text-[var(--text-secondary)] truncate"
                    title={evidence.artifact_sha256}
                  >
                    {truncateHash(evidence.artifact_sha256, 12)}
                  </code>
                  <CopyButton value={evidence.artifact_sha256} title="Copy SHA-256" />
                </div>
              )}

              {/* Evidence ID */}
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-[var(--text-muted)] font-semibold uppercase tracking-wide w-20 flex-shrink-0">
                  Evidence ID
                </span>
                <code className="text-[10px] font-mono text-[var(--text-secondary)] truncate" title={evidence.evidence_id}>
                  {truncateHash(evidence.evidence_id, 12)}
                </code>
                <CopyButton value={evidence.evidence_id} title="Copy Evidence ID" />
              </div>

              {/* Structured data */}
              {evidence.data && Object.keys(evidence.data).length > 0 && (
                <div>
                  <p className="text-[10px] text-[var(--text-muted)] font-semibold uppercase tracking-wide mb-1">
                    Measurements
                  </p>
                  <pre className="text-[10px] font-mono bg-[var(--surface-2)] rounded p-2 overflow-auto text-[var(--text-secondary)] max-h-40 whitespace-pre-wrap break-words">
                    {JSON.stringify(evidence.data, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
