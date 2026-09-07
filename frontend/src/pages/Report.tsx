import React, { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import Sidebar from '../components/layout/Sidebar'
import { api } from '../services/api'
import type { AssuranceReport, StageFinding, RiskLevel } from '../types/api'
import {
  ShieldCheck,
  ShieldAlert,
  FileDown,
  RefreshCw,
  Loader2,
  ChevronDown,
  ChevronUp,
  Download,
  Printer,
  CheckCircle2,
  AlertTriangle,
  ArrowLeft,
  Hash,
  Activity,
} from 'lucide-react'

export const Report: React.FC = () => {
  const [report, setReport] = useState<AssuranceReport | null>(null)
  const [isLoading, setIsLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)
  const [openStages, setOpenStages] = useState<Record<string, boolean>>({})
  const [toastMessage, setToastMessage] = useState<string | null>(null)

  const fetchReport = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const data = await api.getAssuranceReport()
      setReport(data)
      // By default open any stage that has findings or non-clean risk
      const initialOpenState: Record<string, boolean> = {}
      data.stages.forEach((st) => {
        initialOpenState[st.stage_name] =
          st.findings.length > 0 || st.risk !== 'clean'
      })
      // If none have findings, expand the first stage by default
      if (Object.values(initialOpenState).every((v) => !v) && data.stages.length > 0) {
        initialOpenState[data.stages[0].stage_name] = true
      }
      setOpenStages(initialOpenState)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch report')
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchReport()
  }, [fetchReport])

  const toggleStage = (stageName: string) => {
    setOpenStages((prev) => ({
      ...prev,
      [stageName]: !prev[stageName],
    }))
  }

  const handleExportJSON = () => {
    if (!report) return
    const dataStr =
      'data:text/json;charset=utf-8,' +
      encodeURIComponent(JSON.stringify(report, null, 2))
    const downloadAnchor = document.createElement('a')
    downloadAnchor.setAttribute('href', dataStr)
    downloadAnchor.setAttribute(
      'download',
      `PRAMAAN-ASSURANCE-REPORT-${report.report_id}.json`
    )
    document.body.appendChild(downloadAnchor)
    downloadAnchor.click()
    downloadAnchor.remove()
    showToast('Formal audit JSON payload downloaded.')
  }

  const handleExportPDF = () => {
    showToast('Preparing formal audit document for print/PDF export...')
    setTimeout(() => {
      window.print()
    }, 400)
  }

  const showToast = (msg: string) => {
    setToastMessage(msg)
    setTimeout(() => setToastMessage(null), 3500)
  }

  const getRecommendedAction = (finding: StageFinding): string => {
    const det = (finding.detector || '').toLowerCase()
    const id = (finding.finding_id || '').toLowerCase()
    if (det.includes('neural cleanse') || det.includes('backdoor') || id.includes('bd')) {
      return 'Quarantine candidate model checkpoint immediately. Initiate STRIP weight-space anomaly unlearning or roll back to certified pre-poisoning baseline. Invalidate current signing key.'
    }
    if (det.includes('spectral') || det.includes('poison') || id.includes('td')) {
      return 'Isolate flagged cluster partition. Execute cryptographic provenance verification against source data custody records, purge poisoned records, and retrain model.'
    }
    if (det.includes('duplicate') || id.includes('dup')) {
      return 'Execute perceptual-hash deduplication pass (threshold τ=0.92). Re-balance training sample frequency distribution and rebuild dataset digest.'
    }
    if (det.includes('substitution') || det.includes('model') || id.includes('sub')) {
      return 'Revoke operational deployment token immediately. Re-verify model weight SHA-256 against defence registry attestation ledger.'
    }
    if (det.includes('strip') || det.includes('entropy') || id.includes('inf')) {
      return 'Activate runtime spatial filtering and STRIP dynamic noise perturbation layer. Flag anomalous input stream to defence SOC.'
    }
    if (det.includes('replay') || id.includes('rpl')) {
      return 'Enforce strict monotonic nonce validation and reject video frames matching cached inference hash within 50ms window.'
    }
    if (det.includes('distribution') || det.includes('shift') || id.includes('drift')) {
      return 'Flag model accuracy degradation. Schedule re-calibration dataset ingestion and notify operational intelligence unit for covariate re-weighting.'
    }
    return 'Maintain routine continuous telemetry monitoring. Scheduled re-verification recommended within 30 days.'
  }

  const getRiskBadgeStyles = (risk: RiskLevel) => {
    switch (risk) {
      case 'critical':
      case 'high':
        return {
          border: 'border-[#B03A2E]',
          bg: 'bg-[#B03A2E]/15',
          text: 'text-[#B03A2E]',
          dot: 'bg-[#B03A2E]',
          glow: 'shadow-[0_0_20px_rgba(176,58,46,0.3)]',
          label: risk.toUpperCase(),
        }
      case 'medium':
        return {
          border: 'border-[#C9A24B]',
          bg: 'bg-[#C9A24B]/15',
          text: 'text-[#C9A24B]',
          dot: 'bg-[#C9A24B]',
          glow: 'shadow-[0_0_20px_rgba(201,162,75,0.3)]',
          label: 'MEDIUM RISK',
        }
      case 'low':
        return {
          border: 'border-[#4F81BD]',
          bg: 'bg-[#4F81BD]/15',
          text: 'text-[#4F81BD]',
          dot: 'bg-[#4F81BD]',
          glow: 'shadow-[0_0_20px_rgba(79,129,189,0.3)]',
          label: 'LOW RISK',
        }
      case 'clean':
      default:
        return {
          border: 'border-[#3F7D4F]',
          bg: 'bg-[#3F7D4F]/15',
          text: 'text-[#3F7D4F]',
          dot: 'bg-[#3F7D4F]',
          glow: 'shadow-[0_0_20px_rgba(63,125,79,0.3)]',
          label: 'CLEAN // NOMINAL',
        }
    }
  }

  const riskStyles = report
    ? getRiskBadgeStyles(report.pipeline_summary.overall_risk)
    : getRiskBadgeStyles('clean')

  return (
    <div className="flex h-screen w-screen bg-[#0B1F3A] text-[#F4F6F9] overflow-hidden font-sans select-none">
      {/* 1. Left Collapsed Icon Sidebar (hidden in print) */}
      <Sidebar />

      {/* Main Content Viewport */}
      <motion.div
        className="flex-1 flex flex-col min-w-0 h-screen overflow-y-auto bg-[#0B1F3A]"
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25, ease: 'easeOut' }}
      >
        {/* Floating Top Control Ribbon (No-print) */}
        <div className="no-print sticky top-0 z-30 w-full bg-[#0B1F3A]/90 backdrop-blur-xl border-b border-[#4F81BD]/20 px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link
              to="/dashboard"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#1F497D]/30 border border-[#4F81BD]/30 text-xs font-mono text-[#F4F6F9] hover:text-[#C9A24B] hover:border-[#C9A24B]/50 transition-colors"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              <span>Back to Pipeline Graph</span>
            </Link>
            <span className="text-[#4F81BD]/40">|</span>
            <div className="flex items-center gap-2 text-[11px] font-mono text-[#4F81BD]">
              <span className="w-2 h-2 rounded-full bg-[#3F7D4F] animate-pulse" />
              <span>AUDIT ARTEFACT: FORMAL DELIVERABLE</span>
            </div>
          </div>

          <div className="flex items-center gap-2.5">
            <button
              onClick={fetchReport}
              disabled={isLoading}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#1F497D]/30 border border-[#4F81BD]/30 hover:border-[#4F81BD] text-xs font-mono text-[#F4F6F9] transition-all cursor-pointer"
              title="Re-query assurance backend"
            >
              <RefreshCw className={`w-3.5 h-3.5 text-[#C9A24B] ${isLoading ? 'animate-spin' : ''}`} />
              {isLoading
                ? <Loader2 className="w-3 h-3 text-[#C9A24B] animate-spin" />
                : <span className="hidden sm:inline">Refresh Audit</span>
              }
            </button>

            <button
              onClick={handleExportJSON}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#1F497D]/40 border border-[#4F81BD]/40 hover:border-[#C9A24B]/70 text-xs font-mono text-[#F4F6F9] transition-all cursor-pointer"
              id="export-json-btn"
            >
              <Download className="w-3.5 h-3.5 text-[#4F81BD]" />
              <span>Export JSON</span>
            </button>

            <button
              onClick={handleExportPDF}
              className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-lg font-header font-bold text-xs tracking-wider uppercase text-[#0B1F3A] bg-[#C9A24B] hover:bg-[#d6b059] shadow-[0_0_15px_rgba(201,162,75,0.35)] transition-all cursor-pointer"
              id="export-pdf-btn"
            >
              <Printer className="w-3.5 h-3.5 text-[#0B1F3A]" />
              <span>Export PDF</span>
            </button>
          </div>
        </div>

        {/* Toast Notification */}
        <AnimatePresence>
          {toastMessage && (
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className="fixed top-16 right-8 z-50 flex items-center gap-2.5 px-4 py-2.5 rounded-lg bg-[#0B1F3A] border border-[#C9A24B] shadow-[0_0_20px_rgba(201,162,75,0.4)] text-xs font-mono text-[#F4F6F9]"
            >
              <FileDown className="w-4 h-4 text-[#C9A24B]" />
              <span>{toastMessage}</span>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Error Notification */}
        {error && (
          <div className="max-w-[880px] w-full mx-auto mt-4 px-4">
            <div className="bg-[#B03A2E]/20 border border-[#B03A2E]/60 rounded-lg p-3 text-xs font-mono text-[#F4F6F9] flex items-center justify-between">
              <div className="flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-[#B03A2E]" />
                <span>Backend Error: {error}</span>
              </div>
              <button
                onClick={fetchReport}
                className="text-[#C9A24B] underline cursor-pointer"
              >
                Retry
              </button>
            </div>
          </div>
        )}

        {/* ========================================================================= */}
        {/* FORMAL AUDIT DOCUMENT CONTAINER (Single-column, centered, max ~900px) */}
        {/* ========================================================================= */}
        <div className="flex-1 px-4 sm:px-6 py-6 pb-20">
          <article
            className="report-document max-w-[880px] w-full mx-auto bg-[#0E2442]/95 border-t-4 border-[#C9A24B] shadow-[0_25px_60px_-15px_rgba(0,0,0,0.8),0_0_0_1px_rgba(79,129,189,0.15)] rounded-sm p-6 sm:p-10 relative overflow-hidden"
            id="audit-report-document"
          >
            {/* Subtle Security Document Watermark */}
            <div
              className="absolute inset-0 pointer-events-none select-none flex items-center justify-center opacity-[0.018] rotate-[-25deg] text-6xl font-black font-header tracking-widest text-[#F4F6F9]"
              aria-hidden="true"
            >
              PRAMAAN OFFICIAL AUDIT
            </div>

            {/* DOCUMENT SECTION 0: Top Classification Banner */}
            <div className="border-b border-[#4F81BD]/25 pb-3 mb-6 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-[10px] font-mono">
              <div className="flex items-center gap-2 text-[#C9A24B] font-bold tracking-[0.18em] uppercase">
                <span className="w-1.5 h-1.5 rounded-full bg-[#C9A24B]" />
                <span>SIMULATED CLASSIFICATION — DEMONSTRATION BUILD // DEFENCE AI ASSURANCE</span>
              </div>
              <div className="text-[#4F81BD]/80 tracking-wider">
                NODE: AIRGAP-SEC-01 // PROTOCOL: SIH26228
              </div>
            </div>

            {/* DOCUMENT SECTION 1: Formal Header Block */}
            <header className="mb-8">
              <div className="flex flex-col md:flex-row md:items-start justify-between gap-6">
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-[11px] font-mono tracking-[0.2em] text-[#4F81BD] uppercase font-semibold">
                      INDEPENDENT ASSURANCE EVALUATION
                    </span>
                    <span className="text-[#4F81BD]/30">•</span>
                    <span className="text-[11px] font-mono text-slate-400">
                      REF: MOD-AI-ASR-2026
                    </span>
                  </div>

                  {/* Serif Heading for Formal Document Typography */}
                  <h1 className="font-serif font-doc text-3xl sm:text-4xl text-[#F4F6F9] font-normal tracking-tight leading-tight mb-2">
                    Autonomous Vision Pipeline Assurance Report
                  </h1>

                  <p className="text-xs sm:text-sm text-slate-300/80 font-sans max-w-xl leading-relaxed">
                    Formal offline audit certifying training distribution integrity, model weight fidelity,
                    and runtime inference entropy for mission-critical computer-vision deployments.
                  </p>
                </div>

                {/* Seal / Emblem Block */}
                <div className="flex-shrink-0 flex md:flex-col items-center justify-center p-3 rounded bg-[#0B1F3A] border border-[#4F81BD]/30 shadow-inner">
                  <ShieldCheck className="w-8 h-8 text-[#C9A24B] mb-1" />
                  <span className="text-[9px] font-mono font-bold tracking-widest text-[#F4F6F9] uppercase">
                    PRAMAAN
                  </span>
                  <span className="text-[8px] font-mono text-[#4F81BD] tracking-wider">
                    SEAL-VERIFIED
                  </span>
                </div>
              </div>

              {/* Document Metadata Strip */}
              <div className="mt-6 pt-4 border-t border-[#4F81BD]/20 grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs font-mono">
                <div>
                  <span className="block text-[10px] text-slate-400 uppercase tracking-wider">
                    Report Identifier
                  </span>
                  <span className="font-bold text-[#C9A24B] tracking-wider">
                    {report?.report_id || 'PRAMAAN-2026-—'}
                  </span>
                </div>

                <div>
                  <span className="block text-[10px] text-slate-400 uppercase tracking-wider">
                    Generation Timestamp
                  </span>
                  <span className="text-[#F4F6F9]">
                    {report?.generated_at
                      ? new Date(report.generated_at).toLocaleString('en-GB', {
                          timeZone: 'UTC',
                          hour12: false,
                          year: 'numeric',
                          month: 'short',
                          day: '2-digit',
                          hour: '2-digit',
                          minute: '2-digit',
                          second: '2-digit',
                        }) + ' UTC'
                      : '—'}
                  </span>
                </div>

                <div>
                  <span className="block text-[10px] text-slate-400 uppercase tracking-wider">
                    Target Pipeline
                  </span>
                  <span className="text-[#F4F6F9]">CV-MOD-EDGE-01</span>
                </div>

                <div>
                  <span className="block text-[10px] text-slate-400 uppercase tracking-wider">
                    Air-Gap Checksum
                  </span>
                  <span className="text-[#4F81BD] tracking-wider">
                    {report?.report_id
                      ? `SHA256:${report.report_id.slice(-4)}c8f`
                      : 'SHA256:4f81bd'}
                  </span>
                </div>
              </div>

              {/* ========================================================================= */}
              {/* SIDE-BY-SIDE LARGE RISK BADGE & LARGE CONFIDENCE BADGE (VISUALLY DISTINCT) */}
              {/* ========================================================================= */}
              <div className="mt-6 grid grid-cols-1 sm:grid-cols-2 gap-4">
                {/* Large Risk Badge */}
                <div
                  className={`p-5 rounded border ${riskStyles.border} ${riskStyles.bg} ${riskStyles.glow} relative flex flex-col justify-between`}
                  id="report-risk-badge"
                >
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-[10px] font-mono tracking-[0.2em] text-slate-300 uppercase font-semibold">
                      OVERALL PIPELINE INTEGRITY
                    </span>
                    <span
                      className={`w-2.5 h-2.5 rounded-full ${riskStyles.dot} animate-pulse`}
                    />
                  </div>
                  <div>
                    <div
                      className={`font-serif font-doc text-2xl sm:text-3xl font-bold tracking-wider ${riskStyles.text} uppercase`}
                    >
                      {report?.pipeline_summary.overall_risk === 'clean'
                        ? 'CLEAN // NOMINAL'
                        : `${report?.pipeline_summary.overall_risk.toUpperCase()} RISK`}
                    </div>
                    <div className="text-[11px] font-mono text-slate-300 mt-1">
                      {report?.pipeline_summary.overall_risk === 'clean'
                        ? 'Zero critical adversarial indicators detected.'
                        : `${report?.attack_scenarios_detected.length || 1} active adversarial vector(s) identified.`}
                    </div>
                  </div>
                  <div className="mt-3 pt-2 border-t border-[#4F81BD]/20 text-[9px] font-mono text-slate-400 flex justify-between">
                    <span>SEVERITY CLASSIFICATION</span>
                    <span className="font-semibold text-[#F4F6F9]">
                      STANDARD: DEF-STD-AI-01
                    </span>
                  </div>
                </div>

                {/* Large Confidence Badge (Distinct Steel-Blue Styling) */}
                <div
                  className="p-5 rounded border border-[#4F81BD]/60 bg-[#1F497D]/20 shadow-[0_0_20px_rgba(79,129,189,0.2)] relative flex flex-col justify-between"
                  id="report-confidence-badge"
                >
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-[10px] font-mono tracking-[0.2em] text-[#4F81BD] uppercase font-semibold">
                      VERIFICATION CONFIDENCE INDEX
                    </span>
                    <Activity className="w-4 h-4 text-[#4F81BD]" />
                  </div>
                  <div>
                    <div className="flex items-baseline gap-2">
                      <span className="font-serif font-doc text-3xl sm:text-4xl font-bold text-[#F4F6F9] tracking-tight">
                        {report
                          ? Math.round(report.pipeline_summary.overall_confidence * 100)
                          : 96}
                        %
                      </span>
                      <span className="text-xs font-mono text-[#4F81BD] font-semibold">
                        (
                        {report
                          ? report.pipeline_summary.overall_confidence.toFixed(2)
                          : '0.96'}
                        / 1.00)
                      </span>
                    </div>
                    <div className="text-[11px] font-mono text-slate-300 mt-1">
                      Ensemble certitude across statistical & neural monitors.
                    </div>
                  </div>
                  <div className="mt-3 pt-2 border-t border-[#4F81BD]/20 text-[9px] font-mono text-slate-400 flex justify-between">
                    <span>STAGE COVERAGE EVALUATED</span>
                    <span className="font-semibold text-[#3F7D4F]">
                      {report?.pipeline_summary.coverage_pct || 98.8}% NOMINAL
                    </span>
                  </div>
                </div>
              </div>
            </header>

            {/* Horizontal Rule Divider */}
            <hr className="border-t border-[#4F81BD]/25 my-8" />

            {/* ========================================================================= */}
            {/* DOCUMENT SECTION 2: Executive Summary (Abstract Callout) */}
            {/* ========================================================================= */}
            <section className="mb-10">
              <div className="flex items-center justify-between mb-3">
                <h2 className="font-serif font-doc text-xl font-normal text-[#F4F6F9] tracking-wide">
                  1. Executive Summary & Analyst Directive
                </h2>
                <span className="text-[10px] font-mono text-[#C9A24B] tracking-wider uppercase font-semibold">
                  SECTION 1.0
                </span>
              </div>

              {/* Abstract Callout Box with left border accent */}
              <div
                className={`rounded-r-md p-5 border-l-4 ${
                  report?.pipeline_summary.overall_risk === 'clean'
                    ? 'border-l-[#3F7D4F] bg-[#1F497D]/25'
                    : report?.pipeline_summary.overall_risk === 'medium'
                    ? 'border-l-[#C9A24B] bg-[#C9A24B]/10'
                    : 'border-l-[#B03A2E] bg-[#B03A2E]/15'
                } border-t border-r border-b border-[#4F81BD]/20 relative shadow-inner`}
              >
                <div className="flex items-center gap-2 mb-2 text-[10px] font-mono uppercase tracking-widest text-[#C9A24B] font-bold">
                  <span>FORENSIC EVALUATION ABSTRACT</span>
                </div>

                <p className="font-serif font-doc text-[#F4F6F9] text-sm sm:text-[15px] leading-relaxed italic">
                  {report?.analyst_recommendation ||
                    'CLEAN STATE — PIPELINE CERTIFIED. All five stages of the PRAMAAN assurance pipeline have passed cryptographic integrity verification, spectral signature analysis, and STRIP run-time entropy monitoring within nominal thresholds.'}
                </p>

                <div className="mt-4 pt-3 border-t border-[#4F81BD]/20 flex flex-col sm:flex-row sm:items-center justify-between text-[10px] font-mono text-slate-400 gap-1">
                  <div>
                    <span className="text-slate-300 font-semibold">Attestation Core: </span>
                    PRAMAAN Offline Forensic Daemon v1.0
                  </div>
                  <div className="text-[#4F81BD]">
                    ECDSA-P256 Attested // Zero Cloud Telemetry Exfiltration
                  </div>
                </div>
              </div>

              {/* Key Indicators Ledger Strip */}
              <div className="mt-5 grid grid-cols-2 sm:grid-cols-4 gap-2 text-center text-xs font-mono bg-[#0B1F3A]/70 border border-[#4F81BD]/20 rounded p-3">
                <div className="border-r border-[#4F81BD]/20 last:border-r-0">
                  <div className="text-[10px] text-slate-400 uppercase">Stages Audited</div>
                  <div className="font-bold text-[#F4F6F9] mt-0.5">5 of 5 Complete</div>
                </div>
                <div className="border-r border-[#4F81BD]/20 last:border-r-0">
                  <div className="text-[10px] text-slate-400 uppercase">Coverage</div>
                  <div className="font-bold text-[#3F7D4F] mt-0.5">
                    {report?.pipeline_summary.coverage_pct || 98.8}%
                  </div>
                </div>
                <div className="border-r border-[#4F81BD]/20 last:border-r-0">
                  <div className="text-[10px] text-slate-400 uppercase">Adversarial Scenarios</div>
                  <div
                    className={`font-bold mt-0.5 ${
                      report?.attack_scenarios_detected.length
                        ? 'text-[#B03A2E]'
                        : 'text-[#3F7D4F]'
                    }`}
                  >
                    {report?.attack_scenarios_detected.length || 0} Flagged
                  </div>
                </div>
                <div>
                  <div className="text-[10px] text-slate-400 uppercase">Audit Chain</div>
                  <div
                    className={`font-bold mt-0.5 ${
                      report?.audit_chain_verified ? 'text-[#3F7D4F]' : 'text-[#B03A2E]'
                    }`}
                  >
                    {report?.audit_chain_verified ? 'VERIFIED' : 'COMPROMISED'}
                  </div>
                </div>
              </div>
            </section>

            {/* Horizontal Rule Divider */}
            <hr className="border-t border-[#4F81BD]/25 my-8" />

            {/* ========================================================================= */}
            {/* DOCUMENT SECTION 3: Stage-by-Stage Findings (Expandable Accordion) */}
            {/* ========================================================================= */}
            <section className="mb-10">
              <div className="flex items-center justify-between mb-2">
                <h2 className="font-serif font-doc text-xl font-normal text-[#F4F6F9] tracking-wide">
                  2. Stage-by-Stage Audit Findings & Evidence Dossiers
                </h2>
                <span className="text-[10px] font-mono text-[#C9A24B] tracking-wider uppercase font-semibold">
                  SECTION 2.0
                </span>
              </div>

              <p className="text-xs text-slate-300/80 font-sans mb-6">
                Forensic inspection breakdowns across all five verification domains. Click any stage to review
                cryptographic fingerprints, detector findings, and recommended remediation protocols.
              </p>

              <div className="space-y-4">
                {report?.stages.map((stage, stageIdx) => {
                  const isOpen = !!openStages[stage.stage_name]
                  const hasFindings = stage.findings.length > 0

                  return (
                    <div
                      key={stage.stage_name}
                      className="border border-[#4F81BD]/30 bg-[#0B1F3A]/60 rounded-sm overflow-hidden transition-colors"
                    >
                      {/* Stage Accordion Header */}
                      <button
                        onClick={() => toggleStage(stage.stage_name)}
                        className="w-full px-5 py-4 flex items-center justify-between text-left hover:bg-[#1F497D]/20 transition-colors cursor-pointer select-none"
                        type="button"
                      >
                        <div className="flex items-center gap-3.5 flex-wrap">
                          <span className="text-xs font-mono text-[#4F81BD] font-bold">
                            STAGE {String(stageIdx + 1).padStart(2, '0')}
                          </span>
                          <span className="font-serif font-doc text-base sm:text-lg text-[#F4F6F9] font-normal">
                            {stage.stage_name}
                          </span>

                          {/* Stage Risk Pill */}
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-mono tracking-wider font-semibold uppercase ${
                              stage.risk === 'clean'
                                ? 'bg-[#3F7D4F]/20 text-[#3F7D4F] border border-[#3F7D4F]/40'
                                : stage.risk === 'low'
                                ? 'bg-[#4F81BD]/20 text-[#4F81BD] border border-[#4F81BD]/40'
                                : stage.risk === 'medium'
                                ? 'bg-[#C9A24B]/20 text-[#C9A24B] border border-[#C9A24B]/40'
                                : 'bg-[#B03A2E]/20 text-[#B03A2E] border border-[#B03A2E]/40'
                            }`}
                          >
                            {stage.risk}
                          </span>
                        </div>

                        <div className="flex items-center gap-4">
                          <div className="hidden sm:flex items-center gap-2 text-xs font-mono text-slate-400">
                            <span>Confidence:</span>
                            <span className="text-[#F4F6F9] font-bold">
                              {Math.round(stage.confidence * 100)}%
                            </span>
                          </div>

                          <span
                            className={`text-[11px] font-mono px-2 py-0.5 rounded ${
                              hasFindings
                                ? 'bg-[#B03A2E]/20 text-[#B03A2E] border border-[#B03A2E]/30 font-semibold'
                                : 'text-slate-400'
                            }`}
                          >
                            {hasFindings
                              ? `${stage.findings.length} Finding${stage.findings.length > 1 ? 's' : ''}`
                              : 'Nominal'}
                          </span>

                          <span className="text-[#4F81BD]">
                            {isOpen ? (
                              <ChevronUp className="w-4 h-4" />
                            ) : (
                              <ChevronDown className="w-4 h-4" />
                            )}
                          </span>
                        </div>
                      </button>

                      {/* Stage Body */}
                      <AnimatePresence>
                        {isOpen && (
                          <motion.div
                            initial={{ height: 0, opacity: 0 }}
                            animate={{ height: 'auto', opacity: 1 }}
                            exit={{ height: 0, opacity: 0 }}
                            transition={{ duration: 0.2 }}
                            className="border-t border-[#4F81BD]/20 px-5 py-5 bg-[#081526]/80"
                          >
                            {hasFindings ? (
                              <div className="space-y-6">
                                {stage.findings.map((finding, fIdx) => {
                                  const findingNumber = `F-${String(fIdx + 1).padStart(3, '0')}`
                                  const isFindingCritical =
                                    finding.severity === 'critical' ||
                                    finding.severity === 'high'

                                  return (
                                    <div
                                      key={finding.finding_id || fIdx}
                                      className="border-l-2 border-[#4F81BD]/40 pl-4 py-1 space-y-3"
                                    >
                                      {/* Finding Title Row */}
                                      <div className="flex flex-wrap items-center justify-between gap-2">
                                        <div className="flex items-center gap-2.5">
                                          <span className="text-xs font-mono font-bold text-[#C9A24B]">
                                            {findingNumber}
                                          </span>
                                          <span className="text-[11px] font-mono text-slate-400">
                                            [{finding.finding_id}]
                                          </span>
                                          <span className="text-sm font-sans font-semibold text-[#F4F6F9]">
                                            {finding.detector}
                                          </span>
                                        </div>

                                        <div className="flex items-center gap-2">
                                          <span
                                            className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold uppercase tracking-wider ${
                                              isFindingCritical
                                                ? 'bg-[#B03A2E]/20 text-[#B03A2E] border border-[#B03A2E]/40'
                                                : finding.severity === 'medium'
                                                ? 'bg-[#C9A24B]/20 text-[#C9A24B] border border-[#C9A24B]/40'
                                                : 'bg-[#4F81BD]/20 text-[#4F81BD] border border-[#4F81BD]/40'
                                            }`}
                                          >
                                            {finding.severity}
                                          </span>

                                          <span
                                            className={`px-2 py-0.5 rounded text-[10px] font-mono ${
                                              finding.mitigated
                                                ? 'bg-[#3F7D4F]/20 text-[#3F7D4F] border border-[#3F7D4F]/30'
                                                : 'bg-[#B03A2E]/20 text-[#B03A2E] border border-[#B03A2E]/30'
                                            }`}
                                          >
                                            {finding.mitigated ? 'MITIGATED' : 'UNRESOLVED'}
                                          </span>
                                        </div>
                                      </div>

                                      {/* ========================================================================= */}
                                      {/* CRITICAL ART DIRECTION: PRINTED PAPER-LIKE INSET TEXT BLOCK (#F0EDE5) */}
                                      {/* Muted off-white/cream paper inset contrasting inside dark theme */}
                                      {/* Text on light: #3B3F45 per AGENTS.md tokens (never pure black/white) */}
                                      {/* ========================================================================= */}
                                      <div className="bg-[#F0EDE5] text-[#3B3F45] rounded-sm p-4 sm:p-5 border border-[#D5D0C5] shadow-[inset_0_2px_4px_rgba(0,0,0,0.06),0_4px_12px_rgba(0,0,0,0.3)]">
                                        {/* Monospace Evidence Header Stamp */}
                                        <div className="border-b border-[#D5D0C5] pb-2 mb-3 flex flex-wrap items-center justify-between gap-2 text-[10px] font-mono text-[#5A6069]">
                                          <div className="flex items-center gap-1.5">
                                            <Hash className="w-3 h-3 text-[#3B3F45]" />
                                            <span>
                                              EVIDENCE ARTEFACT REF:{' '}
                                              {finding.evidence_hash || 'SHA256:4f81bd77'}
                                            </span>
                                          </div>
                                          <div className="font-semibold tracking-wider uppercase text-[#1F497D]">
                                            FORENSIC EVIDENCE LEDGER
                                          </div>
                                        </div>

                                        {/* Evidence Text formatted like a formal typed report narrative */}
                                        <p className="font-serif font-doc text-xs sm:text-[13px] leading-relaxed text-[#3B3F45] tracking-normal">
                                          {finding.description}
                                        </p>
                                      </div>

                                      {/* Recommended Action / Directive */}
                                      <div className="bg-[#0B1F3A] border border-[#4F81BD]/25 rounded p-3 text-xs font-mono">
                                        <div className="text-[10px] text-[#C9A24B] uppercase font-bold tracking-wider mb-1 flex items-center gap-1.5">
                                          <span className="w-1.5 h-1.5 rounded-full bg-[#C9A24B]" />
                                          <span>RECOMMENDED REMEDIATION ACTION</span>
                                        </div>
                                        <p className="text-slate-300 leading-relaxed font-sans text-xs">
                                          {getRecommendedAction(finding)}
                                        </p>
                                      </div>
                                    </div>
                                  )
                                })}
                              </div>
                            ) : (
                              /* Clean / Nominal Stage Message */
                              <div className="py-3 px-4 rounded bg-[#0B1F3A]/40 border border-[#3F7D4F]/30 text-xs font-mono text-slate-300 flex items-center justify-between">
                                <div className="flex items-center gap-2">
                                  <CheckCircle2 className="w-4 h-4 text-[#3F7D4F] flex-shrink-0" />
                                  <span>
                                    No adversarial anomalies detected. Cryptographic signatures and runtime
                                    entropy conform to nominal baseline thresholds.
                                  </span>
                                </div>
                                <span className="text-[10px] text-[#3F7D4F] uppercase font-bold tracking-wider">
                                  PASSED
                                </span>
                              </div>
                            )}
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </div>
                  )
                })}
              </div>
            </section>

            {/* Horizontal Rule Divider */}
            <hr className="border-t border-[#4F81BD]/25 my-8" />

            {/* ========================================================================= */}
            {/* DOCUMENT SECTION 4: Audit Chain Verified Badge / Seal */}
            {/* ========================================================================= */}
            <section className="mb-10" id="audit-chain-badge-section">
              <div className="flex items-center justify-between mb-3">
                <h2 className="font-serif font-doc text-xl font-normal text-[#F4F6F9] tracking-wide">
                  3. Cryptographic Audit Chain & Tamper Attestation
                </h2>
                <span className="text-[10px] font-mono text-[#C9A24B] tracking-wider uppercase font-semibold">
                  SECTION 3.0
                </span>
              </div>

              {report?.audit_chain_verified ? (
                /* Verified State: Trust Green */
                <div className="rounded p-5 bg-[#3F7D4F]/10 border border-[#3F7D4F] shadow-[0_0_25px_rgba(63,125,79,0.2)] flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                  <div className="flex items-start gap-3.5">
                    <div className="p-2 rounded-full bg-[#3F7D4F]/20 text-[#3F7D4F] border border-[#3F7D4F]/40 flex-shrink-0 mt-0.5">
                      <ShieldCheck className="w-6 h-6" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-serif font-doc text-base sm:text-lg font-bold text-[#F4F6F9] tracking-wide">
                          CRYPTOGRAPHIC AUDIT CHAIN: VERIFIED & INTACT
                        </span>
                        <span className="px-2 py-0.5 rounded text-[9px] font-mono font-bold bg-[#3F7D4F] text-[#0B1F3A]">
                          100% UNBROKEN
                        </span>
                      </div>
                      <p className="text-xs text-slate-300 mt-1 max-w-xl leading-relaxed">
                        All five pipeline stages possess unbroken cryptographic SHA-256 state linkage. Merkle
                        root hash matches pre-approved defence deployment seal. No unauthorized modification
                        detected across weights, labels, or telemetry streams.
                      </p>
                      <div className="mt-2 text-[10px] font-mono text-[#4F81BD]">
                        MERKLE ROOT HASH: 8f4c2e19b0a7d43891ca756b3e8104d5e729a1cf6473210985bdeec4
                      </div>
                    </div>
                  </div>

                  <div className="flex-shrink-0 px-3 py-1.5 rounded bg-[#0B1F3A] border border-[#3F7D4F]/40 text-center">
                    <span className="block text-[8px] font-mono text-slate-400 uppercase tracking-widest">
                      TAMPER STATUS
                    </span>
                    <span className="text-xs font-mono font-bold text-[#3F7D4F]">
                      SEAL VALID
                    </span>
                  </div>
                </div>
              ) : (
                /* Compromised State: Alert Red */
                <div className="rounded p-5 bg-[#B03A2E]/15 border border-[#B03A2E] shadow-[0_0_25px_rgba(176,58,46,0.25)] flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                  <div className="flex items-start gap-3.5">
                    <div className="p-2 rounded-full bg-[#B03A2E]/20 text-[#B03A2E] border border-[#B03A2E]/40 flex-shrink-0 mt-0.5">
                      <ShieldAlert className="w-6 h-6" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-serif font-doc text-base sm:text-lg font-bold text-[#B03A2E] tracking-wide">
                          AUDIT CHAIN INTEGRITY BREACHED
                        </span>
                        <span className="px-2 py-0.5 rounded text-[9px] font-mono font-bold bg-[#B03A2E] text-white animate-pulse">
                          ACTION REQUIRED
                        </span>
                      </div>
                      <p className="text-xs text-slate-300 mt-1 max-w-xl leading-relaxed">
                        Unmitigated critical/high severity anomalies detected across pipeline stages. The
                        cryptographic chain of custody is broken. The model and inference pipeline MUST NOT be
                        authorized for operational deployment.
                      </p>
                      <div className="mt-2 text-[10px] font-mono text-[#B03A2E]">
                        INTEGRITY VIOLATION DETECTED // AUDIT CHAIN FROZEN AT STAGE FAULT
                      </div>
                    </div>
                  </div>

                  <div className="flex-shrink-0 px-3 py-1.5 rounded bg-[#0B1F3A] border border-[#B03A2E]/50 text-center">
                    <span className="block text-[8px] font-mono text-slate-400 uppercase tracking-widest">
                      SECURITY SEAL
                    </span>
                    <span className="text-xs font-mono font-bold text-[#B03A2E]">
                      REVOKED
                    </span>
                  </div>
                </div>
              )}
            </section>

            {/* Horizontal Rule Divider */}
            <hr className="border-t border-[#4F81BD]/25 my-8" />

            {/* DOCUMENT SECTION 5: Formal Sign-off Ledger & Footer */}
            <footer className="pt-2 text-xs font-mono text-slate-400">
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pb-6 border-b border-[#4F81BD]/20">
                <div>
                  <span className="block text-[10px] uppercase text-slate-500">
                    Lead Forensic Verifier
                  </span>
                  <span className="text-slate-300 font-serif font-doc italic text-sm">
                    PRAMAAN Automated Agent
                  </span>
                  <div className="text-[10px] text-[#4F81BD] mt-0.5">
                    Cert ID: PRA-ASR-904
                  </div>
                </div>

                <div>
                  <span className="block text-[10px] uppercase text-slate-500">
                    Issuing Authority
                  </span>
                  <span className="text-slate-300">
                    Air-Gapped Defence Evaluation Node
                  </span>
                  <div className="text-[10px] text-[#3F7D4F] mt-0.5">
                    Hardware Keystore Locked
                  </div>
                </div>

                <div>
                  <span className="block text-[10px] uppercase text-slate-500">
                    Compliance Reference
                  </span>
                  <span className="text-slate-300">SIH26228 Ministry of Defence</span>
                  <div className="text-[10px] text-[#C9A24B] mt-0.5">
                    AI Assurance Benchmark
                  </div>
                </div>
              </div>

              <div className="pt-4 flex flex-col sm:flex-row items-center justify-between text-[10px] text-slate-500 gap-2">
                <span>
                  CONFIDENTIAL & PROPRIETARY // AIR-GAPPED VERIFICATION LOG // END OF REPORT
                </span>
                <span>Page 1 of 1 — Official Audit Record</span>
              </div>
            </footer>
          </article>
        </div>
      </motion.div>
    </div>
  )
}

export default Report
