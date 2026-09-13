import { useEffect, useState, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { 
  ArrowRight, 
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
  ShieldCheck
} from 'lucide-react';
import { createAssessment, getCapabilities, getDemos } from '../api/client';
import type { 
  CapabilitiesResponse, 
  AssessmentResultSchema, 
  UploadResponse, 
  AssessmentCreateRequest, 
  DemoPresetSchema 
} from '../types/api';
import { FileUpload } from '../components/FileUpload';
import { DemoPresets } from '../components/DemoPresets';
import { cn } from '../lib/cn';

type Stage = 'form' | 'running' | 'error';

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

export function NewAssessment() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const initialMode = searchParams.get('mode') === 'demo' || searchParams.get('preset') ? 'demo' : 'custom';
  const [entryMode, setEntryMode] = useState<'custom' | 'demo'>(initialMode);
  const [stage, setStage] = useState<Stage>('form');
  const [title, setTitle] = useState('');

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
      navigate(`/assessments/${result.assessment_id}/result`, { state: { result } });
    } catch (err) {
      if (timerRef.current) clearInterval(timerRef.current);
      setErrorMsg(err instanceof Error ? err.message : 'Assessment execution failed.');
      setStage('error');
    }
  }

  // Running State (Honest Indeterminate Forensic Scanner)
  if (stage === 'running') {
    return (
      <div className="min-h-[calc(100vh-3rem)] flex flex-col items-center justify-center px-6">
        <div className="max-w-md w-full p-8 rounded-2xl border border-[var(--border)] bg-surface text-center space-y-6 shadow-lg">
          <div className="relative w-16 h-16 mx-auto flex items-center justify-center">
            <div className="absolute inset-0 rounded-full border-2 border-accent/20 animate-ping" />
            <div className="w-12 h-12 rounded-full bg-[var(--accent-bg)] border border-accent/40 flex items-center justify-center text-accent">
              <Loader2 className="w-6 h-6 animate-spin" />
            </div>
          </div>

          <div className="space-y-1.5">
            <h1 className="text-xl font-bold text-1">Executing Forensic Assurance Battery</h1>
            <p className="text-xs text-3 leading-relaxed">
              PRAMAAN is evaluating mathematical fingerprints, numerical distributions, and cryptographic bindings in
              local air-gapped memory.
            </p>
          </div>

          <div className="p-3.5 rounded-lg bg-surface-2 border border-[var(--border)] text-xs text-left space-y-2">
            <div className="flex items-center justify-between text-[11px] font-mono text-3">
              <span>EXECUTION TIME</span>
              <span className="text-1 font-bold">{elapsedSeconds}s elapsed</span>
            </div>
            <div className="space-y-1 text-[11px] font-mono text-2 pt-1 border-t border-[var(--border)]">
              <div className="truncate">
                <span className="text-3">Title: </span>
                <span>{title}</span>
              </div>
              {modelPath && (
                <div className="truncate">
                  <span className="text-3">Model: </span>
                  <span>{modelPath}</span>
                </div>
              )}
              {datasetPath && (
                <div className="truncate">
                  <span className="text-3">Dataset: </span>
                  <span>{datasetPath}</span>
                </div>
              )}
            </div>
          </div>

          <p className="text-[11px] text-3 italic">
            Verification is deterministic. No cloud calls or simulated telemetry.
          </p>
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

        {entryMode === 'demo' ? (
          <div className="text-xs text-3 font-mono flex items-center gap-2">
            <ShieldCheck className="w-3.5 h-3.5 text-accent" />
            <span>OFFLINE DETERMINISTIC VERIFICATION</span>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => {
              setEntryMode('demo');
              const p = new URLSearchParams(searchParams);
              p.set('mode', 'demo');
              setSearchParams(p);
            }}
            className="text-xs text-accent hover:underline flex items-center gap-1 font-medium"
          >
            <Sparkles className="w-3.5 h-3.5" />
            <span>Switch to Demo Mode for 1-Click Jury Scenarios</span>
          </button>
        )}
      </div>

      {/* ── Demo Mode Presets Suite OR Custom Mode Teaser ── */}
      {entryMode === 'demo' ? (
        <DemoPresets
          onSelectPreset={handleSelectPreset}
          selectedPresetId={selectedPresetId}
          onExecute={() => handleSubmit()}
          onClearPreset={handleClearPreset}
        />
      ) : (
        <div className="card p-4 border border-[var(--border)] bg-surface-2/40 rounded-xl flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 rounded-md bg-[var(--accent-bg)] text-accent flex items-center justify-center shrink-0">
              <Sparkles className="w-4 h-4" />
            </div>
            <div>
              <p className="text-xs font-semibold text-1">Looking for reproducible evaluation scenarios?</p>
              <p className="text-[11px] text-3">Explore 5 pre-configured offline corpus presets with 1-click execution.</p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => {
              setEntryMode('demo');
              const p = new URLSearchParams(searchParams);
              p.set('mode', 'demo');
              setSearchParams(p);
            }}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-surface border border-[var(--border)] text-xs font-semibold text-1 hover:border-accent/40 transition-colors shadow-sm"
          >
            <Sparkles className="w-3.5 h-3.5 text-accent" />
            <span>Switch to Demo Mode</span>
          </button>
        </div>
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
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-8 items-start">
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

          {/* Right Column: What will run? */}
          <aside className="border border-[var(--border)] rounded-xl bg-surface p-5 space-y-4 lg:sticky lg:top-20 shadow-sm">
            <div>
              <p className="text-[10px] font-mono font-bold text-accent uppercase tracking-wider mb-1">
                Assurance Battery Registry
              </p>
              <h2 className="text-sm font-bold text-1">What will run?</h2>
              <p className="text-xs text-3 leading-relaxed mt-1">
                PRAMAAN automatically selects the applicable checks based on the assets you provide.
              </p>
            </div>

            <div className="divide-y divide-[var(--border)] max-h-[520px] overflow-y-auto pr-1">
              {caps?.detectors.map(d => (
                <div key={d.detector_id} className="py-2.5 flex items-start gap-2.5">
                  <code className="text-[10px] font-mono font-bold text-accent px-1.5 py-0.5 rounded bg-[var(--accent-bg)] border border-accent/20 flex-shrink-0 mt-0.5">
                    {d.detector_id.replace(/^([a-z]{2})(\d{2})/i, '$1-$2').toUpperCase()}
                  </code>
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-semibold text-1 leading-snug">{d.name}</p>
                    <p className="text-[10px] text-3 line-clamp-1">{d.description}</p>
                  </div>
                </div>
              ))}
            </div>

            <div className="pt-2 text-[11px] text-3 border-t border-[var(--border)] flex items-center justify-between font-mono">
              <span>{caps?.detectors.length ?? 0} Detectors Online</span>
              <span className="text-[var(--green)] font-semibold">100% Offline</span>
            </div>
          </aside>
        </div>
      </form>
    </div>
  );
}
