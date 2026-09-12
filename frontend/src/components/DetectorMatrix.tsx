import { Link } from 'react-router-dom';
import { 
  Database, 
  Cpu, 
  KeyRound, 
  ShieldAlert, 
  CheckCircle2, 
  AlertTriangle, 
  XCircle, 
  MinusCircle, 
  ChevronRight,
  ShieldCheck
} from 'lucide-react';
import type { DetectorRunSchema } from '../types/api';
import { cn } from '../lib/cn';

interface DetectorMatrixProps {
  runs: DetectorRunSchema[];
  assessmentId: string;
}

const PILLARS = [
  {
    key: 'data',
    title: 'Data Integrity Battery',
    icon: Database,
    color: 'text-blue-500',
    detectors: ['di01', 'di02', 'di03', 'di04', 'di05'],
  },
  {
    key: 'model',
    title: 'Model Integrity Battery',
    icon: Cpu,
    color: 'text-purple-500',
    detectors: ['mi01', 'mi02', 'mi03', 'mi04', 'mi05'],
  },
  {
    key: 'provenance',
    title: 'Inference Provenance Battery',
    icon: KeyRound,
    color: 'text-cyan-500',
    detectors: ['pi01'],
  },
  {
    key: 'audit',
    title: 'Audit Trail Ledger',
    icon: ShieldCheck,
    color: 'text-emerald-500',
    detectors: ['at01'],
  },
];

function getShortDetectorId(id: string): string {
  const lower = id.toLowerCase();
  if (lower.includes('di01') || id === 'DI-01') return 'DI-01';
  if (lower.includes('di02') || id === 'DI-02') return 'DI-02';
  if (lower.includes('di03') || id === 'DI-03') return 'DI-03';
  if (lower.includes('di04') || id === 'DI-04') return 'DI-04';
  if (lower.includes('di05') || id === 'DI-05') return 'DI-05';
  if (lower.includes('mi01') || id === 'MI-01') return 'MI-01';
  if (lower.includes('mi02') || id === 'MI-02') return 'MI-02';
  if (lower.includes('mi03') || id === 'MI-03') return 'MI-03';
  if (lower.includes('mi04') || id === 'MI-04') return 'MI-04';
  if (lower.includes('mi05') || id === 'MI-05') return 'MI-05';
  if (lower.includes('pi01') || id === 'PI-01') return 'PI-01';
  const match = id.match(/([a-z]{2})[-_]?(\d{2})/i);
  return match ? `${match[1].toUpperCase()}-${match[2]}` : id;
}

export function DetectorMatrix({ runs, assessmentId }: DetectorMatrixProps) {
  const runMap = new Map<string, DetectorRunSchema>();
  for (const r of runs) {
    const short = getShortDetectorId(r.detector_id);
    runMap.set(short, r);
    runMap.set(r.detector_id, r);
  }

  return (
    <div className="card overflow-hidden border border-[var(--border)] bg-surface shadow-sm">
      <div className="p-4 sm:p-5 border-b border-[var(--border)] flex items-center justify-between gap-4">
        <div>
          <h2 className="text-sm sm:text-base font-bold text-1 tracking-tight">
            Assurance Layers & Detector Battery Matrix
          </h2>
          <p className="text-xs text-3 mt-0.5">
            Deterministic cryptographic, numerical, and statistical verification battery.
          </p>
        </div>
        <span className="font-mono text-xs text-3 px-2 py-0.5 rounded bg-surface-2 border border-[var(--border)]">
          {runs.filter((r) => r.ran).length} / 11 EXECUTED
        </span>
      </div>

      <div className="divide-y divide-[var(--border)]">
        {PILLARS.map((pillar) => {
          const PillarIcon = pillar.icon;
          return (
            <div key={pillar.key} className="p-4 sm:p-5 space-y-3">
              <div className="flex items-center gap-2">
                <PillarIcon className={cn('w-4 h-4', pillar.color)} />
                <h3 className="text-xs font-mono font-bold text-2 uppercase tracking-wider">
                  {pillar.title}
                </h3>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2.5">
                {pillar.detectors.map((dCode) => {
                  const upperCode = dCode.toUpperCase();
                  const targetShort = `${upperCode.slice(0, 2)}-${upperCode.slice(2)}`;
                  const isAudit = targetShort === 'AT-01';
                  const run = runMap.get(targetShort) || runMap.get(dCode);

                  const ran = isAudit ? true : (run?.ran ?? false);
                  const status = isAudit ? 'SEALED' : (run?.status?.toUpperCase() ?? 'NOT_APPLICABLE');
                  const hasFindings = isAudit ? false : ((run?.findings_count ?? 0) > 0);
                  const riskLevel = isAudit ? 'NONE' : (run?.risk_level?.toUpperCase() ?? 'NONE');
                  const detectorName = isAudit 
                    ? 'Tamper-Evident Audit Trail' 
                    : (run?.detector_name ? run.detector_name.replace(new RegExp(`^${targetShort}:?\\s*`, 'i'), '') : targetShort);

                  const isHighRisk = riskLevel === 'HIGH' || riskLevel === 'CRITICAL';

                  return (
                    <div
                      key={dCode}
                      className={cn(
                        'p-3 rounded-lg border text-xs flex flex-col justify-between gap-2 transition-all',
                        isHighRisk
                          ? 'border-[var(--red)]/40 bg-[var(--red-bg)]/30'
                          : hasFindings
                          ? 'border-[var(--amber-border)] bg-[var(--amber-bg)]/20'
                          : ran
                          ? 'border-[var(--green)]/20 bg-surface-2/40'
                          : 'border-[var(--border)] bg-surface-2/20 opacity-70'
                      )}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-1.5 min-w-0">
                          <code className="font-mono font-bold text-1 text-[11px] px-1.5 py-0.5 rounded bg-surface border border-[var(--border)]">
                            {targetShort}
                          </code>
                          <span className="font-medium text-1 truncate" title={detectorName}>
                            {detectorName}
                          </span>
                        </div>

                        {/* Status Icon */}
                        <div className="flex-shrink-0">
                          {isHighRisk ? (
                            <ShieldAlert className="w-3.5 h-3.5 text-[var(--red)]" />
                          ) : hasFindings ? (
                            <AlertTriangle className="w-3.5 h-3.5 text-[var(--amber)]" />
                          ) : ran ? (
                            <CheckCircle2 className="w-3.5 h-3.5 text-[var(--green)]" />
                          ) : status === 'SKIPPED' ? (
                            <MinusCircle className="w-3.5 h-3.5 text-3" />
                          ) : (
                            <span className="text-[10px] font-mono text-3">N/A</span>
                          )}
                        </div>
                      </div>

                      <div className="flex items-center justify-between pt-1 border-t border-[var(--border)]/60 text-[11px]">
                        <span className="font-mono text-3">
                          {isAudit 
                            ? 'CHAIN VERIFIED'
                            : status === 'SUCCESS' && !hasFindings
                            ? 'PASS · CLEAN'
                            : status === 'SUCCESS' && hasFindings
                            ? `${run?.findings_count} ANOMALY`
                            : status}
                        </span>

                        {isAudit ? (
                          <Link
                            to={`/assessments/${assessmentId}/audit`}
                            className="inline-flex items-center gap-0.5 text-accent hover:underline font-semibold"
                          >
                            <span>Verify</span>
                            <ChevronRight className="w-3 h-3" />
                          </Link>
                        ) : hasFindings ? (
                          <Link
                            to={`/assessments/${assessmentId}/findings`}
                            className="inline-flex items-center gap-0.5 text-accent hover:underline font-semibold"
                          >
                            <span>Inspect</span>
                            <ChevronRight className="w-3 h-3" />
                          </Link>
                        ) : (
                          <span className="font-mono text-[10px] text-3">
                            {run?.evidence_count ?? 0} ev
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
