/**
 * DemoControls — floating action button + centered modal for attack scenario simulation.
 * FAB sits bottom-right; clicking it opens a modal overlay so it NEVER competes
 * for space with the Evidence Panel. Active scenario count shown as badge on FAB.
 */
import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  SlidersHorizontal,
  X,
  Zap,
  RotateCcw,
  Loader2,
  AlertOctagon,
  ShieldAlert,
} from 'lucide-react'
import type { AttackScenario } from '../../types/api'
import { usePipelineStore } from '../../store/usePipelineStore'

interface ScenarioConfig {
  id: AttackScenario
  label: string
  sublabel: string
  stagesAffected: string
  severity: 'medium' | 'high' | 'critical'
}

const SCENARIOS: ScenarioConfig[] = [
  {
    id: 'label_manipulation',
    label: 'Label Manipulation',
    sublabel: 'Confident Learning',
    stagesAffected: 'Stage 01 + 04',
    severity: 'high',
  },
  {
    id: 'duplicate_flooding',
    label: 'Duplicate Flooding',
    sublabel: 'pHash Deduplication',
    stagesAffected: 'Stage 01',
    severity: 'medium',
  },
  {
    id: 'backdoor_injection',
    label: 'Backdoor Injection',
    sublabel: 'Neural Cleanse + STRIP',
    stagesAffected: 'Stages 01–02–03–04',
    severity: 'critical',
  },
  {
    id: 'model_substitution',
    label: 'Model Substitution',
    sublabel: 'Weight Hash Verifier',
    stagesAffected: 'Stage 02 + 04',
    severity: 'critical',
  },
  {
    id: 'inference_tampering',
    label: 'Inference Tampering',
    sublabel: 'Input Transform Checker',
    stagesAffected: 'Stage 03 + 04',
    severity: 'high',
  },
  {
    id: 'replay_attack',
    label: 'Replay Attack',
    sublabel: 'Temporal Frame Validator',
    stagesAffected: 'Stage 03 + 04',
    severity: 'high',
  },
  {
    id: 'distribution_shift',
    label: 'Distribution Shift',
    sublabel: 'MMD Drift Detector',
    stagesAffected: 'Stages 01–03–04',
    severity: 'medium',
  },
]

const SEVERITY_STYLES = {
  medium: {
    button:
      'bg-[#C9A24B]/10 hover:bg-[#C9A24B]/20 border-[#C9A24B]/40 hover:border-[#C9A24B] text-[#C9A24B]',
    dot: 'bg-[#C9A24B]',
    badge: 'bg-[#C9A24B]/20 text-[#C9A24B]',
    label: 'ELEVATED',
  },
  high: {
    button:
      'bg-[#B03A2E]/10 hover:bg-[#B03A2E]/20 border-[#B03A2E]/40 hover:border-[#B03A2E] text-[#F4F6F9]',
    dot: 'bg-[#B03A2E]',
    badge: 'bg-[#B03A2E]/20 text-[#B03A2E]/90',
    label: 'HIGH',
  },
  critical: {
    button:
      'bg-[#B03A2E]/20 hover:bg-[#B03A2E]/30 border-[#B03A2E]/70 hover:border-[#B03A2E] text-[#F4F6F9]',
    dot: 'bg-[#B03A2E] animate-pulse',
    badge: 'bg-[#B03A2E]/30 text-[#B03A2E]',
    label: 'CRITICAL',
  },
}

export const DemoControls: React.FC<{ hideFab?: boolean }> = ({ hideFab = false }) => {
  const [isModalOpen, setIsModalOpen] = useState(false)
  const { triggerScenario, resetPipeline, isTriggeringScenario, activeScenarios, lastAction } =
    usePipelineStore()

  const hasActive = activeScenarios.length > 0

  return (
    <>
      {/* ── Floating Action Button ─────────────────────────────────────────── */}
      <AnimatePresence>
        {!hideFab && (
          <motion.div
            key="demo-fab-wrapper"
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.8 }}
            transition={{ duration: 0.18 }}
            id="demo-controls-fab-container"
            className="fixed bottom-6 right-6 z-40 flex flex-col items-end"
          >
            {/* Tooltip label (hover only, no text on button) */}
            <div className="group relative">
              <button
                id="demo-controls-fab"
                type="button"
                aria-label="Demo Controls"
                onClick={() => setIsModalOpen(true)}
                className={`
                  relative flex items-center justify-center w-12 h-12 rounded-2xl
                  bg-[#0B1F3A]/95 backdrop-blur-xl
                  border transition-all duration-200 cursor-pointer
                  shadow-[0_4px_24px_rgba(0,0,0,0.5)]
                  ${hasActive
                    ? 'border-[#B03A2E]/70 hover:border-[#B03A2E] shadow-[0_0_20px_rgba(176,58,46,0.35)] hover:shadow-[0_0_28px_rgba(176,58,46,0.5)]'
                    : 'border-[#4F81BD]/40 hover:border-[#C9A24B]/70 hover:shadow-[0_4px_28px_rgba(201,162,75,0.25)]'
                  }
                `}
              >
                <SlidersHorizontal className="w-5 h-5 text-[#F4F6F9]" />

                {/* Active scenario count badge */}
                {hasActive && (
                  <motion.span
                    initial={{ scale: 0 }}
                    animate={{ scale: 1 }}
                    exit={{ scale: 0 }}
                    className="absolute -top-1.5 -right-1.5 min-w-[18px] h-[18px] px-1 rounded-full
                               bg-[#B03A2E] text-[#F4F6F9] text-[9px] font-mono font-bold
                               flex items-center justify-center border border-[#0B1F3A]
                               shadow-[0_0_8px_rgba(176,58,46,0.6)]"
                  >
                    {activeScenarios.length}
                  </motion.span>
                )}
              </button>

              {/* Tooltip */}
              <div
                className="pointer-events-none absolute bottom-full right-0 mb-2
                            px-2.5 py-1.5 rounded-lg
                            bg-[#0B1F3A]/95 border border-[#4F81BD]/30
                            text-[10px] font-mono text-[#F4F6F9] whitespace-nowrap
                            opacity-0 group-hover:opacity-100 transition-opacity duration-150
                            shadow-[0_4px_12px_rgba(0,0,0,0.5)]"
              >
                Demo Controls
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Modal Overlay ─────────────────────────────────────────────────── */}
      <AnimatePresence>
        {isModalOpen && (
          <>
            {/* Backdrop */}
            <motion.div
              key="demo-modal-backdrop"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.18 }}
              onClick={() => setIsModalOpen(false)}
              className="fixed inset-0 z-50 bg-[#0B1F3A]/70 backdrop-blur-sm"
              aria-hidden="true"
            />

            {/* Modal Card */}
            <motion.div
              key="demo-modal-card"
              role="dialog"
              aria-modal="true"
              aria-label="Demo Controls"
              initial={{ opacity: 0, scale: 0.93, y: 16 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.93, y: 10 }}
              transition={{ type: 'spring', damping: 26, stiffness: 300 }}
              className="fixed inset-0 z-50 flex items-center justify-center pointer-events-none"
            >
              <div
                id="demo-controls-modal"
                className="pointer-events-auto w-full max-w-md mx-4
                           rounded-2xl bg-[#0B1F3A]/97 backdrop-blur-2xl
                           border border-[#4F81BD]/30
                           shadow-[0_20px_60px_rgba(0,0,0,0.7),0_0_0_1px_rgba(79,129,189,0.1)]
                           overflow-hidden"
              >
                {/* Modal Header */}
                <div className="px-5 py-4 border-b border-[#4F81BD]/20 bg-[#1F497D]/15 flex items-center justify-between">
                  <div className="flex items-center gap-2.5">
                    <div className="p-1.5 rounded-lg bg-[#B03A2E]/20 border border-[#B03A2E]/50">
                      <ShieldAlert className="w-3.5 h-3.5 text-[#B03A2E]" />
                    </div>
                    <div className="flex flex-col">
                      <span className="text-[11px] font-header font-bold tracking-wider text-[#F4F6F9] uppercase">
                        Live Demo Controls
                      </span>
                      <span className="text-[9px] font-mono text-[#4F81BD] tracking-wider">
                        ATTACK SCENARIO SIMULATION
                      </span>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    {hasActive && (
                      <span className="px-2 py-0.5 rounded-full text-[9px] font-mono font-bold bg-[#B03A2E]/20 border border-[#B03A2E]/50 text-[#B03A2E]">
                        {activeScenarios.length} ACTIVE
                      </span>
                    )}
                    <button
                      id="demo-modal-close"
                      type="button"
                      aria-label="Close demo controls"
                      onClick={() => setIsModalOpen(false)}
                      className="p-1.5 rounded-lg bg-[#1F497D]/25 border border-[#4F81BD]/30
                                 hover:border-[#C9A24B]/60 text-[#F4F6F9]/70 hover:text-white
                                 transition-all cursor-pointer hover:scale-105 active:scale-95"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                </div>

                {/* Scenario Buttons */}
                <div className="p-4 space-y-1.5 max-h-[60vh] overflow-y-auto custom-scrollbar">
                  {SCENARIOS.map((scenario) => {
                    const styles = SEVERITY_STYLES[scenario.severity]
                    const isActive = activeScenarios.includes(scenario.id)
                    const isLoading = isTriggeringScenario

                    return (
                      <button
                        key={scenario.id}
                        id={`scenario-btn-${scenario.id}`}
                        type="button"
                        onClick={() => triggerScenario(scenario.id)}
                        disabled={isLoading}
                        className={`
                          w-full flex items-center justify-between gap-2 px-3 py-2.5
                          rounded-xl border transition-all duration-150 cursor-pointer
                          disabled:opacity-60 disabled:cursor-not-allowed
                          ${styles.button}
                          ${isActive ? 'ring-1 ring-[#B03A2E]/60' : ''}
                        `}
                      >
                        <div className="flex items-center gap-2.5 min-w-0">
                          {isLoading ? (
                            <Loader2 className="w-3 h-3 animate-spin text-[#4F81BD] flex-shrink-0" />
                          ) : (
                            <span className={`w-2 h-2 rounded-full flex-shrink-0 ${styles.dot}`} />
                          )}
                          <div className="flex flex-col items-start min-w-0">
                            <span className="text-[11px] font-header font-semibold text-[#F4F6F9] leading-tight">
                              {scenario.label}
                            </span>
                            <span className="text-[9px] font-mono text-[#F4F6F9]/60 truncate">
                              {scenario.sublabel} · {scenario.stagesAffected}
                            </span>
                          </div>
                        </div>

                        <div className="flex items-center gap-1.5 flex-shrink-0">
                          {isActive && (
                            <span className="px-1.5 py-0.5 rounded text-[8px] font-mono font-bold bg-[#B03A2E] text-[#F4F6F9]">
                              ON
                            </span>
                          )}
                          <span
                            className={`text-[8px] font-mono font-bold px-1.5 py-0.5 rounded ${styles.badge}`}
                          >
                            {styles.label}
                          </span>
                          <Zap className="w-3 h-3 text-[#F4F6F9]/40" />
                        </div>
                      </button>
                    )
                  })}
                </div>

                {/* Last Action Feedback */}
                {lastAction && (
                  <div className="mx-4 mb-3 px-3 py-2 rounded-lg bg-[#1F497D]/20 border border-[#4F81BD]/20 flex items-start gap-2">
                    <AlertOctagon className="w-3.5 h-3.5 text-[#C9A24B] flex-shrink-0 mt-0.5" />
                    <span className="text-[10px] font-mono text-[#F4F6F9]/80 leading-relaxed break-words">
                      {lastAction}
                    </span>
                  </div>
                )}

                {/* Reset Button */}
                <div className="px-4 pb-4">
                  <button
                    id="demo-reset-btn"
                    type="button"
                    onClick={resetPipeline}
                    disabled={isTriggeringScenario || activeScenarios.length === 0}
                    className="w-full flex items-center justify-center gap-2 px-3 py-2.5
                               rounded-xl border border-[#3F7D4F]/50 bg-[#3F7D4F]/10
                               hover:bg-[#3F7D4F]/20 hover:border-[#3F7D4F] text-[#3F7D4F]
                               transition-all duration-150 disabled:opacity-40
                               disabled:cursor-not-allowed text-[11px] font-header font-semibold
                               cursor-pointer tracking-wide"
                  >
                    <RotateCcw className="w-3.5 h-3.5" />
                    Reset to Baseline
                  </button>
                </div>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </>
  )
}

export default DemoControls
