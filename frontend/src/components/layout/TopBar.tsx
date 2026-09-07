import { FileDown, Sparkles, Radio } from 'lucide-react'
import CoverageMeter from '../dashboard/CoverageMeter'

interface TopBarProps {
  onGenerateReport?: () => void
  coveragePct?: number
}

export const TopBar: React.FC<TopBarProps> = ({
  onGenerateReport,
  coveragePct = 98.8,
}) => {
  return (
    <header className="h-16 flex-shrink-0 w-full bg-[#0B1F3A]/90 backdrop-blur-xl border-b border-[#4F81BD]/20 px-6 flex items-center justify-between z-40 relative">
      {/* Left: Wordmark & Classification */}
      <div className="flex items-center gap-4">
        <div className="flex flex-col">
          <div className="flex items-center gap-2.5">
            <span className="text-xl font-header font-black tracking-[0.2em] text-[#F4F6F9] drop-shadow-sm">
              PRAMAAN
            </span>
            <span className="px-2 py-0.5 rounded text-[9px] font-mono tracking-wider font-semibold bg-[#1F497D]/40 text-[#4F81BD] border border-[#4F81BD]/30">
              DEF-GRADE v1.0
            </span>
          </div>
          <div className="flex items-center gap-2 mt-0.5">
            <span className="text-[10px] font-mono text-[#4F81BD] tracking-wider uppercase">
              Offline AI Assurance Platform
            </span>
            <span className="text-[#4F81BD]/40">•</span>
            <span className="flex items-center gap-1 text-[10px] font-mono text-[#3F7D4F]">
              <span className="w-1.5 h-1.5 rounded-full bg-[#3F7D4F] animate-pulse" />
              AIR-GAPPED
            </span>
          </div>
        </div>
      </div>

      {/* Center: Coverage Meter */}
      <div className="hidden md:flex items-center justify-center">
        <CoverageMeter coveragePct={coveragePct} stagesVerified="5/5" />
      </div>

      {/* Right: Hero CTA "Generate Report" */}
      <div className="flex items-center gap-3">
        {/* Real-time telemetry status pill */}
        <div className="hidden xl:flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[#1F497D]/25 border border-[#4F81BD]/25 text-[11px] font-mono text-[#F4F6F9]/80">
          <Radio className="w-3.5 h-3.5 text-[#3F7D4F]" />
          <span>TELEMETRY: SYNCED</span>
        </div>

        {/* HERO CTA BUTTON: Gold Accent, Prominent */}
        <button
          onClick={onGenerateReport}
          type="button"
          id="generate-report-btn"
          className="group relative inline-flex items-center gap-2 px-5 py-2.5 rounded-xl font-header font-bold text-xs tracking-wider uppercase text-[#0B1F3A] bg-[#C9A24B] hover:bg-[#d6b059] active:scale-[0.98] transition-all duration-200 shadow-[0_0_20px_rgba(201,162,75,0.35)] hover:shadow-[0_0_25px_rgba(201,162,75,0.5)] border border-[#C9A24B]/80 cursor-pointer"
        >
          <FileDown className="w-4 h-4 text-[#0B1F3A] stroke-[2.2] group-hover:-translate-y-0.5 transition-transform" />
          <span>Generate Report</span>
          <Sparkles className="w-3.5 h-3.5 text-[#0B1F3A]/70 animate-pulse" />
          
          {/* Subtle gold accent ping on hover */}
          <span className="absolute inset-0 rounded-xl ring-2 ring-[#C9A24B]/50 ring-offset-2 ring-offset-[#0B1F3A] opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none" />
        </button>
      </div>
    </header>
  )
}

export default TopBar
