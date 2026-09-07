import type { StageState } from '../types/dashboard'

export const MOCK_PIPELINE_STAGES: StageState[] = [
  {
    stage_id: 'stage_1',
    stage_number: '01',
    stage_name: 'Training Data',
    stage_subtitle: 'Distribution & Dataset Hygiene',
    risk: 'clean',
    confidence: 0.97,
    coverage_pct: 98.4,
    audit_hash: 'a7f920bc41d8e31a',
    summary: 'Spectral signature scan verified class-conditional features. Marginal dispersion anomaly in night-scene classes is within natural long-tail limits with no poisoning signature.',
    metrics: [
      { label: 'Samples Verified', value: '142,800' },
      { label: 'Class Parity', value: '0.992' },
      { label: 'Poisoning Index', value: '< 0.01' },
    ],
    findings: [
      {
        finding_id: 'F-TD-001',
        severity: 'low',
        detector: 'Spectral Signature Analysis',
        description:
          'Spectral signature scan of class-conditional feature representations identifies a marginal cluster dispersion anomaly in class-7 (night-scene) samples. Singular value decomposition of the activation covariance matrix shows no statistically significant separability (p=0.43) between clean and flagged samples. Consistent with natural long-tail capture conditions.',
        evidence_hash: '8f4a21e69b02',
        mitigated: true,
      },
    ],
  },
  {
    stage_id: 'stage_2',
    stage_number: '02',
    stage_name: 'Model',
    stage_subtitle: 'Weight Integrity & Backdoors',
    risk: 'clean',
    confidence: 0.94,
    coverage_pct: 100.0,
    audit_hash: 'f2c8109d73e2a4b1',
    summary: 'Neural Cleanse pattern inversion scanned 18 classification heads. Minimum trigger norm safely above anomaly threshold; zero backdoor trojans detected.',
    metrics: [
      { label: 'Trigger L1 Norm', value: '1.14 / 2.0 τ' },
      { label: 'Weight Checksum', value: 'MATCH' },
      { label: 'Layer Sparsity', value: '0.08%' },
    ],
    findings: [
      {
        finding_id: 'F-MD-001',
        severity: 'clean',
        detector: 'Neural Cleanse Inversion Scan',
        description:
          'Optimization-based trigger pattern inversion across all 18 output classes yields minimum L1 norm anomaly index of 1.14 (threshold τ=2.0). No candidate trigger pattern detected. Parameter hash matches certified gold-master weights.',
        evidence_hash: 'e3b8a1c904df',
        mitigated: true,
      },
    ],
  },
  {
    stage_id: 'stage_3',
    stage_number: '03',
    stage_name: 'Inference',
    stage_subtitle: 'Runtime Telemetry & Perturbations',
    risk: 'clean',
    confidence: 0.91,
    coverage_pct: 95.6,
    audit_hash: '9d81e4c307ba12f8',
    summary: 'STRIP entropy monitoring active across video frames. Minor transient dip attributed to camera pan homogeneity; no input tampering or trojan execution.',
    metrics: [
      { label: 'Entropy Mean', value: '2.38 nats' },
      { label: 'Input Jitter', value: '0.012 RMS' },
      { label: 'Frame Latency', value: '18.4 ms' },
    ],
    findings: [
      {
        finding_id: 'F-INF-001',
        severity: 'low',
        detector: 'STRIP Entropy Monitor',
        description:
          'STRIP runtime entropy analysis records a transient entropy dip (H=1.82 nats, baseline μ=2.41) across 3 consecutive inference frames during a 40-minute observation window. Spike does not exceed the adaptive threshold τ=1.65 and is attributable to scene homogeneity during camera pan.',
        evidence_hash: '6e84d29f01a3',
        mitigated: true,
      },
    ],
  },
  {
    stage_id: 'stage_4',
    stage_number: '04',
    stage_name: 'Evidence & Risk Engine',
    stage_subtitle: 'Bayesian Fusion & Threat Scoring',
    risk: 'clean',
    confidence: 0.99,
    coverage_pct: 100.0,
    audit_hash: '40be7a9152de83ca',
    summary: 'Continuous evidence fusion combining multi-detector inputs into composite risk metrics. Global threat score sits at 0.018, well below defense threshold.',
    metrics: [
      { label: 'Posterior Risk', value: '0.018' },
      { label: 'Active Detectors', value: '7 / 7 Online' },
      { label: 'State Coherence', value: '0.998' },
    ],
    findings: [
      {
        finding_id: 'F-ENG-001',
        severity: 'clean',
        detector: 'Bayesian Evidence Integrator',
        description:
          'Posterior threat probability fused across all upstream detector streams evaluates to p(threat)=0.018, safely below alerting boundary of 0.150. Multi-sensor cross-correlations show normal dispersion and no correlated adversarial signals.',
        evidence_hash: '82a9c310fb4e',
        mitigated: true,
      },
    ],
  },
  {
    stage_id: 'stage_5',
    stage_number: '05',
    stage_name: 'Assurance Report',
    stage_subtitle: 'Merkle Attestation & Compliance',
    risk: 'clean',
    confidence: 0.99,
    coverage_pct: 100.0,
    audit_hash: '11d739ea60bf28e4',
    summary: 'Immutable audit ledger synchronized with offline Merkle tree root. End-to-end chain of custody verified without discrepancies.',
    metrics: [
      { label: 'Merkle Root', value: 'VERIFIED' },
      { label: 'Compliance Level', value: 'DEF-STD-05' },
      { label: 'Attestation Sign', value: 'ED25519-OK' },
    ],
    findings: [
      {
        finding_id: 'F-REP-001',
        severity: 'clean',
        detector: 'Merkle Tree Root Validator',
        description:
          'All intermediate stage hashes verified against offline immutable Merkle ledger root. Cryptographic chain of custody intact without discrepancies. Defense readiness criteria satisfied.',
        evidence_hash: 'c791d204ba59',
        mitigated: true,
      },
    ],
  },
]

export const DASHBOARD_OVERVIEW = {
  pipeline_id: 'PL-CV-AIRGAP-26228',
  classification: 'RESTRICTED // AIR-GAPPED ASSURANCE',
  overall_risk: 'clean' as const,
  overall_confidence: 0.962,
  coverage_pct: 98.8,
  verified_stages: '5/5',
  last_sync: '2026-09-06 13:30:00 UTC',
  hardware_node: 'SEC-NODE-ALPHA (CUDA OFFLINE)',
}
