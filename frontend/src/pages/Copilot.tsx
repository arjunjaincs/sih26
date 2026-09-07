import React, { useState, useRef, useEffect, useCallback } from 'react'
import { motion } from 'framer-motion'
import { Link } from 'react-router-dom'
import Sidebar from '../components/layout/Sidebar'
import {
  ArrowLeft,
  Terminal,
  ShieldCheck,
  Sparkles,
  Lock,
  CornerDownLeft,
  Trash2,
  Database,
  Cpu,
  Radio,
  FileCheck,
  Layers,
  Hash,
} from 'lucide-react'
import { usePipelineStore } from '../store/usePipelineStore'
import type { EnrichedStageState } from '../store/usePipelineStore'

// ─── Types ────────────────────────────────────────────────────────────────────

interface LogMessage {
  id: string
  timestamp: string
  role: 'analyst' | 'copilot' | 'system'
  content: string
  category?: string
  isAnalyzing?: boolean
}

// ─── Keyword / response helpers ───────────────────────────────────────────────

const STAGE_KEYWORDS: Record<string, string[]> = {
  stage_1: [
    'training', 'training data', 'dataset', 'spectral', 'poison',
    'stage 1', 'stage01', 'stage_1',
    // distribution_shift scenario
    'distribution', 'drift', 'shift', 'mmd', 'discrepancy', 'covariate',
    'out-of-distribution', 'ood', 'f-td-ds',
  ],
  stage_2: [
    'model', 'checkpoint', 'backdoor', 'neural', 'neural cleanse', 'trojan',
    'weight', 'f-md-bi', 'stage 2', 'stage02', 'stage_2',
    'substitution', 'model substitution', 'f-md-ms',
  ],
  stage_3: [
    'inference', 'telemetry', 'strip', 'entropy', 'runtime', 'frame', 'replay',
    'stage 3', 'stage03', 'stage_3',
    // distribution_shift / inference
    'calibration', 'ece', 'confidence', 'f-inf-ds', 'f-inf',
    // replay / tampering
    'tampering', 'optical flow',
  ],
  stage_4: [
    'evidence', 'risk', 'bayesian', 'fusion', 'threat', 'score',
    'stage 4', 'stage04', 'stage_4',
  ],
  stage_5: [
    'audit', 'chain', 'merkle', 'attestation', 'compliance', 'report',
    'stage 5', 'stage05', 'stage_5',
  ],
}

const STAGE_NAMES: Record<string, string> = {
  stage_1: 'Training Data',
  stage_2: 'Model Checkpoint',
  stage_3: 'Inference Telemetry',
  stage_4: 'Evidence & Risk',
  stage_5: 'Assurance Report',
}

const RISK_LABEL: Record<string, string> = {
  clean:    'CLEAN ✓',
  low:      'LOW RISK',
  medium:   'MEDIUM RISK',
  high:     'HIGH RISK',
  critical: 'CRITICAL RISK ⚠',
}

function nowUTC(): string {
  return new Date().toLocaleTimeString('en-GB', { hour12: false }) + ' UTC'
}

function detectStage(q: string): string | null {
  const lower = q.toLowerCase()
  for (const [id, kws] of Object.entries(STAGE_KEYWORDS)) {
    if (kws.some((kw) => lower.includes(kw))) return id
  }
  return null
}

function detectWhyIntent(q: string): boolean {
  return /\b(why|explain|evidence|detail|finding|cause|reason|going on|happening|what is|describe|show me|tell me)\b/i.test(q)
}

function buildResponse(q: string, stages: EnrichedStageState[]): { text: string; category: string } {
  const stageId = detectStage(q)
  const isWhy   = detectWhyIntent(q)

  if (stageId) {
    const stage = stages.find((s) => s.stage_id === stageId)
    const stageName = STAGE_NAMES[stageId] ?? stageId

    if (!stage) {
      return {
        text: `No live telemetry for ${stageName}. Ensure the backend is running.`,
        category: stageName.toUpperCase(),
      }
    }

    const riskLabel      = RISK_LABEL[stage.risk] ?? stage.risk.toUpperCase()
    const activeFindings = stage.findings.filter((f) => !f.mitigated)
    const lines: string[] = [
      `LIVE TELEMETRY REPORT — STAGE ${stage.stage_number} (${stageName.toUpperCase()})`,
      `• Current Risk Level: ${riskLabel}`,
      `• Assurance Confidence: ${Math.round(stage.confidence * 100)}%`,
      `• Coverage: ${Math.round(stage.coverage_pct)}%`,
    ]

    if (stage.metrics?.length) {
      lines.push('• Key Metrics:')
      stage.metrics.forEach((m) => lines.push(`  · ${m.label}: ${m.value}`))
    }

    if (activeFindings.length === 0) {
      lines.push(`• Active Findings: NONE — ${stage.summary}`)
    } else {
      lines.push(`• Active Findings (${activeFindings.length}):`)
      activeFindings.forEach((f) => {
        lines.push(`  [${f.severity.toUpperCase()}] ${f.finding_id} — ${f.description}`)
        if (isWhy) lines.push(`  Detected by: ${f.detector}${f.evidence_hash ? ` (hash: ${f.evidence_hash})` : ''}`)
      })
      if (!isWhy && activeFindings[0]) {
        lines.push(`• Detection Method: ${activeFindings[0].detector}`)
      }
    }

    return { text: lines.join('\n'), category: `STAGE ${stage.stage_number} // ${stageName.toUpperCase()}` }
  }

  // Chain keyword fallback
  if (/\b(chain|tamper|block|ledger|hash)\b/i.test(q)) {
    const s5  = stages.find((s) => s.stage_id === 'stage_5')
    const info = s5
      ? `Stage 05 — Risk: ${RISK_LABEL[s5.risk] ?? s5.risk.toUpperCase()}, Confidence: ${Math.round(s5.confidence * 100)}%.`
      : 'Stage 05 telemetry unavailable.'
    return {
      text:
        'AUDIT LEDGER QUERY: CHAIN-MOD-DEF-2026\n' +
        '• Cryptographic chain evaluated via SHA-256 Merkle DAG.\n' +
        `• ${info}\n` +
        '• For block-level inspection, navigate to /audit-chain.',
      category: 'AUDIT CHAIN INTEGRITY',
    }
  }

  // Overall threat assessment
  if (/\b(overall|threat|summary|status|pipeline|all|assess|posture)\b/i.test(q)) {
    if (stages.length === 0) {
      return { text: 'No pipeline state loaded. Fetch from the dashboard first.', category: 'PIPELINE OVERVIEW' }
    }
    const flagged = stages.filter((s) => s.risk !== 'clean' && s.findings.some((f) => !f.mitigated))
    return {
      text: [
        'OVERALL PIPELINE THREAT ASSESSMENT (STANDARD: MOD-AI-ASR-2026)',
        `• Stages Evaluated: ${stages.length}`,
        `• Flagged Stages: ${
          flagged.length === 0
            ? 'NONE — Pipeline nominal.'
            : flagged.map((s) => `Stage ${s.stage_number} (${STAGE_NAMES[s.stage_id]}, Risk: ${s.risk.toUpperCase()})`).join('; ')
        }`,
        `• Operational Status: ${
          flagged.length > 0
            ? 'DEPLOYMENT HOLD — Active findings require remediation.'
            : 'CLEARED — All stages within acceptable parameters.'
        }`,
      ].join('\n'),
      category: 'PIPELINE OVERVIEW',
    }
  }

  // Fallback
  return {
    text:
      "I can only answer questions grounded in this session's evidence — try asking about a specific pipeline stage or finding.\n" +
      'Available stage queries: "training data", "model", "inference", "evidence", "audit chain"\n' +
      'For "why" explanations, add: "explain", "why", or "evidence"',
    category: 'QUERY UNRESOLVED',
  }
}

// ─── Initial hardcoded demo log ───────────────────────────────────────────────

const INITIAL_EXCHANGES: LogMessage[] = [
  {
    id: 'sys-0',
    timestamp: '14:47:00 UTC',
    role: 'system',
    content:
      'PRAMAAN COPILOT v1.0 [OFFLINE AIR-GAPPED EVALUATION ENCLAVE INITIALIZED]\n' +
      'SESSION ANCHOR: SHA256:8f4c2e19b0a7d43891ca756b3e8104d5e729a1cf6473210985bdeec4\n' +
      'GROUNDING CONSTRAINT: Strict deterministic derivation from active session telemetry only. Zero cloud exfiltration.',
  },
  {
    id: 'msg-1',
    timestamp: '14:48:02 UTC',
    role: 'analyst',
    content: 'explain finding F-MD-BI-001 --evidence-level verbose',
  },
  {
    id: 'msg-2',
    timestamp: '14:48:04 UTC',
    role: 'copilot',
    category: 'STAGE 02 // MODEL INTEGRITY',
    content:
      'EVIDENCE DOSSIER — FINDING REF [F-MD-BI-001]\n' +
      '• Subsystem: Stage 02 (Model Checkpoint ResNet-50-Def)\n' +
      '• Detection Method: Neural Cleanse Weight-Space Inversion (Wang et al., 2019)\n' +
      '• Anomaly Index: AI = 3.41 (Nominal threshold τ = 2.00; values > 2.00 confirm trojan shortcut)\n' +
      '• Perturbation Norm: Minimum trigger L1 = 12.4 (clean model baseline L1 = 38.7)\n' +
      '• Spatial Footprint: Reverse-engineered 5×5 pixel trigger pattern located at coordinates [x:0.82, y:0.85]\n' +
      '• Target Activation: 99.97% classification confidence shift to class-7 under trigger injection\n' +
      '• Forensic Attribution: Distributed backdoor poisoning during training partition compilation\n' +
      '• Remediation Action: Quarantine candidate checkpoint. Initiate STRIP pattern unlearning or revert to certified baseline checkpoint sha256:839b80c51617.',
  },
  {
    id: 'msg-3',
    timestamp: '14:50:11 UTC',
    role: 'analyst',
    content: 'audit telemetry --stage "Inference" --check-replay',
  },
  {
    id: 'msg-4',
    timestamp: '14:50:12 UTC',
    role: 'copilot',
    category: 'STAGE 03 // INFERENCE TELEMETRY',
    content:
      'TELEMETRY INTEGRITY AUDIT — STAGE 03 (INFERENCE)\n' +
      '• Frame Sample Window: 14,280 consecutive video frames evaluated\n' +
      '• Monotonic Nonces: 100% unique cryptographic frame nonces verified. Zero sequence skips or duplicate timestamps\n' +
      '• STRIP Runtime Entropy: Average prediction entropy H = 2.41 nats (adaptive cutoff threshold τ = 1.65)\n' +
      '• Perturbation Invariance: Dynamic noise superposition confirms absence of persistent trojan activation shortcuts\n' +
      '• Hardware Enclave Link: Verified against hardware TPM digest sha256:a571b7e5c265\n' +
      '• Verdict: INFERENCE TELEMETRY PASS — Nominal operational variance confirmed.',
  },
  {
    id: 'msg-5',
    timestamp: '14:52:30 UTC',
    role: 'analyst',
    content: 'assess threat posture --protocol SIH26228',
  },
  {
    id: 'msg-6',
    timestamp: '14:52:32 UTC',
    role: 'copilot',
    category: 'ASSURANCE VERDICT // THREAT MATRIX',
    content:
      'OVERALL PIPELINE THREAT ASSESSMENT (STANDARD: MOD-AI-ASR-2026)\n' +
      '• Current Risk Level: CRITICAL RISK (Adversarial compromise active)\n' +
      '• Flagged Stages: Stage 01 (Training Data: Spectral cluster separation) & Stage 02 (Model: Neural Cleanse backdoor)\n' +
      '• Cryptographic Audit Chain: BROKEN at Block #4 (Weight attestation mismatch)\n' +
      '• Operational Deployment Status: PROHIBITED. Pipeline must not be deployed to forward edge hardware\n' +
      '• Immediate Directive:\n' +
      '  1. Revoke active air-gap inference signing key\n' +
      '  2. Isolate flagged training partition class-3 and rebuild dataset SHA-256 manifest\n' +
      '  3. Re-train target model inside clean-room environment with verified SVD provenance checks.',
  },
]

// ─── Sidebar helpers ──────────────────────────────────────────────────────────

function riskBadgeClass(risk: string): string {
  switch (risk) {
    case 'critical': return 'bg-[#B03A2E]/20 text-[#B03A2E]'
    case 'high':     return 'bg-[#B03A2E]/10 text-[#B03A2E]/80'
    case 'medium':   return 'bg-[#C9A24B]/20 text-[#C9A24B]'
    case 'low':      return 'bg-[#4F81BD]/20 text-[#4F81BD]'
    default:         return 'bg-[#3F7D4F]/20 text-[#3F7D4F]'
  }
}

function cardBorderClass(risk: string): string {
  if (risk === 'critical' || risk === 'high') return 'border-[#B03A2E]/50 shadow-[0_0_12px_rgba(176,58,46,0.12)]'
  if (risk === 'medium')                       return 'border-[#C9A24B]/40'
  return 'border-[#4F81BD]/30'
}

const SIDEBAR_ICONS: Record<string, React.ReactNode> = {
  stage_1: <Database className="w-3.5 h-3.5 text-[#4F81BD]" />,
  stage_2: <Cpu      className="w-3.5 h-3.5 text-[#C9A24B]" />,
  stage_3: <Radio    className="w-3.5 h-3.5 text-[#4F81BD]" />,
  stage_4: <Layers   className="w-3.5 h-3.5 text-[#C9A24B]" />,
  stage_5: <FileCheck className="w-3.5 h-3.5 text-[#3F7D4F]" />,
}

// ─── Component ────────────────────────────────────────────────────────────────

export const Copilot: React.FC = () => {
  const [messages, setMessages] = useState<LogMessage[]>(INITIAL_EXCHANGES)
  const [inputValue, setInputValue] = useState<string>('')
  const terminalEndRef = useRef<HTMLDivElement>(null)
  const inputRef       = useRef<HTMLInputElement>(null)

  const { stages, fetchPipelineState, isLoading } = usePipelineStore()

  // Fetch once on mount if store is empty
  useEffect(() => {
    if (stages.length === 0) fetchPipelineState()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    terminalEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = useCallback(
    (e?: React.FormEvent) => {
      if (e) e.preventDefault()
      const query = inputValue.trim()
      if (!query) return

      const analystMsgId   = `usr-${Date.now()}`
      const analyzingMsgId = `analyzing-${Date.now()}`

      const analystMsg: LogMessage = {
        id: analystMsgId, timestamp: nowUTC(), role: 'analyst', content: query,
      }
      const analyzingMsg: LogMessage = {
        id: analyzingMsgId, timestamp: nowUTC(), role: 'copilot',
        category: 'FORENSIC CO-PROCESSOR', content: 'PRAMAAN:: analyzing evidence...', isAnalyzing: true,
      }

      setMessages((prev) => [...prev, analystMsg, analyzingMsg])
      setInputValue('')

      // 380 ms placeholder → replace with real grounded answer
      setTimeout(() => {
        const { stages: liveStages } = usePipelineStore.getState()
        const { text, category }     = buildResponse(query, liveStages)
        const reply: LogMessage = {
          id: `cop-${Date.now()}`, timestamp: nowUTC(), role: 'copilot', category, content: text,
        }
        setMessages((prev) => prev.map((m) => (m.id === analyzingMsgId ? reply : m)))
      }, 380)
    },
    [inputValue]
  )

  const handleQuickPrompt = (t: string) => { setInputValue(t); inputRef.current?.focus() }
  const handleClearLog    = ()          => setMessages([INITIAL_EXCHANGES[0]])

  // Sidebar uses live stages if available, falls back to static list
  const sidebarStages = stages.length > 0 ? stages : null

  return (
    <div className="flex h-screen w-screen bg-[#0B1F3A] text-[#F4F6F9] overflow-hidden font-sans select-none">
      <Sidebar />

      <motion.div
        className="flex-1 flex flex-col min-w-0 h-screen overflow-hidden bg-[#0B1F3A]"
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25, ease: 'easeOut' }}
      >
        {/* ── Header ─────────────────────────────────────────────────────── */}
        <header className="h-16 flex-shrink-0 w-full bg-[#0B1F3A]/95 backdrop-blur-xl border-b border-[#4F81BD]/25 px-6 flex items-center justify-between z-30">
          <div className="flex items-center gap-3">
            <Link
              to="/dashboard"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#1F497D]/30 border border-[#4F81BD]/30 text-xs font-mono text-[#F4F6F9] hover:text-[#C9A24B] hover:border-[#C9A24B]/50 transition-colors"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Dashboard</span>
            </Link>
            <span className="text-[#4F81BD]/40">|</span>
            <div>
              <div className="flex items-center gap-2">
                <Terminal className="w-4 h-4 text-[#C9A24B]" />
                <h1 className="text-xs sm:text-sm font-mono font-bold tracking-wider text-[#F4F6F9] uppercase">
                  PRAMAAN COPILOT — OFFLINE // GROUNDED IN CURRENT SESSION EVIDENCE ONLY
                </h1>
              </div>
              <p className="text-[10px] font-mono text-[#4F81BD] tracking-wider uppercase">
                Air-Gapped Neural Analyst • Zero Cloud Exfiltration
                {isLoading && <span className="ml-2 text-[#C9A24B] animate-pulse">[ SYNCING TELEMETRY... ]</span>}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="hidden lg:flex items-center gap-2 px-3 py-1 rounded-md bg-[#1F497D]/30 border border-[#3F7D4F]/40 text-[11px] font-mono text-[#3F7D4F]">
              <Lock className="w-3.5 h-3.5" /><span>AIR-GAP ENCLAVE LOCKED</span>
            </div>
            <button
              onClick={handleClearLog}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#1F497D]/30 border border-[#4F81BD]/30 hover:border-[#B03A2E]/50 text-xs font-mono text-slate-300 hover:text-[#B03A2E] transition-all cursor-pointer"
            >
              <Trash2 className="w-3.5 h-3.5" /><span className="hidden sm:inline">Clear Console</span>
            </button>
          </div>
        </header>

        {/* ── Body ───────────────────────────────────────────────────────── */}
        <div className="flex-1 flex min-h-0 overflow-hidden">

          {/* Terminal log */}
          <section className="flex-1 flex flex-col min-w-0 bg-[#0B1F3A]/60 relative">
            <div
              className="flex-1 overflow-y-auto px-6 py-6 font-mono text-xs sm:text-[13px] leading-relaxed space-y-4"
              id="copilot-terminal-log"
            >
              {messages.map((msg) => {
                if (msg.role === 'system') {
                  return (
                    <div key={msg.id} className="p-3 rounded bg-[#0B1F3A]/70 border border-[#4F81BD]/30 text-[#4F81BD] text-[11px] font-mono whitespace-pre-wrap leading-relaxed shadow-inner">
                      {msg.content}
                    </div>
                  )
                }
                const isAnalyst = msg.role === 'analyst'
                return (
                  <div key={msg.id} className="pb-4 border-b border-[#4F81BD]/15 last:border-b-0 space-y-1.5">
                    <div className="flex items-center gap-2.5 text-xs">
                      <span className="text-[#4F81BD]/50 font-mono text-[11px]">[{msg.timestamp}]</span>
                      {isAnalyst ? (
                        <span className="text-[#4F81BD] font-bold tracking-wider uppercase">&gt;&gt; ANALYST</span>
                      ) : (
                        <span className={`font-bold tracking-wider uppercase ${msg.isAnalyzing ? 'text-[#4F81BD]/60 animate-pulse' : 'text-[#C9A24B]'}`}>
                          PRAMAAN::
                        </span>
                      )}
                      {msg.category && (
                        <span className="text-[10px] font-mono text-[#4F81BD]/60 border border-[#4F81BD]/25 px-2 rounded bg-[#0B1F3A]/50">
                          {msg.category}
                        </span>
                      )}
                    </div>
                    <div className={`pl-4 border-l-2 whitespace-pre-wrap ${
                      isAnalyst
                        ? 'border-[#4F81BD] text-[#F4F6F9]'
                        : msg.isAnalyzing
                          ? 'border-slate-500 text-[#4F81BD]/60 italic'
                          : 'border-[#C9A24B] text-[#F4F6F9]/85'
                    }`}>
                      {msg.content}
                    </div>
                  </div>
                )
              })}
              <div ref={terminalEndRef} />
            </div>

            {/* Quick prompts */}
            <div className="px-6 py-2 bg-[#0B1F3A]/80 border-t border-[#4F81BD]/20 flex items-center gap-2 overflow-x-auto text-[11px] font-mono text-[#4F81BD]/60">
              <span className="text-[#C9A24B] flex items-center gap-1 flex-shrink-0 font-semibold">
                <Sparkles className="w-3 h-3" /> QUICK QUERIES:
              </span>
              {[
                ["what's wrong with the model",        "> what's wrong with the model"],
                ['explain training data findings',      '> explain training data findings'],
                ['verify audit chain integrity',        '> verify audit chain integrity'],
                ['assess overall pipeline threat posture', '> assess overall threat posture'],
              ].map(([prompt, label]) => (
                <button
                  key={prompt}
                  onClick={() => handleQuickPrompt(prompt)}
                  className="px-2.5 py-1 rounded bg-[#1F497D]/30 border border-[#4F81BD]/30 hover:border-[#C9A24B] hover:text-[#F4F6F9] whitespace-nowrap transition-colors cursor-pointer"
                >
                  {label}
                </button>
              ))}
            </div>

            {/* Input */}
            <form onSubmit={handleSend} className="p-4 bg-[#0B1F3A] border-t border-[#4F81BD]/30 flex items-center gap-3 z-10" id="copilot-input-form">
              <div className="flex items-center gap-1 text-xs font-mono font-bold text-[#4F81BD] select-none flex-shrink-0">
                <span className="text-[#C9A24B]">&gt;</span>
                <span className="hidden sm:inline">ANALYST@PRAMAAN:~$</span>
              </div>
              <div className="flex-1 relative flex items-center">
                <input
                  ref={inputRef}
                  type="text"
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                  placeholder="Enter forensic query (e.g. model, training data, inference)..."
                  className="w-full bg-[#0B1F3A] border border-[#4F81BD]/30 focus:border-[#C9A24B] rounded px-3 py-2 text-xs sm:text-sm font-mono text-[#F4F6F9] placeholder:text-[#4F81BD]/40 outline-none transition-colors"
                  id="copilot-command-input"
                />
                {!inputValue && <span className="absolute right-3 w-2 h-4 bg-[#C9A24B] animate-pulse pointer-events-none" />}
              </div>
              <button
                type="submit"
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded font-mono font-bold text-xs uppercase tracking-wider text-[#0B1F3A] bg-[#C9A24B] hover:bg-[#d6b059] shadow-[0_0_12px_rgba(201,162,75,0.3)] transition-all cursor-pointer flex-shrink-0"
                id="copilot-send-btn"
              >
                <span>Execute</span><CornerDownLeft className="w-3.5 h-3.5" />
              </button>
            </form>
          </section>

          {/* ── Session Context Sidebar ─────────────────────────────────── */}
          <aside className="w-80 flex-shrink-0 h-full bg-[#0B1F3A]/95 border-l border-[#4F81BD]/25 p-5 flex flex-col justify-between overflow-y-auto z-20">
            <div>
              <div className="flex items-center gap-2 pb-3 border-b border-[#4F81BD]/20 mb-4">
                <Hash className="w-4 h-4 text-[#C9A24B]" />
                <div>
                  <h3 className="text-xs font-bold text-[#F4F6F9] tracking-wider uppercase">Session Context Scope</h3>
                  <p className="text-[10px] font-mono text-[#4F81BD]">
                    {sidebarStages ? 'Live Zustand Telemetry' : 'Awaiting telemetry sync...'}
                  </p>
                </div>
              </div>

              <div className="space-y-3 font-mono text-xs">
                {sidebarStages
                  ? sidebarStages.map((stage) => {
                      const active     = stage.findings.filter((f) => !f.mitigated)
                      const effectiveR = active.length > 0 ? stage.risk : 'clean'
                      return (
                        <div key={stage.stage_id} className={`p-3 rounded bg-[#1F497D]/20 border space-y-1.5 ${cardBorderClass(effectiveR)}`}>
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-1.5 text-xs text-[#F4F6F9] font-bold">
                              {SIDEBAR_ICONS[stage.stage_id]}
                              <span>Stage {stage.stage_number}: {STAGE_NAMES[stage.stage_id]}</span>
                            </div>
                            <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${riskBadgeClass(effectiveR)}`}>
                              {active.length > 0 ? stage.risk.toUpperCase() : 'NOMINAL'}
                            </span>
                          </div>
                          {active.length > 0 ? (
                            <>
                              <div className="text-[10px] text-[#F4F6F9]/70 font-sans">• {active.length} finding(s) — <span className="font-mono text-[#B03A2E]">{active[0].finding_id}</span></div>
                              <div className="text-[9px] text-[#4F81BD]/60 truncate">{active[0].description}</div>
                            </>
                          ) : (
                            <div className="text-[9px] text-[#4F81BD]/60">Confidence: {Math.round(stage.confidence * 100)}% | Coverage: {Math.round(stage.coverage_pct)}%</div>
                          )}
                        </div>
                      )
                    })
                  : /* Static fallback while loading */
                    [
                      { num: '01', name: 'Training Data',       ref: 'F-TD-001',    label: '1 FINDING',  detail: 'Spectral SVD Covariance',     status: 'Nominal long-tail variance (p=0.43)',     border: 'border-[#4F81BD]/30',  badge: 'bg-[#4F81BD]/20 text-[#4F81BD]',   icon: <Database className="w-3.5 h-3.5 text-[#4F81BD]" /> },
                      { num: '02', name: 'Model Checkpoint',    ref: 'F-MD-BI-001', label: 'CRITICAL',   detail: 'Neural Cleanse Anomaly',       status: 'AI=3.41 trigger pattern',                border: 'border-[#B03A2E]/50 shadow-[0_0_12px_rgba(176,58,46,0.15)]', badge: 'bg-[#B03A2E]/20 text-[#B03A2E]', icon: <Cpu className="w-3.5 h-3.5 text-[#C9A24B]" /> },
                      { num: '03', name: 'Inference Telemetry', ref: null,           label: 'NOMINAL',    detail: 'STRIP entropy H=2.41 nats',    status: 'Zero frame replay collisions',            border: 'border-[#4F81BD]/30',  badge: 'bg-[#3F7D4F]/20 text-[#3F7D4F]',  icon: <Radio className="w-3.5 h-3.5 text-[#4F81BD]" /> },
                      { num: '04', name: 'Evidence & Risk',     ref: null,           label: 'ATTESTED',   detail: 'Merkle root 8f4c2e19b0a7...',  status: '11 blocks in immutable chain',            border: 'border-[#4F81BD]/30',  badge: 'bg-[#C9A24B]/20 text-[#C9A24B]',  icon: <Layers className="w-3.5 h-3.5 text-[#C9A24B]" /> },
                      { num: '05', name: 'Assurance Report',    ref: null,           label: 'SEALED',     detail: 'Report PRAMAAN-2026-6866',     status: 'Formal deliverable compiled',             border: 'border-[#4F81BD]/30',  badge: 'bg-[#3F7D4F]/20 text-[#3F7D4F]',  icon: <FileCheck className="w-3.5 h-3.5 text-[#3F7D4F]" /> },
                    ].map((s) => (
                      <div key={s.num} className={`p-3 rounded bg-[#1F497D]/20 border space-y-1.5 ${s.border}`}>
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-1.5 text-xs text-[#F4F6F9] font-bold">{s.icon}<span>Stage {s.num}: {s.name}</span></div>
                          <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${s.badge}`}>{s.label}</span>
                        </div>
                        <div className="text-[10px] text-[#F4F6F9]/70 font-sans">• {s.detail}</div>
                        <div className="text-[9px] text-[#4F81BD]/60">{s.status}</div>
                      </div>
                    ))
                }
              </div>
            </div>

            <div className="mt-4 p-3 rounded bg-[#0B1F3A] border border-[#4F81BD]/30 text-[10px] font-mono text-[#4F81BD]/60 space-y-1">
              <div className="text-[#3F7D4F] font-bold flex items-center gap-1.5 uppercase">
                <ShieldCheck className="w-3.5 h-3.5" /><span>OFFLINE ATTESTATION</span>
              </div>
              <p className="leading-relaxed">
                PRAMAAN Copilot runs locally inside the air-gapped security boundary.
                Responses are strictly synthesized from live Zustand telemetry — no external API calls.
              </p>
            </div>
          </aside>
        </div>
      </motion.div>
    </div>
  )
}

export default Copilot
