import { useEffect, useState, useRef, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { 
  ArrowRight, 
  ArrowDown,
  X, 
  Cpu, 
  Database, 
  KeyRound, 
  SlidersHorizontal, 
  ChevronDown, 
  ChevronUp, 
  Loader2, 
  AlertCircle,
  Sparkles,
  ShieldCheck,
  CheckCircle2
} from 'lucide-react';
import { formatPercent } from '../lib/format';
import { createAssessment, getCapabilities, getDemos } from '../api/client';
import { normalizeDetectorCode, getDetectorDetail } from '../lib/detectorRegistry';
import type { 
  CapabilitiesResponse, 
  AssessmentResultSchema, 
  UploadResponse, 
  AssessmentCreateRequest, 
  DemoPresetSchema,
  DetectorCapabilitySchema
} from '../types/api';
import { FileUpload } from '../components/FileUpload';
import { DemoPresets } from '../components/DemoPresets';
import { cn } from '../lib/cn';

type Stage = 'form' | 'running' | 'completed' | 'error';

interface FieldProps {
  label: string;
  id: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  required?: boolean;
  helpText?: string;
  type?: string;
  onClear?: () => void;
}

function Field({ label, id, value, onChange, placeholder, required, helpText, type = 'text', onClear }: FieldProps) {
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="label text-xs font-semibold text-2">
        {label}
        {required && <span className="text-[var(--red)] ml-0.5">*</span>}
      </label>
      <div className="relative">
        <input
          id={id}
          type={type}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          required={required}
          className={cn(
            'w-full h-9 px-3 rounded-lg border border-[var(--border)] bg-surface text-1',
            'text-xs font-mono placeholder:text-3 placeholder:font-sans',
            'focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30',
            'transition-colors duration-150',
            onClear && value && 'pr-8'
          )}
        />
        {onClear && value && (
          <button
            type="button"
            onClick={onClear}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-3 hover:text-1"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        )}
      </div>
      {helpText && <p className="text-[11px] text-3 leading-tight">{helpText}</p>}
    </div>
  );
}

function ModeToggle({ mode, onChange }: { mode: 'upload' | 'local'; onChange: (m: 'upload' | 'local') => void }) {
  return (
    <div className="flex rounded-lg border border-[var(--border)] p-0.5 bg-surface-2/60 w-fit text-xs">
      <button
        type="button"
        onClick={() => onChange('upload')}
        className={cn(
          'px-2.5 py-1 rounded-md font-medium transition-colors text-[11px]',
          mode === 'upload' ? 'bg-surface text-1 shadow-sm font-semibold' : 'text-3 hover:text-2'
        )}
      >
        Upload File
      </button>
      <button
        type="button"
        onClick={() => onChange('local')}
        className={cn(
          'px-2.5 py-1 rounded-md font-medium transition-colors text-[11px]',
          mode === 'local' ? 'bg-surface text-1 shadow-sm font-semibold' : 'text-3 hover:text-2'
        )}
      >
        Local Path (Advanced)
      </button>
    </div>
  );
}

function getDetectorLayerInfo(detectorId: string, liveCap?: DetectorCapabilitySchema | null) {
  const code = normalizeDetectorCode(detectorId);
  const spec = getDetectorDetail(detectorId, liveCap);

  if (code.startsWith('DI')) {
    return {
      code,
      name: spec.name,
      layer: 'Data Integrity',
      pillClass: 'text-sky-400 bg-sky-950/40 border-sky-800/60',
    };
  }
  if (code.startsWith('MI')) {
    return {
      code,
      name: spec.name,
      layer: 'Model Integrity',
      pillClass: 'text-emerald-400 bg-emerald-950/40 border-emerald-800/60',
    };
  }
  if (code.startsWith('PI')) {
    return {
      code,
      name: spec.name,
      layer: 'Inference Provenance',
      pillClass: 'text-amber-400 bg-amber-950/40 border-amber-800/60',
    };
  }
  return {
    code: code || detectorId,
    name: spec.name,
    layer: spec.pillar || 'Assurance Layer',
    pillClass: 'text-violet-400 bg-violet-950/40 border-violet-800/60',
  };
}

export function NewAssessment() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const initialMode = searchParams.get('mode') === 'demo' || searchParams.get('preset') ? 'demo' : 'custom';
  const [entryMode, setEntryMode] = useState<'custom' | 'demo'>(initialMode);
  const [stage, setStage] = useState<Stage>('form');
  const [title, setTitle] = useState('');
  const [assessmentResult, setAssessmentResult] = useState<AssessmentResultSchema | null>(null);

  // Selected preset tracking
  const [selectedPresetId, setSelectedPresetId] = useState<string | null>(null);

  // Model input states
  const [modelMode, setModelMode] = useState<'upload' | 'local'>('upload');
  const [uploadedModel, setUploadedModel] = useState<UploadResponse | null>(null);
  const [modelPath, setModelPath] = useState('');

  // Reference Model (for MI-04)
  const [refModelMode, setRefModelMode] = useState<'upload' | 'local'>('local');
  const [uploadedRefModel, setUploadedRefModel] = useState<UploadResponse | null>(null);
  const [refModelPath, setRefModelPath] = useState('');

  // Dataset input states
  const [datasetMode, setDatasetMode] = useState<'upload' | 'local'>('upload');
  const [uploadedDataset, setUploadedDataset] = useState<UploadResponse | null>(null);
  const [datasetPath, setDatasetPath] = useState('');
  const [datasetFormat, setDatasetFormat] = useState('image_dir');

  // Provenance states
  const [provenanceJsonText, setProvenanceJsonText] = useState('');
  const [provenancePublicKeyHex, setProvenancePublicKeyHex] = useState('');
  const [actualInputHex, setActualInputHex] = useState('');
  const [actualOutputHex, setActualOutputHex] = useState('');
  const [actualModelSha, setActualModelSha] = useState('');

  // Advanced threshold states
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [phashThreshold, setPhashThreshold] = useState(10);
  const [dhashThreshold, setDhashThreshold] = useState(10);
  const [minClusterSize, setMinClusterSize] = useState(2);

  const [caps, setCaps] = useState<CapabilitiesResponse | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [errorMsg, setErrorMsg] = useState('');

  // Elapsed execution timer
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const hasDatasetInput = Boolean(uploadedDataset || datasetPath.trim());
  const hasModelInput = Boolean(uploadedModel || modelPath.trim());
  const hasRefModelInput = Boolean(uploadedRefModel || refModelPath.trim());
  const hasProvenanceInput = Boolean(
    provenanceJsonText.trim() || provenancePublicKeyHex.trim() || actualInputHex.trim()
  );

  const getDetectorExecutionStatus = (detectorId: string) => {
    const code = normalizeDetectorCode(detectorId);
    if (code === 'MI-04') {
      if (hasModelInput && hasRefModelInput) {
        return { status: 'will_run', label: 'Will Run' };
      }
      return { status: 'needs_input', label: 'Requires Ref Model' };
    }
    if (code.startsWith('DI')) {
      if (hasDatasetInput) {
        return { status: 'will_run', label: 'Will Run' };
      }
      return { status: 'needs_input', label: 'Awaiting Dataset' };
    }
    if (code.startsWith('MI')) {
      if (hasModelInput) {
        return { status: 'will_run', label: 'Will Run' };
      }
      return { status: 'needs_input', label: 'Awaiting Model' };
    }
    if (code.startsWith('PI')) {
      if (hasProvenanceInput || hasModelInput) {
        return { status: 'will_run', label: 'Will Run' };
      }
      return { status: 'needs_input', label: 'Awaiting Provenance' };
    }
    return { status: 'will_run', label: 'Ready' };
  };

  const readyDetectorsCount = useMemo(() => {
    if (!caps?.detectors) return 0;
    return caps.detectors.filter(
      (d) => getDetectorExecutionStatus(d.detector_id).status === 'will_run'
    ).length;
  }, [caps, hasDatasetInput, hasModelInput, hasRefModelInput, hasProvenanceInput]);

  useEffect(() => {
    getCapabilities().then(setCaps).catch(() => {});
    const presetParam = searchParams.get('preset');
    if (presetParam) {
      getDemos().then((res) => {
        const match = res.demos.find((d) => d.id === presetParam);
        if (match) {
          handleSelectPreset(match);
          setEntryMode('demo');
        }
      }).catch(() => {});
    }
  }, []);

  function handleClearPreset() {
    setSelectedPresetId(null);
    setTitle('');
    setModelMode('upload');
    setModelPath('');
    setUploadedModel(null);
    setRefModelMode('local');
    setRefModelPath('');
    setUploadedRefModel(null);
    setDatasetMode('upload');
    setDatasetPath('');
    setUploadedDataset(null);
    setProvenanceJsonText('');
    setProvenancePublicKeyHex('');
    setActualInputHex('');
    setActualOutputHex('');
    setActualModelSha('');
    setErrors([]);
  }

  function handleSelectPreset(preset: DemoPresetSchema) {
    setSelectedPresetId(preset.id);
    const p = preset.payload;

    setTitle(p.title || `Assessment: ${preset.name}`);

    // Model
    if (p.model_path) {
      setModelMode('local');
      setModelPath(p.model_path);
      setUploadedModel(null);
    }

    // Reference model
    if (p.model_reference_path) {
      setRefModelMode('local');
      setRefModelPath(p.model_reference_path);
      setUploadedRefModel(null);
    } else {
      setRefModelPath('');
    }

    // Dataset
    if (p.dataset_path) {
      setDatasetMode('local');
      setDatasetPath(p.dataset_path);
      setDatasetFormat(p.dataset_format || 'image_dir');
      setUploadedDataset(null);
    }

    // Provenance
    if (p.provenance_manifest) {
      setProvenanceJsonText(JSON.stringify(p.provenance_manifest, null, 2));
    } else {
      setProvenanceJsonText('');
    }
    setProvenancePublicKeyHex(p.provenance_public_key_hex || '');
    setActualInputHex(p.actual_input_bytes_hex || '');
    setActualOutputHex(p.actual_output_bytes_hex || '');
    setActualModelSha(p.actual_model_sha256 || '');

    // Thresholds
    if (p.phash_threshold !== undefined) setPhashThreshold(p.phash_threshold);
    if (p.dhash_threshold !== undefined) setDhashThreshold(p.dhash_threshold);
    if (p.min_cluster_size !== undefined) setMinClusterSize(p.min_cluster_size);

    setErrors([]);
  }

  function validate() {
    const e: string[] = [];
    if (!title.trim()) e.push('Assessment title is required.');

    const hasModel = modelMode === 'upload' ? !!uploadedModel : !!modelPath.trim();
    const hasDataset = datasetMode === 'upload' ? !!uploadedDataset : !!datasetPath.trim();
    const hasProvenance = !!provenanceJsonText.trim();

    if (!hasModel && !hasDataset && !hasProvenance) {
      e.push('Provide at least one model or dataset asset.');
    }

    if (provenanceJsonText.trim()) {
      try {
        JSON.parse(provenanceJsonText.trim());
      } catch (jsonErr) {
        e.push(`Malformed Provenance Manifest JSON: ${jsonErr instanceof Error ? jsonErr.message : 'Invalid JSON'}`);
      }
    }

    return e;
  }

  async function handleSubmit(e?: React.FormEvent) {
    if (e) e.preventDefault();
    const errs = validate();
    if (errs.length) {
      setErrors(errs);
      return;
    }

    setErrors([]);
    setStage('running');
    setElapsedSeconds(0);
    timerRef.current = setInterval(() => {
      setElapsedSeconds((sec) => sec + 1);
    }, 1000);

    let parsedManifest: Record<string, unknown> | null = null;
    if (provenanceJsonText.trim()) {
      try {
        parsedManifest = JSON.parse(provenanceJsonText.trim());
      } catch {
        // Handled in validation
      }
    }

    try {
      const payload: AssessmentCreateRequest = {
        title: title.trim(),
        model_asset_id: modelMode === 'upload' && uploadedModel ? uploadedModel.asset_id : null,
        model_path: modelMode === 'local' && modelPath.trim() ? modelPath.trim() : null,
        model_reference_asset_id: refModelMode === 'upload' && uploadedRefModel ? uploadedRefModel.asset_id : null,
        model_reference_path: refModelMode === 'local' && refModelPath.trim() ? refModelPath.trim() : null,
        dataset_asset_id: datasetMode === 'upload' && uploadedDataset ? uploadedDataset.asset_id : null,
        dataset_path: datasetMode === 'local' && datasetPath.trim() ? datasetPath.trim() : null,
        dataset_format:
          datasetMode === 'upload' && uploadedDataset
            ? uploadedDataset.format || null
            : datasetPath.trim()
            ? datasetFormat
            : null,
        provenance_manifest: parsedManifest,
        provenance_public_key_hex: provenancePublicKeyHex.trim() || null,
        actual_input_bytes_hex: actualInputHex.trim() || null,
        actual_output_bytes_hex: actualOutputHex.trim() || null,
        actual_model_sha256: actualModelSha.trim() || null,
        phash_threshold: Number(phashThreshold),
        dhash_threshold: Number(dhashThreshold),
        min_cluster_size: Number(minClusterSize),
      };

      const result: AssessmentResultSchema = await createAssessment(payload);
      if (timerRef.current) clearInterval(timerRef.current);
      sessionStorage.setItem('pramaan_last_assessment_id', result.assessment_id);
      setAssessmentResult(result);
      setStage('completed');
    } catch (err) {
      if (timerRef.current) clearInterval(timerRef.current);
      setErrorMsg(err instanceof Error ? err.message : 'Assessment execution failed.');
      setStage('error');
    }
  }

  // Unified Running & Completed Workstation State
  if (stage === 'running' || (stage === 'completed' && assessmentResult)) {
    const isRunning = stage === 'running';
    const normRisk = assessmentResult?.overall_risk?.toLowerCase() || 'none';
    const normConf = assessmentResult?.overall_confidence?.toLowerCase() || 'high';

    const riskAccent =
      normRisk === 'critical' ? '--risk-critical' :
      normRisk === 'high' ? '--risk-high' :
      normRisk === 'medium' ? '--risk-medium' :
      normRisk === 'low' ? '--risk-low' :
      '--risk-none';

    const pipelineRow1 = [
      { id: 'ingest', name: 'INGEST' },
      { id: 'validate', name: 'VALIDATE' },
      { id: 'identify', name: 'IDENTIFY ASSETS' },
      { id: 'fingerprint', name: 'FINGERPRINT' },
    ];

    const pipelineRow2 = [
      { id: 'profile', name: 'PROFILE ACCESS' },
      { id: 'select', name: 'SELECT METHODS' },
      { id: 'execute', name: 'EXECUTE' },
      { id: 'evidence', name: 'COLLECT EVIDENCE' },
    ];

    const pipelineRow3 = [
      { id: 'risk', name: 'RISK', full: 'CALCULATE RISK' },
      { id: 'confidence', name: 'CONFIDENCE', full: 'CALCULATE CONFIDENCE' },
      { id: 'coverage', name: 'COVERAGE', full: 'DETERMINE COVERAGE' },
      { id: 'findings', name: 'FINDINGS', full: 'GENERATE FINDINGS' },
      { id: 'audit', name: 'AUDIT', full: 'AUDIT TRAIL' },
      { id: 'report', name: 'REPORT', full: 'ASSURANCE REPORT' },
    ];

    const allLifecycleStages = [
      'INGEST',
      'VALIDATE',
      'IDENTIFY ASSETS',
      'FINGERPRINT',
      'PROFILE ACCESS',
      'SELECT METHODS',
      'EXECUTE',
      'COLLECT EVIDENCE',
      'RISK',
      'CONFIDENCE',
      'COVERAGE',
      'FINDINGS',
      'AUDIT',
      'REPORT',
    ];

    return (
      <div className="min-h-[calc(100vh-3.5rem)] flex flex-col justify-center px-4 sm:px-6 py-4 sm:py-6">
        <div className="max-w-4xl lg:max-w-5xl 2xl:max-w-6xl w-full mx-auto bg-surface border border-[var(--border)] rounded-2xl shadow-xl overflow-hidden transition-all duration-200">
          {/* Top Indicator Accent */}
          <div
            className={cn(
              'h-1 w-full',
              isRunning
                ? 'bg-gradient-to-r from-accent/40 via-accent to-[var(--green)] animate-pulse'
                : 'bg-gradient-to-r from-[var(--green)]/40 via-[var(--green)] to-[var(--accent)]'
            )}
          />

          <div className="p-5 sm:p-6 lg:p-7 space-y-4 sm:space-y-5">
            {/* Header: Status icon + title + subtitle */}
            <div className="text-center space-y-1">
              {isRunning ? (
                <div className="inline-flex items-center justify-center w-11 h-11 rounded-full bg-[var(--accent-bg)] border border-accent/30 text-accent shadow-[0_0_18px_rgba(59,130,246,0.15)] mb-0.5">
                  <Loader2 className="w-6 h-6 animate-spin text-accent" />
                </div>
              ) : (
                <div className="inline-flex items-center justify-center w-11 h-11 rounded-full bg-[var(--green-bg)] border border-[var(--green)]/30 text-[var(--green)] shadow-[0_0_18px_rgba(16,185,129,0.15)] mb-0.5">
                  <CheckCircle2 className="w-6 h-6" />
                </div>
              )}
              <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-1">
                {isRunning ? 'Executing Forensic Assurance Battery' : 'Assessment Complete'}
              </h1>
              <p className="text-xs text-3 max-w-lg mx-auto">
                {isRunning
                  ? `Evaluating mathematical fingerprints, numerical distributions, and cryptographic bindings in local air-gapped memory (${elapsedSeconds}s elapsed).`
                  : 'Forensic battery finished successfully.'}
              </p>
            </div>

            {/* ASSURANCE SUMMARY */}
            <div className="space-y-2">
              <div className="flex items-center justify-between pb-1 border-b border-[var(--border)]">
                <span className="text-[10px] sm:text-[11px] font-mono tracking-wider text-3 uppercase font-semibold">
                  Assurance Summary
                </span>
                <span className="text-[10px] font-mono text-3 hidden sm:inline">
                  Deterministic ADR-003
                </span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                {/* Risk */}
                <div className="p-3.5 sm:p-4 rounded-xl border border-[var(--border)] bg-surface-2/60 flex flex-col justify-between space-y-1 shadow-sm">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] uppercase text-3 font-mono font-semibold tracking-wider">Risk</span>
                    <span className="text-[9px] font-mono text-3 px-1.5 py-0.2 rounded bg-surface border border-[var(--border)]">
                      {isRunning ? 'IN PROGRESS' : 'DEFECT'}
                    </span>
                  </div>
                  <div className="my-0.5 flex items-center">
                    {isRunning ? (
                      <>
                        <span className="w-2.5 h-2.5 rounded-full mr-2 shrink-0 bg-accent animate-ping" />
                        <span className="text-2xl sm:text-3xl font-mono font-bold tracking-tight text-accent animate-pulse">
                          ANALYZING
                        </span>
                      </>
                    ) : (
                      <>
                        <span
                          className="w-2.5 h-2.5 rounded-full mr-2 shrink-0"
                          style={{ backgroundColor: `var(${riskAccent})` }}
                        />
                        <span
                          className="text-2xl sm:text-3xl font-mono font-bold tracking-tight"
                          style={{ color: `var(${riskAccent})` }}
                        >
                          {normRisk.toUpperCase()}
                        </span>
                      </>
                    )}
                  </div>
                  <div className="text-[11px] text-3 font-mono leading-snug line-clamp-2 min-h-[2rem]">
                    {isRunning
                      ? 'Evaluating defect distributions & threshold bounds...'
                      : (assessmentResult?.risk_qualitative || 'Overall Defect Severity')}
                  </div>
                </div>

                {/* Confidence */}
                <div className="p-3.5 sm:p-4 rounded-xl border border-[var(--border)] bg-surface-2/60 flex flex-col justify-between space-y-1 shadow-sm">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] uppercase text-3 font-mono font-semibold tracking-wider">Confidence</span>
                    <span className="text-[9px] font-mono text-3 px-1.5 py-0.2 rounded bg-surface border border-[var(--border)]">
                      {isRunning ? 'CALCULATING' : 'STATISTICAL'}
                    </span>
                  </div>
                  <div className="my-0.5 flex items-center">
                    {isRunning ? (
                      <>
                        <span className="w-2.5 h-2.5 rounded-full mr-2 shrink-0 bg-accent/60" />
                        <span className="text-2xl sm:text-3xl font-mono font-bold tracking-tight text-2 animate-pulse">
                          CALCULATING
                        </span>
                      </>
                    ) : (
                      <>
                        <span className="w-2.5 h-2.5 rounded-full mr-2 shrink-0 bg-[var(--green)]" />
                        <span className="text-2xl sm:text-3xl font-mono font-bold tracking-tight text-1">
                          {normConf.toUpperCase()}
                        </span>
                      </>
                    )}
                  </div>
                  <div className="text-[11px] text-3 font-mono leading-snug line-clamp-2 min-h-[2rem]">
                    {isRunning
                      ? 'Deriving mathematical and statistical certainty...'
                      : (assessmentResult?.confidence_qualifier || 'Mathematical Certainty')}
                  </div>
                </div>

                {/* Coverage */}
                <div className="p-3.5 sm:p-4 rounded-xl border border-[var(--border)] bg-surface-2/60 flex flex-col justify-between space-y-1 shadow-sm">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] uppercase text-3 font-mono font-semibold tracking-wider">Coverage</span>
                    <span className="text-[9px] font-mono text-3 px-1.5 py-0.2 rounded bg-surface border border-[var(--border)]">
                      {isRunning ? 'ACTIVE' : 'VERIFIED'}
                    </span>
                  </div>
                  <div className="my-0.5 flex items-center">
                    {isRunning ? (
                      <>
                        <span className="w-2.5 h-2.5 rounded-full mr-2 shrink-0 bg-accent animate-pulse" />
                        <span className="text-2xl sm:text-3xl font-mono font-bold tracking-tight text-accent">
                          RUNNING
                        </span>
                      </>
                    ) : (
                      <>
                        <span className="w-2.5 h-2.5 rounded-full mr-2 shrink-0 bg-accent" />
                        <span className="text-2xl sm:text-3xl font-mono font-bold tracking-tight text-accent">
                          {formatPercent(assessmentResult?.coverage_fraction ?? 1.0)}
                        </span>
                      </>
                    )}
                  </div>
                  <div className="text-[11px] text-3 font-mono leading-snug line-clamp-2 min-h-[2rem]">
                    {isRunning ? '14 Lifecycle Checkpoints in progress' : '14 / 14 Checkpoints Complete'}
                  </div>
                </div>
              </div>
            </div>

            {/* ASSESSMENT PIPELINE */}
            <div className="space-y-2">
              <div className="flex items-center justify-between pb-1 border-b border-[var(--border)]">
                <span className="text-[10px] sm:text-[11px] font-mono tracking-wider text-3 uppercase font-semibold">
                  Assessment Pipeline
                </span>
                <div className="inline-flex items-center gap-1.5 text-[10px] sm:text-[11px] font-mono text-[var(--green)]">
                  {isRunning ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 animate-spin text-accent" />
                      <span className="text-accent">14 Stages In Execution</span>
                    </>
                  ) : (
                    <>
                      <span className="w-1.5 h-1.5 rounded-full bg-[var(--green)]" />
                      <span>14/14 Stages Verified</span>
                    </>
                  )}
                </div>
              </div>

              {/* Desktop Compact Lifecycle Visualization */}
              <div className="hidden md:flex flex-col gap-1">
                {/* Row 1 */}
                <div className="flex items-center justify-between gap-1.5">
                  {pipelineRow1.map((item, idx) => (
                    <div key={item.id} className="flex-1 flex items-center">
                      <div className={cn(
                        "flex-1 flex items-center justify-center gap-1.5 py-1.5 px-2 rounded-lg bg-surface-2/80 border text-xs font-mono font-medium shadow-sm transition-colors",
                        isRunning ? "border-accent/30 text-2" : "border-[var(--border)] text-1 hover:border-[var(--green)]/40"
                      )}>
                        {isRunning ? (
                          <Loader2 className="w-3.5 h-3.5 text-accent animate-spin shrink-0" />
                        ) : (
                          <CheckCircle2 className="w-3.5 h-3.5 text-[var(--green)] shrink-0" />
                        )}
                        <span className="truncate">{item.name}</span>
                      </div>
                      {idx < pipelineRow1.length - 1 && (
                        <ArrowRight className="w-3.5 h-3.5 text-3/40 shrink-0 mx-1.5" />
                      )}
                    </div>
                  ))}
                </div>

                {/* Connector Down */}
                <div className="flex items-center -my-0.5 select-none">
                  <div className={cn("w-1/4 flex justify-center", isRunning ? "text-accent" : "text-[var(--green)]/80")}>
                    <ArrowDown className="w-3.5 h-3.5" />
                  </div>
                  <div className="flex-1 h-px bg-gradient-to-r from-[var(--border)] via-[var(--border)]/40 to-transparent" />
                </div>

                {/* Row 2 */}
                <div className="flex items-center justify-between gap-1.5">
                  {pipelineRow2.map((item, idx) => (
                    <div key={item.id} className="flex-1 flex items-center">
                      <div className={cn(
                        "flex-1 flex items-center justify-center gap-1.5 py-1.5 px-2 rounded-lg bg-surface-2/80 border text-xs font-mono font-medium shadow-sm transition-colors",
                        isRunning ? "border-accent/30 text-2" : "border-[var(--border)] text-1 hover:border-[var(--green)]/40"
                      )}>
                        {isRunning ? (
                          <Loader2 className="w-3.5 h-3.5 text-accent animate-spin shrink-0" />
                        ) : (
                          <CheckCircle2 className="w-3.5 h-3.5 text-[var(--green)] shrink-0" />
                        )}
                        <span className="truncate">{item.name}</span>
                      </div>
                      {idx < pipelineRow2.length - 1 && (
                        <ArrowRight className="w-3.5 h-3.5 text-3/40 shrink-0 mx-1.5" />
                      )}
                    </div>
                  ))}
                </div>

                {/* Connector Down */}
                <div className="flex items-center -my-0.5 select-none">
                  <div className={cn("w-1/4 flex justify-center", isRunning ? "text-accent" : "text-[var(--green)]/80")}>
                    <ArrowDown className="w-3.5 h-3.5" />
                  </div>
                  <div className="flex-1 h-px bg-gradient-to-r from-[var(--border)] via-[var(--border)]/40 to-transparent" />
                </div>

                {/* Row 3 */}
                <div className="flex items-center justify-between gap-1.5">
                  {pipelineRow3.map((item, idx) => (
                    <div key={item.id} className="flex-1 flex items-center">
                      <div
                        title={item.full}
                        className={cn(
                          "flex-1 flex items-center justify-center gap-1.5 py-1.5 px-1.5 rounded-lg bg-surface-2/80 border text-xs font-mono font-medium shadow-sm transition-colors",
                          isRunning ? "border-accent/30 text-2" : "border-[var(--border)] text-1 hover:border-[var(--green)]/40"
                        )}
                      >
                        {isRunning ? (
                          <Loader2 className="w-3.5 h-3.5 text-accent animate-spin shrink-0" />
                        ) : (
                          <CheckCircle2 className="w-3.5 h-3.5 text-[var(--green)] shrink-0" />
                        )}
                        <span className="truncate">{item.name}</span>
                      </div>
                      {idx < pipelineRow3.length - 1 && (
                        <ArrowRight className="w-3.5 h-3.5 text-3/40 shrink-0 mx-1" />
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {/* Mobile / Tablet Grid */}
              <div className="grid grid-cols-2 gap-1.5 md:hidden">
                {allLifecycleStages.map((stg) => (
                  <div
                    key={stg}
                    className="flex items-center gap-2 p-2 rounded-lg bg-surface-2/80 border border-[var(--border)] text-xs font-mono font-medium text-1"
                  >
                    {isRunning ? (
                      <Loader2 className="w-3.5 h-3.5 text-accent animate-spin shrink-0" />
                    ) : (
                      <CheckCircle2 className="w-3.5 h-3.5 text-[var(--green)] shrink-0" />
                    )}
                    <span className="truncate">{stg}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* ACTION BUTTONS & METADATA FOOTER */}
            <div className="flex flex-col sm:flex-row items-center justify-between gap-3 pt-3 sm:pt-4 border-t border-[var(--border)]">
              <div className="text-xs text-3 font-mono hidden sm:flex items-center gap-2">
                <span className="text-3 font-semibold">
                  {isRunning ? 'EXECUTION MODE:' : 'ASSESSMENT ID:'}
                </span>
                <span className="text-1 font-bold">
                  {isRunning ? 'LOCAL AIR-GAPPED EVALUATION' : assessmentResult?.assessment_id.slice(0, 16)}
                </span>
              </div>

              <div className="flex flex-col sm:flex-row items-center gap-3 w-full sm:w-auto">
                {isRunning ? (
                  <button
                    disabled
                    type="button"
                    className="w-full sm:w-auto px-6 py-2.5 rounded-lg bg-surface-2 border border-[var(--border)] text-3 text-xs font-semibold flex items-center justify-center gap-2 cursor-wait opacity-80"
                  >
                    <Loader2 className="w-4 h-4 animate-spin text-accent" />
                    <span>Executing Battery ({elapsedSeconds}s)…</span>
                  </button>
                ) : (
                  <>
                    <button
                      type="button"
                      onClick={() => navigate(`/assessments/${assessmentResult!.assessment_id}/findings`)}
                      className="w-full sm:w-auto px-5 py-2.5 rounded-lg border border-[var(--border)] bg-surface hover:bg-surface-2 text-xs font-semibold text-1 transition-colors flex items-center justify-center gap-2 shadow-sm"
                    >
                      View Findings
                    </button>
                    <button
                      type="button"
                      onClick={() => navigate(`/assessments/${assessmentResult!.assessment_id}/result`, { state: { result: assessmentResult } })}
                      className="w-full sm:w-auto px-6 py-2.5 rounded-lg bg-accent text-white text-xs font-semibold hover:bg-[var(--accent-2)] transition-colors flex items-center justify-center gap-2 shadow-sm hover:shadow"
                    >
                      <span>Proceed to Report</span>
                      <ArrowRight className="w-4 h-4" />
                    </button>
                  </>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Error State
  if (stage === 'error') {
    return (
      <div className="min-h-[calc(100vh-3rem)] flex flex-col items-center justify-center px-6">
        <div className="max-w-lg w-full p-8 rounded-2xl border border-[var(--red)]/30 bg-surface text-center space-y-5 shadow-lg">
          <div className="w-12 h-12 rounded-full bg-[var(--red-bg)] border border-[var(--red)]/40 flex items-center justify-center text-[var(--red)] mx-auto">
            <AlertCircle className="w-6 h-6" />
          </div>

          <div className="space-y-1">
            <h1 className="text-lg font-bold text-1">Assessment Ingestion Rejected</h1>
            <p className="text-xs text-2 leading-relaxed">{errorMsg}</p>
          </div>

          <button
            type="button"
            onClick={() => {
              setStage('form');
              setTimeout(() => {
                document.getElementById('assessment-title')?.focus();
              }, 50);
            }}
            className="px-4 py-2 rounded-lg bg-accent text-white text-xs font-semibold hover:bg-[var(--accent-2)] transition-colors focus-visible:ring-2 focus-visible:ring-accent focus:outline-none"
          >
            Review & Edit Inputs
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 py-6 sm:py-8 space-y-8">
      {/* Page Header */}
      <div>
        <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-[var(--accent-bg)] border border-accent/25 text-accent text-[11px] font-mono font-semibold uppercase mb-2">
          New Assurance Run
        </div>
        <h1 className="text-2xl sm:text-3xl font-extrabold text-1 tracking-tight">New Assessment</h1>
        <p className="text-xs text-3 mt-1">
          Select an evaluation preset or provide candidate model, dataset, and provenance assets for offline assurance.
        </p>
      </div>

      {/* ── Mode Switcher Tabs ── */}
      <div className="flex items-center justify-between border-b border-[var(--border)] pb-4 gap-4 flex-wrap">
        <div className="flex items-center gap-2 p-1 rounded-xl bg-surface-2 border border-[var(--border)]">
          <button
            type="button"
            onClick={() => {
              setEntryMode('custom');
              const p = new URLSearchParams(searchParams);
              p.delete('mode');
              p.delete('preset');
              setSearchParams(p);
            }}
            className={cn(
              'px-4 py-2 rounded-lg text-xs font-semibold transition-all duration-150 select-none flex items-center gap-2',
              entryMode === 'custom'
                ? 'bg-surface text-1 shadow-sm border border-[var(--border)]'
                : 'text-3 hover:text-1'
            )}
          >
            <SlidersHorizontal className="w-3.5 h-3.5" />
            <span>Custom Assessment</span>
          </button>

          <button
            type="button"
            onClick={() => {
              setEntryMode('demo');
              const p = new URLSearchParams(searchParams);
              p.set('mode', 'demo');
              setSearchParams(p);
            }}
            className={cn(
              'px-4 py-2 rounded-lg text-xs font-semibold transition-all duration-150 select-none flex items-center gap-2',
              entryMode === 'demo'
                ? 'bg-accent text-white shadow-sm'
                : 'text-3 hover:text-1'
            )}
          >
            <Sparkles className="w-3.5 h-3.5" />
            <span>Demo Mode (Corpus Scenarios)</span>
            <span className={cn(
              'px-1.5 py-0.2 rounded font-mono text-[9px] font-bold uppercase',
              entryMode === 'demo' ? 'bg-white/20 text-white' : 'bg-surface text-accent border border-accent/30'
            )}>
              5 PRESETS
            </span>
          </button>
        </div>

        {entryMode === 'demo' && (
          <div className="text-xs text-3 font-mono flex items-center gap-2">
            <ShieldCheck className="w-3.5 h-3.5 text-accent" />
            <span>OFFLINE DETERMINISTIC VERIFICATION</span>
          </div>
        )}
      </div>

      {/* ── Demo Mode Presets Suite (when Demo Mode is selected) ── */}
      {entryMode === 'demo' && (
        <DemoPresets
          onSelectPreset={handleSelectPreset}
          selectedPresetId={selectedPresetId}
          onExecute={() => handleSubmit()}
          onClearPreset={handleClearPreset}
        />
      )}

      {/* Errors Banner */}
      {errors.length > 0 && (
        <div className="p-4 rounded-xl bg-[var(--red-bg)]/20 border border-[var(--red)]/40 text-xs text-[var(--red)] space-y-1">
          <p className="font-bold">Please resolve the following input requirements:</p>
          <ul className="list-disc list-inside space-y-0.5">
            {errors.map((err, i) => (
              <li key={i}>{err}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Main Configuration Form with Right-Hand Assurance Battery Registry */}
      <form onSubmit={handleSubmit} className="space-y-6">
        <div className="grid grid-cols-1 xl:grid-cols-[1fr_420px] gap-8 items-start">
          {/* Main Form Fields */}
          <div className="space-y-6">
            {/* Assessment Title */}
            <div className="card p-5 border border-[var(--border)] bg-surface rounded-xl space-y-3">
          <Field
            label="Assessment Title"
            id="assessment-title"
            value={title}
            onChange={setTitle}
            placeholder="e.g. YOLOv8 Production Model Validation (Baseline v1.2)"
            required
            helpText="Authoritative descriptive title for the audit ledger and PDF assurance report."
          />
        </div>

        {/* ── Section: Candidate Model Ingestion ── */}
        <div className="card p-5 border border-[var(--border)] bg-surface rounded-xl space-y-4">
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <div className="flex items-center gap-2">
              <Cpu className="w-4 h-4 text-purple-500" />
              <h2 className="text-xs font-mono font-bold text-1 uppercase tracking-wider">
                Candidate Model Artifact (MI-01..MI-05)
              </h2>
            </div>
            <ModeToggle mode={modelMode} onChange={setModelMode} />
          </div>

          {modelMode === 'upload' ? (
            <FileUpload
              accept=".onnx,.pt,.pth,.ts,.zip"
              assetType="model"
              label="Upload Candidate Model (.onnx, .pt, .pth)"
              description="Maximum 500 MB. Files are stored in local content-addressed blob store."
              onUploadSuccess={setUploadedModel}
              currentUpload={uploadedModel}
              onClear={() => setUploadedModel(null)}
            />
          ) : (
            <Field
              label="Local Model Absolute Path"
              id="model-path"
              value={modelPath}
              onChange={setModelPath}
              placeholder="e.g. C:/models/classifier.onnx"
              helpText="Must be an absolute filesystem path accessible to the local PRAMAAN engine."
              onClear={() => setModelPath('')}
            />
          )}

          {/* Reference Model (MI-04 Differential Analysis) */}
          <div className="pt-3 border-t border-[var(--border)] space-y-3">
            <div className="flex items-center justify-between gap-4 flex-wrap">
              <div>
                <label className="text-xs font-semibold text-2">
                  Reference Baseline Model (Optional — Required for MI-04)
                </label>
                <p className="text-[11px] text-3">
                  Authoritative reference model for parameter subtraction and architectural differential analysis.
                </p>
              </div>
              <div className="flex rounded-lg border border-[var(--border)] p-0.5 bg-surface-2/60 w-fit text-xs">
                <button
                  type="button"
                  onClick={() => setRefModelMode('upload')}
                  className={cn(
                    'px-2.5 py-1 rounded-md font-medium transition-colors text-[11px]',
                    refModelMode === 'upload' ? 'bg-surface text-1 shadow-sm font-semibold' : 'text-3 hover:text-2'
                  )}
                >
                  Upload Baseline
                </button>
                <button
                  type="button"
                  onClick={() => setRefModelMode('local')}
                  className={cn(
                    'px-2.5 py-1 rounded-md font-medium transition-colors text-[11px]',
                    refModelMode === 'local' ? 'bg-surface text-1 shadow-sm font-semibold' : 'text-3 hover:text-2'
                  )}
                >
                  Local Baseline Path
                </button>
              </div>
            </div>

            {refModelMode === 'upload' ? (
              <FileUpload
                accept=".onnx,.pt,.pth,.ts,.zip"
                assetType="model"
                label="Upload Reference Baseline (.onnx, .pt, .pth)"
                onUploadSuccess={setUploadedRefModel}
                currentUpload={uploadedRefModel}
                onClear={() => setUploadedRefModel(null)}
              />
            ) : (
              <Field
                label="Reference Model Absolute Path"
                id="ref-model-path"
                value={refModelPath}
                onChange={setRefModelPath}
                placeholder="C:\models\reference_baseline.onnx"
                onClear={() => setRefModelPath('')}
              />
            )}
          </div>
        </div>

        {/* ── Section: Dataset Ingestion ── */}
        <div className="card p-5 border border-[var(--border)] bg-surface rounded-xl space-y-4">
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <div className="flex items-center gap-2">
              <Database className="w-4 h-4 text-blue-500" />
              <h2 className="text-xs font-mono font-bold text-1 uppercase tracking-wider">
                Dataset / Training Images (DI-01..DI-05)
              </h2>
            </div>
            <ModeToggle mode={datasetMode} onChange={setDatasetMode} />
          </div>

          {datasetMode === 'upload' ? (
            <FileUpload
              accept=".zip"
              assetType="dataset"
              label="Upload Dataset ZIP Archive"
              description="Maximum 500 MB. ZIP containing JPEG, PNG, or WEBP images."
              onUploadSuccess={setUploadedDataset}
              currentUpload={uploadedDataset}
              onClear={() => setUploadedDataset(null)}
            />
          ) : (
            <div className="space-y-3">
              <Field
                label="Local Dataset Directory Path"
                id="dataset-path"
                value={datasetPath}
                onChange={setDatasetPath}
                placeholder="C:\datasets\coco_val or /workspace/datasets/images"
                helpText="Directory containing image samples for data integrity analysis."
                onClear={() => setDatasetPath('')}
              />

              <div className="space-y-1">
                <label htmlFor="dataset-format" className="label text-xs font-semibold text-2">
                  Dataset Format
                </label>
                <select
                  id="dataset-format"
                  value={datasetFormat}
                  onChange={(e) => setDatasetFormat(e.target.value)}
                  className="w-full h-9 px-3 rounded-lg border border-[var(--border)] bg-surface text-1 text-xs focus:outline-none focus:border-accent"
                >
                  <option value="image_dir">Image Directory (Raw samples)</option>
                  <option value="coco_json">COCO JSON Schema (Annotations included)</option>
                </select>
              </div>
            </div>
          )}
        </div>

        {/* ── Section: Inference Provenance Manifest (PI-01) ── */}
        <div className="card p-5 border border-[var(--border)] bg-surface rounded-xl space-y-4">
          <div className="flex items-center gap-2">
            <KeyRound className="w-4 h-4 text-cyan-500" />
            <div>
              <h2 className="text-xs font-mono font-bold text-1 uppercase tracking-wider">
                Inference Provenance Manifest (Optional — PI-01)
              </h2>
              <p className="text-[11px] text-3">
                Attach a signed ProvenanceManifest for Ed25519 signature verification, replay protection, and output binding.
              </p>
            </div>
          </div>

          <div className="space-y-1">
            <label htmlFor="provenance-json" className="label text-xs font-semibold text-2">
              Signed ProvenanceManifest JSON Payload
            </label>
            <textarea
              id="provenance-json"
              rows={4}
              value={provenanceJsonText}
              onChange={(e) => setProvenanceJsonText(e.target.value)}
              placeholder='Paste JSON manifest or {"manifest_id": "...", "input_sha256": "...", ...}'
              className="w-full p-3 rounded-lg border border-[var(--border)] bg-surface text-1 text-xs font-mono placeholder:font-sans focus:outline-none focus:border-accent"
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Field
              label="Signer Ed25519 Public Key (Hex)"
              id="prov-public-key"
              value={provenancePublicKeyHex}
              onChange={setProvenancePublicKeyHex}
              placeholder="32-byte hex public key"
            />
            <Field
              label="Actual Model SHA-256 (For Binding Check)"
              id="prov-model-sha"
              value={actualModelSha}
              onChange={setActualModelSha}
              placeholder="64-char hex SHA-256"
            />
          </div>
        </div>

        {/* ── Section: Advanced Detector Thresholds (Accordion) ── */}
        <div className="border border-[var(--border)] bg-surface rounded-xl overflow-hidden">
          <button
            type="button"
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="w-full p-4 flex items-center justify-between text-left hover:bg-surface-2/40 transition-colors"
          >
            <div className="flex items-center gap-2">
              <SlidersHorizontal className="w-4 h-4 text-accent" />
              <span className="text-xs font-mono font-bold text-1 uppercase tracking-wider">
                Advanced Detector Thresholds
              </span>
              <span className="text-[10px] text-3 font-mono">(Defaults: pHash 10, dHash 10, cluster 2)</span>
            </div>
            {showAdvanced ? <ChevronUp className="w-4 h-4 text-3" /> : <ChevronDown className="w-4 h-4 text-3" />}
          </button>

          {showAdvanced && (
            <div className="p-5 border-t border-[var(--border)] bg-surface-2/20 grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs">
              <div className="space-y-1">
                <label htmlFor="phash-thresh" className="font-semibold text-2">
                  pHash Hamming Threshold: <span className="text-accent font-mono">{phashThreshold}</span>
                </label>
                <input
                  id="phash-thresh"
                  type="range"
                  min={0}
                  max={64}
                  value={phashThreshold}
                  onChange={(e) => setPhashThreshold(Number(e.target.value))}
                  className="w-full accent-accent"
                />
                <p className="text-[10px] text-3">Hamming distance &le; {phashThreshold} classifies perceptual near-duplicates.</p>
              </div>

              <div className="space-y-1">
                <label htmlFor="dhash-thresh" className="font-semibold text-2">
                  dHash Hamming Threshold: <span className="text-accent font-mono">{dhashThreshold}</span>
                </label>
                <input
                  id="dhash-thresh"
                  type="range"
                  min={0}
                  max={64}
                  value={dhashThreshold}
                  onChange={(e) => setDhashThreshold(Number(e.target.value))}
                  className="w-full accent-accent"
                />
                <p className="text-[10px] text-3">Gradient difference hash distance threshold.</p>
              </div>

              <div className="space-y-1">
                <label htmlFor="min-cluster" className="font-semibold text-2">
                  Min Duplicate Cluster Size: <span className="text-accent font-mono">{minClusterSize}</span>
                </label>
                <input
                  id="min-cluster"
                  type="number"
                  min={2}
                  max={50}
                  value={minClusterSize}
                  onChange={(e) => setMinClusterSize(Math.max(2, Number(e.target.value)))}
                  className="w-full h-8 px-2 rounded border border-[var(--border)] bg-surface text-1 font-mono text-xs"
                />
                <p className="text-[10px] text-3">Minimum identical/near samples to form a cluster.</p>
              </div>
            </div>
          )}
        </div>

            {/* Submit Execution Button */}
            <div className="pt-2 flex items-center justify-end gap-4">
              <button
                type="submit"
                className="inline-flex items-center gap-2 px-6 py-2.5 rounded-lg bg-accent text-white text-xs sm:text-sm font-semibold hover:bg-[var(--accent-2)] transition-all shadow-sm active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
              >
                <span>Run Assessment</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Right Column on Desktop (>= xl) / Bottom Section (< xl): Assurance Battery Registry */}
          <aside className="border border-[var(--border)] rounded-xl bg-surface p-5 sm:p-6 space-y-4 xl:sticky xl:top-20 shadow-sm">
            <div className="flex items-start justify-between gap-4 border-b border-[var(--border)] pb-4">
              <div>
                <p className="text-[10px] font-mono font-bold text-accent uppercase tracking-wider mb-1">
                  Assurance Battery Registry
                </p>
                <h2 className="text-sm sm:text-base font-bold text-1">What will PRAMAAN check?</h2>
                <p className="text-xs text-3 leading-relaxed mt-1">
                  Forensic checks adapt deterministically to the input artifacts provided.
                </p>
              </div>
              <span className="shrink-0 text-[10px] font-mono px-2 py-0.5 rounded bg-[var(--green-bg)] text-[var(--green)] border border-[var(--green)]/30 font-semibold">
                100% Offline
              </span>
            </div>

            {/* Detector List: 2 cols on tablet/stacked mobile, single col in xl sidebar */}
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-1 gap-2.5 max-h-[580px] overflow-y-auto pr-1">
              {caps?.detectors.map(d => {
                const layerInfo = getDetectorLayerInfo(d.detector_id, d);
                const execStatus = getDetectorExecutionStatus(d.detector_id);
                const formattedId = layerInfo.code;

                return (
                  <div
                    key={d.detector_id}
                    className="p-3 rounded-lg border border-[var(--border)] bg-surface-2/40 hover:bg-surface-2 transition-all space-y-2 shadow-sm"
                  >
                    <div className="flex items-center justify-between gap-2 flex-wrap">
                      <div className="flex items-center gap-1.5">
                        <code className="text-[10px] font-mono font-bold text-accent px-1.5 py-0.5 rounded bg-[var(--accent-bg)] border border-accent/20">
                          {formattedId}
                        </code>
                        <span className={`text-[9px] font-mono px-1.5 py-0.5 rounded border uppercase font-semibold ${layerInfo.pillClass}`}>
                          {layerInfo.layer}
                        </span>
                      </div>
                      {execStatus.status === 'will_run' ? (
                        <span className="inline-flex items-center gap-1 text-[10px] font-mono font-semibold text-[var(--green)] bg-[var(--green-bg)] px-2 py-0.5 rounded border border-[var(--green)]/30">
                          <CheckCircle2 className="w-3 h-3" />
                          <span>{execStatus.label}</span>
                        </span>
                      ) : (
                        <span className="text-[10px] font-mono text-3 bg-surface-2 px-2 py-0.5 rounded border border-[var(--border)]">
                          {execStatus.label}
                        </span>
                      )}
                    </div>
                    <div>
                      <p className="text-xs font-bold text-1 leading-snug">{d.name || layerInfo.name}</p>
                      <p className="text-[11px] text-3 leading-relaxed mt-1">{d.description}</p>
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="pt-3 text-[11px] text-3 border-t border-[var(--border)] flex items-center justify-between font-mono">
              <span>{caps?.detectors.length ?? 0} Detectors Configured</span>
              <span className="text-accent font-semibold">
                {readyDetectorsCount} Ready to Run
              </span>
            </div>
          </aside>
        </div>
      </form>
    </div>
  );
}
