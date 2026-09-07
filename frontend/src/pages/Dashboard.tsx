import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import Sidebar from '../components/layout/Sidebar'
import TopBar from '../components/layout/TopBar'
import PipelineCard from '../components/dashboard/PipelineCard'
import EvidencePanel from '../components/dashboard/EvidencePanel'
import DemoControls from '../components/dashboard/DemoControls'
import { usePipelineStore } from '../store/usePipelineStore'
import type { EnrichedStageState } from '../store/usePipelineStore'
import {
  ChevronRight,
  ShieldCheck,
  Activity,
  Cpu,
  Terminal,
  AlertTriangle,
  RefreshCw,
  Loader2,
} from 'lucide-react'

export const Dashboard: React.FC = () => {
  const navigate = useNavigate()
  const {
    stages,
    overallRisk,
    overallConfidence,
    coveragePct,
    pipelineId,
    capturedAt,
    activeScenarios,
    isLoading,
    error,
    fetchPipelineState,
  } = usePipelineStore()

  const [selectedStage, setSelectedStage] = useState<EnrichedStageState | null>(null)
  const [isPanelOpen, setIsPanelOpen] = useState(false)

  // Initial fetch + auto-refresh every 5s (fast enough for demo, no WebSocket needed)
  useEffect(() => {
    fetchPipelineState()
    const id = setInterval(fetchPipelineState, 5000)
    return () => clearInterval(id)
  }, [fetchPipelineState])

  // Keep the evidence panel's selected stage in sync as data refreshes
  useEffect(() => {
    if (selectedStage && stages.length > 0) {
      const updated = stages.find((s) => s.stage_id === selectedStage.stage_id)
      if (updated) setSelectedStage(updated)
    }
  }, [stages]) // eslint-disable-line react-hooks/exhaustive-deps

  const handleStageClick = (stage: EnrichedStageState) => {
    setSelectedStage(stage)
    setIsPanelOpen(true)
  }

  const handleGenerateReport = () => {
    navigate('/report')
  }

  const overallRiskColor =
    overallRisk === 'clean' || overallRisk === 'low'
      ? 'text-[#3F7D4F]'
      : overallRisk === 'medium'
      ? 'text-[#C9A24B]'
      : 'text-[#B03A2E]'

  const formattedTimestamp = capturedAt
    ? new Date(capturedAt).toLocaleTimeString('en-GB', { hour12: false })
    : '—'

  return (
    <div className="flex h-screen w-screen bg-[#0B1F3A] text-[#F4F6F9] overflow-hidden font-sans select-none">
      {/* 1. Left Collapsed Icon Sidebar */}
      <Sidebar />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 h-screen overflow-hidden bg-[#0B1F3A]">
        {/* 2. Top Bar */}
        <TopBar
          onGenerateReport={handleGenerateReport}
          coveragePct={coveragePct || 0}
        />

        {/* Backend Error Banner */}
        <AnimatePresence>
          {error && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              className="bg-[#B03A2E]/20 border-b border-[#B03A2E]/40 px-6 py-2 flex items-center gap-3 text-[11px] font-mono text-[#F4F6F9]/90"
            >
              <AlertTriangle className="w-3.5 h-3.5 text-[#B03A2E] flex-shrink-0" />
              <span>Backend unreachable: {error}</span>
              <button
                onClick={() => fetchPipelineState()}
                className="ml-auto flex items-center gap-1.5 text-[#C9A24B] hover:underline cursor-pointer"
              >
                <RefreshCw className="w-3 h-3" /> Retry
              </button>
            </motion.div>
          )}
        </AnimatePresence>

        {/* 3. Main Workspace Area */}
        <motion.main
          className="flex-1 overflow-y-auto px-6 py-6 flex flex-col justify-between max-w-[1440px] mx-auto w-full"
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25, ease: 'easeOut' }}
        >
          {/* Subheader / Context Bar */}
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-[#4F81BD]/20">
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-mono text-[#C9A24B] font-bold tracking-wider uppercase">
                  ACTIVE PIPELINE GRAPH
                </span>
                <span className="text-[#4F81BD]/40">•</span>
                <span className="text-xs font-mono text-[#4F81BD]">
                  ID: {pipelineId}
                </span>
                {isLoading && (
                  <Loader2 className="w-3.5 h-3.5 text-[#4F81BD] animate-spin ml-1" />
                )}
              </div>
              <h1 className="text-2xl font-header font-black tracking-tight text-[#F4F6F9] mt-0.5">
                Computer-Vision Assurance Pipeline
              </h1>
            </div>

            {/* Live Status Indicators */}
            <div className="flex items-center gap-3 flex-wrap">
              {/* Active scenarios badges */}
              {activeScenarios.length > 0 && (
                <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#B03A2E]/15 border border-[#B03A2E]/40 text-[11px] font-mono">
                  <AlertTriangle className="w-3.5 h-3.5 text-[#B03A2E] animate-pulse" />
                  <span className="text-[#B03A2E] font-bold">
                    {activeScenarios.length} SCENARIO{activeScenarios.length > 1 ? 'S' : ''} ACTIVE
                  </span>
                </div>
              )}

              <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[#1F497D]/20 border border-[#4F81BD]/25 text-[11px] font-mono">
                <ShieldCheck className={`w-3.5 h-3.5 ${overallRiskColor}`} />
                <span className="text-[#F4F6F9]/80">VERDICT:</span>
                <span className={`font-bold ${overallRiskColor}`}>
                  {overallRisk.toUpperCase()}
                  {activeScenarios.length > 0 ? ' / COMPROMISED' : ' / BASELINE'}
                </span>
              </div>

              <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[#1F497D]/20 border border-[#4F81BD]/25 text-[11px] font-mono">
                <Activity className="w-3.5 h-3.5 text-[#C9A24B]" />
                <span className="text-[#F4F6F9]/80">CONFIDENCE:</span>
                <span className="font-bold text-[#F4F6F9]">
                  {(overallConfidence * 100).toFixed(1)}%
                </span>
              </div>
            </div>
          </div>

          {/* Horizontal Pipeline Flow (5 Stages as Clickable Cards) */}
          <div className="my-auto py-6">
            <div className="flex items-center justify-between mb-3 px-1">
              <span className="text-xs font-mono text-[#4F81BD] tracking-wider uppercase flex items-center gap-1.5">
                <Terminal className="w-3.5 h-3.5 text-[#C9A24B]" />
                STAGES SEQUENCE (CLICK CARD TO OPEN EVIDENCE PANEL)
              </span>
              <span className="text-[11px] font-mono text-[#F4F6F9]/60">
                {selectedStage
                  ? `Selected: Stage ${selectedStage.stage_number} (${selectedStage.stage_name})`
                  : 'Select a stage'}
              </span>
            </div>

            {/* 5 Pipeline Stage Cards */}
            {stages.length === 0 && !isLoading ? (
              <div className="flex items-center justify-center h-40 text-[#4F81BD]/60 font-mono text-xs">
                Waiting for backend data…
              </div>
            ) : (
              <div className="relative pt-3 pb-3 px-1 overflow-x-auto no-scrollbar [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden">
                <div className="grid grid-cols-5 min-w-[760px] md:min-w-0 gap-2.5 xl:gap-3.5 items-stretch">
                  {stages.map((stage, idx) => {
                    const isSelected = selectedStage?.stage_id === stage.stage_id
                    const isLast = idx === stages.length - 1

                    return (
                      <div
                        key={stage.stage_id}
                        className={`relative flex flex-col justify-center ${
                          isSelected ? 'z-20' : 'z-10'
                        }`}
                      >
                        <PipelineCard
                          stage={stage}
                          isSelected={isSelected}
                          onClick={() => handleStageClick(stage)}
                        />

                        {/* Connector Arrow */}
                        {!isLast && (
                          <div className="hidden md:flex absolute -right-2 top-1/2 -translate-y-1/2 z-30 pointer-events-none">
                            <ChevronRight className="w-3.5 h-3.5 text-[#C9A24B]/70" />
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            )}
          </div>

          {/* Bottom Status Strip */}
          <div className="mt-auto pt-4 border-t border-[#4F81BD]/20 grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="p-3.5 rounded-xl bg-[#1F497D]/15 border border-[#4F81BD]/20 flex items-center gap-3">
              <div className="p-2 rounded-lg bg-[#0B1F3A] border border-[#4F81BD]/30">
                <Cpu className="w-4 h-4 text-[#C9A24B]" />
              </div>
              <div className="flex flex-col min-w-0">
                <span className="text-[10px] font-mono text-[#4F81BD] uppercase tracking-wider">
                  Verification Node
                </span>
                <span className="text-xs font-mono font-bold text-[#F4F6F9] truncate">
                  SEC-NODE-ALPHA
                </span>
              </div>
            </div>

            <div className="p-3.5 rounded-xl bg-[#1F497D]/15 border border-[#4F81BD]/20 flex items-center gap-3">
              <div className="p-2 rounded-lg bg-[#0B1F3A] border border-[#4F81BD]/30">
                <Activity className="w-4 h-4 text-[#3F7D4F]" />
              </div>
              <div className="flex flex-col min-w-0">
                <span className="text-[10px] font-mono text-[#4F81BD] uppercase tracking-wider">
                  Last Verified
                </span>
                <span className="text-xs font-mono font-bold text-[#F4F6F9] truncate">
                  {formattedTimestamp} UTC
                </span>
              </div>
            </div>
          </div>
        </motion.main>
      </div>

      {/* 4. Slide-in Evidence Panel */}
      <EvidencePanel
        stage={selectedStage}
        isOpen={isPanelOpen}
        onClose={() => setIsPanelOpen(false)}
      />

      {/* 5. Demo Controls FAB — hidden while Evidence Panel is open */}
      <DemoControls hideFab={isPanelOpen} />
    </div>
  )
}

export default Dashboard
