import { useState, useEffect, useRef } from 'react';
import type {
  AIChatResponse,
  AICopilotScope,
  AISourceReference,
  AIStatusResponse,
} from '../types/api';
import { chatWithCopilot, getAIStatus } from '../api/client';

interface Message {
  id: string;
  sender: 'user' | 'assistant' | 'system';
  text: string;
  scope?: string;
  sources?: AISourceReference[];
  timestamp: string;
  error?: boolean;
}

interface AnalystCopilotProps {
  assessmentId: string;
  isOpen: boolean;
  onClose: () => void;
  initialScope?: AICopilotScope;
  initialFindingId?: string | null;
  onSelectFinding?: (findingId: string) => void;
}

const SUGGESTED_QUESTIONS = [
  'Explain the highest-risk finding',
  'Why is this finding classified as HIGH?',
  'What evidence supports this finding?',
  'Could this be a false positive?',
  'What should I investigate first?',
  'Summarize this assessment',
  'Explain the coverage gaps',
];

export function AnalystCopilot({
  assessmentId,
  isOpen,
  onClose,
  initialScope = 'assessment',
  initialFindingId = null,
  onSelectFinding,
}: AnalystCopilotProps) {
  const [status, setStatus] = useState<AIStatusResponse | null>(null);
  const [loadingStatus, setLoadingStatus] = useState<boolean>(true);
  const [scope, setScope] = useState<AICopilotScope>(initialScope);
  const [findingId, setFindingId] = useState<string | null>(initialFindingId);
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputPrompt, setInputPrompt] = useState<string>('');
  const [submitting, setSubmitting] = useState<boolean>(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Sync initial scope/finding props when opening
  useEffect(() => {
    if (initialFindingId) {
      setScope('finding');
      setFindingId(initialFindingId);
    } else if (initialScope) {
      setScope(initialScope);
      setFindingId(null);
    }
  }, [initialScope, initialFindingId, isOpen]);

  // Load AI configuration status
  useEffect(() => {
    let mounted = true;
    async function fetchStatus() {
      try {
        setLoadingStatus(true);
        const res = await getAIStatus();
        if (mounted) setStatus(res);
      } catch (err) {
        console.warn('Failed to load AI status:', err);
      } finally {
        if (mounted) setLoadingStatus(false);
      }
    }
    if (isOpen) {
      fetchStatus();
    }
    return () => {
      mounted = false;
    };
  }, [isOpen]);

  // Auto-scroll on new messages
  useEffect(() => {
    if (typeof messagesEndRef.current?.scrollIntoView === 'function') {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, submitting]);

  if (!isOpen) return null;

  const handleSendMessage = async (textToSend?: string) => {
    const query = (textToSend || inputPrompt).trim();
    if (!query || submitting) return;

    const userMsg: Message = {
      id: `user-${Date.now()}`,
      sender: 'user',
      text: query,
      scope: scope === 'finding' && findingId ? `Finding ${findingId}` : 'Assessment',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInputPrompt('');
    setSubmitting(true);

    try {
      const response: AIChatResponse = await chatWithCopilot(assessmentId, {
        message: query,
        scope: scope,
        finding_id: scope === 'finding' ? findingId : undefined,
      });

      const assistantMsg: Message = {
        id: `assistant-${Date.now()}`,
        sender: 'assistant',
        text: response.answer,
        scope: response.scope,
        sources: response.sources,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };

      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : 'Failed to communicate with AI provider.';
      setMessages((prev) => [
        ...prev,
        {
          id: `err-${Date.now()}`,
          sender: 'assistant',
          text: `Error: ${errMsg}`,
          error: true,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ]);
    } finally {
      setSubmitting(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const isConfigured = status?.configured && status.status === 'connected';

  return (
    <aside
      aria-label="PRAMAAN Analyst Copilot"
      className="fixed inset-y-0 right-0 z-50 w-full sm:w-[480px] bg-slate-900/95 backdrop-blur-xl border-l border-slate-700/80 shadow-2xl flex flex-col transition-all duration-300 animate-in slide-in-from-right"
    >
      {/* Header */}
      <div className="p-4 border-b border-slate-700/70 flex items-center justify-between bg-slate-900/80">
        <div className="flex items-center gap-2.5">
          <div className="p-1.5 rounded-lg bg-purple-500/10 border border-purple-500/30 text-purple-400">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.75}
                d="M13 10V3L4 14h7v7l9-11h-7z"
              />
            </svg>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-semibold text-slate-100 tracking-tight">
                PRAMAAN Analyst Copilot
              </h2>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-semibold tracking-wide uppercase bg-purple-500/15 border border-purple-500/30 text-purple-300">
                CLOUD AI
              </span>
            </div>
            <p className="text-xs text-slate-400">
              {status?.model ? `Model: ${status.model}` : 'Optional assistance layer'}
            </p>
          </div>
        </div>

        <button
          onClick={onClose}
          aria-label="Close Copilot"
          className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Cloud AI Boundary & Disclosure Banner */}
      <div className="bg-purple-950/20 border-b border-purple-800/30 px-4 py-2.5 flex items-start gap-2.5 text-xs text-purple-200/90">
        <svg
          className="w-4 h-4 text-purple-400 shrink-0 mt-0.5"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
          />
        </svg>
        <div>
          <span className="font-semibold text-purple-300">CLOUD AI ENABLED: </span>
          Assessment engine remains local and authoritative. Bounded evidence context is transmitted to OpenRouter to generate Copilot answers.
        </div>
      </div>

      {/* Active Scope Selector */}
      <div className="px-4 py-2 bg-slate-950/40 border-b border-slate-800 flex items-center justify-between text-xs">
        <div className="flex items-center gap-1.5 text-slate-400">
          <span>Active Scope:</span>
          {scope === 'finding' && findingId ? (
            <span className="font-mono text-cyan-300 bg-cyan-950/50 border border-cyan-800/50 px-2 py-0.5 rounded">
              Finding: {findingId}
            </span>
          ) : (
            <span className="font-medium text-slate-200 bg-slate-800 px-2 py-0.5 rounded">
              Assessment-Wide
            </span>
          )}
        </div>
        {scope === 'finding' && (
          <button
            onClick={() => {
              setScope('assessment');
              setFindingId(null);
            }}
            className="text-[11px] text-slate-400 hover:text-slate-200 underline transition-colors"
          >
            Reset to Assessment
          </button>
        )}
      </div>

      {/* Status Warning if unconfigured */}
      {!loadingStatus && !isConfigured && (
        <div className="m-4 p-3.5 rounded-xl border border-amber-500/30 bg-amber-500/10 text-amber-200 text-xs space-y-2">
          <div className="flex items-center gap-2 font-semibold text-amber-300">
            <svg className="w-4 h-4 text-amber-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            Cloud AI Not Configured
          </div>
          <p className="text-amber-200/90 leading-relaxed">
            PRAMAAN deterministic assessment execution remains 100% functional offline. To enable the AI Analyst Copilot, provide an OpenRouter API key in your environment or <a href="/settings" className="underline font-semibold hover:text-amber-100">Settings</a>.
          </p>
        </div>
      )}

      {/* Message Stream */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 text-sm">
        {messages.length === 0 ? (
          <div className="py-6 px-2 text-center space-y-4">
            <div className="w-12 h-12 rounded-2xl bg-purple-500/10 border border-purple-500/20 text-purple-400 flex items-center justify-center mx-auto">
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
              </svg>
            </div>
            <div className="space-y-1">
              <h3 className="font-semibold text-slate-200">How can I assist your analysis?</h3>
              <p className="text-xs text-slate-400 max-w-sm mx-auto">
                Ask questions about risk severity, supporting evidence, potential false positives, or investigation priorities.
              </p>
            </div>

            {/* Suggested Prompts */}
            <div className="pt-2 text-left space-y-2">
              <p className="text-xs font-medium text-slate-400 px-1">Suggested Questions:</p>
              <div className="flex flex-wrap gap-1.5">
                {SUGGESTED_QUESTIONS.map((q) => (
                  <button
                    key={q}
                    disabled={submitting}
                    onClick={() => handleSendMessage(q)}
                    className="text-xs text-slate-300 bg-slate-800/80 hover:bg-slate-750 hover:text-white border border-slate-700/80 rounded-lg px-2.5 py-1.5 text-left transition-colors"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          messages.map((m) => (
            <div
              key={m.id}
              className={`flex flex-col ${m.sender === 'user' ? 'items-end' : 'items-start'}`}
            >
              <div className="text-[10px] text-slate-500 mb-1 px-1 flex items-center gap-1.5">
                <span>{m.sender === 'user' ? 'Analyst' : 'Copilot'}</span>
                <span>•</span>
                <span>{m.timestamp}</span>
                {m.scope && (
                  <>
                    <span>•</span>
                    <span className="font-mono">{m.scope}</span>
                  </>
                )}
              </div>
              <div
                className={`max-w-[90%] rounded-2xl px-4 py-2.5 leading-relaxed text-xs sm:text-sm whitespace-pre-wrap ${
                  m.sender === 'user'
                    ? 'bg-purple-600 text-white rounded-tr-sm shadow-md'
                    : m.error
                    ? 'bg-red-950/40 border border-red-800/50 text-red-200 rounded-tl-sm'
                    : 'bg-slate-800/90 border border-slate-700 text-slate-200 rounded-tl-sm shadow-sm'
                }`}
              >
                {m.text}
              </div>

              {/* Source citations */}
              {m.sources && m.sources.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5 max-w-[90%] px-1">
                  <span className="text-[11px] text-slate-500 self-center">Sources:</span>
                  {m.sources.map((src) => (
                    <button
                      key={`${src.type}-${src.id}`}
                      onClick={() => {
                        if (src.type === 'finding' && onSelectFinding) {
                          onSelectFinding(src.id);
                        }
                      }}
                      className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-mono bg-slate-800/90 border border-slate-700 text-cyan-300 hover:border-cyan-500 transition-colors"
                    >
                      <span className="opacity-60 uppercase">{src.type}:</span>
                      <span>{src.id}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))
        )}

        {submitting && (
          <div className="flex items-center gap-2 text-xs text-purple-400 py-2 px-1">
            <div className="w-3.5 h-3.5 border-2 border-purple-400 border-t-transparent rounded-full animate-spin" />
            <span>Copilot is analyzing evidence...</span>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Form */}
      <div className="p-3 border-t border-slate-800 bg-slate-900/90">
        <div className="relative rounded-xl border border-slate-700 focus-within:border-purple-500 bg-slate-950/60 transition-colors">
          <textarea
            value={inputPrompt}
            onChange={(e) => setInputPrompt(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              scope === 'finding' && findingId
                ? `Ask about finding ${findingId} (Shift+Enter for newline)...`
                : 'Ask Copilot about this assessment (Shift+Enter for newline)...'
            }
            rows={2}
            className="w-full bg-transparent px-3 py-2.5 text-xs sm:text-sm text-slate-100 placeholder-slate-500 focus:outline-none resize-none"
          />
          <div className="flex items-center justify-between px-2.5 py-1.5 border-t border-slate-800/60 bg-slate-900/40 rounded-b-xl">
            <div className="text-[11px] text-slate-500">
              Read-only • Grounded in assessment evidence
            </div>
            <button
              onClick={() => handleSendMessage()}
              disabled={!inputPrompt.trim() || submitting}
              aria-label="Send message"
              className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-medium text-white bg-purple-600 hover:bg-purple-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <span>Send</span>
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </aside>
  );
}
