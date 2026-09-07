import { BrowserRouter, Routes, Route, Link } from 'react-router-dom'
import PipelineHero from './components/3d/PipelineHero'
import Dashboard from './pages/Dashboard'
import Report from './pages/Report'
import AuditChain from './pages/AuditChain'
import Copilot from './pages/Copilot'
import NotFound from './pages/NotFound'
import { ShieldCheck, ArrowRight } from 'lucide-react'

function HeroPage() {
  return (
    <div className="min-h-screen bg-pramaan-navy text-pramaan-text-dark font-sans overflow-hidden flex flex-col relative">
      {/* Top Header Overlay */}
      <header className="absolute top-0 left-0 w-full z-20 px-8 py-5 flex justify-between items-center bg-gradient-to-b from-pramaan-navy via-pramaan-navy/60 to-transparent pointer-events-none">
        <div className="flex items-center gap-3.5 pointer-events-auto">
          <div className="p-2 rounded-lg bg-pramaan-navy-header/40 border border-pramaan-gold/30 backdrop-blur-md shadow-[0_0_12px_rgba(201,162,75,0.25)]">
            <ShieldCheck className="w-6 h-6 text-pramaan-gold" />
          </div>
          <div>
            <h1 className="text-xl font-header font-bold tracking-[0.15em] text-pramaan-text-dark">
              PRAMAAN
            </h1>
            <p className="text-[10px] font-mono text-pramaan-steelblue tracking-[0.2em] uppercase">
              Offline AI Assurance Platform
            </p>
          </div>
        </div>

        <div className="flex items-center pointer-events-auto">
          <div className="flex items-center gap-2 text-[11px] font-mono bg-pramaan-navy-header/40 backdrop-blur-md border border-pramaan-steelblue/30 px-3.5 py-1.5 rounded-full shadow-lg">
            <span className="w-2 h-2 rounded-full bg-pramaan-green shadow-[0_0_8px_rgba(63,125,79,0.9)] animate-pulse"></span>
            <span className="text-[#F4F6F9]/80">TELEMETRY ACTIVE</span>
          </div>
        </div>
      </header>

      {/* Main 3D Hero Scene */}
      <main className="flex-1 relative cursor-grab active:cursor-grabbing w-full h-full">
        <PipelineHero />

        {/* Integrated Typography with strict vertical rhythm */}
        <div className="absolute top-20 left-0 right-0 pointer-events-none flex flex-col items-center justify-center text-center px-4 z-10">
          <div className="max-w-2xl flex flex-col items-center">
            {/* Badge */}
            <div className="inline-flex items-center gap-2 px-3.5 py-1 rounded-full border border-pramaan-gold/35 bg-pramaan-navy/60 backdrop-blur-md text-pramaan-gold text-[10px] font-mono tracking-[0.2em] uppercase mb-3.5 shadow-[0_2px_12px_rgba(0,0,0,0.4)]">
              <span className="w-1.5 h-1.5 rounded-full bg-pramaan-gold animate-pulse"></span>
              Autonomous Pipeline Assurance
            </div>

            {/* Heading */}
            <h2 className="text-4xl md:text-5xl font-header font-black tracking-tight text-transparent bg-clip-text bg-gradient-to-b from-white via-slate-100 to-pramaan-steelblue mb-3.5 drop-shadow-[0_4px_24px_rgba(0,0,0,0.95)]">
              End-to-End AI Assurance
            </h2>

            {/* Subtext */}
            <p className="text-sm md:text-base text-slate-300/80 font-normal tracking-wide leading-relaxed max-w-xl mx-auto drop-shadow-[0_2px_10px_rgba(0,0,0,0.95)] mb-5">
              Continuous cryptographic verification of training distributions, model weights, and inference telemetry for mission-critical vision pipelines.
            </p>

            <Link
              to="/dashboard"
              className="pointer-events-auto inline-flex items-center gap-2.5 px-6 py-2.5 rounded-xl font-header font-bold text-xs tracking-wider uppercase text-[#0B1F3A] bg-[#C9A24B] hover:bg-[#d6b059] shadow-[0_0_20px_rgba(201,162,75,0.4)] transition-all hover:scale-105"
            >
              <span>Access Assurance Dashboard</span>
              <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        </div>
      </main>
    </div>
  )
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<HeroPage />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/report" element={<Report />} />
        <Route path="/audit-chain" element={<AuditChain />} />
        <Route path="/copilot" element={<Copilot />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
