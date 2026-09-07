# PRAMAAN — Offline AI Assurance Platform

PRAMAAN (SIH26228, Ministry of Defence theme) is an offline assurance dashboard for computer-vision AI pipelines. It gives a defence analyst cryptographic evidence — not just a pass/fail verdict — about whether training data, model weights, and inference telemetry can be trusted. The frontend is built with React + Vite + TailwindCSS + Three.js and the backend with FastAPI serving fixture-driven telemetry for demonstration. All verification runs air-gapped; no data leaves the local network boundary.

**Screens:** 3D Pipeline Hero → Dashboard → Assurance Report → Immutable Audit Chain → PRAMAAN Copilot (offline AI analyst)

**Start:** `cd backend && uvicorn app.main:app --reload` then `cd frontend && npm run dev`
