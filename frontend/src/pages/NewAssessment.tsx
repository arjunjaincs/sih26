import { useEffect, useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, X } from 'lucide-react';
import { createAssessment, getCapabilities } from '../api/client';
import type { CapabilitiesResponse, AssessmentResultSchema, DetectorCapabilitySchema, UploadResponse, AssessmentCreateRequest } from '../types/api';
import { FileUpload } from '../components/FileUpload';
import { cn } from '../lib/cn';

type Stage = 'form' | 'running' | 'error';

const PIPELINE_STEPS = [
  'Validating input files',
  'Ingesting assets',
  'Running detectors',
  'Collecting evidence',
  'Generating report',
];

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
      <label htmlFor={id} className="label">
        {label}
        {required && <span className="text-[var(--red)] ml-0.5">*</span>}
      </label>
      <div className="relative">
        <input
          id={id}
          type={type}
          value={value}
          onChange={e => onChange(e.target.value)}
          placeholder={placeholder}
          required={required}
          className={cn(
            'w-full h-9 px-3 rounded border border-[var(--border)] bg-surface text-1',
            'text-sm placeholder:text-4',
            'focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30',
            'transition-colors duration-150',
            onClear && value && 'pr-8',
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
      {helpText && <p className="text-[11px] text-3">{helpText}</p>}
    </div>
  );
}

function Select({ label, id, value, onChange, options }: {
  label: string; id: string; value: string; onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="label">{label}</label>
      <select
        id={id}
        value={value}
        onChange={e => onChange(e.target.value)}
        className={cn(
          'w-full h-9 px-3 rounded border border-[var(--border)] bg-surface text-1 text-sm',
          'focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30',
          'transition-colors duration-150',
        )}
      >
        <option value="">Select…</option>
        {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </div>
  );
}

function getShortDetectorId(id: string): string {
  const lower = id.toLowerCase();
  if (lower.includes('di01') || id === 'DI-01') return 'DI-01';
  if (lower.includes('mi01') || id === 'MI-01') return 'MI-01';
  if (lower.includes('pi01') || id === 'PI-01') return 'PI-01';
  if (lower.includes('at01') || id === 'AT-01') return 'AT-01';
  const match = id.match(/([a-z]{2})[-_]?(\d{2})/i);
  if (match) return `${match[1].toUpperCase()}-${match[2]}`;
  const parts = id.split('.');
  const lastPart = parts[parts.length - 1];
  return lastPart.length <= 6 ? lastPart.toUpperCase() : lastPart.slice(0, 5).toUpperCase();
}

function DetectorRow({ d }: { d: DetectorCapabilitySchema }) {
  const shortId = getShortDetectorId(d.detector_id);
  const displayName = d.name.replace(new RegExp(`^${shortId}:?\\s*`, 'i'), '');

  return (
    <div className="flex items-center justify-between py-2 border-b border-[var(--border)] last:border-0 gap-2">
      <div className="flex items-center gap-2 min-w-0 flex-1">
        <code className="text-[10px] font-mono font-semibold text-accent px-1.5 py-0.5 rounded bg-accent/10 flex-shrink-0 tracking-wider">
          {shortId}
        </code>
        <span className="text-xs text-2 truncate" title={d.name}>
          {displayName}
        </span>
        <span className="text-[10px] text-3 flex-shrink-0">(optional)</span>
      </div>
      <div
        className={cn(
          'flex-shrink-0 w-1.5 h-1.5 rounded-full',
          d.available ? 'bg-[var(--green)]' : 'bg-[var(--border-strong)]',
        )}
        title={d.available ? 'Available' : 'Unavailable'}
      />
    </div>
  );
}

function ModeSelector({
  mode,
  onChange,
}: {
  mode: 'upload' | 'local';
  onChange: (m: 'upload' | 'local') => void;
}) {
  return (
    <div className="inline-flex items-center rounded-md border border-[var(--border)] bg-surface-2 p-0.5 text-xs">
      <button
        type="button"
        onClick={() => onChange('upload')}
        className={cn(
          'px-2.5 py-1 rounded font-medium transition-colors text-[11px]',
          mode === 'upload'
            ? 'bg-surface text-1 shadow-sm'
            : 'text-3 hover:text-2',
        )}
      >
        Upload File
      </button>
      <button
        type="button"
        onClick={() => onChange('local')}
        className={cn(
          'px-2.5 py-1 rounded font-medium transition-colors text-[11px]',
          mode === 'local'
            ? 'bg-surface text-1 shadow-sm'
            : 'text-3 hover:text-2',
        )}
      >
        Local Path (Advanced)
      </button>
    </div>
  );
}

export function NewAssessment() {
  const navigate = useNavigate();
  const [stage, setStage] = useState<Stage>('form');
  const [title, setTitle] = useState('');

  // Model input states
  const [modelMode, setModelMode] = useState<'upload' | 'local'>('upload');
  const [uploadedModel, setUploadedModel] = useState<UploadResponse | null>(null);
  const [modelPath, setModelPath] = useState('');

  // Dataset input states
  const [datasetMode, setDatasetMode] = useState<'upload' | 'local'>('upload');
  const [uploadedDataset, setUploadedDataset] = useState<UploadResponse | null>(null);
  const [datasetPath, setDatasetPath] = useState('');
  const [datasetFormat, setDatasetFormat] = useState('image_dir');

  const [provenancePath, setProvenancePath] = useState('');
  const [caps, setCaps] = useState<CapabilitiesResponse | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [errorMsg, setErrorMsg] = useState('');
  const [pipelineStep, setPipelineStep] = useState(0);
  const pipelineRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    getCapabilities().then(setCaps).catch(() => {});
  }, []);

  function validate() {
    const e: string[] = [];
    if (!title.trim()) e.push('Assessment title is required.');

    const hasModel = modelMode === 'upload' ? !!uploadedModel : !!modelPath.trim();
    const hasDataset = datasetMode === 'upload' ? !!uploadedDataset : !!datasetPath.trim();

    if (!hasModel && !hasDataset && !provenancePath.trim()) {
      e.push('Provide at least one model or dataset asset.');
    }
    return e;
  }

  function startPipelineAnimation() {
    setPipelineStep(0);
    let step = 0;
    pipelineRef.current = setInterval(() => {
      step++;
      if (step < PIPELINE_STEPS.length - 1) {
        setPipelineStep(step);
      }
    }, 1800);
  }

  function stopPipeline() {
    if (pipelineRef.current) clearInterval(pipelineRef.current);
    setPipelineStep(PIPELINE_STEPS.length - 1);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const errs = validate();
    if (errs.length) { setErrors(errs); return; }
    setErrors([]);
    setStage('running');
    startPipelineAnimation();

    try {
      const payload: AssessmentCreateRequest = {
        title: title.trim(),
        model_asset_id: modelMode === 'upload' && uploadedModel ? uploadedModel.asset_id : null,
        model_path: modelMode === 'local' && modelPath.trim() ? modelPath.trim() : null,
        dataset_asset_id: datasetMode === 'upload' && uploadedDataset ? uploadedDataset.asset_id : null,
        dataset_path: datasetMode === 'local' && datasetPath.trim() ? datasetPath.trim() : null,
        dataset_format: datasetMode === 'upload' && uploadedDataset ? (uploadedDataset.format || null) : (datasetPath.trim() ? datasetFormat : null),
      };

      const result: AssessmentResultSchema = await createAssessment(payload);
      stopPipeline();
      sessionStorage.setItem('pramaan_last_assessment_id', result.assessment_id);
      navigate(`/assessments/${result.assessment_id}/result`, { state: { result } });
    } catch (err) {
      stopPipeline();
      setErrorMsg(err instanceof Error ? err.message : 'Assessment failed.');
      setStage('error');
    }
  }

  if (stage === 'running') {
    return (
      <div className="min-h-[calc(100vh-3rem)] flex flex-col items-center justify-center px-6">
        <div className="max-w-lg w-full space-y-8">
          <div>
            <p className="label text-accent mb-2">PRAMAAN · Running</p>
            <h1 className="text-2xl font-bold text-1">Running Assessment</h1>
            <p className="mt-1 text-sm text-3">
              PRAMAAN is analysing your assets. This may take a few moments.
            </p>
          </div>

          <div className="space-y-1">
            {PIPELINE_STEPS.map((step, i) => {
              const done = i < pipelineStep;
              const active = i === pipelineStep;
              return (
                <div key={step} className="flex items-center gap-3 py-2.5 border-b border-[var(--border)] last:border-0">
                  <div className={cn(
                    'flex-shrink-0 w-5 h-5 rounded-full flex items-center justify-center border',
                    done  ? 'bg-[var(--green)] border-[var(--green)]' :
                    active ? 'border-accent' :
                    'border-[var(--border)]',
                  )}>
                    {done ? (
                      <svg className="w-3 h-3 text-white" viewBox="0 0 12 12" fill="none">
                        <path d="M2 6l3 3 5-5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                      </svg>
                    ) : active ? (
                      <div className="w-2 h-2 rounded-full bg-accent animate-pulse" />
                    ) : null}
                  </div>
                  <span className="text-sm text-2 flex-1">{step}</span>
                  <span className={cn(
                    'text-xs',
                    done ? 'text-[var(--green)]' : active ? 'text-accent' : 'text-3',
                  )}>
                    {done ? 'Completed' : active ? 'in progress…' : 'Pending'}
                  </span>
                </div>
              );
            })}
          </div>

          <p className="text-xs text-3 italic text-center">"Evidence over assumptions."</p>
        </div>
      </div>
    );
  }

  if (stage === 'error') {
    return (
      <div className="min-h-[calc(100vh-3rem)] flex flex-col items-center justify-center px-6">
        <div className="max-w-md w-full text-center space-y-4">
          <div className="w-10 h-10 rounded-full bg-[var(--red-bg)] flex items-center justify-center mx-auto">
            <X className="w-5 h-5 text-[var(--red)]" />
          </div>
          <h2 className="text-lg font-semibold text-1">Assessment Failed</h2>
          <p className="text-sm text-3">{errorMsg}</p>
          {errorMsg.toLowerCase().includes('reach') || errorMsg.toLowerCase().includes('connect') ? (
            <p className="text-xs text-3">Start the local PRAMAAN service and try again.</p>
          ) : null}
          <button
            onClick={() => { setStage('form'); setErrorMsg(''); }}
            className="px-4 py-2 rounded border border-[var(--border)] text-sm text-1 hover:bg-surface-2 transition-colors"
          >
            Back to form
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-6 py-10">
      <div className="mb-6">
        <p className="label text-accent mb-1">PRAMAAN · Assessment</p>
        <h1 className="text-2xl font-bold text-1">New Assessment</h1>
        <p className="mt-1 text-sm text-3">
          Select the assets you want to assess. PRAMAAN will run the applicable integrity checks
          and generate a detailed report.
        </p>
      </div>

      <form onSubmit={handleSubmit} noValidate>
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-8">
          {/* Main form */}
          <div className="space-y-6">
            {/* Errors */}
            {errors.length > 0 && (
              <div className="p-3 rounded border border-[var(--red)]/30 bg-[var(--red-bg)] space-y-1">
                {errors.map((e, i) => <p key={i} className="text-xs text-[var(--red)]">{e}</p>)}
              </div>
            )}

            <Field
              label="Assessment Title"
              id="title"
              value={title}
              onChange={setTitle}
              placeholder="My Model Safety Check"
              required
              helpText="A descriptive name for this assessment."
            />

            {/* Model Section */}
            <div className="pt-1 space-y-3">
              <div className="flex items-center justify-between">
                <label className="label">Model File (ONNX / PyTorch)</label>
                <ModeSelector mode={modelMode} onChange={setModelMode} />
              </div>

              {modelMode === 'upload' ? (
                <FileUpload
                  id="model-upload"
                  assetType="model"
                  accept=".onnx,.pt,.pth"
                  value={uploadedModel}
                  onChange={setUploadedModel}
                  helpText="Supported formats: .onnx, .pt, .pth (Air-gapped safe staging & SHA-256 verified)"
                />
              ) : (
                <div>
                  <div className="relative">
                    <input
                      id="model_path"
                      type="text"
                      value={modelPath}
                      onChange={e => setModelPath(e.target.value)}
                      placeholder="e.g. C:/models/classifier.onnx"
                      className={cn(
                        'w-full h-9 px-3 pr-8 rounded border border-[var(--border)] bg-surface text-1 text-sm placeholder:text-4',
                        'focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30',
                        'transition-colors duration-150',
                      )}
                    />
                    {modelPath && (
                      <button type="button" onClick={() => setModelPath('')}
                        className="absolute right-2 top-1/2 -translate-y-1/2 text-3 hover:text-1">
                        <X className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>
                  <p className="mt-1 text-[11px] text-3">Absolute path to a .onnx or .pt/.pth model file on this machine.</p>
                </div>
              )}
            </div>

            {/* Dataset Section */}
            <div className="border-t border-[var(--border)] pt-5 space-y-3">
              <div className="flex items-center justify-between">
                <label className="label">Dataset (Images, Archive, or Manifest)</label>
                <ModeSelector mode={datasetMode} onChange={setDatasetMode} />
              </div>

              {datasetMode === 'upload' ? (
                <FileUpload
                  id="dataset-upload"
                  assetType="dataset"
                  accept=".zip,.json,.jpg,.jpeg,.png"
                  value={uploadedDataset}
                  onChange={setUploadedDataset}
                  helpText="Supported formats: .zip archive (extracted securely), .json (COCO manifest), or image files"
                />
              ) : (
                <div className="space-y-4">
                  <Field
                    label=""
                    id="dataset_path"
                    value={datasetPath}
                    onChange={setDatasetPath}
                    placeholder="e.g. C:/datasets/val2017 or C:/datasets/instances.json"
                    onClear={() => setDatasetPath('')}
                    helpText="Absolute directory path or manifest path on this machine."
                  />
                  {datasetPath && (
                    <Select
                      label="Format"
                      id="dataset_format"
                      value={datasetFormat}
                      onChange={setDatasetFormat}
                      options={[
                        { value: 'image_dir', label: 'Image Directory' },
                        { value: 'coco_json', label: 'COCO JSON' },
                      ]}
                    />
                  )}
                </div>
              )}
            </div>

            <div className="border-t border-[var(--border)] pt-5">
              <Field
                label="Provenance Manifest (JSON)"
                id="provenance"
                value={provenancePath}
                onChange={setProvenancePath}
                placeholder="Select provenance manifest (optional)"
                onClear={() => setProvenancePath('')}
              />
            </div>

            {/* CTA */}
            <div className="pt-2">
              <button
                type="submit"
                disabled={!title.trim()}
                className={cn(
                  'inline-flex items-center gap-2 px-6 py-2.5 rounded',
                  'bg-accent text-white text-sm font-semibold',
                  'hover:bg-[var(--accent-2)] transition-colors duration-150',
                  'active:scale-[0.97]',
                  'disabled:opacity-40 disabled:cursor-not-allowed',
                )}
              >
                Run Assessment
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Right: What will run */}
          <aside className="border border-[var(--border)] rounded-lg bg-surface p-5 h-fit space-y-4 lg:sticky lg:top-16">
            <div>
              <p className="label mb-1">What will run?</p>
              <p className="text-xs text-3 leading-relaxed">
                PRAMAAN automatically selects the applicable checks based on the assets you provide.
              </p>
            </div>

            <div className="divide-y divide-[var(--border)]">
              {caps?.detectors.map(d => (
                <DetectorRow key={d.detector_id} d={d} />
              )) ?? (
                <div className="space-y-2 py-1">
                  {['DI-01', 'MI-01', 'PI-01'].map(id => (
                    <div key={id} className="flex items-center gap-2 py-2 text-xs text-3">
                      <code className="text-[10px] font-mono font-semibold text-accent px-1.5 py-0.5 rounded bg-accent/10 flex-shrink-0 tracking-wider">{id}</code>
                      <span>–</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="pt-1 text-[11px] text-3 border-t border-[var(--border)]">
              <p className="font-medium text-2 mb-0.5">Not sure?</p>
              <p>PRAMAAN automatically detects which checks are applicable based on the assets you provide.</p>
            </div>
          </aside>
        </div>
      </form>
    </div>
  );
}
