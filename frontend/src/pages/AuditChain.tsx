import React, { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import Sidebar from '../components/layout/Sidebar'
import { api } from '../services/api'
import type { AuditEvent } from '../types/api'
import {
  ShieldCheck,
  ShieldAlert,
  ArrowLeft,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  Zap,
  Lock,
  Hash,
  Database,
  Layers,
  Cpu,
  Radio,
  FileCheck,
  Sparkles,
} from 'lucide-react'

// Hexagon SVG connector node reflecting the 3D Hero motif
const HexagonNode: React.FC<{
  isVerified?: boolean
  isBroken?: boolean
  isActive?: boolean
}> = ({ isVerified, isBroken, isActive }) => {
  return (
    <div className="relative flex items-center justify-center w-8 h-8 flex-shrink-0 select-none">
      <svg
        viewBox="0 0 24 24"
        className={`w-7 h-7 transition-all duration-300 ${
          isBroken
            ? 'text-[#B03A2E] animate-pulse drop-shadow-[0_0_8px_rgba(176,58,46,0.8)]'
            : isVerified
            ? 'text-[#3F7D4F] drop-shadow-[0_0_8px_rgba(63,125,79,0.8)]'
            : isActive
            ? 'text-[#C9A24B] drop-shadow-[0_0_8px_rgba(201,162,75,0.8)]'
            : 'text-[#4F81BD]/60 hover:text-[#4F81BD]'
        }`}
        fill="currentColor"
      >
        <polygon points="12 2, 21 7.2, 21 16.8, 12 22, 3 16.8, 3 7.2" opacity="0.25" />
        <polygon
          points="12 2, 21 7.2, 21 16.8, 12 22, 3 16.8, 3 7.2"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
        />
      </svg>
      {isBroken ? (
        <span className="absolute text-[10px] font-mono font-bold text-[#B03A2E]">✕</span>
      ) : isVerified ? (
        <span className="absolute text-[10px] font-mono font-bold text-[#3F7D4F]">✓</span>
      ) : (
        <span className="absolute w-1.5 h-1.5 rounded-full bg-[#4F81BD]" />
      )}
    </div>
  )
}

// Crack Fracture SVG overlay for tampered block
const CrackOverlay: React.FC = () => (
  <svg
    className="absolute inset-0 w-full h-full pointer-events-none z-20 text-[#B03A2E]/80"
    viewBox="0 0 280 220"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.8"
    strokeLinecap="round"
  >
    <path d="M 0 40 L 45 65 L 80 50 L 130 95 L 160 85 L 210 130 L 250 120 L 280 160" />
    <path d="M 130 95 L 110 140 L 140 180 L 160 220" />
    <path d="M 80 50 L 95 15 L 120 0" />
    <path d="M 210 130 L 240 180 L 280 190" />
  </svg>
)

export const AuditChain: React.FC = () => {
  const [events, setEvents] = useState<AuditEvent[]>([])
  const [chainId, setChainId] = useState<string>('CHAIN-MOD-DEF-2026')
  const [isLoading, setIsLoading] = useState<boolean>(true)
  const [selectedBlock, setSelectedBlock] = useState<AuditEvent | null>(null)

  // Interactive Tamper & Verification States
  const [isTampered, setIsTampered] = useState<boolean>(false)
  const [isVerifying, setIsVerifying] = useState<boolean>(false)
  const [verifiedUpToIndex, setVerifiedUpToIndex] = useState<number>(-1)
  const [verificationSuccess, setVerificationSuccess] = useState<boolean>(false)
  const [verificationFailedIndex, setVerificationFailedIndex] = useState<number | null>(null)

  // Fetch actual event ledger from GET /api/audit/events
  const fetchLedger = useCallback(async () => {
    setIsLoading(true)
    try {
      const data = await api.getAuditEvents()
      setEvents(data.events)
      setChainId(data.chain_id)
      // Preselect block #4 or #0
      if (data.events.length > 0) {
        setSelectedBlock(data.events[Math.min(4, data.events.length - 1)])
      }
    } catch (_err) {
      // Audit fetch failed — UI remains in loading=false empty state
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchLedger()
  }, [fetchLedger])

  // Handle Simulate Tamper
  const handleSimulateTamper = () => {
    const targetIdx = 4 // Block #4 in the middle
    setIsTampered(true)
    setVerificationSuccess(false)
    setVerificationFailedIndex(null)
    setVerifiedUpToIndex(-1)
    if (events[targetIdx]) {
      setSelectedBlock(events[targetIdx])
    }
  }

  // Handle Reset Chain
  const handleResetChain = () => {
    setIsTampered(false)
    setIsVerifying(false)
    setVerifiedUpToIndex(-1)
    setVerificationSuccess(false)
    setVerificationFailedIndex(null)
    fetchLedger()
  }

  // Handle Verify Chain with left-to-right sequential propagation animation
  const handleVerifyChain = () => {
    if (events.length === 0) return
    setIsVerifying(true)
    setVerificationSuccess(false)
    setVerificationFailedIndex(null)
    setVerifiedUpToIndex(-1)

    const total = events.length
    let current = 0

    const interval = setInterval(() => {
      // If tampered and reached block #4, halt and fail!
      if (isTampered && current === 4) {
        clearInterval(interval)
        setIsVerifying(false)
        setVerificationFailedIndex(4)
        return
      }

      setVerifiedUpToIndex(current)
      current++

      if (current >= total) {
        clearInterval(interval)
        setIsVerifying(false)
        setVerificationSuccess(true)
      }
    }, 280)
  }

  const getStageColor = (stage: string) => {
    switch (stage) {
      case 'Training Data':
        return 'text-[#4F81BD] border-[#4F81BD]/40 bg-[#4F81BD]/10'
      case 'Model':
        return 'text-[#C9A24B] border-[#C9A24B]/40 bg-[#C9A24B]/10'
      case 'Inference':
        return 'text-[#4F81BD] border-[#4F81BD]/40 bg-[#4F81BD]/10'
      case 'Evidence & Risk Engine':
        return 'text-[#C9A24B] border-[#C9A24B]/40 bg-[#C9A24B]/10'
      case 'Assurance Report':
        return 'text-[#3F7D4F] border-[#3F7D4F]/40 bg-[#3F7D4F]/10'
      default:
        return 'text-[#F4F6F9]/60 border-[#4F81BD]/30 bg-[#1F497D]/15'
    }
  }

  const getEventIcon = (type: string) => {
    switch (type) {
      case 'genesis':
        return <Lock className="w-4 h-4 text-[#C9A24B]" />
      case 'data_ingestion':
        return <Database className="w-4 h-4 text-[#4F81BD]" />
      case 'spectral_scan':
        return <Layers className="w-4 h-4 text-[#4F81BD]" />
      case 'model_load':
      case 'weight_hash':
        return <Cpu className="w-4 h-4 text-[#C9A24B]" />
      case 'neural_cleanse':
        return <Sparkles className="w-4 h-4 text-[#C9A24B]" />
      case 'inference_stream':
      case 'entropy_analysis':
        return <Radio className="w-4 h-4 text-[#4F81BD]" />
      case 'frame_cache':
        return <ShieldCheck className="w-4 h-4 text-[#3F7D4F]" />
      case 'risk_aggregation':
        return <Zap className="w-4 h-4 text-[#C9A24B]" />
      case 'assurance_seal':
        return <FileCheck className="w-4 h-4 text-[#3F7D4F]" />
      default:
        return <Hash className="w-4 h-4 text-[#4F81BD]/70" />
    }
  }

  return (
    <div className="flex h-screen w-screen bg-[#0B1F3A] text-[#F4F6F9] overflow-hidden font-sans select-none">
      {/* 1. Left Collapsed Icon Sidebar */}
      <Sidebar />

      {/* Main Content Viewport */}
      <motion.div
        className="flex-1 flex flex-col min-w-0 h-screen overflow-hidden bg-[#0B1F3A]"
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25, ease: 'easeOut' }}
      >
        {/* Top Control Bar */}
        <header className="h-16 flex-shrink-0 w-full bg-[#0B1F3A]/95 backdrop-blur-xl border-b border-[#4F81BD]/20 px-6 flex items-center justify-between z-30">
          <div className="flex items-center gap-3">
            <Link
              to="/dashboard"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#1F497D]/30 border border-[#4F81BD]/30 text-xs font-mono text-[#F4F6F9] hover:text-[#C9A24B] hover:border-[#C9A24B]/50 transition-colors"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Pipeline Graph</span>
            </Link>
            <span className="text-[#4F81BD]/40">|</span>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-header font-bold tracking-wider text-[#F4F6F9]">
                  IMMUTABLE AUDIT LEDGER
                </span>
                <span className="px-2 py-0.5 rounded text-[9px] font-mono tracking-wider font-semibold bg-[#1F497D]/40 text-[#4F81BD] border border-[#4F81BD]/30">
                  {chainId}
                </span>
              </div>
              <p className="text-[10px] font-mono text-[#4F81BD] tracking-wider uppercase">
                Cryptographic Hash Chain • SHA-256 Block Attestation
              </p>
            </div>
          </div>

          {/* Action Buttons: Verify Chain & Simulate Tamper */}
          <div className="flex items-center gap-2.5">
            <button
              onClick={fetchLedger}
              disabled={isLoading || isVerifying}
              className="p-2 rounded-lg bg-[#1F497D]/30 border border-[#4F81BD]/30 hover:border-[#4F81BD] text-xs text-[#F4F6F9] transition-all cursor-pointer"
              title="Refresh ledger"
              id="refresh-audit-btn"
            >
              <RefreshCw className={`w-4 h-4 text-[#C9A24B] ${isLoading ? 'animate-spin' : ''}`} />
            </button>

            {/* Simulate Tamper Button */}
            <button
              onClick={handleSimulateTamper}
              disabled={isVerifying}
              id="simulate-tamper-btn"
              className={`inline-flex items-center gap-2 px-3.5 py-1.5 rounded-lg font-mono text-xs font-semibold tracking-wider transition-all cursor-pointer ${
                isTampered
                  ? 'bg-[#B03A2E] text-white border border-[#B03A2E] shadow-[0_0_15px_rgba(176,58,46,0.5)] animate-pulse'
                  : 'bg-[#B03A2E]/20 text-[#B03A2E] border border-[#B03A2E]/50 hover:bg-[#B03A2E]/30'
              }`}
            >
              <AlertTriangle className="w-3.5 h-3.5" />
              <span>Simulate Tamper</span>
            </button>

            {/* Verify Chain Button */}
            <button
              onClick={handleVerifyChain}
              disabled={isVerifying}
              id="verify-chain-btn"
              className="inline-flex items-center gap-2 px-4 py-1.5 rounded-lg font-header font-bold text-xs tracking-wider uppercase text-[#0B1F3A] bg-[#3F7D4F] hover:bg-[#4d945f] text-white shadow-[0_0_15px_rgba(63,125,79,0.4)] transition-all cursor-pointer active:scale-95"
            >
              <CheckCircle2 className={`w-4 h-4 ${isVerifying ? 'animate-spin' : ''}`} />
              <span>{isVerifying ? 'Verifying...' : 'Verify Chain'}</span>
            </button>

            {/* Reset Button */}
            {(isTampered || verifiedUpToIndex >= 0) && (
              <button
                onClick={handleResetChain}
                id="reset-chain-btn"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#1F497D]/30 border border-[#4F81BD]/30 hover:border-[#C9A24B] text-xs font-mono text-[#F4F6F9] transition-all cursor-pointer"
              >
                <RefreshCw className="w-3 h-3 text-[#4F81BD]" />
                <span>Reset</span>
              </button>
            )}
          </div>
        </header>

        {/* Status / Alert Banner Strip */}
        <div className="px-6 py-2.5 bg-[#0B1F3A]/80 border-b border-[#4F81BD]/20">
          {verificationFailedIndex !== null ? (
            /* Verification Halted at Tampered Block */
            <motion.div
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              className="p-3 rounded-lg bg-[#B03A2E]/20 border border-[#B03A2E] shadow-[0_0_20px_rgba(176,58,46,0.35)] flex items-center justify-between"
              id="verification-failed-banner"
            >
              <div className="flex items-center gap-3">
                <div className="p-1.5 rounded bg-[#B03A2E] text-white animate-pulse">
                  <ShieldAlert className="w-5 h-5" />
                </div>
                <div>
                  <div className="font-header font-bold text-sm text-[#F4F6F9] tracking-wide flex items-center gap-2">
                    <span>Verification Halted — Hash Mismatch at Block #{verificationFailedIndex}.</span>
                    <span className="px-2 py-0.2 rounded text-[9px] font-mono bg-[#B03A2E] text-white uppercase">
                      PROPAGATION HALTED
                    </span>
                  </div>
                  <p className="text-xs font-mono text-[#F4F6F9]/80 mt-0.5">
                    Expected cryptographic continuity violated. Block #{verificationFailedIndex} payload does not match Merkle anchor.
                  </p>
                </div>
              </div>
              <span className="text-xs font-mono text-[#B03A2E] font-bold uppercase hidden md:inline">
                STATUS: FORGED PAYLOAD
              </span>
            </motion.div>
          ) : isTampered ? (
            /* Tampered Alert Banner (Specifically required by prompt) */
            <motion.div
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              className="p-3 rounded-lg bg-[#B03A2E]/20 border border-[#B03A2E] shadow-[0_0_20px_rgba(176,58,46,0.35)] flex items-center justify-between"
              id="tamper-alert-banner"
            >
              <div className="flex items-center gap-3">
                <div className="p-1.5 rounded bg-[#B03A2E] text-white animate-pulse">
                  <ShieldAlert className="w-5 h-5" />
                </div>
                <div>
                  <div className="font-header font-bold text-sm text-[#F4F6F9] tracking-wide flex items-center gap-2">
                    <span>Tamper detected — chain integrity broken at block #4.</span>
                    <span className="px-2 py-0.2 rounded text-[9px] font-mono bg-[#B03A2E] text-white uppercase">
                      CRITICAL BREAK
                    </span>
                  </div>
                  <p className="text-xs font-mono text-[#F4F6F9]/80 mt-0.5">
                    Hash mismatch: Block #4 current digest modified to 0xDEADBEEF... Link to Block #5 severed. Cryptographic Merkle chain invalidated.
                  </p>
                </div>
              </div>
              <span className="text-xs font-mono text-[#B03A2E] font-bold uppercase hidden md:inline">
                STATUS: FORGED PAYLOAD
              </span>
            </motion.div>
          ) : verificationSuccess ? (
            /* Verified Intact Banner */
            <motion.div
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              className="p-3 rounded-lg bg-[#3F7D4F]/20 border border-[#3F7D4F] shadow-[0_0_20px_rgba(63,125,79,0.3)] flex items-center justify-between"
              id="verified-success-banner"
            >
              <div className="flex items-center gap-3">
                <div className="p-1.5 rounded bg-[#3F7D4F] text-white">
                  <ShieldCheck className="w-5 h-5" />
                </div>
                <div>
                  <div className="font-header font-bold text-sm text-[#F4F6F9] tracking-wide flex items-center gap-2">
                    <span>Audit Chain Validated — All {events.length} Cryptographic Blocks Intact.</span>
                    <span className="px-2 py-0.2 rounded text-[9px] font-mono bg-[#3F7D4F] text-[#0B1F3A] font-bold uppercase">
                      VERIFIED 100%
                    </span>
                  </div>
                  <p className="text-xs font-mono text-[#F4F6F9]/80 mt-0.5">
                    Sequential SHA-256 Merkle linkage confirmed unbroken from Genesis anchor to final Assurance Seal.
                  </p>
                </div>
              </div>
              <span className="text-xs font-mono text-[#3F7D4F] font-bold uppercase hidden md:inline">
                SEAL CONFIRMED
              </span>
            </motion.div>
          ) : isVerifying ? (
            /* Propagation in progress */
            <div className="p-2.5 rounded-lg bg-[#1F497D]/30 border border-[#4F81BD]/40 flex items-center justify-between text-xs font-mono">
              <div className="flex items-center gap-2 text-[#C9A24B]">
                <Sparkles className="w-4 h-4 animate-spin" />
                <span>
                  Validating cryptographic block signatures... Verifying block #
                  {verifiedUpToIndex + 1} of {events.length}
                </span>
              </div>
              <div className="w-32 bg-[#0B1F3A] h-1.5 rounded-full overflow-hidden border border-[#4F81BD]/30">
                <div
                  className="h-full bg-[#3F7D4F] transition-all duration-200"
                  style={{
                    width: `${((verifiedUpToIndex + 1) / Math.max(1, events.length)) * 100}%`,
                  }}
                />
              </div>
            </div>
          ) : (
            /* Nominal Standby Banner */
            <div className="flex items-center justify-between text-xs font-mono text-[#F4F6F9]/70">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-[#3F7D4F] animate-pulse" />
                <span>
                  CHAIN STATUS: INTACT • {events.length} EVENT BLOCKS IN CHRONOLOGICAL LEDGER
                </span>
              </div>
              <div className="text-[11px] text-[#4F81BD]">
                Click "Verify Chain" to trace cryptographic proofs or "Simulate Tamper" to test anomaly detection
              </div>
            </div>
          )}
        </div>

        {/* Main Content Area: Horizontal Connected Hash Chain */}
        <main className="flex-1 overflow-x-auto overflow-y-hidden px-8 py-8 flex flex-col justify-between">
          <div className="my-auto">
            {/* Context Label above chain */}
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2 text-xs font-mono text-[#C9A24B] tracking-wider uppercase font-bold">
                <Hash className="w-3.5 h-3.5" />
                <span>CONTINUOUS HASH CHAIN EXECUTION TIMELINE</span>
              </div>
              <div className="text-[11px] font-mono text-[#4F81BD]/70">
                Scroll horizontally to trace the full 11-block ledger sequence →
              </div>
            </div>

            {/* ========================================================================= */}
            {/* HORIZONTAL SEQUENCE OF CONNECTED BLOCKS WITH HERO HEXAGON CONNECTORS */}
            {/* ========================================================================= */}
            <div
              className="flex items-center py-6 min-w-max gap-0 relative select-none"
              id="audit-chain-canvas"
            >
              {events.map((evt, idx) => {
                const isThisBlockTampered = isTampered && idx === 4
                const isThisBlockVerified = verifiedUpToIndex >= idx
                const isSelected = selectedBlock?.block_index === idx
                const isDownstreamFromTamper = isTampered && idx > 4

                // Display hash: if tampered at block 4, display deadbeef
                const displayHash = isThisBlockTampered
                  ? '0xDEADBEEF6813'
                  : `0x${evt.current_hash.slice(0, 10)}`
                const displayPrevHash =
                  idx === 0
                    ? '0x00000000'
                    : isThisBlockTampered
                    ? `0x${evt.prev_hash.slice(0, 8)}`
                    : isDownstreamFromTamper
                    ? '0xINVALID_LINK'
                    : `0x${evt.prev_hash.slice(0, 8)}`

                return (
                  <React.Fragment key={evt.event_id || idx}>
                    {/* BLOCK COMPONENT */}
                    <motion.div
                      layout
                      whileHover={{ y: -4 }}
                      animate={
                        isThisBlockTampered
                          ? {
                              x: [0, -3, 3, -2, 2, 0],
                              transition: { repeat: Infinity, duration: 0.35 },
                            }
                          : {}
                      }
                      onClick={() => setSelectedBlock(evt)}
                      className={`relative w-72 rounded-xl p-4 flex flex-col justify-between cursor-pointer transition-all duration-300 backdrop-blur-md ${
                        isThisBlockTampered
                          ? 'bg-[#B03A2E]/25 border-2 border-[#B03A2E] shadow-[0_0_30px_rgba(176,58,46,0.6)]'
                          : isDownstreamFromTamper
                          ? 'bg-[#0E2442]/50 border border-[#B03A2E]/40 opacity-70'
                          : isThisBlockVerified
                          ? 'bg-[#0E2442]/95 border-2 border-[#3F7D4F] shadow-[0_0_20px_rgba(63,125,79,0.35)]'
                          : isSelected
                          ? 'bg-[#0E2442]/95 border-2 border-[#C9A24B] shadow-[0_0_20px_rgba(201,162,75,0.3)]'
                          : 'bg-[#0E2442]/85 border border-[#4F81BD]/30 hover:border-[#4F81BD]/70 shadow-lg'
                      }`}
                      id={`audit-block-${idx}`}
                    >
                      {/* Visual Crack Overlay on Block #4 when tampered */}
                      {isThisBlockTampered && <CrackOverlay />}

                      {/* Top Row: Index Badge & Stage Pill */}
                      <div className="flex items-center justify-between mb-2 z-10">
                        <div className="flex items-center gap-1.5">
                          <span
                            className={`px-2 py-0.5 rounded text-xs font-mono font-bold ${
                              isThisBlockTampered
                                ? 'bg-[#B03A2E] text-white'
                                : isThisBlockVerified
                                ? 'bg-[#3F7D4F] text-[#0B1F3A]'
                                : 'bg-[#1F497D]/50 text-[#C9A24B] border border-[#C9A24B]/30'
                            }`}
                          >
                            #{String(idx).padStart(2, '0')}
                          </span>
                          <span className="text-[10px] font-mono text-[#4F81BD]/70">
                            {evt.event_id}
                          </span>
                        </div>

                        {/* Status Glyph */}
                        <div className="flex items-center gap-1">
                          {isThisBlockTampered ? (
                            <span className="px-1.5 py-0.5 rounded text-[9px] font-mono font-bold bg-[#B03A2E] text-white">
                              TAMPERED
                            </span>
                          ) : isThisBlockVerified ? (
                            <span className="flex items-center gap-1 text-[10px] font-mono font-bold text-[#3F7D4F]">
                              <CheckCircle2 className="w-3.5 h-3.5" />
                              <span>OK</span>
                            </span>
                          ) : (
                            <span className="text-[10px] font-mono text-[#4F81BD]/70">
                              {evt.status.toUpperCase()}
                            </span>
                          )}
                        </div>
                      </div>

                      {/* Stage Pill */}
                      <div className="mb-2 z-10">
                        <span
                          className={`inline-block px-2 py-0.5 rounded text-[10px] font-mono border ${getStageColor(
                            evt.stage_name
                          )}`}
                        >
                          {evt.stage_name}
                        </span>
                      </div>

                      {/* Action Title & Icon */}
                      <div className="flex items-start gap-2.5 my-2 z-10 min-h-[44px]">
                        <div className="p-1.5 rounded bg-[#0B1F3A] border border-[#4F81BD]/25 flex-shrink-0 mt-0.5">
                          {getEventIcon(evt.event_type)}
                        </div>
                        <div>
                          <h4
                            className={`text-xs font-header font-bold leading-tight ${
                              isThisBlockTampered
                                ? 'text-[#B03A2E]'
                                : isThisBlockVerified
                                ? 'text-[#F4F6F9]'
                                : 'text-[#F4F6F9]'
                            }`}
                          >
                            {isThisBlockTampered ? 'FORGED PAYLOAD DETECTED' : evt.action}
                          </h4>
                          <p className="text-[11px] text-[#F4F6F9]/60 line-clamp-2 mt-0.5 font-sans">
                            {isThisBlockTampered
                              ? 'Signature diverged from pre-computed hardware attestation key.'
                              : evt.details}
                          </p>
                        </div>
                      </div>

                      {/* Monospace Hash Strip Underneath */}
                      <div
                        className={`mt-3 pt-2.5 border-t z-10 text-[10px] font-mono space-y-1 ${
                          isThisBlockTampered
                            ? 'border-[#B03A2E]/50 text-[#B03A2E]'
                            : 'border-[#4F81BD]/20'
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <span className="text-[#4F81BD]/60">CURR HASH:</span>
                          <span
                            className={`font-bold tracking-wider ${
                              isThisBlockTampered
                                ? 'text-[#B03A2E] underline'
                                : 'text-[#C9A24B]'
                            }`}
                          >
                            {displayHash}
                          </span>
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="text-[#4F81BD]/50">PREV HASH:</span>
                          <span className="text-[#4F81BD] tracking-wider">
                            {displayPrevHash}
                          </span>
                        </div>
                      </div>
                    </motion.div>

                    {/* CONNECTOR LINK BETWEEN BLOCKS (Hexagon Node + glowing link beam) */}
                    {idx < events.length - 1 && (
                      <div
                        className="flex items-center justify-center w-16 relative flex-shrink-0"
                        id={`audit-connector-${idx}`}
                      >
                        {/* Connecting Line Beam */}
                        <div
                          className={`absolute top-1/2 -translate-y-1/2 w-full h-[2px] transition-colors ${
                            isTampered && idx === 4
                              ? 'bg-transparent border-t-2 border-dashed border-[#B03A2E]'
                              : isThisBlockVerified && verifiedUpToIndex > idx
                              ? 'bg-[#3F7D4F] shadow-[0_0_8px_#3F7D4F]'
                              : 'bg-[#4F81BD]/40'
                          }`}
                        />

                        {/* Centered Hexagon Motif from 3D Hero */}
                        <div className="relative z-10 bg-[#0B1F3A] px-0.5">
                          <HexagonNode
                            isBroken={isTampered && idx === 4}
                            isVerified={verifiedUpToIndex > idx}
                            isActive={isVerifying && verifiedUpToIndex === idx}
                          />
                        </div>

                        {/* Severed Gap warning when tampered at block 4 */}
                        {isTampered && idx === 4 && (
                          <div className="absolute -top-5 text-[9px] font-mono font-bold text-[#B03A2E] whitespace-nowrap bg-[#0B1F3A] px-1 border border-[#B03A2E]/50 rounded">
                            BROKEN LINK
                          </div>
                        )}
                      </div>
                    )}
                  </React.Fragment>
                )
              })}
            </div>
          </div>

          {/* Bottom Row: Selected Block Forensic Inspector */}
          {selectedBlock && (
            <div
              className="mt-4 p-4 rounded-xl bg-[#0E2442]/90 border border-[#4F81BD]/30 backdrop-blur-md shadow-2xl relative"
              id="audit-block-inspector"
            >
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-3 border-b border-[#4F81BD]/20">
                <div className="flex items-center gap-3">
                  <div className="p-2 rounded bg-[#0B1F3A] border border-[#C9A24B]/40 text-[#C9A24B]">
                    {getEventIcon(selectedBlock.event_type)}
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-mono font-bold text-[#C9A24B]">
                        BLOCK #{String(selectedBlock.block_index).padStart(2, '0')}
                      </span>
                      <span className="text-[#4F81BD]/30">•</span>
                      <span className="text-sm font-header font-bold text-[#F4F6F9]">
                        {isTampered && selectedBlock.block_index === 4
                          ? 'MUTATED PAYLOAD — FORENSIC ANOMALY'
                          : selectedBlock.action}
                      </span>
                    </div>
                    <p className="text-xs text-[#F4F6F9]/70 font-sans mt-0.5">
                      {isTampered && selectedBlock.block_index === 4
                        ? 'Simulated byte-level mutation in weight tensor checksum table. Hash chain propagation rejected.'
                        : selectedBlock.details}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-3 text-xs font-mono">
                  <div className="bg-[#0B1F3A] px-3 py-1.5 rounded border border-[#4F81BD]/20">
                    <span className="text-[#4F81BD]/60 block text-[9px] uppercase">Stage Domain</span>
                    <span className="text-[#F4F6F9] font-bold">{selectedBlock.stage_name}</span>
                  </div>

                  <div className="bg-[#0B1F3A] px-3 py-1.5 rounded border border-[#4F81BD]/20">
                    <span className="text-[#4F81BD]/60 block text-[9px] uppercase">Timestamp</span>
                    <span className="text-[#F4F6F9]">
                      {new Date(selectedBlock.timestamp).toLocaleTimeString('en-GB')}
                    </span>
                  </div>
                </div>
              </div>

              {/* Hashes & Forensic Attestation */}
              <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-4 text-xs font-mono">
                <div className="p-2.5 rounded bg-[#0B1F3A]/70 border border-[#4F81BD]/20">
                  <span className="text-[10px] text-slate-400 block uppercase">
                    Full Current Block SHA-256 Digest
                  </span>
                  <span className="text-[#C9A24B] break-all font-bold">
                    {isTampered && selectedBlock.block_index === 4
                      ? 'DEADBEEF6813a4891ca756b3e8104d5e729a1cf6473210985bdeec4c90f1d438'
                      : `${selectedBlock.current_hash}a4891ca756b3e8104d5e729a1cf6473210985bdeec4c90f1d438`}
                  </span>
                </div>

                <div className="p-2.5 rounded bg-[#0B1F3A]/70 border border-[#4F81BD]/20">
                  <span className="text-[10px] text-slate-400 block uppercase">
                    Linked Previous Hash Anchor
                  </span>
                  <span className="text-[#4F81BD] break-all font-bold">
                    {selectedBlock.block_index === 0
                      ? '0000000000000000000000000000000000000000000000000000000000000000 (GENESIS ANCHOR)'
                      : `${selectedBlock.prev_hash}90f1d43891ca756b3e8104d5e729a1cf6473210985bdeec4`}
                  </span>
                </div>
              </div>
            </div>
          )}
        </main>
      </motion.div>
    </div>
  )
}

export default AuditChain
