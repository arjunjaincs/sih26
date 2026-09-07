import { motion, AnimatePresence } from 'framer-motion'
import { 
  X, 
  ShieldCheck, 
  AlertTriangle, 
  Activity, 
  Hash, 
  CheckCircle2, 
  Lock,
  Layers,
  FileCheck
} from 'lucide-react'
import type { EnrichedStageState } from '../../store/usePipelineStore'
import type { RiskLevel, StageFinding } from '../../types/api'

interface EvidencePanelProps {
  stage: EnrichedStageState | null
  isOpen: boolean
  onClose: () => void
}

const getRiskDisplay = (risk: RiskLevel) => {
  switch (risk) {
    case 'clean':
      return {
        badgeBg: 'bg-[#3F7D4F]/20',
        badgeBorder: 'border-[#3F7D4F]/60',
        textColor: 'text-[#3F7D4F]',
        label: 'ASSURANCE RISK: CLEAN',
        summary: 'Target stage passes all non-parametric integrity bounds. Zero adversarial perturbation detected.',
        icon: ShieldCheck,
      }
    case 'low':
      return {
        badgeBg: 'bg-[#4F81BD]/20',
        badgeBorder: 'border-[#4F81BD]/60',
        textColor: 'text-[#4F81BD]',
        label: 'ASSURANCE RISK: LOW',
        summary: 'Marginal dispersion observed within natural long-tail tolerance. Baseline integrity satisfied.',
        icon: CheckCircle2,
      }
    case 'medium':
      return {
        badgeBg: 'bg-[#C9A24B]/20',
        badgeBorder: 'border-[#C9A24B]/70',
        textColor: 'text-[#C9A24B]',
        label: 'ASSURANCE RISK: ELEVATED',
        summary: 'Statistical anomaly detected requiring secondary verification. Not fatal to mission.',
        icon: AlertTriangle,
      }
    case 'high':
    case 'critical':
      return {
        badgeBg: 'bg-[#B03A2E]/25',
        badgeBorder: 'border-[#B03A2E]/70',
        textColor: 'text-[#B03A2E]',
        label: 'ASSURANCE RISK: CRITICAL',
        summary: 'High-confidence adversarial attack vector surfaced. Pipeline isolation recommended.',
        icon: AlertTriangle,
      }
    default:
      return {
        badgeBg: 'bg-[#4F81BD]/20',
        badgeBorder: 'border-[#4F81BD]/50',
        textColor: 'text-[#4F81BD]',
        label: 'ASSURANCE RISK: NOMINAL',
        summary: 'Normal operational telemetry.',
        icon: ShieldCheck,
      }
  }
}

export const EvidencePanel: React.FC<EvidencePanelProps> = ({
  stage,
  isOpen,
  onClose,
}) => {
  if (!stage) return null

  const riskMeta = getRiskDisplay(stage.risk)
  const RiskIcon = riskMeta.icon

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Subtle dark backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={onClose}
            className="fixed top-16 inset-x-0 bottom-0 bg-[#0B1F3A]/60 backdrop-blur-sm z-30 lg:hidden"
          />

          {/* Slide-in Evidence Panel */}
          <motion.div
            initial={{ x: '100%', opacity: 0.5 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: '100%', opacity: 0 }}
            transition={{ type: 'spring', damping: 28, stiffness: 240 }}
            className="fixed top-16 right-0 h-[calc(100vh-4rem)] w-full sm:w-[480px] lg:w-[520px] bg-[#0B1F3A]/95 backdrop-blur-2xl border-l border-[#4F81BD]/30 shadow-[-10px_0_30px_rgba(0,0,0,0.5)] z-30 flex flex-col justify-between overflow-hidden"
          >
            {/* Header */}
            <div className="p-6 border-b border-[#4F81BD]/20 flex items-start justify-between gap-4 bg-[#1F497D]/10">
              <div className="flex flex-col gap-1">
                <div className="flex items-center gap-2">
                  <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-[#1F497D]/40 border border-[#4F81BD]/40 text-[#C9A24B]">
                    STAGE {stage.stage_number}
                  </span>
                  <span className="text-[10px] font-mono text-[#4F81BD] tracking-wider uppercase">
                    EVIDENCE LOG
                  </span>
                </div>
                <h2 className="text-xl font-header font-bold text-[#F4F6F9] tracking-tight mt-0.5">
                  {stage.stage_name}
                </h2>
                <div className="flex items-center gap-1.5 text-[11px] font-mono text-[#4F81BD] mt-0.5">
                  <Hash className="w-3 h-3 text-[#C9A24B]" />
                  <span className="truncate text-[#4F81BD]/70">ID: {stage.audit_hash}</span>
                </div>
              </div>

              {/* Close Button */}
              <button
                type="button"
                onClick={onClose}
                aria-label="Close evidence panel"
                className="p-2 rounded-xl bg-[#1F497D]/25 border border-[#4F81BD]/30 hover:border-[#C9A24B]/60 text-[#F4F6F9]/70 hover:text-white transition-all cursor-pointer shadow-sm hover:scale-105 active:scale-95"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Panel Scrollable Body */}
            <div className="flex-1 overflow-y-auto px-6 py-5 space-y-6 custom-scrollbar">
              {/* STAGE SUMMARY */}
              <div className="p-4 rounded-xl bg-[#1F497D]/15 border border-[#4F81BD]/20 backdrop-blur-md">
                <p className="text-xs font-sans text-[#F4F6F9]/90 leading-relaxed">
                  {stage.summary}
                </p>
              </div>

              {/* SECTION: SEPARATE, VISUALLY DISTINCT BADGES (Risk & Confidence) */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-mono tracking-wider text-[#4F81BD] uppercase font-semibold">
                    Stage Verdict
                  </span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
                  {/* ELEMENT 1: RISK BADGE */}
                  <div className={`p-4 rounded-xl border backdrop-blur-md ${riskMeta.badgeBg} ${riskMeta.badgeBorder} flex flex-col justify-between shadow-md`}>
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-[10px] font-mono uppercase tracking-widest text-[#F4F6F9]/70">
                        Risk Factor
                      </span>
                      <RiskIcon className={`w-4 h-4 ${riskMeta.textColor}`} />
                    </div>
                    <div>
                      <div className={`text-base font-header font-black tracking-tight ${riskMeta.textColor}`}>
                        {stage.risk.toUpperCase()}
                      </div>
                      <p className="text-[10px] font-mono text-[#F4F6F9]/70 mt-1 leading-snug">
                        {riskMeta.label}
                      </p>
                    </div>
                  </div>

                  {/* ELEMENT 2: CONFIDENCE BADGE */}
                  <div className="p-4 rounded-xl border border-[#4F81BD]/40 bg-[#0B1F3A]/80 backdrop-blur-md flex flex-col justify-between shadow-md">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-[10px] font-mono uppercase tracking-widest text-[#4F81BD]">
                        Model Confidence
                      </span>
                      <Activity className="w-4 h-4 text-[#C9A24B]" />
                    </div>
                    <div>
                      <div className="text-2xl font-header font-black tracking-tight text-[#F4F6F9]">
                        {(stage.confidence * 100).toFixed(1)}%
                      </div>
                      <div className="w-full bg-[#1F497D]/40 h-1.5 rounded-full mt-2 overflow-hidden">
                        <div 
                          className="h-full rounded-full bg-gradient-to-r from-[#4F81BD] to-[#C9A24B]" 
                          style={{ width: `${stage.confidence * 100}%` }}
                        />
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* STAGE METRICS GRID */}
              <div className="p-4 rounded-xl bg-[#1F497D]/15 border border-[#4F81BD]/20">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-[10px] font-mono uppercase tracking-wider text-[#4F81BD]">
                    Stage Verification Telemetry
                  </span>
                  <span className="text-[10px] font-mono text-[#C9A24B]">
                    Coverage: {stage.coverage_pct.toFixed(1)}%
                  </span>
                </div>
                <div className="grid grid-cols-3 gap-2">
                  {stage.metrics.map((metric, i) => (
                    <div key={i} className="p-2.5 rounded-lg bg-[#0B1F3A]/70 border border-[#4F81BD]/20 flex flex-col">
                      <span className="text-[9px] font-mono text-[#F4F6F9]/60 truncate">{metric.label}</span>
                      <span className="text-xs font-mono font-bold text-[#F4F6F9] mt-1 truncate">{metric.value}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* FINDINGS & EVIDENCE CARDS */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Layers className="w-4 h-4 text-[#4F81BD]" />
                    <h4 className="text-xs font-mono uppercase tracking-wider text-[#F4F6F9] font-bold">
                      Detector Findings ({stage.findings.length})
                    </h4>
                  </div>
                  <span className="text-[10px] font-mono text-[#3F7D4F] flex items-center gap-1">
                    <CheckCircle2 className="w-3 h-3" />
                    TAMPER RESISTANT
                  </span>
                </div>

                {stage.findings.length === 0 ? (
                  <div className="p-5 rounded-xl bg-[#1F497D]/10 border border-[#4F81BD]/20 text-center flex flex-col items-center">
                    <FileCheck className="w-8 h-8 text-[#3F7D4F] mb-2" />
                    <span className="text-xs font-header font-bold text-[#F4F6F9]">
                      Clean Execution Baseline
                    </span>
                    <p className="text-[11px] font-sans text-[#F4F6F9]/70 mt-1 max-w-xs">
                      All adversarial ML detection modules returned zero anomalies for this stage.
                    </p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {stage.findings.map((finding: StageFinding) => (
                      <motion.div
                        key={finding.finding_id}
                        whileHover={{ y: -2 }}
                        className="p-4 rounded-xl bg-[#1F497D]/20 hover:bg-[#1F497D]/30 border border-[#4F81BD]/30 hover:border-[#C9A24B]/50 transition-all duration-200 backdrop-blur-md shadow-sm"
                      >
                        {/* Finding Header */}
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center gap-2">
                            <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-[#0B1F3A] border border-[#4F81BD]/30 text-[#C9A24B]">
                              {finding.finding_id}
                            </span>
                            <span className="text-[11px] font-mono font-bold text-[#F4F6F9]">
                              {finding.detector}
                            </span>
                          </div>
                          {finding.mitigated && (
                            <span className="px-2 py-0.5 rounded-full text-[9px] font-mono font-semibold bg-[#3F7D4F]/20 text-[#3F7D4F] border border-[#3F7D4F]/40">
                              MITIGATED
                            </span>
                          )}
                        </div>

                        {/* Finding Body */}
                        <p className="text-xs font-sans text-[#F4F6F9]/85 leading-relaxed mt-2">
                          {finding.description}
                        </p>

                        {/* Evidence Hash */}
                        {finding.evidence_hash && (
                          <div className="mt-3 pt-2.5 border-t border-[#4F81BD]/15 flex items-center justify-between text-[10px] font-mono text-[#4F81BD]">
                            <span className="flex items-center gap-1 text-[#4F81BD]">
                              <Hash className="w-3 h-3 text-[#C9A24B]" />
                              evidence_hash: {finding.evidence_hash}
                            </span>
                            <span className="text-[9px] text-[#3F7D4F]">IMMUTABLE ATTESTATION</span>
                          </div>
                        )}
                      </motion.div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Panel Footer */}
            <div className="p-5 border-t border-[#4F81BD]/20 bg-[#0B1F3A]/90 flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 text-[10px] font-mono text-[#4F81BD]">
                <Lock className="w-3.5 h-3.5 text-[#3F7D4F]" />
                <span>SIGNATURE: ED25519-ATTESTED</span>
              </div>

              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 rounded-xl text-xs font-mono font-semibold bg-[#1F497D]/40 hover:bg-[#1F497D]/60 border border-[#4F81BD]/40 text-[#F4F6F9] transition-all cursor-pointer"
              >
                Close Panel
              </button>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}

export default EvidencePanel
