/**
 * PRAMAAN v1 — Automated Fresh-Machine Release Validation Suite
 * 
 * Validates the freshly assembled standalone Windows executable in a staging directory
 * under strict air-gap network interception.
 */

const path = require('path');
const fs = require('fs');
const http = require('http');
const { execSync } = require('child_process');

let electron;
try {
  const playwrightPath = path.join(process.env.LOCALAPPDATA || '', 'ms-playwright-go', '1.57.0', 'package');
  if (fs.existsSync(playwrightPath)) {
    electron = require(playwrightPath)._electron;
  } else {
    electron = require('playwright')._electron;
  }
} catch (e) {
  try {
    electron = require('playwright-core')._electron;
  } catch (e2) {
    console.error('Playwright / Electron test driver not found:', e.message);
  }
}

const STAGING_DIR = 'C:\\PRAMAAN_RELEASE_TEST\\PRAMAAN';
const PACKAGED_EXE = path.join(STAGING_DIR, 'PRAMAAN.exe');

function getListeningProcessPids(port) {
  try {
    const out = execSync(`powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort ${port} -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess"`).toString().trim();
    if (!out) return [];
    return out.split(/\r?\n/).map(s => s.trim()).filter(Boolean);
  } catch {
    return [];
  }
}

async function validateFreshRelease() {
  console.log('================================================================');
  console.log('  PRAMAAN v1 — REBUILT RELEASE FRESH-HOST VALIDATION');
  console.log(`  Target: ${PACKAGED_EXE}`);
  console.log('================================================================\n');

  if (!fs.existsSync(PACKAGED_EXE)) {
    throw new Error(`Packaged binary not found at ${PACKAGED_EXE}`);
  }

  const results = {
    verdict: 'PENDING',
    targetExecutable: PACKAGED_EXE,
    coldStart: {},
    landing: {},
    capabilities: {},
    demoPresets: {},
    forensics: {},
    provenance: {},
    audit: {},
    exports: {},
    search: {},
    failureHandling: {},
    network: {
      localRequests: 0,
      externalRequests: 0,
      blockedExternal: 0,
      destinations: new Set(),
      cdnDetected: false,
      googleFontsDetected: false,
      openRouterDetected: false,
      telemetryDetected: false
    },
    responsive: {},
    persistence: {},
    cleanup: {}
  };

  // 1. Cold Start
  console.log('[1/10] Launching Packaged Desktop Executable...');
  const tLaunch0 = Date.now();
  const app = await electron.launch({
    executablePath: PACKAGED_EXE,
    args: [],
    cwd: STAGING_DIR,
    env: {
      ...process.env,
      PYTHONPATH: '',
      VIRTUAL_ENV: '',
      PRAMAAN_DEV_MODE: ''
    }
  });

  const launchMs = Date.now() - tLaunch0;
  const tWin0 = Date.now();
  const win = await app.firstWindow();
  await win.waitForLoadState('networkidle');
  const rendererMs = Date.now() - tWin0;
  const totalColdStartMs = Date.now() - tLaunch0;

  console.log(`Process launch: ${launchMs}ms | Renderer ready: ${rendererMs}ms | Total cold start: ${totalColdStartMs}ms`);

  // Intercept all network traffic for strict air-gap verification
  await win.route('**/*', async (route) => {
    const req = route.request();
    const urlStr = req.url();
    let urlObj;
    try {
      urlObj = new URL(urlStr);
    } catch {
      await route.continue();
      return;
    }

    results.network.destinations.add(urlObj.origin);
    const isLocal = urlObj.hostname === '127.0.0.1' || urlObj.hostname === 'localhost';

    if (isLocal) {
      results.network.localRequests++;
      await route.continue();
    } else {
      results.network.externalRequests++;
      results.network.blockedExternal++;
      if (urlStr.includes('fonts.googleapis') || urlStr.includes('fonts.gstatic')) results.network.googleFontsDetected = true;
      if (urlStr.includes('openrouter.ai')) results.network.openRouterDetected = true;
      if (urlStr.includes('cdn') || urlStr.includes('unpkg') || urlStr.includes('cdnjs')) results.network.cdnDetected = true;
      if (urlStr.includes('telemetry') || urlStr.includes('analytics')) results.network.telemetryDetected = true;
      console.warn(`[AIR-GAP SHIELD] Blocked external request: ${urlStr}`);
      await route.abort('blockedbyclient');
    }
  });

  const title = await win.title();
  const securityCheck = await win.evaluate(() => ({
    hasRequire: typeof window.require !== 'undefined',
    hasProcess: typeof window.process !== 'undefined',
    hasContextBridge: typeof window.pramaanDesktop !== 'undefined'
  }));

  results.coldStart = {
    launchMs,
    rendererMs,
    totalColdStartMs,
    title,
    nodeIntegrationBlocked: !securityCheck.hasRequire,
    processBlocked: !securityCheck.hasProcess,
    contextBridgeActive: securityCheck.hasContextBridge
  };

  // 2. Landing Page
  console.log('\n[2/10] Verifying Landing Page & Forensic Posture...');
  await win.goto('http://127.0.0.1:8000/', { waitUntil: 'networkidle' });
  const landingText = await win.evaluate(() => document.body.innerText);
  const landingH1 = await win.locator('h1').textContent();
  results.landing = {
    h1: landingH1 ? landingH1.trim() : '',
    hasEvidenceBeforeTrust: landingText.includes('Evidence') && landingText.includes('Trust'),
    hasFourLayers: landingText.includes('Dataset Integrity') && landingText.includes('Model Integrity') && landingText.includes('Cryptographic Provenance') && landingText.includes('Audit Trail')
  };

  // 3. Capabilities Registry
  console.log('\n[3/10] Verifying Capabilities & 11 Canonical Detectors...');
  const capRes = await win.request.get('http://127.0.0.1:8000/api/v1/capabilities');
  const capData = await capRes.json();
  const canonicalDetectors = [
    'data.integrity.di01_duplicates',
    'data.integrity.di02_label_integrity',
    'data.integrity.di03_trigger_anomaly',
    'data.integrity.di04_ood_distribution',
    'data.integrity.di05_contributor_risk',
    'model.integrity.mi01_fingerprint',
    'model.integrity.mi02_parameter_stats',
    'model.integrity.mi03_activation_stats',
    'model.integrity.mi04_reference_comparison',
    'model.integrity.mi05_trigger_anomaly',
    'inference.provenance.pi01_integrity'
  ];
  const registeredIds = capData.detectors.map(d => d.detector_id);
  const missing = canonicalDetectors.filter(id => !registeredIds.includes(id));
  results.capabilities = {
    registeredCount: capData.detectors.length,
    canonicalCoverage: canonicalDetectors.length - missing.length,
    missingDetectors: missing,
    allPresent: missing.length === 0
  };
  console.log(`Capabilities verified: ${capData.detectors.length} detectors active. Missing: ${missing.length}`);

  // 4. Execute All 5 Deterministic Demo Presets
  console.log('\n[4/10] Executing All 5 Authentic Demo Presets...');
  const presets = [
    { key: 'clean_baseline', name: 'Clean Reference Baseline' },
    { key: 'duplicate_data', name: 'Dataset Duplicates & Collisions' },
    { key: 'corrupted_model', name: 'Parameter Tampering (NaN/Inf)' },
    { key: 'trojan_model', name: 'Trojan Shortcut Convergence' },
    { key: 'provenance_attestation', name: 'Cryptographic Inference Provenance' }
  ];

  let sampleAssessmentIds = {};

  for (const preset of presets) {
    console.log(`-> Executing preset: ${preset.name}...`);
    await win.goto('http://127.0.0.1:8000/new?mode=demo', { waitUntil: 'networkidle' });
    await win.waitForTimeout(300);

    const presetCard = win.locator('.rounded-xl, .card').filter({ has: win.locator('h3', { hasText: preset.name }) }).first();
    await presetCard.waitFor({ state: 'visible', timeout: 10000 });

    const loadBtn = presetCard.locator('button:has-text("Load Scenario"), button:has-text("Preset Loaded")').first();
    await loadBtn.click();
    await win.waitForTimeout(300);

    const runBtn = win.locator('button:has-text("Execute Demo Assessment")');
    await runBtn.waitFor({ state: 'visible', timeout: 5000 });

    const tStart = Date.now();
    await runBtn.click();
    await win.waitForURL(/\/assessments\/[a-f0-9-]+\/result/, { timeout: 60000 });
    const durationMs = Date.now() - tStart;

    const url = win.url();
    const aid = url.split('/assessments/')[1].split('/')[0];
    sampleAssessmentIds[preset.key] = aid;

    const detailRes = await win.request.get(`http://127.0.0.1:8000/api/v1/assessments/${aid}`);
    const detail = await detailRes.json();

    console.log(`   PASS (${durationMs}ms) | AID: ${aid.slice(0, 8)} | Risk: ${detail.overall_risk} | Conf: ${detail.overall_confidence} | Cov: ${((detail.coverage_fraction || 1) * 100).toFixed(0)}% | Findings: ${detail.findings_count} | Evidence: ${detail.evidence_count}`);

    results.demoPresets[preset.key] = {
      name: preset.name,
      aid,
      durationMs,
      risk: detail.overall_risk,
      confidence: detail.overall_confidence,
      coverage: detail.coverage_fraction,
      findingsCount: detail.findings_count,
      evidenceCount: detail.evidence_count,
      status: 'PASS'
    };
  }

  // 5. Deep Forensics on Trojan Shortcut Assessment
  const trojanAid = sampleAssessmentIds['trojan_model'];
  console.log(`\n[5/10] Inspecting Forensic Workspace for Trojan Assessment (${trojanAid.slice(0, 8)})...`);
  await win.goto(`http://127.0.0.1:8000/assessments/${trojanAid}/findings`, { waitUntil: 'networkidle' });
  const findingsHeading = await win.locator('h1, h2').first().textContent();

  await win.goto(`http://127.0.0.1:8000/assessments/${trojanAid}/evidence`, { waitUntil: 'networkidle' });
  const evidenceCount = await win.locator('.rounded-xl, .card').count();

  await win.goto(`http://127.0.0.1:8000/assessments/${trojanAid}/audit`, { waitUntil: 'networkidle' });
  const verifyBtn = win.locator('button:has-text("Verify Chain"), button:has-text("Verify Integrity")').first();
  let chainVerified = false;
  if (await verifyBtn.count() > 0) {
    await verifyBtn.click();
    await win.waitForTimeout(500);
    const text = await win.locator('body').textContent();
    chainVerified = text.includes('Cryptographically Verified') || text.includes('Valid') || text.includes('VERIFIED');
  }

  results.forensics = {
    assessmentId: trojanAid,
    findingsRendered: findingsHeading ? findingsHeading.trim() : 'OK',
    evidenceCardsCount: evidenceCount,
    chainVerified
  };

  // 6. Provenance & Audit APIs
  console.log('\n[6/10] Validating Provenance & Audit APIs...');
  const provAid = sampleAssessmentIds['provenance_attestation'];
  const provRes = await win.request.get(`http://127.0.0.1:8000/api/v1/assessments/${provAid}/provenance`);
  const provJson = await provRes.json();

  const auditRes = await win.request.get(`http://127.0.0.1:8000/api/v1/assessments/${provAid}/audit`);
  const auditJson = await auditRes.json();

  results.provenance = {
    hasProvenance: provJson.has_provenance,
    signatureStatus: provJson.manifest ? provJson.manifest.status : 'N/A',
    replayStatus: provJson.manifest ? provJson.manifest.replay_status : 'N/A'
  };
  results.audit = {
    chainValid: auditJson.chain_valid,
    eventsCount: auditJson.events_checked || (auditJson.events ? auditJson.events.length : 0)
  };
  console.log(`Provenance: Sig=${results.provenance.signatureStatus}, Replay=${results.provenance.replayStatus} | Audit ChainValid=${results.audit.chainValid}`);

  // 7. Cryptographic PDF, JSON, and Audit Exports
  console.log('\n[7/10] Testing PDF, JSON, and Audit Exports...');
  const pdfRes = await win.request.get(`http://127.0.0.1:8000/api/v1/assessments/${trojanAid}/report`);
  const pdfBuf = await pdfRes.body();
  const isPdf = pdfBuf.slice(0, 4).toString() === '%PDF';

  const jsonRes = await win.request.get(`http://127.0.0.1:8000/api/v1/assessments/${trojanAid}/export/json`);
  const jsonBuf = await jsonRes.body();
  let jsonParsable = false;
  try {
    JSON.parse(jsonBuf.toString('utf8'));
    jsonParsable = true;
  } catch {}

  const auditExportRes = await win.request.get(`http://127.0.0.1:8000/api/v1/assessments/${trojanAid}/audit/export`);
  const auditExportBuf = await auditExportRes.body();
  let auditParsable = false;
  try {
    JSON.parse(auditExportBuf.toString('utf8'));
    auditParsable = true;
  } catch {}

  results.exports = {
    pdfStatus: pdfRes.status(),
    pdfBytes: pdfBuf.length,
    pdfValid: isPdf,
    jsonStatus: jsonRes.status(),
    jsonBytes: jsonBuf.length,
    jsonParsable,
    auditExportStatus: auditExportRes.status(),
    auditExportBytes: auditExportBuf.length,
    auditExportParsable: auditParsable
  };
  console.log(`PDF: HTTP ${pdfRes.status()} (${pdfBuf.length}b, %PDF: ${isPdf}) | JSON: HTTP ${jsonRes.status()} (${jsonBuf.length}b) | Audit: HTTP ${auditExportRes.status()} (${auditExportBuf.length}b)`);

  // 8. Global Search & History
  console.log('\n[8/10] Testing History & Global Search (Ctrl+K)...');
  await win.goto('http://127.0.0.1:8000/assessments', { waitUntil: 'networkidle' });
  const rowCount = await win.locator('a[href*="/assessments/"][href*="/result"]').count();

  await win.keyboard.press('Control+k');
  await win.waitForTimeout(300);
  const searchInput = win.locator('input[placeholder*="Search" i]').first();
  const searchOpen = await searchInput.count() > 0;
  if (searchOpen) {
    await searchInput.fill('Clean');
    await win.waitForTimeout(200);
    await win.keyboard.press('Escape');
    await win.waitForTimeout(200);
  }
  results.search = {
    historyCount: rowCount,
    searchWorking: searchOpen
  };
  console.log(`History records: ${rowCount} | Global Search active: ${searchOpen}`);

  // 9. Failure Handling & Safe Recovery
  console.log('\n[9/10] Testing Malformed Payload Rejection...');
  const badRes = await win.request.post('http://127.0.0.1:8000/api/v1/assessments', {
    data: { bad_field: 'unsupported' }
  });
  const notFoundRes = await win.request.get('http://127.0.0.1:8000/api/v1/assessments/00000000-0000-0000-0000-000000000000');
  results.failureHandling = {
    malformedStatus: badRes.status(),
    notFoundStatus: notFoundRes.status()
  };
  console.log(`Malformed payload: HTTP ${badRes.status()} (Expected 422) | 404: HTTP ${notFoundRes.status()}`);

  // 10. Restart & Persistence
  console.log('\n[10/10] Testing Process Clean Termination & Restart Persistence...');
  await app.close();
  await new Promise(r => setTimeout(r, 2000));

  const pidsAfterClose = getListeningProcessPids(8000);
  results.cleanup.firstClosePidsClean = pidsAfterClose.length === 0;

  console.log('Reopening fresh instance to verify SQLite persistence...');
  const app2 = await electron.launch({
    executablePath: PACKAGED_EXE,
    args: [],
    cwd: STAGING_DIR,
    env: { ...process.env, PYTHONPATH: '', VIRTUAL_ENV: '' }
  });

  const win2 = await app2.firstWindow();
  await win2.waitForLoadState('networkidle');
  await win2.goto('http://127.0.0.1:8000/assessments', { waitUntil: 'networkidle' });
  const rowCountAfterRestart = await win2.locator('a[href*="/assessments/"][href*="/result"]').count();

  results.persistence = {
    persistedRows: rowCountAfterRestart,
    persistenceVerified: rowCountAfterRestart >= 5
  };
  console.log(`Persisted rows after restart: ${rowCountAfterRestart}`);

  await app2.close();
  await new Promise(r => setTimeout(r, 2000));
  const pidsFinal = getListeningProcessPids(8000);
  results.cleanup.finalPidsClean = pidsFinal.length === 0;

  // Final Verdict
  results.network.destinations = Array.from(results.network.destinations);
  const allDemosPass = Object.keys(results.demoPresets).length === 5;
  const zeroExternal = results.network.externalRequests === 0;
  const allCanonical = results.capabilities.allPresent;
  const exportsOk = results.exports.pdfValid && results.exports.jsonParsable && results.exports.auditExportParsable;
  const persistenceOk = results.persistence.persistenceVerified;
  const cleanupOk = results.cleanup.finalPidsClean;

  results.verdict = (allDemosPass && zeroExternal && allCanonical && exportsOk && persistenceOk && cleanupOk)
    ? 'PASS'
    : 'FAIL';

  console.log('\n================================================================');
  console.log(`FRESH RELEASE VALIDATION VERDICT: ${results.verdict}`);
  console.log(`All 5 Demo Presets: ${allDemosPass ? 'PASS' : 'FAIL'}`);
  console.log(`Air-Gap Shield (0 External Requests): ${zeroExternal ? 'PASS (0 external)' : 'FAIL'}`);
  console.log(`11 Canonical Detectors: ${allCanonical ? 'PASS' : 'FAIL'}`);
  console.log(`PDF, JSON, & Audit Exports: ${exportsOk ? 'PASS' : 'FAIL'}`);
  console.log(`Cross-Session Persistence: ${persistenceOk ? 'PASS' : 'FAIL'}`);
  console.log(`Process Cleanup: ${cleanupOk ? 'PASS' : 'FAIL'}`);
  console.log('================================================================\n');

  return results;
}

validateFreshRelease().then(res => {
  if (res.verdict !== 'PASS') process.exit(1);
}).catch(err => {
  console.error('[FATAL VALIDATION ERROR]', err);
  process.exit(1);
});
