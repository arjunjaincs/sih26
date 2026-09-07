import { Link } from 'react-router-dom'
import { ShieldAlert, ArrowLeft, Terminal } from 'lucide-react'
import { motion } from 'framer-motion'

/**
 * NotFound — PRAMAAN-branded 404 page.
 * Displayed for any unrecognised route. Matches design system exactly.
 */
export const NotFound: React.FC = () => {
  return (
    <div className="min-h-screen w-screen bg-[#0B1F3A] text-[#F4F6F9] flex flex-col items-center justify-center font-sans select-none px-6">
      {/* Gold accent top border */}
      <div className="fixed top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-transparent via-[#C9A24B] to-transparent" />

      <motion.div
        className="flex flex-col items-center text-center max-w-lg"
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35, ease: 'easeOut' }}
      >
        {/* Icon */}
        <div className="p-4 rounded-2xl bg-[#1F497D]/30 border border-[#B03A2E]/40 shadow-[0_0_30px_rgba(176,58,46,0.2)] mb-6">
          <ShieldAlert className="w-12 h-12 text-[#B03A2E]" />
        </div>

        {/* Status code */}
        <div className="font-mono text-[10px] tracking-[0.4em] uppercase text-[#C9A24B] mb-2">
          ERROR CODE: 404
        </div>

        <h1 className="text-4xl font-header font-black tracking-tight text-[#F4F6F9] mb-3">
          Route Not Found
        </h1>

        <p className="text-sm font-mono text-[#4F81BD] leading-relaxed mb-2">
          The requested assurance endpoint does not exist within this pipeline boundary.
        </p>

        {/* Terminal-style error block */}
        <div className="w-full mt-4 mb-8 p-4 rounded-lg bg-[#1F497D]/20 border border-[#4F81BD]/25 text-left">
          <div className="flex items-center gap-2 text-[10px] font-mono text-[#C9A24B] uppercase tracking-wider mb-2">
            <Terminal className="w-3.5 h-3.5" />
            <span>PRAMAAN ROUTING LOG</span>
          </div>
          <div className="font-mono text-xs space-y-1 text-[#F4F6F9]/60">
            <div><span className="text-[#B03A2E]">✕</span> Route resolution failed — no handler registered</div>
            <div><span className="text-[#4F81BD]">→</span> Verify URL against the authorised endpoint manifest</div>
            <div><span className="text-[#3F7D4F]">↩</span> Redirecting to authorised navigation</div>
          </div>
        </div>

        {/* Navigation actions */}
        <div className="flex items-center gap-3 flex-wrap justify-center">
          <Link
            to="/dashboard"
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl font-header font-bold text-xs tracking-wider uppercase text-[#0B1F3A] bg-[#C9A24B] hover:bg-[#d6b059] shadow-[0_0_20px_rgba(201,162,75,0.35)] transition-all hover:scale-[1.02] active:scale-[0.98]"
          >
            <ArrowLeft className="w-4 h-4" />
            Return to Dashboard
          </Link>
          <Link
            to="/"
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl font-header font-semibold text-xs tracking-wider uppercase text-[#F4F6F9] bg-[#1F497D]/40 border border-[#4F81BD]/30 hover:border-[#C9A24B]/50 hover:text-[#C9A24B] transition-all"
          >
            3D Pipeline View
          </Link>
        </div>
      </motion.div>

      {/* Bottom watermark */}
      <div className="fixed bottom-5 font-mono text-[9px] tracking-[0.3em] uppercase text-[#4F81BD]/40">
        PRAMAAN — OFFLINE AI ASSURANCE // SIH26228 // MINISTRY OF DEFENCE
      </div>
    </div>
  )
}

export default NotFound
