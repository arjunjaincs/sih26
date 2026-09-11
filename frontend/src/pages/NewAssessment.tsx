import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Play, ChevronDown, ChevronRight, Info } from 'lucide-react';
import { createAssessment, getCapabilities, NetworkError } from '../api/client';
import type { CapabilitiesResponse, AssessmentResultSchema } from '../types/api';
import { Panel } from '../components/Panel';
import { Button } from '../components/Button';
import { ErrorState } from '../components/ErrorState';
import { cn } from '../lib/cn';

type Stage = 'form' | 'submitting' | 'error';

const DATASET_FORMATS = [
  { value: 'image_dir', label: 'Image Directory' },
  { value: 'coco_json', label: 'COCO JSON' },
];

interface FormState {
  title: string;
  datasetPath: string;
  datasetFormat: string;
  modelPath: string;
  phashThreshold: number;
  dhashThreshold: number;
  minClusterSize: number;
}

const INITIAL_FORM: FormState = {
  title: '',
  datasetPath: '',
  datasetFormat: 'image_dir',
  modelPath: '',
  phashThreshold: 10,
  dhashThreshold: 10,
  minClusterSize: 2,
};

function InputField({
  label, id, value, onChange, placeholder, required, helpText, type = 'text',
}: {
  label: string; id: string; value: string | number; onChange: (v: string) => void;
  placeholder?: string; required?: boolean; helpText?: string; type?: string;
}) {
  return (
    <div>
      <label htmlFor={id} className="block text-xs font-semibold text-[var(--text-secondary)] mb-1">
        {label}{required && <span className="text-[var(--risk-critical)] ml-0.5">*</span>}
      </label>
      <input
        id={id}
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        required={required}
        className={cn(
          'w-full rounded border border-[var(--border)] bg-[var(--surface-0)]',
          'px-3 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)]',
          'focus:outline-none focus:border-[var(--accent)] focus:ring-1 focus:ring-[var(--accent)]',
          'transition-colors duration-150',
        )}
      />
      {helpText && <p className="mt-1 text-[10px] text-[var(--text-muted)]">{helpText}</p>}
    </div>
  );
}

export function NewAssessment() {
  const navigate = useNavigate();
  const [stage, setStage] = useState<Stage>('form');
  const [form, setForm] = useState<FormState>(INITIAL_FORM);
  const [caps, setCaps] = useState<CapabilitiesResponse | null>(null);
  const [error, setError] = useState<{ message: string; isNetwork: boolean } | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [validationErrors, setValidationErrors] = useState<string[]>([]);

  useEffect(() => {
    getCapabilities().then(setCaps).catch(() => {});
  }, []);

  const update = (field: keyof FormState) => (value: string) => {
    setForm((f) => ({ ...f, [field]: field.includes('Threshold') || field === 'minClusterSize' ? Number(value) : value }));
  };

  const hasDataset = form.datasetPath.trim().length > 0;
  const hasModel = form.modelPath.trim().length > 0;
  const hasAsset = hasDataset || hasModel;

  function validate(): string[] {
    const errs: string[] = [];
    if (!form.title.trim()) errs.push('Assessment title is required.');
    if (!hasAsset) errs.push('At least one of Dataset Path or Model Path must be provided.');
    if (hasDataset && !form.datasetFormat) errs.push('Dataset format is required when dataset path is set.');
    return errs;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const errs = validate();
    if (errs.length > 0) { setValidationErrors(errs); return; }
    setValidationErrors([]);
    setStage('submitting');
    setError(null);

    try {
      const result: AssessmentResultSchema = await createAssessment({
        title: form.title.trim(),
        dataset_path: hasDataset ? form.datasetPath.trim() : null,
        dataset_format: hasDataset ? form.datasetFormat : null,
        model_path: hasModel ? form.modelPath.trim() : null,
        phash_threshold: form.phashThreshold,
        dhash_threshold: form.dhashThreshold,
        min_cluster_size: form.minClusterSize,
      });

      // Store result in sessionStorage for the result page
      sessionStorage.setItem('pramaan_last_assessment_id', result.assessment_id);
      navigate(`/assessments/${result.assessment_id}/result`, { state: { result } });
    } catch (err) {
      setStage('error');
      setError({
        message: err instanceof Error ? err.message : 'Assessment failed.',
        isNetwork: err instanceof NetworkError,
      });
    }
  }

  return (
    <div className="max-w-2xl mx-auto px-6 py-8 space-y-5">
      <div>
        <h1 className="text-xl font-bold text-[var(--text-primary)] tracking-tight">New Assessment</h1>
        <p className="mt-1 text-sm text-[var(--text-muted)]">
          Configure and run an integrity assurance assessment against local assets.
        </p>
      </div>

      {stage === 'submitting' && (
        <Panel title="Running Assessment">
          <div className="py-8 flex flex-col items-center gap-4 text-center">
            <div className="flex items-center gap-3">
              {['SUBMITTING', 'PROCESSING'].map((s, i) => (
                <div key={s} className="flex items-center gap-2">
                  {i > 0 && <div className="w-6 h-px bg-[var(--border)]" />}
                  <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-[var(--accent)] bg-[var(--accent-light)]">
                    <div className="w-1.5 h-1.5 rounded-full bg-[var(--accent)] animate-pulse" />
                    <span className="text-xs font-semibold text-[var(--accent)]">{s}</span>
                  </div>
                </div>
              ))}
            </div>
            <p className="text-sm text-[var(--text-secondary)]">
              PRAMAAN is running real analysis against your assets.
            </p>
            <p className="text-xs text-[var(--text-muted)]">
              This may take a moment depending on dataset and model size.
            </p>
          </div>
        </Panel>
      )}

      {stage === 'error' && error && (
        <Panel>
          <ErrorState
            title={error.isNetwork ? 'Backend Unavailable' : 'Assessment Failed'}
            message={error.message}
            isNetwork={error.isNetwork}
            onRetry={() => { setStage('form'); setError(null); }}
          />
        </Panel>
      )}

      {stage === 'form' && (
        <form onSubmit={handleSubmit} noValidate className="space-y-5">
          {/* Validation errors */}
          {validationErrors.length > 0 && (
            <div className="rounded-lg border border-[var(--risk-critical)] bg-[var(--risk-critical-bg)] p-3 space-y-1">
              {validationErrors.map((e, i) => (
                <p key={i} className="text-xs text-[var(--risk-critical)]">{e}</p>
              ))}
            </div>
          )}

          {/* Basic info */}
          <Panel title="Assessment Details">
            <InputField
              label="Title"
              id="title"
              value={form.title}
              onChange={update('title')}
              placeholder="e.g. Pedestrian Detection Dataset Audit Q3-2026"
              required
            />
          </Panel>

          {/* Dataset */}
          <Panel title="Dataset" description="Optional — required for Data Integrity (DI-01) analysis">
            <div className="space-y-4">
              <InputField
                label="Dataset Path"
                id="dataset_path"
                value={form.datasetPath}
                onChange={update('datasetPath')}
                placeholder="C:\absolute\path\to\dataset"
                helpText="Absolute path to an image directory or COCO JSON file. Must exist on this machine."
              />
              {hasDataset && (
                <div>
                  <label htmlFor="dataset_format" className="block text-xs font-semibold text-[var(--text-secondary)] mb-1">
                    Dataset Format<span className="text-[var(--risk-critical)] ml-0.5">*</span>
                  </label>
                  <select
                    id="dataset_format"
                    value={form.datasetFormat}
                    onChange={(e) => setForm((f) => ({ ...f, datasetFormat: e.target.value }))}
                    className={cn(
                      'w-full rounded border border-[var(--border)] bg-[var(--surface-0)]',
                      'px-3 py-2 text-sm text-[var(--text-primary)]',
                      'focus:outline-none focus:border-[var(--accent)] focus:ring-1 focus:ring-[var(--accent)]',
                    )}
                  >
                    {DATASET_FORMATS.map((f) => (
                      <option key={f.value} value={f.value}>{f.label}</option>
                    ))}
                  </select>
                </div>
              )}
            </div>
          </Panel>

          {/* Model */}
          <Panel title="Model" description="Optional — required for Model Integrity (MI-01) analysis">
            <InputField
              label="Model Path"
              id="model_path"
              value={form.modelPath}
              onChange={update('modelPath')}
              placeholder="C:\absolute\path\to\model.onnx"
              helpText="Absolute path to a .onnx, .pt, or .pth model file."
            />
          </Panel>

          {/* Available detectors for context */}
          {caps && (
            <div className="flex flex-wrap gap-2 px-1">
              {caps.detectors.map((d) => (
                <div
                  key={d.detector_id}
                  className="flex items-center gap-1.5 text-[10px] px-2 py-1 rounded bg-[var(--surface-1)] border border-[var(--border)] text-[var(--text-muted)]"
                >
                  <div className={`w-1.5 h-1.5 rounded-full ${d.available ? 'bg-[var(--risk-none)]' : 'bg-[var(--border)]'}`} />
                  {d.detector_id} · {d.available ? 'available' : 'unavailable'}
                </div>
              ))}
            </div>
          )}

          {/* Advanced */}
          <div>
            <button
              type="button"
              onClick={() => setShowAdvanced((s) => !s)}
              className="flex items-center gap-1.5 text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
            >
              {showAdvanced ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
              Advanced detector settings
            </button>
            {showAdvanced && (
              <Panel className="mt-2">
                <div className="grid grid-cols-3 gap-4">
                  <InputField
                    label="pHash Threshold"
                    id="phash_threshold"
                    type="number"
                    value={form.phashThreshold}
                    onChange={update('phashThreshold')}
                    helpText="0–64, default 10"
                  />
                  <InputField
                    label="dHash Threshold"
                    id="dhash_threshold"
                    type="number"
                    value={form.dhashThreshold}
                    onChange={update('dhashThreshold')}
                    helpText="0–64, default 10"
                  />
                  <InputField
                    label="Min Cluster Size"
                    id="min_cluster_size"
                    type="number"
                    value={form.minClusterSize}
                    onChange={update('minClusterSize')}
                    helpText="≥2, default 2"
                  />
                </div>
              </Panel>
            )}
          </div>

          {/* Summary before submit */}
          {hasAsset && form.title.trim() && (
            <Panel className="border-[var(--accent)]">
              <div className="flex items-start gap-2">
                <Info className="w-4 h-4 text-[var(--accent)] flex-shrink-0 mt-0.5" />
                <div className="text-xs text-[var(--text-secondary)] space-y-0.5">
                  <p className="font-semibold text-[var(--text-primary)]">Ready to run:</p>
                  <p>Title: <span className="font-medium">{form.title}</span></p>
                  {hasDataset && <p>Dataset: <span className="font-mono text-[10px]">{form.datasetPath}</span> ({form.datasetFormat})</p>}
                  {hasModel && <p>Model: <span className="font-mono text-[10px]">{form.modelPath}</span></p>}
                </div>
              </div>
            </Panel>
          )}

          <div className="flex justify-end gap-3">
            <Button
              type="button"
              variant="secondary"
              onClick={() => { setForm(INITIAL_FORM); setValidationErrors([]); }}
            >
              Reset
            </Button>
            <Button
              type="submit"
              leftIcon={<Play className="w-4 h-4" />}
              disabled={!form.title.trim() || !hasAsset}
            >
              Run Assurance Assessment
            </Button>
          </div>
        </form>
      )}
    </div>
  );
}
