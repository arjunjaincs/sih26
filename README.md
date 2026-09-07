# PRAMAAN — Offline AI Assurance Platform

> **Air-gapped AI assurance dashboard for computer-vision pipelines (Ministry of Defence theme).**  
> Cryptographic evidence, tamper verification, and telemetry audit across the complete model lifecycle.

---

## Overview

**PRAMAAN** provides defence analysts and mission operators with cryptographic certainty — not just a pass/fail score — regarding the integrity of computer-vision AI systems. It monitors, audits, and proves non-parametric integrity across five distinct pipeline stages:

1. **Training Data Hygiene** — Poisoning detection, spectral signature analysis, label noise bounds
2. **Model Architecture & Weights** — Neural backdoor detection, weight hash verification, trojan trigger scans
3. **Inference Telemetry** — Adversarial perturbation detection, latency profiling, out-of-distribution drift
4. **Evidence & Threat Scoring** — Bayesian risk aggregation, cross-stage correlation, security verdicts
5. **Assurance & Merkle Audit** — Immutable Merkle tree attestation, tamper detection, exportable mission reports

All verification runs **fully offline / air-gapped**; zero telemetry or model data leaves the local secure environment.

---

## Core Features

- **Interactive 3D Pipeline Topology:** Hardware-accelerated Three.js visualizer rendering realtime node status and interconnects.
- **Assurance Dashboard:** Clickable pipeline stages with slide-in evidence panels detailing mathematical bounds, cryptographic hashes, and statistical distributions.
- **Interactive Attack Scenarios:** Trigger live demo scenarios (Clean Baseline, Backdoor Poisoning, FGSM Adversarial Evasion, Model Extraction, Multi-Stage APT, Distribution Drift) to observe live pipeline reactions.
- **Tamper-Evident Merkle Audit Chain:** Cryptographic tree hashing with an interactive tamper simulator demonstrating immediate detection of compromised pipeline blocks.
- **Formal Assurance Report:** Printable, audit-compliant technical reports with SHA-256 signatures, analyst sign-off, and findings breakdown.
- **PRAMAAN Copilot:** Grounded natural-language terminal answering analyst queries strictly based on current session cryptographic evidence.

---

## Architecture

```
sih26/
├── backend/                  # FastAPI Python backend
│   ├── app/
│   │   ├── fixtures/         # Clean & compromised scenario telemetry
│   │   ├── models/           # Pydantic schemas (Pipeline, Stages, Audit)
│   │   ├── routers/          # API endpoints (/pipeline, /audit, /report)
│   │   └── services/         # State management & scenario engine
│   ├── tests/                # Pytest test suite
│   ├── pytest.ini
│   └── requirements.txt
├── frontend/                 # React 19 + Vite + TypeScript frontend
│   ├── src/
│   │   ├── components/       # 3D views, dashboard cards, modal controls
│   │   ├── pages/            # Hero, Dashboard, Report, Audit Chain, Copilot
│   │   ├── store/            # Zustand global state store
│   │   └── types/            # TypeScript type definitions
│   ├── index.html
│   ├── package.json
│   └── vite.config.ts
├── start.bat                 # One-click Windows server launcher
└── README.md
```

---

## Quick Start

### Option 1: Automatic Launch (Windows)

Double-click `start.bat` or run:

```cmd
start.bat
```

This launches both the FastAPI backend (`http://localhost:8000`) and the Vite frontend (`http://localhost:5173`) in separate terminal windows.

---

### Option 2: Manual Launch

#### 1. Backend Setup (FastAPI)

```bash
cd backend
python -m venv venv
venv\Scripts\activate       # On Windows (or 'source venv/bin/activate' on Linux/macOS)
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

- **Backend API:** [http://localhost:8000](http://localhost:8000)
- **API Documentation:** [http://localhost:8000/docs](http://localhost:8000/docs)

#### 2. Frontend Setup (Vite + React)

```bash
cd frontend
npm install
npm run dev
```

- **Web Dashboard:** [http://localhost:5173](http://localhost:5173)

---

## Verification & Tests

### Backend Tests
```bash
cd backend
venv\Scripts\activate
pytest
```

### Frontend Typecheck & Build
```bash
cd frontend
npm run build
```

---

## License

Internal defence / academic research evaluation.
