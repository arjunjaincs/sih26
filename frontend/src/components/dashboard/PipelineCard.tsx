import { motion } from 'framer-motion'
import { 
  Database, 
  Cpu, 
  Eye, 
  Scale, 
  FileCheck2, 
  ChevronRight, 
  ShieldCheck, 
  AlertTriangle,
  CheckCircle2,
  Sparkles,
  type LucideIcon
} from 'lucide-react'
import type { EnrichedStageState } from '../../store/usePipelineStore'
import type { RiskLevel } from '../../types/api'

interface PipelineCardProps {
  stage: EnrichedStageState
  isSelected: boolean
  onClick: () => void
}

const STAGE_ICONS: Record<string, LucideIcon> = {
  stage_1: Database,
  stage_2: Cpu,
  stage_3: Eye,
  stage_4: Scale,
  stage_5: FileCheck2,
}

const getRiskColor = (risk: RiskLevel) => {
  switch (risk) {
    case 'clean':
      return {
        bg: 'bg-[#3F7D4F]/15',
        border: 'border-[#3F7D4F]/40',
        text: 'text-[#3F7D4F]',
        label: 'CLEAN',
        icon: ShieldCheck,
      }
    case 'low':
      return {
        bg: 'bg-[#4F81BD]/15',
        border: 'border-[#4F81BD]/40',
        text: 'text-[#4F81BD]',
        label: 'LOW RISK',
        icon: CheckCircle2,
      }
    case 'medium':
      return {
        bg: 'bg-[#C9A24B]/15',
        border: 'border-[#C9A24B]/50',
        text: 'text-[#C9A24B]',
        label: 'ELEVATED',
        icon: AlertTriangle,
      }
    case 'high':
    case 'critical':
      return {
        bg: 'bg-[#B03A2E]/20',
        border: 'border-[#B03A2E]/50',
        text: 'text-[#B03A2E]',
        label: 'CRITICAL',
        icon: AlertTriangle,
      }
    default:
      return {
        bg: 'bg-[#4F81BD]/15',
        border: 'border-[#4F81BD]/40',
        text: 'text-[#4F81BD]',
        label: 'NOMINAL',
        icon: ShieldCheck,
      }
  }
}

export const PipelineCard: React.FC<PipelineCardProps> = ({
  stage,
  isSelected,
  onClick,
}) => {
  const Icon = STAGE_ICONS[stage.stage_id] || Database
  const riskMeta = getRiskColor(stage.risk)
  const RiskIcon = riskMeta.icon

  return (
    <motion.button
      type="button"
      onClick={onClick}
      animate={{ y: isSelected ? -4 : 0 }}
      whileHover={{ y: isSelected ? -6 : -4, transition: { duration: 0.15, ease: 'easeOut' } }}
      whileTap={{ scale: 0.98 }}
      className={`relative w-full text-left rounded-2xl p-4 xl:p-4.5 backdrop-blur-md transition-all duration-200 cursor-pointer flex flex-col justify-between select-none ${
        isSelected
          ? 'bg-[#1F497D]/35 border-2 border-[#C9A24B] shadow-[0_0_24px_rgba(201,162,75,0.28)]'
          : 'bg-[#1F497D]/15 hover:bg-[#1F497D]/25 border border-[#4F81BD]/25 hover:border-[#C9A24B]/50 shadow-lg'
      }`}
    >
      {/* Top Bar: Stage Number, Icon & Selection Glow */}
      <div className="flex items-center justify-between w-full mb-3">
        <div className="flex items-center gap-2">
          <span className="flex items-center justify-center w-6.5 h-6.5 rounded-lg bg-[#0B1F3A]/90 border border-[#4F81BD]/30 text-[10.5px] font-mono font-bold text-[#C9A24B]">
            {stage.stage_number}
          </span>
          <div className="p-1.5 rounded-xl bg-[#0B1F3A]/60 border border-[#4F81BD]/20 text-[#4F81BD]">
            <Icon className="w-3.5 h-3.5 text-[#F4F6F9]" />
          </div>
        </div>

        {/* Top Right: Status Pulse / Indicator */}
        <div className="flex items-center gap-1.5">
          {isSelected ? (
            <span className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-[#C9A24B]/20 border border-[#C9A24B]/60 text-[9px] font-mono font-bold text-[#C9A24B]">
              <Sparkles className="w-2.5 h-2.5" />
              INSPECTING
            </span>
          ) : (
            <span className="w-2 h-2 rounded-full bg-[#3F7D4F] shadow-[0_0_6px_#3F7D4F]" />
          )}
        </div>
      </div>

      {/* Title and Subtitle */}
      <div className="mb-3">
        <h3 className="text-[14px] xl:text-base font-header font-bold text-[#F4F6F9] tracking-tight group-hover:text-white transition-colors line-clamp-1">
          {stage.stage_name}
        </h3>
        <p className="text-[10px] xl:text-[10.5px] font-mono text-[#4F81BD] tracking-tight leading-tight mt-0.5 line-clamp-2 min-h-[26px]">
          {stage.stage_subtitle}
        </p>
      </div>

      {/* Visually Distinct Badges on Card: Risk & Confidence */}
      <div className="grid grid-cols-2 gap-1.5 mb-3.5 w-full">
        {/* Risk Badge */}
        <div className={`flex items-center gap-1.5 px-2 py-1.5 rounded-lg border ${riskMeta.bg} ${riskMeta.border} min-w-0`}>
          <RiskIcon className={`w-3.5 h-3.5 ${riskMeta.text} flex-shrink-0`} />
          <div className="flex flex-col min-w-0 overflow-hidden">
            <span className="text-[7.5px] font-mono text-[#F4F6F9]/60 uppercase tracking-wider">Risk</span>
            <span className={`text-[9.5px] font-mono font-bold tracking-tight truncate ${riskMeta.text}`}>
              {riskMeta.label}
            </span>
          </div>
        </div>

        {/* Confidence Badge */}
        <div className="flex items-center gap-1.5 px-2 py-1.5 rounded-lg border bg-[#0B1F3A]/70 border-[#4F81BD]/25 min-w-0">
          <div className="flex flex-col min-w-0 overflow-hidden">
            <span className="text-[7.5px] font-mono text-[#F4F6F9]/60 uppercase tracking-wider">Confidence</span>
            <span className="text-[9.5px] font-mono font-bold text-[#F4F6F9] tracking-tight">
              {(stage.confidence * 100).toFixed(0)}%
            </span>
          </div>
        </div>
      </div>

      {/* Metrics Row */}
      <div className="flex flex-col gap-1.5 pt-2.5 border-t border-[#4F81BD]/15 w-full">
        <div className="flex items-center justify-between text-[10.5px] font-mono">
          <span className="text-[#F4F6F9]/60">Stage Coverage</span>
          <span className="text-[#F4F6F9] font-bold">{stage.coverage_pct.toFixed(1)}%</span>
        </div>

        {/* Findings Pill & Action Trigger */}
        <div className="flex items-center justify-between mt-0.5 pt-0.5">
          <span className="px-1.5 py-0.5 rounded text-[9.5px] font-mono bg-[#1F497D]/30 border border-[#4F81BD]/20 text-[#4F81BD]">
            {stage.findings.length} {stage.findings.length === 1 ? 'Finding' : 'Findings'}
          </span>
          <div className="flex items-center gap-0.5 text-[10.5px] font-mono text-[#C9A24B] group-hover:translate-x-0.5 transition-transform">
            <span>Evidence</span>
            <ChevronRight className="w-3 h-3" />
          </div>
        </div>
      </div>
    </motion.button>
  )
}

export default PipelineCard
