import { Shield, CheckCircle2 } from 'lucide-react'

interface CoverageMeterProps {
  coveragePct?: number
  stagesVerified?: string
}

export const CoverageMeter: React.FC<CoverageMeterProps> = ({
  coveragePct = 98.8,
  stagesVerified = '5/5',
}) => {
  return (
    <div className="flex items-center gap-4 px-4 py-2 rounded-xl bg-[#1F497D]/20 border border-[#4F81BD]/25 backdrop-blur-md shadow-sm">
      <div className="flex items-center gap-2">
        <div className="p-1 rounded-md bg-[#1F497D]/40 text-[#4F81BD]">
          <Shield className="w-3.5 h-3.5 text-[#C9A24B]" />
        </div>
        <div className="flex flex-col">
          <div className="flex items-center gap-2">
            <span className="text-[11px] font-mono tracking-wider text-[#F4F6F9]/80 uppercase">
              Assurance Coverage
            </span>
            <span className="text-[11px] font-mono font-bold text-[#C9A24B]">
              {coveragePct.toFixed(1)}%
            </span>
          </div>
          <span className="text-[9px] font-mono text-[#4F81BD] tracking-tight">
            {stagesVerified} stages verified offline
          </span>
        </div>
      </div>

      {/* Progress Bar with Glow */}
      <div className="w-36 md:w-48 flex flex-col gap-1">
        <div className="w-full h-2 rounded-full bg-[#0B1F3A] border border-[#4F81BD]/30 p-[1px] overflow-hidden">
          <div
            className="h-full rounded-full bg-gradient-to-r from-[#4F81BD] via-[#3F7D4F] to-[#C9A24B] shadow-[0_0_8px_rgba(201,162,75,0.4)] transition-all duration-500 ease-out"
            style={{ width: `${Math.min(coveragePct, 100)}%` }}
          />
        </div>
      </div>

      <div className="hidden lg:flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-[#3F7D4F]/15 border border-[#3F7D4F]/40 text-[10px] font-mono text-[#3F7D4F]">
        <CheckCircle2 className="w-3 h-3" />
        <span>ATTESTED</span>
      </div>
    </div>
  )
}

export default CoverageMeter
