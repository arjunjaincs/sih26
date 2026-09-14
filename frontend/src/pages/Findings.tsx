import { useParams, Link, useOutletContext, useSearchParams } from 'react-router-dom';
import { useEffect, useState, useMemo } from 'react';
import type { AssessmentWorkspaceContext } from '../layouts/AssessmentWorkspaceLayout';
import {
  ChevronDown,
  ChevronUp,
  CheckCircle2,
  Copy,
  Check,
  SlidersHorizontal,
  ArrowRight,
  Sparkles,
  Search,
  X,
  RotateCcw,
  Layers,
  Shield,
  ChevronsUpDown,
  ChevronsDownUp,
  FilterX,
} from 'lucide-react';
import type {
  FindingsResponse,
  FindingSchema,
  AssessmentResultSchema,
  DetectorRunSchema
} from '../types/api';
import { getFindings, getAssessment } from '../api/client';
import { StatusBadge } from '../components/StatusBadge';
import { ErrorState } from '../components/ErrorState';
import { AssessmentSubNav } from '../components/AssessmentSubNav';

/* ── Assurance Layer Definitions ── */
export type AssuranceLayerId = 'data_integrity' | 'model_integrity' | 'inference_provenance' | 'audit_integrity';

export interface AssuranceLayerMeta {
  id: AssuranceLayerId;
  label: string;
  description: string;
  badgeClass: string;
}

export const ASSURANCE_LAYERS: Record<AssuranceLayerId, AssuranceLayerMeta> = {
  data_integrity: {
    id: 'data_integrity',
    label: 'Data Integrity',
    description: 'Dataset quality, perceptual duplicates, label anomalies, and out-of-distribution drift',
    badgeClass: 'text-sky-400 bg-sky-950/40 border-sky-800/60',
  },
  model_integrity: {
    id: 'model_integrity',
    label: 'Model Integrity',
    description: 'Weight integrity, architectural fingerprinting, reference comparison, and backdoor triggers',
    badgeClass: 'text-emerald-400 bg-emerald-950/40 border-emerald-800/60',
  },
  inference_provenance: {
    id: 'inference_provenance',
    label: 'Provenance & Inference',
    description: 'Cryptographic execution manifests, signatures, replay detection, and I/O binding verification',
    badgeClass: 'text-amber-400 bg-amber-950/40 border-amber-800/60',
  },
  audit_integrity: {
    id: 'audit_integrity',
    label: 'Audit & Ledger',
    description: 'Tamper-evident append-only hash chains, sequence validation, and coverage assurance gaps',
    badgeClass: 'text-violet-400 bg-violet-950/40 border-violet-800/60',
  },
};

export function getFindingLayer(finding: FindingSchema): AssuranceLayerId {
  const cat = (finding.category || '').toLowerCase();
  const det = (finding.detector_id || '').toLowerCase();

  if (cat.includes('model') || det.includes('model') || det.startsWith('mi')) {
    return 'model_integrity';
  }
  if (cat.includes('provenance') || cat.includes('inference') || det.includes('provenance') || det.includes('inference') || det.startsWith('pi')) {
    return 'inference_provenance';
  }
  if (cat.includes('audit') || cat.includes('ledger') || det.includes('audit') || det.startsWith('at')) {
    return 'audit_integrity';
  }
  if (cat.includes('data') || cat.includes('drift') || det.includes('data') || det.startsWith('di')) {
    return 'data_integrity';
  }
  return 'data_integrity';
}

export type GroupByMode = 'layer' | 'detector' | 'severity' | 'none';

export function formatDetectorCode(detectorId: string): string {
  if (!detectorId) return 'UNKNOWN';
  const match = detectorId.match(/(di|mi|pi|ai)0?(\d+)/i);
  if (match) {
    const prefix = match[1].toUpperCase();
    const num = match[2].padStart(2, '0');
    return `${prefix}-${num}`;
  }
  return detectorId.toUpperCase();
}

/* ── Copy Button ── */
function CopyMiniBtn({ value, label }: { value: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={e => {
        e.stopPropagation();
        navigator.clipboard.writeText(value).then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 1400);
        });
      }}
      className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono text-3 hover:text-1 hover:bg-surface-2 transition-colors border border-transparent hover:border-[var(--border)]"
      title={`Copy ${label ?? 'value'}`}
    >
      {copied ? <Check className="w-3 h-3 text-[var(--green)]" /> : <Copy className="w-3 h-3" />}
      {copied ? 'Copied' : null}
    </button>
  );
}

/* ── Single finding card (expandable, 5-part forensic hierarchy) ── */
export function FindingCard({
  finding,
  detectorRun,
  assessmentId,
  onAskCopilot,
}: {
  finding: FindingSchema;
  detectorRun?: DetectorRunSchema;
  assessmentId?: string;
  onAskCopilot?: (findingId: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const layer = getFindingLayer(finding);
  const layerMeta = ASSURANCE_LAYERS[layer];

  const severityAccent =
    finding.severity === 'critical' ? '--risk-critical' :
    finding.severity === 'high' ? '--risk-high' :
    finding.severity === 'medium' ? '--risk-medium' :
    finding.severity === 'low' ? '--risk-low' : '--text-3';

  // Forensic localization extraction (WHERE)
  const desc = finding.description || '';
  const fileMatch = desc.match(/\b([a-zA-Z0-9_\-]+\.(?:png|jpg|jpeg|webp|json|txt|onnx|pt))\b/i);
  const tensorMatch = desc.match(/(?:tensor|layer|weight|node)\s+([a-zA-Z0-9_.\-]+)/i);
  const counterMatch = desc.match(/(?:counter|sequence|record|signature)\s+([a-zA-Z0-9_\-]+)/i);

  const locationInfo = fileMatch
    ? { label: 'Artifact File Sample', value: fileMatch[1] }
    : tensorMatch
    ? { label: 'Model Graph Tensor / Node', value: tensorMatch[1] }
    : counterMatch
    ? { label: 'Provenance Record Counter', value: counterMatch[1] }
    : { label: 'Asset Reference Scope', value: finding.asset_id || 'Global Assessment Scope' };

  return (
    <div
      id={`finding-${finding.finding_id}`}
      data-finding-id={finding.finding_id}
      data-detector-id={finding.detector_id}
      data-detector-code={formatDetectorCode(finding.detector_id)}
      className="card overflow-hidden border border-border transition-all duration-200"
    >
      {/* ── CARD HEADER (COLLAPSIBLE TOGGLE) ── */}
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        data-testid={`finding-card-${formatDetectorCode(finding.detector_id)}`}
        className="w-full flex items-center gap-3.5 px-5 py-4 bg-surface hover:bg-surface-2/60 transition-colors text-left focus-visible:outline-none focus-visible:bg-surface-2"
      >
        {/* Severity indicator bar */}
        <div
          className="flex-shrink-0 w-1.5 h-10 rounded-full self-start mt-0.5"
          style={{ background: `var(${severityAccent})` }}
        />

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <StatusBadge value={finding.severity} variant="severity" />
            <span className="font-mono text-[11px] font-bold text-accent px-2 py-0.5 rounded bg-[var(--accent-bg)] border border-accent/20">
              {formatDetectorCode(finding.detector_id)}
            </span>
            <span className={`text-[10px] font-mono px-2 py-0.5 rounded border ${layerMeta.badgeClass}`}>
              {layerMeta.label}
            </span>
            <span className="text-[11px] text-3 font-mono">
              {finding.subcategory || finding.category}
            </span>
          </div>
          <p className="text-sm font-semibold text-1 leading-snug pr-4">
            {finding.title}
          </p>
        </div>

        <div className="flex items-center gap-2 flex-shrink-0 text-3">
          <span className="text-xs hidden sm:inline text-3">
            {open ? 'Collapse' : 'Inspect'}
          </span>
          {open ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </div>
      </button>

      {open && (
        <div className="border-t border-[var(--border)] px-5 py-5 space-y-4 bg-surface-2/15 text-xs">
          {/* 1. WHAT */}
          <div className="p-4 rounded-xl border border-[var(--border)] bg-surface space-y-1.5 shadow-sm">
            <div className="flex items-center gap-2 text-sky-400 font-semibold text-xs">
              <span className="w-5 h-5 rounded-full bg-sky-500/10 border border-sky-500/20 flex items-center justify-center text-[10px] font-bold">1</span>
              <span>WHAT — Forensic Defect Summary</span>
            </div>
            <p className="text-1 text-xs sm:text-sm font-medium leading-relaxed">
              {finding.description}
            </p>
          </div>

          {/* 2. WHERE */}
          <div className="p-4 rounded-xl border border-[var(--border)] bg-surface space-y-2.5 shadow-sm">
            <div className="flex items-center gap-2 text-indigo-400 font-semibold text-xs">
              <span className="w-5 h-5 rounded-full bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-[10px] font-bold">2</span>
              <span>WHERE — Localized Artifact Defect</span>
            </div>

            {/* Evidence Sample Preview if dataset image */}
            {fileMatch && (
              <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3 p-3 rounded-lg bg-surface-2/40 border border-[var(--border)]">
                <div className="w-16 h-16 rounded-md bg-black/30 border border-[var(--border)] flex items-center justify-center overflow-hidden flex-shrink-0">
                  <img
                    src={`/api/v1/assessments/${assessmentId || 'default'}/evidence/${fileMatch[1]}`}
                    alt={fileMatch[1]}
                    className="w-full h-full object-cover"
                    onError={(e) => {
                      (e.target as HTMLElement).style.display = 'none';
                    }}
                  />
                  <span className="text-[10px] font-mono text-3 p-1 text-center">IMG</span>
                </div>
                <div className="min-w-0 space-y-0.5">
                  <p className="text-xs font-semibold text-1 truncate">{fileMatch[1]}</p>
                  <p className="text-[11px] text-3">Exact payload file localized by {finding.detector_id}.</p>
                  <span className="inline-block px-1.5 py-0.5 rounded text-[10px] font-mono bg-amber-500/10 text-amber-300 border border-amber-500/20">
                    Defective Sample
                  </span>
                </div>
              </div>
            )}

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs pt-1">
              <div className="p-2.5 rounded-lg border border-[var(--border)] bg-surface-2/30">
                <p className="text-[10px] font-mono text-3 mb-0.5">{locationInfo.label}</p>
                <code className="font-mono text-1 text-xs break-all">{locationInfo.value}</code>
              </div>
              <div className="p-2.5 rounded-lg border border-[var(--border)] bg-surface-2/30">
                <p className="text-[10px] font-mono text-3 mb-0.5">Affected Asset</p>
                <span className="font-mono text-1 text-xs truncate block max-w-full">{finding.asset_id || 'Global Scope'}</span>
              </div>
            </div>
            <p className="text-[11px] text-3 italic pt-1">
              Source location unavailable for this artifact (model/dataset binary payload). Forensic locator verified deterministically.
            </p>
          </div>

          {/* 3. WHY */}
          <div className="p-4 rounded-xl border border-[var(--border)] bg-surface space-y-2 shadow-sm">
            <div className="flex items-center gap-2 text-amber-400 font-semibold text-xs">
              <span className="w-5 h-5 rounded-full bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-[10px] font-bold">3</span>
              <span>WHY — Recommended Analyst Disposition</span>
            </div>
            <p className="label text-accent font-semibold flex items-center gap-1.5">
              Recommended Analyst Disposition
            </p>
            <p className="text-2 leading-relaxed">
              {finding.recommended_disposition || `Detector ${finding.detector_id} flagged this defect because computed features exceeded safety thresholds for ${layerMeta.label.toLowerCase()}.`}
            </p>
            {finding.limitations && finding.limitations.length > 0 && (
              <div className="pt-2 border-t border-[var(--border)]">
                <p className="text-[10px] font-mono text-3 mb-1">Assurance Limitations:</p>
                <ul className="list-disc list-inside space-y-0.5 text-3 text-[11px]">
                  {finding.limitations.map((l, i) => (
                    <li key={i}>{l}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {/* 4. EVIDENCE */}
          <div className="p-4 rounded-xl border border-[var(--border)] bg-surface space-y-2.5 shadow-sm">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-purple-400 font-semibold text-xs">
                <span className="w-5 h-5 rounded-full bg-purple-500/10 border border-purple-500/20 flex items-center justify-center text-[10px] font-bold">4</span>
                <span>EVIDENCE — Quantitative Assurance Data</span>
              </div>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1 text-[11px]">
              <div className="p-2 rounded-lg border border-[var(--border)] bg-surface-2/20">
                <span className="text-3 block text-[10px]">Detector Assessed Risk</span>
                <StatusBadge value={finding.severity} variant="severity" />
              </div>
              <div className="p-2 rounded-lg border border-[var(--border)] bg-surface-2/20">
                <span className="text-3 block text-[10px]">Detection Method</span>
                <span className="text-2 font-mono text-[10px] block truncate">{finding.detection_method || 'Deterministic Analyzer'}</span>
              </div>
              <div className="p-2 rounded-lg border border-[var(--border)] bg-surface-2/20">
                <span className="text-3 block text-[10px]">Finding ID</span>
                <div className="flex items-center gap-1">
                  <code className="text-2 font-mono truncate block text-[10px]">{finding.finding_id}</code>
                  <CopyMiniBtn value={finding.finding_id} label="Finding ID" />
                </div>
              </div>
              <div className="p-2 rounded-lg border border-[var(--border)] bg-surface-2/20">
                <span className="text-3 block text-[10px]">Detector</span>
                <span className="text-2 font-mono text-[10px] font-bold text-accent">{finding.detector_id}</span>
              </div>
              {detectorRun && (
                <div className="p-2 rounded-lg border border-[var(--border)] bg-surface-2/20">
                  <span className="text-3 block text-[10px]">Detector Confidence</span>
                  <span className="text-2 font-mono text-[10px] font-bold text-emerald-400">{detectorRun.confidence_level}</span>
                </div>
              )}
            </div>
          </div>

          {/* 5. NEXT ACTION */}
          <div className="p-4 rounded-xl border border-[var(--border)] bg-surface flex flex-wrap items-center justify-between gap-3 shadow-sm">
            <div className="flex items-center gap-2 text-accent font-semibold text-xs">
              <span className="w-5 h-5 rounded-full bg-accent/10 border border-accent/20 flex items-center justify-center text-[10px] font-bold">5</span>
              <span>NEXT ACTION — Analysis & Evidence</span>
            </div>

            <div className="flex flex-wrap items-center gap-2 ml-auto">
              {onAskCopilot && (
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    onAskCopilot(finding.finding_id);
                  }}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-purple-200 bg-purple-950/40 hover:bg-purple-900/50 border border-purple-700/50 transition-colors"
                >
                  <Sparkles className="w-3.5 h-3.5 text-purple-400" />
                  <span>Ask Copilot</span>
                </button>
              )}

              {assessmentId && (
                <Link
                  to={`/assessments/${assessmentId}/evidence`}
                  className="inline-flex items-center gap-1.5 text-xs text-accent hover:underline font-semibold px-2 py-1"
                >
                  <span>Inspect Supporting Evidence</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </Link>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Section Group Wrapper ── */
function FindingsGroupSection({
  title,
  subtitle,
  badge,
  badgeClass,
  findings,
  detectorRunMap,
  assessmentId,
  onAskCopilot,
  isOpen,
  onToggle,
}: {
  title: string;
  subtitle?: string;
  badge: string;
  badgeClass?: string;
  findings: FindingSchema[];
  detectorRunMap: Map<string, DetectorRunSchema>;
  assessmentId?: string;
  onAskCopilot?: (findingId: string) => void;
  isOpen: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="border border-[var(--border)] rounded-xl overflow-hidden bg-surface/50 transition-colors">
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-center justify-between py-3.5 px-4 sm:px-5 bg-surface-2/40 hover:bg-surface-2/70 transition-colors text-left"
      >
        <div className="flex items-center gap-3 flex-wrap">
          {badge && (
            <span className={`text-xs font-mono font-bold px-2 py-0.5 rounded border ${badgeClass || 'bg-[var(--accent-bg)] border-accent/20 text-accent'}`}>
              {badge}
            </span>
          )}
          <span className="text-sm font-bold text-1">{title}</span>
          {subtitle && (
            <span className="text-xs text-3 hidden md:inline font-mono">
              — {subtitle}
            </span>
          )}
        </div>

        <div className="flex items-center gap-2.5 flex-shrink-0">
          <span className="text-xs font-mono font-semibold px-2 py-0.5 rounded-full bg-surface border border-[var(--border)] text-2">
            {findings.length} {findings.length === 1 ? 'finding' : 'findings'}
          </span>
          {isOpen ? <ChevronUp className="w-4 h-4 text-3" /> : <ChevronDown className="w-4 h-4 text-3" />}
        </div>
      </button>

      {isOpen && (
        <div className="p-4 sm:p-5 space-y-3 bg-surface/30">
          {findings.map(f => (
            <FindingCard
              key={f.finding_id}
              finding={f}
              detectorRun={detectorRunMap.get(f.detector_id)}
              assessmentId={assessmentId}
              onAskCopilot={onAskCopilot}
            />
          ))}
        </div>
      )}
    </div>
  );
}

/* ────────────────────────────────────────────────────────────
   Findings Page Component
──────────────────────────────────────────────────────────── */
export function Findings() {
  const { id } = useParams<{ id?: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const outletCtx = useOutletContext<AssessmentWorkspaceContext | undefined>();

  const [data, setData] = useState<FindingsResponse | null>(null);
  const [assessmentResult, setAssessmentResult] = useState<AssessmentResultSchema | null>(outletCtx?.result ?? null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Group accordion state (group key -> boolean is expanded)
  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>({});

  useEffect(() => {
    if (outletCtx?.result) {
      setAssessmentResult(outletCtx.result);
    }
  }, [outletCtx?.result]);

  useEffect(() => {
    if (!id) { setLoading(false); return; }
    let isMounted = true;

    const fetchFindings = getFindings(id);
    const fetchAssess = outletCtx?.result
      ? Promise.resolve(outletCtx.result)
      : getAssessment(id).catch(() => null);

    Promise.all([fetchFindings, fetchAssess])
      .then(([fData, aData]) => {
        if (!isMounted) return;
        setData(fData);
        if (aData) setAssessmentResult(aData);
        setLoading(false);
      })
      .catch(err => {
        if (!isMounted) return;
        setError(err.message);
        setLoading(false);
      });

    return () => { isMounted = false; };
  }, [id, outletCtx?.result]);

  // Detector Run Map for correlated metadata
  const detectorRunMap = useMemo(() => {
    const map = new Map<string, DetectorRunSchema>();
    if (assessmentResult?.detector_runs) {
      for (const run of assessmentResult.detector_runs) {
        map.set(run.detector_id, run);
        map.set(run.detector_id.toUpperCase(), run);
      }
    }
    return map;
  }, [assessmentResult]);

  // Raw findings list
  const allFindings = useMemo(() => data?.findings ?? [], [data]);

  // Unique detectors in findings
  const uniqueDetectors = useMemo(() => {
    return Array.from(new Set(allFindings.map(f => f.detector_id).filter(Boolean))).sort();
  }, [allFindings]);

  // Derived filter state from URL search params
  const layerFilter = searchParams.get('layer') || 'all';
  const detectorFilter = searchParams.get('detector') || 'all';
  const severityFilter = searchParams.get('severity') || 'all';
  const riskFilter = searchParams.get('risk') || 'all';
  const confidenceFilter = searchParams.get('confidence') || 'all';
  const statusFilter = searchParams.get('status') || 'all';
  const searchQuery = searchParams.get('q') || '';
  const groupBy = (searchParams.get('groupBy') as GroupByMode) || 'layer';

  // Helper to update a URL search param
  const updateFilter = (key: string, value: string) => {
    setSearchParams(prev => {
      const next = new URLSearchParams(prev);
      if (!value || value === 'all') {
        next.delete(key);
      } else {
        next.set(key, value);
      }
      return next;
    }, { replace: true });
  };

  // Helper to reset all filters while preserving groupBy
  const resetAllFilters = () => {
    setSearchParams(prev => {
      const next = new URLSearchParams();
      const currentGroupBy = prev.get('groupBy');
      if (currentGroupBy && currentGroupBy !== 'layer') {
        next.set('groupBy', currentGroupBy);
      }
      return next;
    }, { replace: true });
  };

  // Active filters list for chips/badges
  const activeFilters = useMemo(() => {
    const list: { key: string; label: string; value: string; displayValue: string }[] = [];
    if (layerFilter !== 'all') {
      const meta = ASSURANCE_LAYERS[layerFilter as AssuranceLayerId];
      list.push({ key: 'layer', label: 'Layer', value: layerFilter, displayValue: meta?.label || layerFilter });
    }
    if (detectorFilter !== 'all') {
      list.push({ key: 'detector', label: 'Detector', value: detectorFilter, displayValue: detectorFilter });
    }
    if (severityFilter !== 'all') {
      list.push({ key: 'severity', label: 'Severity', value: severityFilter, displayValue: severityFilter.toUpperCase() });
    }
    if (riskFilter !== 'all') {
      list.push({ key: 'risk', label: 'Risk', value: riskFilter, displayValue: riskFilter.toUpperCase() });
    }
    if (confidenceFilter !== 'all') {
      list.push({ key: 'confidence', label: 'Confidence', value: confidenceFilter, displayValue: confidenceFilter.toUpperCase() });
    }
    if (statusFilter !== 'all') {
      list.push({ key: 'status', label: 'Status', value: statusFilter, displayValue: statusFilter.toUpperCase() });
    }
    if (searchQuery.trim()) {
      list.push({ key: 'q', label: 'Search', value: searchQuery, displayValue: `"${searchQuery}"` });
    }
    return list;
  }, [layerFilter, detectorFilter, severityFilter, riskFilter, confidenceFilter, statusFilter, searchQuery]);

  // Filter findings based on active criteria
  const filteredFindings = useMemo(() => {
    return allFindings.filter(finding => {
      // 1. Assurance Layer
      if (layerFilter !== 'all') {
        const fLayer = getFindingLayer(finding);
        if (fLayer !== layerFilter) return false;
      }

      // 2. Detector ID
      if (detectorFilter !== 'all' && finding.detector_id !== detectorFilter) {
        return false;
      }

      // 3. Severity
      if (severityFilter !== 'all' && finding.severity?.toLowerCase() !== severityFilter.toLowerCase()) {
        return false;
      }

      // 4. Correlated Detector Risk
      const run = detectorRunMap.get(finding.detector_id) || detectorRunMap.get(finding.detector_id.toUpperCase());
      if (riskFilter !== 'all') {
        const runRisk = (run?.risk_level || 'none').toLowerCase();
        if (runRisk !== riskFilter.toLowerCase()) return false;
      }

      // 5. Correlated Detector Confidence
      if (confidenceFilter !== 'all') {
        const runConfidence = (run?.confidence_level || 'low').toLowerCase();
        if (runConfidence !== confidenceFilter.toLowerCase()) return false;
      }

      // 6. Correlated Detector Status
      if (statusFilter !== 'all') {
        const runStatus = (run?.status || '').toLowerCase();
        if (runStatus !== statusFilter.toLowerCase()) return false;
      }

      // 7. Search text
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchesTitle = finding.title?.toLowerCase().includes(q);
        const matchesDesc = finding.description?.toLowerCase().includes(q);
        const matchesDet = finding.detector_id?.toLowerCase().includes(q);
        const matchesSubcat = finding.subcategory?.toLowerCase().includes(q);
        const matchesCat = finding.category?.toLowerCase().includes(q);
        const matchesId = finding.finding_id?.toLowerCase().includes(q);
        const matchesAsset = finding.asset_id?.toLowerCase().includes(q);
        const matchesDisp = finding.recommended_disposition?.toLowerCase().includes(q);
        if (!matchesTitle && !matchesDesc && !matchesDet && !matchesSubcat && !matchesCat && !matchesId && !matchesAsset && !matchesDisp) {
          return false;
        }
      }

      return true;
    });
  }, [allFindings, layerFilter, detectorFilter, severityFilter, riskFilter, confidenceFilter, statusFilter, searchQuery, detectorRunMap]);

  // Grouping logic
  const groupedSections = useMemo(() => {
    if (groupBy === 'layer') {
      const layerOrder: AssuranceLayerId[] = ['data_integrity', 'model_integrity', 'inference_provenance', 'audit_integrity'];
      return layerOrder
        .map(layerId => {
          const meta = ASSURANCE_LAYERS[layerId];
          const items = filteredFindings.filter(f => getFindingLayer(f) === layerId);
          return {
            key: `layer-${layerId}`,
            title: meta.label,
            subtitle: meta.description,
            badge: meta.label,
            badgeClass: meta.badgeClass,
            findings: items,
          };
        })
        .filter(s => s.findings.length > 0);
    }

    if (groupBy === 'detector') {
      const detectorIds = Array.from(new Set(filteredFindings.map(f => f.detector_id).filter(Boolean))).sort();
      return detectorIds.map(detId => {
        const items = filteredFindings.filter(f => f.detector_id === detId);
        const run = detectorRunMap.get(detId);
        const detName = run?.detector_name || detId;
        return {
          key: `detector-${detId}`,
          title: detName,
          subtitle: `Detector ID: ${detId}`,
          badge: detId,
          badgeClass: 'bg-[var(--accent-bg)] border-accent/20 text-accent font-mono',
          findings: items,
        };
      });
    }

    if (groupBy === 'severity') {
      const severities = ['critical', 'high', 'medium', 'low', 'info'];
      return severities
        .map(sev => {
          const items = filteredFindings.filter(f => (f.severity || '').toLowerCase() === sev);
          const badgeClass =
            sev === 'critical' ? 'text-red-400 bg-red-950/40 border-red-800/60' :
            sev === 'high' ? 'text-amber-400 bg-amber-950/40 border-amber-800/60' :
            sev === 'medium' ? 'text-yellow-400 bg-yellow-950/40 border-yellow-800/60' :
            sev === 'low' ? 'text-blue-400 bg-blue-950/40 border-blue-800/60' :
            'text-zinc-400 bg-zinc-900/40 border-zinc-700/60';
          return {
            key: `severity-${sev}`,
            title: sev.charAt(0).toUpperCase() + sev.slice(1) + ' Severity',
            subtitle: `${items.length} defect records categorized as ${sev}`,
            badge: sev.toUpperCase(),
            badgeClass,
            findings: items,
          };
        })
        .filter(s => s.findings.length > 0);
    }

    return [];
  }, [groupBy, filteredFindings, detectorRunMap]);

  // Toggle group open/collapse
  const toggleGroup = (groupKey: string) => {
    setCollapsedGroups(prev => ({
      ...prev,
      [groupKey]: !prev[groupKey],
    }));
  };

  // Expand all / Collapse all groups
  const isAllCollapsed = groupedSections.length > 0 && groupedSections.every(s => collapsedGroups[s.key]);
  const toggleAllGroups = () => {
    if (isAllCollapsed) {
      setCollapsedGroups({});
    } else {
      const allTrue: Record<string, boolean> = {};
      groupedSections.forEach(s => { allTrue[s.key] = true; });
      setCollapsedGroups(allTrue);
    }
  };

  const onAskCopilot = (findingId: string) => {
    if (outletCtx?.openCopilot) {
      outletCtx.openCopilot('finding', findingId);
    }
  };

  if (loading) {
    return (
      <div className={outletCtx ? "space-y-4 animate-pulse" : "max-w-5xl mx-auto px-6 py-8 space-y-4 animate-pulse"}>
        <div className="h-10 bg-surface-2 rounded w-1/3" />
        {[...Array(3)].map((_, i) => (
          <div key={i} className="h-24 bg-surface-2 rounded-xl" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className={outletCtx ? "" : "max-w-5xl mx-auto px-6 py-8"}>
        <ErrorState title="Could not load assessment findings" message={error} />
      </div>
    );
  }

  return (
    <div className={outletCtx ? "space-y-6" : "max-w-5xl mx-auto px-6 py-8 space-y-6"}>
      {/* Sub-navigation only if accessed outside master workspace layout */}
      {!outletCtx && id && (
        <AssessmentSubNav
          assessmentId={id}
          findingsCount={allFindings.length}
        />
      )}

      {/* Header */}
      <div className="border-b border-[var(--border)] pb-5 flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1.5">
            <span className="font-mono text-[11px] font-bold text-accent px-2 py-0.5 rounded bg-[var(--accent-bg)] border border-accent/20 flex items-center gap-1.5">
              <Shield className="w-3 h-3" />
              DEFECT REGISTRY
            </span>
            <span className="text-xs text-3 font-mono">ASSURANCE AUDIT</span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-bold text-1 tracking-tight">
            Assessment Findings
          </h1>
          <p className="mt-1 text-sm text-2 max-w-2xl leading-relaxed">
            Cryptographic, structural, and behavioral defect records detected during deterministic analysis.
          </p>
        </div>

        {/* Global summary badge */}
        {allFindings.length > 0 && (
          <div className="flex items-center gap-3 self-start md:self-auto">
            <div className="text-right">
              <span className="text-[11px] font-mono text-3 block uppercase">Total Verified</span>
              <span className="text-lg font-bold font-mono text-1">{allFindings.length} Records</span>
            </div>
          </div>
        )}
      </div>

      {/* Filter and Group Controls Bar */}
      {allFindings.length > 0 && (
        <div className="space-y-3 bg-surface p-4 rounded-xl border border-[var(--border)] shadow-sm">
          {/* Top Row: Search input + Group By + Expand/Collapse */}
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
            {/* Search Input */}
            <div className="relative flex-1">
              <Search className="w-4 h-4 text-3 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={searchQuery}
                onChange={e => updateFilter('q', e.target.value)}
                placeholder="Search findings, detectors, titles, descriptions..."
                className="w-full h-9 pl-9 pr-8 rounded-lg border border-[var(--border)] bg-surface-2/40 text-xs text-1 placeholder:text-3 focus:outline-none focus:border-accent focus:bg-surface font-sans"
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={() => updateFilter('q', '')}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-3 hover:text-1 p-0.5"
                  title="Clear search"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>

            {/* Group By selector */}
            <div className="flex items-center gap-2 flex-shrink-0">
              <div className="flex items-center gap-1.5 text-xs text-3 font-mono">
                <Layers className="w-3.5 h-3.5 text-accent" />
                <span>Group By:</span>
              </div>
              <select
                aria-label="Group findings by"
                value={groupBy}
                onChange={e => updateFilter('groupBy', e.target.value)}
                className="h-9 px-2.5 rounded-lg border border-[var(--border)] bg-surface-2/40 text-xs text-1 font-mono focus:outline-none focus:border-accent"
              >
                <option value="layer">Assurance Layer</option>
                <option value="detector">Detector</option>
                <option value="severity">Severity</option>
                <option value="none">Flat List</option>
              </select>

              {/* Expand / Collapse All Toggle (only in grouped mode) */}
              {groupBy !== 'none' && groupedSections.length > 0 && (
                <button
                  type="button"
                  onClick={toggleAllGroups}
                  className="h-9 px-3 rounded-lg border border-[var(--border)] bg-surface-2/40 hover:bg-surface-2 text-xs text-2 hover:text-1 font-mono inline-flex items-center gap-1.5 transition-colors"
                  title={isAllCollapsed ? 'Expand All Groups' : 'Collapse All Groups'}
                >
                  {isAllCollapsed ? (
                    <>
                      <ChevronsUpDown className="w-3.5 h-3.5 text-accent" />
                      <span className="hidden sm:inline">Expand All</span>
                    </>
                  ) : (
                    <>
                      <ChevronsDownUp className="w-3.5 h-3.5 text-accent" />
                      <span className="hidden sm:inline">Collapse All</span>
                    </>
                  )}
                </button>
              )}
            </div>
          </div>

          {/* Bottom Row: Multi-dimensional filter dropdowns */}
          <div className="pt-2 border-t border-[var(--border)] flex flex-wrap items-center gap-2 text-xs">
            <div className="flex items-center gap-1.5 text-3 font-mono mr-1">
              <SlidersHorizontal className="w-3.5 h-3.5 text-accent" />
              <span>Filters:</span>
            </div>

            {/* 1. Assurance Layer Filter */}
            <select
              aria-label="Filter by layer"
              value={layerFilter}
              onChange={e => updateFilter('layer', e.target.value)}
              className="h-8 px-2.5 rounded-lg border border-[var(--border)] bg-surface text-xs text-1 font-mono focus:outline-none focus:border-accent"
            >
              <option value="all">All Layers</option>
              <option value="data_integrity">Data Integrity</option>
              <option value="model_integrity">Model Integrity</option>
              <option value="inference_provenance">Provenance & Inference</option>
              <option value="audit_integrity">Audit & Ledger</option>
            </select>

            {/* 2. Severity Filter */}
            <select
              aria-label="Filter by severity"
              value={severityFilter}
              onChange={e => updateFilter('severity', e.target.value)}
              className="h-8 px-2.5 rounded-lg border border-[var(--border)] bg-surface text-xs text-1 font-mono focus:outline-none focus:border-accent"
            >
              <option value="all">All Severities</option>
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
              <option value="info">Info</option>
            </select>

            {/* 3. Detector ID Filter */}
            {uniqueDetectors.length > 0 && (
              <select
                aria-label="Filter by detector"
                value={detectorFilter}
                onChange={e => updateFilter('detector', e.target.value)}
                className="h-8 px-2.5 rounded-lg border border-[var(--border)] bg-surface text-xs text-1 font-mono focus:outline-none focus:border-accent"
              >
                <option value="all">All Detectors ({uniqueDetectors.length})</option>
                {uniqueDetectors.map(d => (
                  <option key={d} value={d}>{d}</option>
                ))}
              </select>
            )}

            {/* 4. Detector Risk Filter */}
            <select
              aria-label="Filter by detector risk"
              value={riskFilter}
              onChange={e => updateFilter('risk', e.target.value)}
              className="h-8 px-2.5 rounded-lg border border-[var(--border)] bg-surface text-xs text-1 font-mono focus:outline-none focus:border-accent"
            >
              <option value="all">All Detector Risks</option>
              <option value="critical">Critical Risk</option>
              <option value="high">High Risk</option>
              <option value="medium">Medium Risk</option>
              <option value="low">Low Risk</option>
              <option value="none">Zero / None Risk</option>
            </select>

            {/* 5. Detector Confidence Filter */}
            <select
              aria-label="Filter by detector confidence"
              value={confidenceFilter}
              onChange={e => updateFilter('confidence', e.target.value)}
              className="h-8 px-2.5 rounded-lg border border-[var(--border)] bg-surface text-xs text-1 font-mono focus:outline-none focus:border-accent"
            >
              <option value="all">All Confidences</option>
              <option value="high">High Confidence</option>
              <option value="moderate">Moderate Confidence</option>
              <option value="low">Low Confidence</option>
            </select>

            {/* 6. Detector Status Filter */}
            <select
              aria-label="Filter by detector status"
              value={statusFilter}
              onChange={e => updateFilter('status', e.target.value)}
              className="h-8 px-2.5 rounded-lg border border-[var(--border)] bg-surface text-xs text-1 font-mono focus:outline-none focus:border-accent"
            >
              <option value="all">All Statuses</option>
              <option value="pass">Pass</option>
              <option value="fail">Fail</option>
              <option value="warn">Warn</option>
              <option value="error">Error</option>
              <option value="skipped">Skipped</option>
            </select>

            {/* Reset All Button */}
            {activeFilters.length > 0 && (
              <button
                type="button"
                onClick={resetAllFilters}
                className="h-8 px-2.5 rounded-lg border border-[var(--border)] hover:bg-surface-2 text-xs text-accent hover:text-accent font-mono inline-flex items-center gap-1 transition-colors ml-auto"
                title="Reset all active filters"
              >
                <RotateCcw className="w-3 h-3" />
                <span>Reset All</span>
              </button>
            )}
          </div>

          {/* Active Filter Chips / Badges */}
          {activeFilters.length > 0 && (
            <div className="pt-2 border-t border-[var(--border)] flex flex-wrap items-center gap-2">
              <span className="text-[11px] font-mono text-3 mr-1">Active Filters:</span>
              {activeFilters.map(f => (
                <span
                  key={f.key}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-mono bg-surface-2 border border-[var(--border)] text-1"
                >
                  <span className="text-3">{f.label}:</span>
                  <span className="font-semibold text-accent">{f.displayValue}</span>
                  <button
                    type="button"
                    onClick={() => updateFilter(f.key, '')}
                    className="text-3 hover:text-1 ml-0.5 p-0.5 hover:bg-surface rounded"
                    title={`Remove ${f.label} filter`}
                  >
                    <X className="w-3 h-3" />
                  </button>
                </span>
              ))}

              <div className="ml-auto text-[11px] font-mono text-3">
                Showing <strong className="text-1">{filteredFindings.length}</strong> of{' '}
                <strong className="text-1">{allFindings.length}</strong>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Main Content Area */}
      {allFindings.length === 0 ? (
        /* Empty State — Zero Findings in Assessment */
        <div className="card p-12 text-center space-y-3 border border-dashed border-[var(--border)]">
          <div className="w-12 h-12 rounded-full bg-[var(--green-bg)] text-[var(--green)] mx-auto flex items-center justify-center">
            <CheckCircle2 className="w-6 h-6" />
          </div>
          <h2 className="text-base font-semibold text-1">Zero Findings Recorded</h2>
          <p className="text-xs text-3 max-w-sm mx-auto leading-relaxed">
            No structural mutations, duplicate anomalies, decode errors, or provenance signature mismatches were identified.
          </p>
          {id && (
            <div className="pt-2">
              <Link
                to={`/assessments/${id}/evidence`}
                className="inline-flex items-center gap-1.5 text-xs text-accent font-semibold hover:underline"
              >
                <span>Inspect Verified Evidence Artifacts</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </Link>
            </div>
          )}
        </div>
      ) : filteredFindings.length === 0 ? (
        /* Empty State — Active filters matched 0 findings */
        <div className="card p-10 text-center space-y-3 border border-dashed border-[var(--border)]">
          <div className="w-10 h-10 rounded-full bg-surface-2 text-3 mx-auto flex items-center justify-center">
            <FilterX className="w-5 h-5" />
          </div>
          <p className="text-sm font-semibold text-1">No findings match the selected filters</p>
          <p className="text-xs text-3 max-w-md mx-auto leading-relaxed">
            No defect records matched your active filter criteria. Adjust your layer, detector, severity, or search parameters.
          </p>
          <div className="pt-2">
            <button
              type="button"
              onClick={resetAllFilters}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[var(--border)] bg-surface hover:bg-surface-2 text-xs font-mono text-accent transition-colors"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>Reset all filters ({activeFilters.length})</span>
            </button>
          </div>
        </div>
      ) : groupBy === 'none' ? (
        /* Flat Stream List View */
        <div className="space-y-3">
          {filteredFindings.map(f => (
            <FindingCard
              key={f.finding_id}
              finding={f}
              detectorRun={detectorRunMap.get(f.detector_id)}
              assessmentId={id}
              onAskCopilot={onAskCopilot}
            />
          ))}
        </div>
      ) : (
        /* Grouped Accordion Sections View */
        <div className="space-y-4">
          {groupedSections.map(section => (
            <FindingsGroupSection
              key={section.key}
              title={section.title}
              subtitle={section.subtitle}
              badge={section.badge}
              badgeClass={section.badgeClass}
              findings={section.findings}
              detectorRunMap={detectorRunMap}
              assessmentId={id}
              onAskCopilot={onAskCopilot}
              isOpen={!collapsedGroups[section.key]}
              onToggle={() => toggleGroup(section.key)}
            />
          ))}
        </div>
      )}

      {/* ── Workflow Navigation Action Bar ── */}
      {id && (
        <div className="card p-5 border border-[var(--border)] bg-surface rounded-xl flex flex-col sm:flex-row items-center justify-between gap-4 mt-6 shadow-sm">
          <div className="space-y-0.5 text-center sm:text-left">
            <p className="text-xs font-bold text-1">Findings Review Complete</p>
            <p className="text-[11px] text-3">Proceed to the authoritative forensic assurance report or inspect cryptographic evidence artifacts.</p>
          </div>
          <div className="flex items-center gap-3 w-full sm:w-auto">
            <Link
              to={`/assessments/${id}/evidence`}
              className="flex-1 sm:flex-none px-4 py-2 rounded-lg border border-[var(--border)] bg-surface hover:bg-surface-2 text-xs font-semibold text-2 transition-colors text-center shadow-sm"
            >
              Inspect Evidence
            </Link>
            <Link
              to={`/assessments/${id}/result`}
              className="flex-1 sm:flex-none px-5 py-2 rounded-lg bg-accent text-white text-xs font-semibold hover:bg-[var(--accent-2)] transition-colors inline-flex items-center justify-center gap-1.5 shadow-sm"
            >
              <span>Proceed to Report</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
