import { useState, useEffect } from 'react';
import { getAIStatus, testAIConnection } from '../api/client';
import type { AIStatusResponse, ConnectionTestResponse } from '../types/api';

export function Settings() {
  const [aiStatus, setAiStatus] = useState<AIStatusResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [testResult, setTestResult] = useState<ConnectionTestResponse | null>(null);
  const [testing, setTesting] = useState<boolean>(false);

  useEffect(() => {
    async function loadStatus() {
      try {
        setLoading(true);
        const res = await getAIStatus();
        setAiStatus(res);
      } catch (err) {
        console.error('Failed to load AI status:', err);
      } finally {
        setLoading(false);
      }
    }
    loadStatus();
  }, []);

  const handleTestConnection = async () => {
    try {
      setTesting(true);
      setTestResult(null);
      const res = await testAIConnection();
      setTestResult(res);
    } catch (err: unknown) {
      setTestResult({
        ok: false,
        message: err instanceof Error ? err.message : 'Connection test failed',
      });
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 py-8 space-y-8">
      {/* Page Header */}
      <div>
        <h1 className="text-2xl sm:text-3xl font-extrabold text-1 tracking-tight">System Settings</h1>
        <p className="text-xs text-3 mt-1">
          Configure runtime parameters and optional assistance services.
        </p>
      </div>

      {/* Cloud AI Section */}
      <div className="card p-6 border border-[var(--border)] bg-surface rounded-xl space-y-6 shadow-sm">
        <div className="flex items-start justify-between flex-wrap gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2.5 flex-wrap">
              <h2 className="text-base font-semibold text-1">
                PRAMAAN Analyst Copilot (Cloud AI)
              </h2>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-semibold tracking-wide uppercase bg-purple-500/15 border border-purple-500/30 text-purple-700 dark:text-purple-300">
                OPTIONAL LAYER
              </span>
            </div>
            <p className="text-xs text-3 max-w-xl leading-relaxed">
              Provides interactive explanation and evidence interrogation for human analysts.
              The deterministic assessment engine, detectors, and audit logs remain 100% local and authoritative.
            </p>
          </div>

          <button
            onClick={handleTestConnection}
            disabled={testing || loading}
            className="inline-flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-semibold text-1 bg-surface-2 hover:bg-surface-3 border border-[var(--border)] transition-colors disabled:opacity-50 shadow-sm"
          >
            {testing ? (
              <>
                <div className="w-3.5 h-3.5 border-2 border-accent border-t-transparent rounded-full animate-spin" />
                <span>Testing...</span>
              </>
            ) : (
              <>
                <svg className="w-4 h-4 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
                <span>Test Connection</span>
              </>
            )}
          </button>
        </div>

        {/* Test Result Toast */}
        {testResult && (
          <div
            className={`p-3.5 rounded-xl border text-xs flex items-center gap-2.5 ${
              testResult.ok
                ? 'bg-[var(--green-bg)] border-[var(--green)]/30 text-[var(--green)]'
                : 'bg-[var(--red-bg)] border-[var(--red)]/30 text-[var(--red)]'
            }`}
          >
            <div
              className={`w-2 h-2 rounded-full ${
                testResult.ok ? 'bg-[var(--green)]' : 'bg-[var(--red)]'
              }`}
            />
            <span>{testResult.message}</span>
          </div>
        )}

        {/* Configuration Overview Table */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="p-4 rounded-xl bg-surface-2/60 border border-[var(--border)] space-y-1">
            <span className="text-[11px] font-mono uppercase text-3">Provider</span>
            <div className="text-sm font-medium text-1 flex items-center gap-2">
              <span className="capitalize">{aiStatus?.provider || 'OpenRouter'}</span>
              <span className="text-xs text-3 font-normal">
                (OpenAI compatible API)
              </span>
            </div>
            <p className="text-[11px] text-3 mt-1">
              Extensible abstraction designed for future local Ollama support.
            </p>
          </div>

          <div className="p-4 rounded-xl bg-surface-2/60 border border-[var(--border)] space-y-1">
            <span className="text-[11px] font-mono uppercase text-3">Configured Model</span>
            <div className="text-sm font-mono text-accent font-semibold truncate">
              {aiStatus?.model || 'anthropic/claude-3.5-sonnet'}
            </div>
            <p className="text-[11px] text-3 mt-1">
              Configurable via <code className="px-1 py-0.5 rounded bg-surface border border-[var(--border)] text-1 font-mono text-[10px]">OPENROUTER_MODEL</code> environment variable.
            </p>
          </div>

          <div className="p-4 rounded-xl bg-surface-2/60 border border-[var(--border)] space-y-1">
            <span className="text-[11px] font-mono uppercase text-3">Status</span>
            <div className="flex items-center gap-2">
              <div
                className={`w-2 h-2 rounded-full ${
                  aiStatus?.status === 'connected'
                    ? 'bg-[var(--green)] animate-pulse'
                    : aiStatus?.status === 'not_configured'
                    ? 'bg-[var(--amber)]'
                    : 'bg-[var(--red)]'
                }`}
              />
              <span className="text-sm font-medium text-1 capitalize">
                {aiStatus?.status ? aiStatus.status.replace('_', ' ') : 'Loading...'}
              </span>
            </div>
            <p className="text-[11px] text-3 mt-1">
              {aiStatus?.status === 'connected'
                ? 'Ready to assist analyst inquiries.'
                : 'Set OPENROUTER_API_KEY in environment to activate.'}
            </p>
          </div>

          <div className="p-4 rounded-xl bg-surface-2/60 border border-[var(--border)] space-y-1">
            <span className="text-[11px] font-mono uppercase text-3">API Key</span>
            <div className="text-sm font-medium text-1 flex items-center gap-2">
              {aiStatus?.has_api_key ? (
                <span className="text-[var(--green)] flex items-center gap-1.5 font-medium">
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  Configured (Masked)
                </span>
              ) : (
                <span className="text-[var(--amber)] flex items-center gap-1.5 font-medium">
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                  </svg>
                  Not Configured
                </span>
              )}
            </div>
            <p className="text-[11px] text-3 mt-1">
              Keys are never stored in SQLite or sent to browser clients.
            </p>
          </div>
        </div>

        {/* Privacy & Air-gap Notice */}
        <div className="p-4 rounded-xl bg-surface-2/60 border border-[var(--border)] text-xs text-2 space-y-2">
          <div className="font-semibold text-1 flex items-center gap-2">
            <svg className="w-4 h-4 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
            </svg>
            Assurance Boundary & Privacy Notice
          </div>
          <p className="leading-relaxed text-3">
            {aiStatus?.privacy_disclosure ||
              'Cloud AI — provider privacy policies apply. Selected assessment context is sanitized and bounded prior to transmission. No raw datasets, model weights, or private keys are ever transmitted.'}
          </p>
        </div>
      </div>
    </div>
  );
}
