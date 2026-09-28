const { app, BrowserWindow, dialog } = require('electron');
const path = require('path');
const fs = require('fs');
const http = require('http');
const { spawn, execSync } = require('child_process');

// -------------------------------------------------------------
// 1. Electron Security & Air-Gap Command Line Switches
// -------------------------------------------------------------
// Disable all background networking, telemetry, and external checks
app.commandLine.appendSwitch('disable-background-networking');
app.commandLine.appendSwitch('disable-default-apps');
app.commandLine.appendSwitch('disable-component-update');
app.commandLine.appendSwitch('disable-domain-reliability');
app.commandLine.appendSwitch('no-default-browser-check');
app.commandLine.appendSwitch('disable-search-engine-choice-screen');
app.commandLine.appendSwitch('disable-breakpad'); // No crash reporter telemetry
app.commandLine.appendSwitch('disable-sync');

const PROJECT_ROOT = path.resolve(__dirname, '..');
const FRONTEND_DIR = path.join(PROJECT_ROOT, 'frontend');

// -------------------------------------------------------------
// Load environment variables from repo root .env if present
// -------------------------------------------------------------
const envFilePath = path.join(PROJECT_ROOT, '.env');
if (fs.existsSync(envFilePath)) {
  try {
    const envContent = fs.readFileSync(envFilePath, 'utf8');
    for (const rawLine of envContent.split(/\r?\n/)) {
      const line = rawLine.trim();
      if (!line || line.startsWith('#')) continue;
      const eqIdx = line.indexOf('=');
      if (eqIdx > 0) {
        const key = line.slice(0, eqIdx).trim();
        let val = line.slice(eqIdx + 1).trim();
        if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith("'") && val.endsWith("'"))) {
          val = val.slice(1, -1);
        }
        if (!process.env[key]) {
          process.env[key] = val;
        }
      }
    }
  } catch (err) {
    console.warn('[PRAMAAN Shell] Could not load .env:', err);
  }
}

// -------------------------------------------------------------
// Detect Mode: Production Distributable vs Development Source
// -------------------------------------------------------------
const PACKAGED_PYTHON = path.join(process.resourcesPath || '', 'backend', 'python', 'python.exe');
const LOCAL_RELEASE_PYTHON = path.join(PROJECT_ROOT, 'resources', 'backend', 'python', 'python.exe');
const VENV_PYTHON = process.platform === 'win32'
  ? path.join(PROJECT_ROOT, '.venv', 'Scripts', 'python.exe')
  : path.join(PROJECT_ROOT, '.venv', 'bin', 'python');

let isProduction = false;
let PYTHON_BIN = '';
let BACKEND_CWD = PROJECT_ROOT;
let BACKEND_ENV = {};
let TARGET_URL = 'http://127.0.0.1:5173/';

if (fs.existsSync(PACKAGED_PYTHON)) {
  isProduction = true;
  PYTHON_BIN = PACKAGED_PYTHON;
  const resourcesRoot = path.join(process.resourcesPath, 'backend');
  BACKEND_CWD = resourcesRoot;
  const userDataDir = path.join(app.getPath('userData'), 'data');
  fs.mkdirSync(userDataDir, { recursive: true });

  const pyDir = path.dirname(PYTHON_BIN);
  const currentPath = process.env.PATH || '';

  BACKEND_ENV = {
    ...process.env,
    PATH: `${pyDir};${path.join(pyDir, 'DLLs')};${currentPath}`,
    PYTHONPATH: resourcesRoot,
    PRAMAAN_DATA_DIR: userDataDir,
    PRAMAAN_CORPUS_DIR: path.join(resourcesRoot, 'data', 'corpus'),
    PRAMAAN_FRONTEND_DIST: path.join(resourcesRoot, 'frontend', 'dist'),
    PRAMAAN_AI_ENABLED: process.env.PRAMAAN_AI_ENABLED || 'true'
  };
  TARGET_URL = 'http://127.0.0.1:8000/';
} else if (fs.existsSync(LOCAL_RELEASE_PYTHON)) {
  isProduction = true;
  PYTHON_BIN = LOCAL_RELEASE_PYTHON;
  const resourcesRoot = path.join(PROJECT_ROOT, 'resources', 'backend');
  BACKEND_CWD = resourcesRoot;
  const userDataDir = path.join(app.getPath('userData'), 'data');
  fs.mkdirSync(userDataDir, { recursive: true });

  const pyDir = path.dirname(PYTHON_BIN);
  const currentPath = process.env.PATH || '';

  BACKEND_ENV = {
    ...process.env,
    PATH: `${pyDir};${path.join(pyDir, 'DLLs')};${currentPath}`,
    PYTHONPATH: resourcesRoot,
    PRAMAAN_DATA_DIR: userDataDir,
    PRAMAAN_CORPUS_DIR: path.join(resourcesRoot, 'data', 'corpus'),
    PRAMAAN_FRONTEND_DIST: path.join(resourcesRoot, 'frontend', 'dist'),
    PRAMAAN_AI_ENABLED: process.env.PRAMAAN_AI_ENABLED || 'true'
  };
  TARGET_URL = 'http://127.0.0.1:8000/';
} else {
  // Development mode using source tree .venv
  isProduction = false;
  PYTHON_BIN = fs.existsSync(VENV_PYTHON) ? VENV_PYTHON : 'python';
  BACKEND_CWD = PROJECT_ROOT;
  BACKEND_ENV = {
    ...process.env,
    PRAMAAN_AI_ENABLED: process.env.PRAMAAN_AI_ENABLED || 'true'
  };
  TARGET_URL = 'http://127.0.0.1:5173/';
}

console.log(`[PRAMAAN Shell] Mode: ${isProduction ? 'PRODUCTION DISTRIBUTABLE' : 'DEVELOPMENT'}`);
console.log(`[PRAMAAN Shell] Target Window URL: ${TARGET_URL}`);

let mainWindow = null;
let backendProcess = null;
let frontendProcess = null;
let isQuitting = false;

// -------------------------------------------------------------
// 2. Health Polling Helper
// -------------------------------------------------------------
function checkEndpoint(urlStr) {
  return new Promise((resolve) => {
    try {
      const u = new URL(urlStr);
      const req = http.request({
        hostname: u.hostname,
        port: u.port,
        path: u.pathname,
        method: 'GET',
        timeout: 1000
      }, (res) => {
        resolve(res.statusCode === 200);
      });
      req.on('error', () => resolve(false));
      req.on('timeout', () => { req.destroy(); resolve(false); });
      req.end();
    } catch {
      resolve(false);
    }
  });
}

async function waitForService(name, urlStr, timeoutSec = 30) {
  console.log(`[PRAMAAN Launcher] Waiting for ${name} at ${urlStr}...`);
  const start = Date.now();
  while (Date.now() - start < timeoutSec * 1000) {
    const ok = await checkEndpoint(urlStr);
    if (ok) {
      console.log(`[PRAMAAN Launcher] ${name} is READY.`);
      return true;
    }
    await new Promise(r => setTimeout(r, 400));
  }
  return false;
}

// -------------------------------------------------------------
// 3. Process Tree Cleanup Helper (Windows Compatible)
// -------------------------------------------------------------
function killProcessTree(proc, name) {
  if (!proc || !proc.pid) return;
  console.log(`[PRAMAAN Launcher] Terminating ${name} (PID ${proc.pid})...`);
  try {
    if (process.platform === 'win32') {
      execSync(`taskkill /pid ${proc.pid} /T /F`, { stdio: 'ignore' });
    } else {
      process.kill(-proc.pid, 'SIGKILL');
    }
  } catch (err) {
    // Process may have already exited
  }
}

function cleanupChildProcesses() {
  if (backendProcess) {
    killProcessTree(backendProcess, 'FastAPI Backend');
    backendProcess = null;
  }
  if (frontendProcess) {
    killProcessTree(frontendProcess, 'Vite Frontend');
    frontendProcess = null;
  }
}

// -------------------------------------------------------------
// 4. Start Child Services (if not already running)
// -------------------------------------------------------------
async function ensureServices() {
  // Check Backend (Port 8000)
  const isBackendRunning = await checkEndpoint('http://127.0.0.1:8000/health');
  if (isBackendRunning) {
    console.log('[PRAMAAN Launcher] Backend already active on port 8000.');
  } else {
    console.log(`[PRAMAAN Launcher] Spawning backend using ${PYTHON_BIN}...`);
    backendProcess = spawn(PYTHON_BIN, [
      '-m', 'uvicorn', 'backend.api.app:app',
      '--host', '127.0.0.1',
      '--port', '8000'
    ], {
      cwd: BACKEND_CWD,
      stdio: ['ignore', 'pipe', 'pipe'],
      env: BACKEND_ENV
    });

    backendProcess.stdout.on('data', (d) => {
      // console.log(`[Backend] ${d.toString().trim()}`);
    });
    backendProcess.stderr.on('data', (d) => {
      const msg = d.toString().trim();
      if (!msg.includes('DeprecationWarning')) {
        console.error(`[Backend ERR] ${msg}`);
      }
    });
  }

  // Check Frontend (Only needed in Development mode)
  if (!isProduction) {
    const isFrontendRunning = await checkEndpoint('http://127.0.0.1:5173/');
    if (isFrontendRunning) {
      console.log('[PRAMAAN Launcher] Frontend already active on port 5173.');
    } else {
      console.log('[PRAMAAN Launcher] Spawning Vite development server...');
      const npmCmd = process.platform === 'win32' ? 'cmd.exe' : 'npx';
      const npmArgs = process.platform === 'win32'
        ? ['/c', 'npx', 'vite', '--host', '127.0.0.1', '--port', '5173']
        : ['vite', '--host', '127.0.0.1', '--port', '5173'];

      frontendProcess = spawn(npmCmd, npmArgs, {
        cwd: FRONTEND_DIR,
        stdio: ['ignore', 'pipe', 'pipe']
      });

      frontendProcess.stdout.on('data', (d) => {
        // console.log(`[Frontend] ${d.toString().trim()}`);
      });
      frontendProcess.stderr.on('data', (d) => {
        console.error(`[Frontend ERR] ${d.toString().trim()}`);
      });
    }
  }

  // Wait for Backend
  const backendReady = await waitForService('FastAPI Backend', 'http://127.0.0.1:8000/health', 30);
  if (!backendReady) {
    throw new Error('FastAPI Backend failed to become ready on http://127.0.0.1:8000/health within 30 seconds.');
  }

  // Wait for Frontend (only in Dev mode)
  if (!isProduction) {
    const frontendReady = await waitForService('Vite Frontend', 'http://127.0.0.1:5173/', 30);
    if (!frontendReady) {
      throw new Error('Vite Frontend failed to become ready on http://127.0.0.1:5173/ within 30 seconds.');
    }
  }
}

// -------------------------------------------------------------
// 5. Create Desktop Window
// -------------------------------------------------------------
function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 700,
    title: 'PRAMAAN — Evidence Before Trust',
    autoHideMenuBar: true,
    backgroundColor: '#0C1824',
    show: false,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      preload: path.join(__dirname, 'preload.cjs'),
      webSecurity: true,
      allowRunningInsecureContent: false,
      spellcheck: false
    }
  });

  mainWindow.loadURL(TARGET_URL);

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
    console.log('[PRAMAAN Desktop] Main Workstation Window visible.');
  });

  // Security: Deny window popups / new-window abuse
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    console.warn(`[SECURITY] Blocked popup window request: ${url}`);
    return { action: 'deny' };
  });

  // Security: Prevent navigation away from local workstation
  mainWindow.webContents.on('will-navigate', (event, url) => {
    try {
      const parsed = new URL(url);
      const isAllowedLocal = (parsed.hostname === '127.0.0.1' || parsed.hostname === 'localhost') &&
        (parsed.port === '8000' || (!isProduction && parsed.port === '5173'));
      if (!isAllowedLocal) {
        event.preventDefault();
        console.warn(`[SECURITY] Blocked unauthorized navigation attempt: ${url}`);
      }
    } catch {
      event.preventDefault();
    }
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// -------------------------------------------------------------
// 6. Application Lifecycle
// -------------------------------------------------------------
app.whenReady().then(async () => {
  try {
    await ensureServices();
    createWindow();
  } catch (err) {
    console.error(`[PRAMAAN FATAL] Startup failed: ${err.message}`);
    dialog.showErrorBox(
      'PRAMAAN Desktop Startup Failure',
      `Could not initialize local workstation services:\n\n${err.message}\n\nPlease check logs and ensure port 8000 and 5173 are available.`
    );
    cleanupChildProcesses();
    app.quit();
  }
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    cleanupChildProcesses();
    app.quit();
  }
});

app.on('before-quit', () => {
  isQuitting = true;
  cleanupChildProcesses();
});

process.on('SIGINT', () => {
  cleanupChildProcesses();
  process.exit(0);
});

process.on('SIGTERM', () => {
  cleanupChildProcesses();
  process.exit(0);
});
