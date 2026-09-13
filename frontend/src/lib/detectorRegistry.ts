/**
 * Authoritative Detector Registry & Method Detail Specifications.
 *
 * All claims derive directly from the backend detector implementation and metadata.
 * Do NOT claim capabilities that the detector does not actually provide.
 */

import { Database, Cpu, GitBranch, ShieldCheck, HelpCircle, type LucideIcon } from 'lucide-react';
import type { DetectorCapabilitySchema } from '../types/api';

export interface DetectorDetailSpec {
  id: string;
  code: string;
  name: string;
  pillar: string;
  category: 'detector' | 'ledger';
  purpose: string;
  applicableAssetTypes: string[];
  accessRequirements: string;
  dependencies: string[];
  supportedFormats: string[];
  whatItAnalyzes: string;
  evidenceProduced: string[];
  confidenceSemantics: string;
  limitations: string[];
  status: 'AVAILABLE' | 'UNAVAILABLE';
  referenceMethod: string;
  version: string;
  icon: LucideIcon;
  color: string;
  bg: string;
  whatItChecks?: string;
  supportedInput?: string;
  statusBadge?: 'implemented' | 'limited' | 'not_applicable' | 'unavailable';
}

export const DETECTOR_SPECS: Record<string, DetectorDetailSpec> = {
  'DI-01': {
    id: 'data.integrity.di01_duplicates',
    code: 'DI-01',
    name: 'DI-01: Duplicate / Near-Duplicate Image Detector',
    pillar: 'Dataset Integrity',
    category: 'detector',
    purpose: 'Identifies byte-identical duplicate files and perceptual near-duplicate image flooding in training datasets.',
    applicableAssetTypes: ['dataset'],
    accessRequirements: 'Black-Box (raw image bytes)',
    dependencies: ['Pillow', 'imagehash', 'sqlite3'],
    supportedFormats: ['JPEG', 'PNG', 'WEBP'],
    whatItAnalyzes:
      'Scans dataset samples for exact byte collisions (SHA-256) and perceptual near-duplicates via DCT pHash Hamming distance clustering (Hamming <= 10). Identifies image truncation, decode errors, and format non-conformance.',
    evidenceProduced: [
      'EvidenceType.CLUSTER: Duplicate image cluster manifests with member counts',
      'Normalized Hamming distance metrics (0–64) and representative hash digests',
      'SHA-256 byte collision matching records',
      'Corrupt and unreadable image file list',
    ],
    confidenceSemantics:
      'Decoupled from risk (ADR-003): Exact byte duplicates yield HIGH confidence. Near-duplicates with Hamming <= 10 yield MODERATE confidence as candidate relationships. Insufficient samples (< 2) yield LOW confidence.',
    limitations: [
      'Pixel & perceptual space analysis only; does not infer high-level semantic equivalence.',
      'Does not claim duplicates are malicious or intentional poisoning without contextual corroboration.',
      'Does not execute foundation model embeddings or CLIP.',
    ],
    status: 'AVAILABLE',
    referenceMethod: 'ADR-004 (Pure deterministic execution); imagehash DCT perceptual hashing (Zauner, 2010)',
    version: '1.0.0',
    icon: Database,
    color: 'text-blue-500',
    bg: 'bg-blue-500/10 border-blue-500/20',
  },
  'DI-02': {
    id: 'data.integrity.di02_label_integrity',
    code: 'DI-02',
    name: 'DI-02: Label Integrity & Mislabelling Detector',
    pillar: 'Dataset Integrity',
    category: 'detector',
    purpose: 'Detects conflicting contradictory annotations across near-duplicates and statistical class centroid outliers.',
    applicableAssetTypes: ['dataset'],
    accessRequirements: 'Black-Box with Labels (sample images + class annotations)',
    dependencies: ['Pillow', 'imagehash', 'numpy', 'sqlite3'],
    supportedFormats: ['COCO JSON annotations', 'metadata.json / labels.json', 'Directory class mappings'],
    whatItAnalyzes:
      'Inspects labeled samples to detect contradictory class annotations across perceptual near-duplicates (Hamming <= 4) and statistical class centroid outliers (> 2.5 sigma) that are closer to an alternate class centroid (candidate label flip).',
    evidenceProduced: [
      'EvidenceType.CLUSTER: Conflicting duplicate sample pair records with divergent label assignments',
      'pHash Hamming distance between conflicting duplicates',
      'Class centroid distance metrics and nearest alternate class projections',
      'Candidate label flip recommendations',
    ],
    confidenceSemantics:
      'Conflicting identical/near-identical duplicates yield HIGH confidence. Statistical centroid outliers yield MODERATE confidence pending human verification.',
    limitations: [
      'Requires labeled dataset with at least 2 labeled samples.',
      'Statistical centroid distance is a heuristic and cannot prove definitive label error without ground-truth verification.',
      'Operates purely offline without external LLM/VLM label validators.',
    ],
    status: 'AVAILABLE',
    referenceMethod: 'ADR-003 (Risk/Confidence Decoupling); Perceptual hash space centroid clustering',
    version: '1.0.0',
    icon: Database,
    color: 'text-blue-500',
    bg: 'bg-blue-500/10 border-blue-500/20',
  },
  'DI-03': {
    id: 'data.integrity.di03_trigger_anomaly',
    code: 'DI-03',
    name: 'DI-03: Trigger & Pattern Anomaly Detector',
    pillar: 'Dataset Integrity',
    category: 'detector',
    purpose: 'Detects recurring localized spatial trigger patches and high-contrast corner artifacts indicative of backdoor injection.',
    applicableAssetTypes: ['dataset'],
    accessRequirements: 'Black-Box (sample images)',
    dependencies: ['Pillow', 'imagehash', 'numpy', 'sqlite3'],
    supportedFormats: ['JPEG', 'PNG', 'WEBP'],
    whatItAnalyzes:
      'Inspects localized image regions (four corners: top-left, top-right, bottom-left, bottom-right, plus center) across dataset samples to identify recurring identical/near-identical localized visual patches and artificial high-contrast spatial patterns indicative of backdoor trigger injection.',
    evidenceProduced: [
      'EvidenceType.CLUSTER: Recurring localized patch coordinates and sample bindings',
      'Localized patch dHash / variance metrics and occurrence counts',
      'Sample file paths exhibiting recurring trigger patterns',
    ],
    confidenceSemantics:
      'Recurring high-frequency patches across >= 3 distinct samples yield HIGH confidence. Moderate variance recurrences yield MODERATE confidence.',
    limitations: [
      'Detects visible localized spatial triggers (patches/watermarks).',
      'Does not detect full-canvas, invisible, or blended adversarial perturbations without localized footprints.',
      'Operates purely offline without model training.',
    ],
    status: 'AVAILABLE',
    referenceMethod: 'BadNets (Gu et al., 2017) localized spatial trigger threat model',
    version: '1.0.0',
    icon: Database,
    color: 'text-blue-500',
    bg: 'bg-blue-500/10 border-blue-500/20',
  },
  'DI-04': {
    id: 'data.integrity.di04_ood_distribution',
    code: 'DI-04',
    name: 'DI-04: Distribution & Out-of-Distribution (OOD) Detector',
    pillar: 'Dataset Integrity',
    category: 'detector',
    purpose: 'Identifies samples that deviate significantly from the baseline dataset feature distribution.',
    applicableAssetTypes: ['dataset'],
    accessRequirements: 'Black-Box (sample images)',
    dependencies: ['Pillow', 'numpy', 'sqlite3'],
    supportedFormats: ['JPEG', 'PNG', 'WEBP'],
    whatItAnalyzes:
      'Extracts 6D multivariate feature vectors (aspect ratio, normalized byte density, RGB channel means, luminance variance, spectral texture) and computes standardized multivariate distance (median / IQR z-scores) against the dataset baseline to detect samples significantly outside the dominant distribution.',
    evidenceProduced: [
      'EvidenceType.CLUSTER: Standardized multivariate distance scores (median/IQR)',
      'Per-dimension outlier score breakdown across geometry, color, and texture',
      'Identified anomalous sample paths and dimensional deviation',
      'Baseline distribution parameter estimates',
    ],
    confidenceSemantics:
      'Severe multi-dimensional outliers (> 4.0 IQR) yield HIGH confidence of distribution deviation. Single-dimension deviations yield MODERATE confidence.',
    limitations: [
      'Evaluates low-level photometric and geometric distributions; does not perform high-level semantic OOD classification.',
      'Requires a baseline of at least 5 samples in the dataset.',
      'Benign anomalies (unusual lighting, framing) may be flagged as outliers.',
    ],
    status: 'AVAILABLE',
    referenceMethod: 'Robust Multivariate Median Absolute Deviation (MAD / IQR outlier detection)',
    version: '1.0.0',
    icon: Database,
    color: 'text-blue-500',
    bg: 'bg-blue-500/10 border-blue-500/20',
  },
  'DI-05': {
    id: 'data.integrity.di05_contributor_risk',
    code: 'DI-05',
    name: 'DI-05: Contributor & Source Risk Aggregation',
    pillar: 'Dataset Integrity',
    category: 'detector',
    purpose: 'Aggregates multi-detector findings by data contributor or source to identify concentrated defect hot-spots.',
    applicableAssetTypes: ['dataset'],
    accessRequirements: 'Black-Box with Attribution (sample metadata, user_id, or source directories)',
    dependencies: ['sqlite3'],
    supportedFormats: ['COCO user/contributor fields', 'Directory-based source grouping', 'metadata.json attribution'],
    whatItAnalyzes:
      'Aggregates findings from all data integrity detectors (DI-01 through DI-04) by contributor or source group to compute per-contributor defect rates and identify sources with disproportionately high defect concentration.',
    evidenceProduced: [
      'EvidenceType.CLUSTER: Per-contributor defect rate and volume comparison',
      'Disproportionate defect concentration alerts (defect rate >= 30% and count >= 2)',
      'Multi-contributor risk breakdown summary matrix',
    ],
    confidenceSemantics:
      'Concentrated defect patterns with high sample volume yield HIGH confidence. Small sample counts yield MODERATE or LOW confidence.',
    limitations: [
      'Requires contributor or source attribution metadata. When absent, detector reports an explicit coverage gap (SKIPPED).',
      'Statistical concentration indicates pipeline degradation or source risk, not definitive proof of malicious intent.',
    ],
    status: 'AVAILABLE',
    referenceMethod: 'ADR-003; Cross-detector statistical defect attribution',
    version: '1.0.0',
    icon: Database,
    color: 'text-blue-500',
    bg: 'bg-blue-500/10 border-blue-500/20',
  },
  'MI-01': {
    id: 'model.integrity.mi01_fingerprint',
    code: 'MI-01',
    name: 'MI-01: Model Integrity Fingerprinting and Comparison',
    pillar: 'Model Integrity',
    category: 'detector',
    purpose: 'Produces multi-layer structural AST and weight fingerprints and compares against reference baselines.',
    applicableAssetTypes: ['model'],
    accessRequirements: 'White-Box (serialized model artifact)',
    dependencies: ['onnx', 'onnxruntime', 'torch', 'sqlite3'],
    supportedFormats: ['.onnx', '.pt', '.pth', '.ts'],
    whatItAnalyzes:
      'Multi-layer structural AST and weight fingerprinting: Layer 1 (raw byte SHA-256, size, timestamp), Layer 2 (graph topology, node counts, operator inventory, I/O tensor schemas), Layer 3 (deterministic reference-input behavioral battery on ONNX: zeros, ones, seeded noise), Layer 4 (reference baseline comparison).',
    evidenceProduced: [
      'Structural topology digest and operator frequency table',
      'Input/output tensor shape, name, and dtype compliance records',
      'Deterministic output deviation statistics (mean, std, min, max, hash)',
      'Reference baseline delta finding (observed vs expected)',
    ],
    confidenceSemantics:
      'Exact cryptographic and structural matches yield HIGH confidence. Behavioral execution differences yield HIGH confidence. Unexecutable state dicts yield LOW confidence for execution layers.',
    limitations: [
      'Behavioral battery requires executable computational graph (ONNX / TorchScript).',
      'PyTorch state dicts lacking architecture definitions cannot execute behavioral probes and report a coverage gap for Layer 3.',
    ],
    status: 'AVAILABLE',
    referenceMethod: 'ADR-004; Multi-layer cryptographic model fingerprinting',
    version: '1.0.0',
    icon: Cpu,
    color: 'text-purple-500',
    bg: 'bg-purple-500/10 border-purple-500/20',
  },
  'MI-02': {
    id: 'model.integrity.mi02_parameter_stats',
    code: 'MI-02',
    name: 'MI-02: Model Parameter Statistics Detector',
    pillar: 'Model Integrity',
    category: 'detector',
    purpose: 'Inspects weight tensor distributions, moments, sparsity, and detects non-finite IEEE-754 numbers.',
    applicableAssetTypes: ['model'],
    accessRequirements: 'White-Box (model parameter weights / tensors)',
    dependencies: ['onnx', 'onnxruntime', 'torch', 'numpy'],
    supportedFormats: ['.onnx', '.pt', '.pth', '.ts'],
    whatItAnalyzes:
      'Performs deep inspection of model parameter tensors: total parameter count, tensor count, dtype distribution, weight moments (min, max, mean, std), layer sparsity (% zeros), non-finite IEEE-754 values (NaN, +Inf, -Inf), extreme weight anomalies (|w| > 10,000), and abnormal layer collapse.',
    evidenceProduced: [
      'Global parameter count and tensor dtype distribution',
      'Weight moments (min, max, mean, std) and sparsity ratio per tensor',
      'Non-finite parameter alerts (NaN / Inf counter per tensor)',
      'Extreme weight magnitude outlier warnings (|w| > 1e4)',
    ],
    confidenceSemantics:
      'Direct numerical inspection of IEEE-754 weights yields HIGH confidence. Non-finite values or extreme magnitude anomalies yield HIGH risk.',
    limitations: [
      'Requires deserializable parameter tensors (uses safe deserialization weights_only=True).',
      'Calculates numerical statistics; does not infer functional semantics of individual weight matrices.',
    ],
    status: 'AVAILABLE',
    referenceMethod: 'ADR-003; IEEE-754 floating point validity & parameter distribution analysis',
    version: '1.0.0',
    icon: Cpu,
    color: 'text-purple-500',
    bg: 'bg-purple-500/10 border-purple-500/20',
  },
  'MI-03': {
    id: 'model.integrity.mi03_activation_stats',
    code: 'MI-03',
    name: 'MI-03: Model Activation & Representation Statistics',
    pillar: 'Model Integrity',
    category: 'detector',
    purpose: 'Profiles internal intermediate layer activations for dead representation syndrome, saturation, and overflow.',
    applicableAssetTypes: ['model'],
    accessRequirements: 'White-Box Executable (computational graph with forward pass capability)',
    dependencies: ['onnxruntime', 'torch', 'numpy'],
    supportedFormats: ['.onnx', '.ts'],
    whatItAnalyzes:
      'Executes calibrated deterministic probe inputs (zeros, ones, gradient, seeded noise) to capture intermediate and output layer activation statistics. Identifies dead representation syndrome (> 98% zero activations across non-zero probes), numerical instability (NaN/Inf in forward pass), and severe activation saturation.',
    evidenceProduced: [
      'Monitored layer activation summary metrics (mean, std, min, max)',
      'Dead activation ratio per layer across non-zero probes',
      'Numerical instability alerts (NaN / Inf forward pass outputs)',
      'Layer saturation and clipping diagnostics',
    ],
    confidenceSemantics:
      'Direct forward execution on calibrated inputs yields HIGH confidence. Unexecutable model formats report explicit UNAVAILABLE coverage gap with LOW confidence.',
    limitations: [
      'Requires executable computational graph; cannot run on standalone weight state dicts.',
      'Monitors initial bounded layers to prevent memory exhaustion on large architectures.',
    ],
    status: 'AVAILABLE',
    referenceMethod: 'ADR-004; Intermediate representation activation profiling',
    version: '1.0.0',
    icon: Cpu,
    color: 'text-purple-500',
    bg: 'bg-purple-500/10 border-purple-500/20',
  },
  'MI-04': {
    id: 'model.integrity.mi04_reference_comparison',
    code: 'MI-04',
    name: 'MI-04: Reference Model Comparison Battery',
    pillar: 'Model Integrity',
    category: 'detector',
    purpose: 'Performs multi-layer differential comparative analysis between candidate and authorized baseline reference models.',
    applicableAssetTypes: ['model'],
    accessRequirements: 'White-Box Comparative (candidate model + authorized reference model/profile)',
    dependencies: ['onnx', 'onnxruntime', 'torch', 'numpy'],
    supportedFormats: ['.onnx', '.pt', '.pth', '.ts'],
    whatItAnalyzes:
      'Performs multi-layer comparative assurance between a candidate model and an authorized baseline reference: Layer 1 (cryptographic SHA-256 match), Layer 2 (graph topology and I/O schema compatibility), Layer 3 (parameter statistical delta and weight distance), Layer 4 (behavioral divergence across deterministic probe battery: MSE, Max Diff, Cosine Similarity).',
    evidenceProduced: [
      'Cryptographic match verification (exact SHA-256 identity)',
      'Structural schema and topology delta report',
      'Behavioral divergence metrics (MSE, Max Absolute Difference, Cosine Similarity)',
      'Substitution and format mismatch classifications',
    ],
    confidenceSemantics:
      'Comparative checks against an authorized reference yield HIGH confidence. If no reference is supplied, detector emits a clear coverage gap (UNAVAILABLE).',
    limitations: [
      'Requires an authorized reference model file or stored baseline profile.',
      'Cannot verify authenticity if the provided reference itself is untrusted or unauthenticated.',
    ],
    status: 'AVAILABLE',
    referenceMethod: 'ADR-003; Differential behavioral & structural comparison',
    version: '1.0.0',
    icon: Cpu,
    color: 'text-purple-500',
    bg: 'bg-purple-500/10 border-purple-500/20',
  },
  'MI-05': {
    id: 'model.integrity.mi05_trigger_anomaly',
    code: 'MI-05',
    name: 'MI-05: Model Trigger & Behavioral Perturbation Search',
    pillar: 'Model Integrity',
    category: 'detector',
    purpose: 'Tests candidate spatial perturbations to evaluate whether they cause Trojan shortcut target mode convergence.',
    applicableAssetTypes: ['model'],
    accessRequirements: 'White-Box Executable (computational graph with forward pass capability)',
    dependencies: ['onnxruntime', 'torch', 'numpy'],
    supportedFormats: ['.onnx', '.ts'],
    whatItAnalyzes:
      'Evaluates model sensitivity to localized spatial trigger perturbations across diverse clean probe inputs. Tests candidate localized perturbations (top-left patch, bottom-right patch, center mark, uniform bias control) and calculates output shift and Target Mode Convergence Ratio (CR = PairwiseDiversity(perturbed) / PairwiseDiversity(clean)) to detect Trojan backdoor shortcuts.',
    evidenceProduced: [
      'Candidate perturbation evaluations (shift magnitude, output diversity)',
      'Target mode convergence ratio metrics (CR < 0.15 threshold)',
      'Flagged suspicious trigger patch coordinates and patterns',
      'Baseline clean pairwise diversity benchmarks',
    ],
    confidenceSemantics:
      'Convergence ratio CR < 0.15 with elevated output shift yields HIGH risk and HIGH confidence of Trojan shortcut behavior. Normal smooth perturbation responses yield NONE risk with HIGH confidence.',
    limitations: [
      'Tests concrete candidate localized spatial patch hypotheses.',
      'Does NOT guarantee detection of complex blended, invisible, or semantic triggers without access to the original training distribution.',
    ],
    status: 'AVAILABLE',
    referenceMethod: 'Neural Cleanse (Wang et al., 2019) target convergence principles adapted for deterministic offline probe evaluation',
    version: '1.0.0',
    icon: Cpu,
    color: 'text-purple-500',
    bg: 'bg-purple-500/10 border-purple-500/20',
  },
  'PI-01': {
    id: 'inference.provenance.pi01_integrity',
    code: 'PI-01',
    name: 'PI-01: Inference Provenance Integrity Detector',
    pillar: 'Inference Provenance',
    category: 'detector',
    purpose: 'Verifies RFC 8032 Ed25519 digital signatures and cryptographic SHA-256 bindings across input, model, and output assets.',
    applicableAssetTypes: ['manifest', 'inference_bundle'],
    accessRequirements: 'Black-Box (signed provenance manifest + cryptographic public key)',
    dependencies: ['cryptography (Ed25519)', 'hashlib (SHA-256)', 'sqlite3'],
    supportedFormats: ['provenance_manifest.json (RFC 8032 Ed25519 signature)', 'Raw input/model/output asset bytes'],
    whatItAnalyzes:
      'Verifies the cryptographic authenticity and integrity of inference execution: validates RFC 8032 Ed25519 digital signature over canonical manifest, validates cryptographic SHA-256 byte bindings for input data, model weights, and inference outputs, and inspects sequence numbers and nonces for replay attacks.',
    evidenceProduced: [
      'Ed25519 cryptographic signature verification result',
      'Input, model, and output SHA-256 binding match statements',
      'Manifest schema and timestamp replay / sequence verification',
      'Missing or tampered asset reference alerts',
    ],
    confidenceSemantics:
      'Cryptographic signature validation and SHA-256 matching are mathematical certainties yielding HIGH confidence. Missing binding files yield MODERATE confidence with an explicit coverage gap.',
    limitations: [
      'Validates post-training inference transmission and execution binding.',
      'Does not authenticate the training pipeline if the manifest was signed dishonestly by an authorized key holder.',
    ],
    status: 'AVAILABLE',
    referenceMethod: 'RFC 8032 (Ed25519 Edwards-curve Digital Signature Algorithm); ADR-003',
    version: '1.0.0',
    icon: GitBranch,
    color: 'text-amber-500',
    bg: 'bg-amber-500/10 border-amber-500/20',
  },
  'AT-01': {
    id: 'audit.trail.at01_hash_chain',
    code: 'AT-01',
    name: 'AT-01: Tamper-Evident Append-Only Audit Trail Ledger',
    pillar: 'Audit Trail Ledger',
    category: 'ledger',
    purpose: 'Guarantees the immutability of assessment records and events via sequential SHA-256 hash chains back to the genesis block.',
    applicableAssetTypes: ['assessment_event_stream'],
    accessRequirements: 'System Internal (immutable SQLite audit ledger)',
    dependencies: ['sqlite3', 'hashlib (SHA-256)'],
    supportedFormats: ['Cryptographic block stream', 'JSON audit export verification'],
    whatItAnalyzes:
      'Cryptographic append-only hash chain linking all assessment events, findings, and evidence sequentially back to the genesis block. Guarantees event immutability across the audit lifecycle and verifies integrity upon access.',
    evidenceProduced: [
      'Sequential block hash links (current_hash and previous_hash)',
      'Chain verification result (valid vs broken linkage)',
      'Tamper and event break point localization',
      'Exportable verification payload for third-party auditing',
    ],
    confidenceSemantics:
      'Mathematical certainty: Any alteration of past event records, findings, or sequence causes immediate hash mismatch at the modified block.',
    limitations: [
      'Tamper-evident ledger detects and pinpoints modification/deletion.',
      'Relies on local node SQLite storage and requires external hash chain export for cross-node multi-party verification.',
    ],
    status: 'AVAILABLE',
    referenceMethod: 'ADR-002 (Append-Only Audit Ledger); Cryptographic Merkle/Hash-Chain Verification',
    version: '1.0.0',
    icon: ShieldCheck,
    color: 'text-emerald-500',
    bg: 'bg-emerald-500/10 border-emerald-500/20',
  },
};

/**
 * Normalizes an arbitrary detector ID or code into canonical key ('DI-01'..'DI-05', 'MI-01'..'MI-05', 'PI-01', 'AT-01').
 */
export function normalizeDetectorCode(idOrCode: string): string {
  if (!idOrCode) return '';
  const trimmed = idOrCode.trim();
  const upper = trimmed.toUpperCase();

  // Exact matches
  if (DETECTOR_SPECS[upper]) return upper;

  const lower = trimmed.toLowerCase();
  if (lower.includes('di01') || lower.includes('di-01') || lower.includes('duplicates')) return 'DI-01';
  if (lower.includes('di02') || lower.includes('di-02') || lower.includes('label')) return 'DI-02';
  if (lower.includes('di03') || lower.includes('di-03') || lower.includes('trigger_anomaly')) return 'DI-03';
  if (lower.includes('di04') || lower.includes('di-04') || lower.includes('distribution') || lower.includes('ood')) return 'DI-04';
  if (lower.includes('di05') || lower.includes('di-05') || lower.includes('contributor')) return 'DI-05';

  if (lower.includes('mi01') || lower.includes('mi-01') || lower.includes('fingerprint')) return 'MI-01';
  if (lower.includes('mi02') || lower.includes('mi-02') || lower.includes('parameter')) return 'MI-02';
  if (lower.includes('mi03') || lower.includes('mi-03') || lower.includes('activation')) return 'MI-03';
  if (lower.includes('mi04') || lower.includes('mi-04') || lower.includes('reference')) return 'MI-04';
  if (lower.includes('mi05') || lower.includes('mi-05') || lower.includes('trigger')) return 'MI-05';

  if (lower.includes('pi01') || lower.includes('pi-01') || lower.includes('provenance')) return 'PI-01';
  if (lower.includes('at01') || lower.includes('at-01') || lower.includes('audit')) return 'AT-01';

  // Generic 2-letter 2-digit format (e.g. AB-01)
  const match = trimmed.match(/([a-z]{2})[-_]?(\d{2})/i);
  if (match) {
    const candidate = `${match[1].toUpperCase()}-${match[2]}`;
    if (DETECTOR_SPECS[candidate]) return candidate;
  }

  return upper;
}

/**
 * Retrieves the comprehensive detector method specification, merging live capability availability
 * while gracefully handling unknown/missing detectors without crashing.
 */
export function getDetectorDetail(
  idOrCode: string,
  liveCap?: DetectorCapabilitySchema | null
): DetectorDetailSpec {
  const code = normalizeDetectorCode(idOrCode);
  const spec = DETECTOR_SPECS[code];

  if (!spec) {
    // Graceful fallback for unregistered or unknown detectors
    const isAvailable = liveCap?.available ?? false;
    return {
      id: liveCap?.detector_id || idOrCode,
      code: code || idOrCode.toUpperCase() || 'UNKNOWN',
      name: liveCap?.name || `Unregistered Detector (${idOrCode})`,
      pillar: liveCap?.pillar || 'Unknown Assurance Layer',
      category: 'detector',
      purpose: liveCap?.description || 'No registered detector specification exists in the PRAMAAN catalog.',
      applicableAssetTypes: liveCap?.applicable_asset_types || ['unknown'],
      accessRequirements: liveCap?.access_requirements || 'Not Specified',
      dependencies: liveCap?.dependencies || ['Not specified'],
      supportedFormats: liveCap?.supported_formats || ['Not specified'],
      whatItAnalyzes: liveCap?.what_it_analyzes || 'No analysis details available for this unregistered detector.',
      evidenceProduced: liveCap?.evidence_produced || ['No evidence specification'],
      confidenceSemantics: liveCap?.confidence_semantics || 'Confidence semantics not specified.',
      limitations: liveCap?.limitations || ['Detector is not officially registered in this PRAMAAN environment.'],
      status: isAvailable ? 'AVAILABLE' : 'UNAVAILABLE',
      statusBadge: isAvailable ? 'implemented' : 'unavailable',
      whatItChecks: liveCap?.what_it_analyzes || 'No analysis details available for this unregistered detector.',
      supportedInput: 'Standard Format',
      referenceMethod: liveCap?.reference_method || 'Unregistered',
      version: liveCap?.version || '0.0.0',
      icon: HelpCircle,
      color: 'text-gray-400',
      bg: 'bg-gray-500/10 border-gray-500/20',
    };
  }

  // If liveCap provides runtime availability or backend overrides, merge them cleanly
  const isAvailable = liveCap ? liveCap.available : spec.status === 'AVAILABLE';
  const whatItAnalyzes = liveCap?.what_it_analyzes || spec.whatItAnalyzes;
  const accessReq = liveCap?.access_requirements || spec.accessRequirements;
  const formats = (liveCap?.supported_formats && liveCap.supported_formats.length > 0)
    ? liveCap.supported_formats
    : spec.supportedFormats;

  return {
    ...spec,
    status: isAvailable ? 'AVAILABLE' : 'UNAVAILABLE',
    statusBadge: isAvailable ? 'implemented' : 'unavailable',
    whatItAnalyzes,
    whatItChecks: whatItAnalyzes,
    supportedInput: `${accessReq} · ${formats.join(', ')}`,
    confidenceSemantics: liveCap?.confidence_semantics || spec.confidenceSemantics,
    limitations: (liveCap?.limitations && liveCap.limitations.length > 0) ? liveCap.limitations : spec.limitations,
    referenceMethod: liveCap?.reference_method || spec.referenceMethod,
    accessRequirements: accessReq,
    dependencies: (liveCap?.dependencies && liveCap.dependencies.length > 0) ? liveCap.dependencies : spec.dependencies,
    supportedFormats: formats,
    evidenceProduced: (liveCap?.evidence_produced && liveCap.evidence_produced.length > 0) ? liveCap.evidence_produced : spec.evidenceProduced,
  };
}
