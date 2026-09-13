import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Search,
  X,
  FileText,
  TriangleAlert,
  FileSearch,
  Loader2,
  ExternalLink,
  Command,
  Database
} from 'lucide-react';
import { searchAll } from '../api/client';
import type {
  GlobalSearchResponse,
  SearchResultAssessment,
  SearchResultFinding,
  SearchResultEvidence
} from '../types/api';
import { cn } from '../lib/cn';
import { formatDatetime } from '../lib/format';

interface GlobalSearchModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function GlobalSearchModal({ isOpen, onClose }: GlobalSearchModalProps) {
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<GlobalSearchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const navigate = useNavigate();

  // Focus input on open & remember previous active focus
  useEffect(() => {
    if (isOpen) {
      previousFocusRef.current = document.activeElement as HTMLElement;
      setTimeout(() => {
        inputRef.current?.focus();
      }, 50);
    } else {
      setQuery('');
      setResults(null);
      setError(null);
      previousFocusRef.current?.focus();
    }
  }, [isOpen]);

  // Handle ESC key to close
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  // Debounced search
  useEffect(() => {
    const trimmed = query.trim();
    if (!trimmed) {
      setResults(null);
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);

    const timer = setTimeout(async () => {
      try {
        const resp = await searchAll(trimmed, 15);
        setResults(resp);
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : 'Search request failed.');
      } finally {
        setLoading(false);
      }
    }, 200);

    return () => clearTimeout(timer);
  }, [query]);

  if (!isOpen) return null;

  const handleSelect = (url: string) => {
    onClose();
    navigate(url);
  };

  const handleInputKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      const first = containerRef.current?.querySelector<HTMLButtonElement>('.search-result-item');
      first?.focus();
    }
  };

  const handleResultKeyDown = (e: React.KeyboardEvent<HTMLButtonElement>, targetUrl: string) => {
    const allItems = Array.from(containerRef.current?.querySelectorAll<HTMLButtonElement>('.search-result-item') || []);
    const idx = allItems.indexOf(e.currentTarget);

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (idx >= 0 && idx < allItems.length - 1) {
        allItems[idx + 1].focus();
      }
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (idx > 0) {
        allItems[idx - 1].focus();
      } else {
        inputRef.current?.focus();
      }
    } else if (e.key === 'Enter') {
      e.preventDefault();
      handleSelect(targetUrl);
    }
  };

  const hasAssessments = (results?.assessments?.length ?? 0) > 0;
  const hasFindings = (results?.findings?.length ?? 0) > 0;
  const hasEvidence = (results?.evidence?.length ?? 0) > 0;
  const hasAnyResults = hasAssessments || hasFindings || hasEvidence;
  const isSearching = query.trim().length > 0;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-16 sm:pt-24 px-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-150"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Global Search"
    >
      <div
        className="w-full max-w-2xl bg-surface border border-[var(--border)] rounded-xl shadow-2xl overflow-hidden flex flex-col max-h-[80vh]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Search Input Bar */}
        <div className="flex items-center px-4 border-b border-[var(--border)] bg-surface-2/60">
          <Search className="w-5 h-5 text-3 flex-shrink-0" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleInputKeyDown}
            placeholder="Search assessments, findings, detectors (e.g. DI-01), evidence…"
            className="w-full px-3 py-3.5 bg-transparent text-1 placeholder:text-3 text-sm focus:outline-none"
            aria-label="Search query"
          />
          {loading && (
            <Loader2 className="w-4 h-4 text-accent animate-spin flex-shrink-0 mr-2" />
          )}
          {query && (
            <button
              type="button"
              onClick={() => setQuery('')}
              className="p-1 rounded text-3 hover:text-1 hover:bg-surface-2 transition-colors mr-1.5"
              aria-label="Clear search"
            >
              <X className="w-4 h-4" />
            </button>
          )}
          <kbd className="hidden sm:inline-flex items-center gap-1 font-mono text-[10px] text-3 px-1.5 py-0.5 rounded bg-surface border border-[var(--border)] select-none">
            ESC
          </kbd>
        </div>

        {/* Results Container */}
        <div ref={containerRef} className="overflow-y-auto flex-1 divide-y divide-[var(--border)]/60 p-2 space-y-4">
          {error && (
            <div className="p-4 text-xs text-[var(--red)] bg-[var(--red-bg)] rounded-lg m-2">
              {error}
            </div>
          )}

          {/* Empty Query Initial State */}
          {!isSearching && (
            <div className="p-8 text-center space-y-3">
              <div className="inline-flex p-3 rounded-xl bg-surface-2 text-3 mb-1">
                <Command className="w-6 h-6 text-accent" />
              </div>
              <p className="text-sm font-semibold text-1">Lightweight Global Search</p>
              <p className="text-xs text-3 max-w-sm mx-auto leading-relaxed">
                Quickly locate assessments, findings, detectors (such as DI-01 or MI-05), evidence records, and ingested assets across persisted database tables.
              </p>
              <div className="flex items-center justify-center gap-2 pt-2">
                <span className="text-[11px] font-mono text-3 px-2 py-0.5 rounded bg-surface-2 border border-[var(--border)]">
                  Ctrl + K
                </span>
                <span className="text-xs text-3">to open anytime</span>
              </div>
            </div>
          )}

          {/* No Match State */}
          {isSearching && !loading && !hasAnyResults && (
            <div className="p-8 text-center space-y-2">
              <Database className="w-6 h-6 text-3 mx-auto mb-1" />
              <p className="text-sm font-semibold text-1">No results found for &ldquo;{query}&rdquo;</p>
              <p className="text-xs text-3 max-w-sm mx-auto">
                No matching assessments, findings, or evidence. Try checking spelling or search by detector code like <span className="font-mono text-accent">DI-01</span> or <span className="font-mono text-accent">MI-02</span>.
              </p>
            </div>
          )}

          {/* 1. Assessments Group */}
          {hasAssessments && (
            <div className="space-y-1 pt-1 first:pt-0">
              <div className="px-3 py-1 flex items-center justify-between text-[11px] font-mono font-bold tracking-wider text-3 uppercase">
                <span>Assessments ({results?.counts?.assessments})</span>
              </div>
              {results?.assessments.map((asm: SearchResultAssessment) => (
                <button
                  key={asm.assessment_id}
                  type="button"
                  onClick={() => handleSelect(asm.target_url)}
                  onKeyDown={(e) => handleResultKeyDown(e, asm.target_url)}
                  className="search-result-item w-full text-left px-3 py-2.5 rounded-lg hover:bg-surface-2 focus-visible:bg-surface-2 focus-visible:ring-2 focus-visible:ring-accent focus:outline-none transition-colors flex items-center justify-between gap-3 group cursor-pointer"
                >
                  <div className="flex items-center gap-2.5 min-w-0">
                    <FileText className="w-4 h-4 text-accent flex-shrink-0" />
                    <div className="min-w-0">
                      <div className="text-xs font-semibold text-1 truncate group-hover:text-accent transition-colors">
                        {asm.title}
                      </div>
                      <div className="flex items-center gap-2 mt-0.5">
                        <span className="font-mono text-[10px] text-3 px-1.5 py-0.2 rounded bg-surface border border-[var(--border)]">
                          {asm.assessment_id}
                        </span>
                        <span className="text-[11px] text-3">
                          {formatDatetime(asm.created_at)}
                        </span>
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <span className={cn(
                      'text-[10px] font-mono font-medium px-2 py-0.5 rounded border uppercase',
                      asm.state?.toLowerCase() === 'complete' ? 'bg-[var(--green-bg)] text-[var(--green)] border-[var(--green)]/30' : 'bg-surface-2 text-2 border-[var(--border)]'
                    )}>
                      {asm.state?.toUpperCase()}
                    </span>
                    <ExternalLink className="w-3.5 h-3.5 text-3 group-hover:text-1 opacity-0 group-hover:opacity-100 transition-opacity" />
                  </div>
                </button>
              ))}
            </div>
          )}

          {/* 2. Findings Group */}
          {hasFindings && (
            <div className="space-y-1 pt-2">
              <div className="px-3 py-1 flex items-center justify-between text-[11px] font-mono font-bold tracking-wider text-3 uppercase">
                <span>Findings ({results?.counts?.findings})</span>
              </div>
              {results?.findings.map((fnd: SearchResultFinding) => (
                <button
                  key={fnd.finding_id}
                  type="button"
                  onClick={() => handleSelect(fnd.target_url)}
                  onKeyDown={(e) => handleResultKeyDown(e, fnd.target_url)}
                  className="search-result-item w-full text-left px-3 py-2.5 rounded-lg hover:bg-surface-2 focus-visible:bg-surface-2 focus-visible:ring-2 focus-visible:ring-accent focus:outline-none transition-colors flex items-center justify-between gap-3 group cursor-pointer"
                >
                  <div className="flex items-center gap-2.5 min-w-0">
                    <TriangleAlert className="w-4 h-4 text-[var(--yellow)] flex-shrink-0" />
                    <div className="min-w-0">
                      <div className="text-xs font-semibold text-1 truncate group-hover:text-accent transition-colors">
                        {fnd.title}
                      </div>
                      <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                        <span className="font-mono text-[10px] text-3">
                          {fnd.finding_id}
                        </span>
                        {fnd.detector_code && (
                          <span className="font-mono text-[10px] font-semibold text-accent px-1.5 py-0.2 rounded bg-[var(--accent-bg)] border border-accent/20">
                            {fnd.detector_code}
                          </span>
                        )}
                        {fnd.asset_name && (
                          <span className="text-[11px] text-3 truncate max-w-[150px]">
                            {fnd.asset_name}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <span className={cn(
                      'text-[10px] font-mono font-semibold px-2 py-0.5 rounded border uppercase',
                      fnd.severity?.toLowerCase() === 'critical' || fnd.severity?.toLowerCase() === 'high'
                        ? 'bg-[var(--red-bg)] text-[var(--red)] border-[var(--red)]/30'
                        : fnd.severity?.toLowerCase() === 'medium'
                        ? 'bg-[var(--yellow-bg)] text-[var(--yellow)] border-[var(--yellow)]/30'
                        : 'bg-surface-2 text-2 border-[var(--border)]'
                    )}>
                      {fnd.severity?.toUpperCase()}
                    </span>
                    <ExternalLink className="w-3.5 h-3.5 text-3 group-hover:text-1 opacity-0 group-hover:opacity-100 transition-opacity" />
                  </div>
                </button>
              ))}
            </div>
          )}

          {/* 3. Evidence Group */}
          {hasEvidence && (
            <div className="space-y-1 pt-2">
              <div className="px-3 py-1 flex items-center justify-between text-[11px] font-mono font-bold tracking-wider text-3 uppercase">
                <span>Evidence ({results?.counts?.evidence})</span>
              </div>
              {results?.evidence.map((evi: SearchResultEvidence) => (
                <button
                  key={evi.evidence_id}
                  type="button"
                  onClick={() => handleSelect(evi.target_url)}
                  onKeyDown={(e) => handleResultKeyDown(e, evi.target_url)}
                  className="search-result-item w-full text-left px-3 py-2.5 rounded-lg hover:bg-surface-2 focus-visible:bg-surface-2 focus-visible:ring-2 focus-visible:ring-accent focus:outline-none transition-colors flex items-center justify-between gap-3 group cursor-pointer"
                >
                  <div className="flex items-center gap-2.5 min-w-0">
                    <FileSearch className="w-4 h-4 text-accent flex-shrink-0" />
                    <div className="min-w-0">
                      <div className="text-xs font-semibold text-1 truncate group-hover:text-accent transition-colors">
                        {evi.description}
                      </div>
                      <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                        <span className="font-mono text-[10px] text-3">
                          {evi.evidence_id}
                        </span>
                        {evi.detector_code && (
                          <span className="font-mono text-[10px] font-semibold text-accent px-1.5 py-0.2 rounded bg-[var(--accent-bg)] border border-accent/20">
                            {evi.detector_code}
                          </span>
                        )}
                        {evi.finding_title && (
                          <span className="text-[11px] text-3 truncate max-w-[200px]">
                            {evi.finding_title}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <span className="text-[10px] font-mono text-3 px-1.5 py-0.5 rounded bg-surface border border-[var(--border)]">
                      {evi.evidence_type}
                    </span>
                    <ExternalLink className="w-3.5 h-3.5 text-3 group-hover:text-1 opacity-0 group-hover:opacity-100 transition-opacity" />
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-4 py-2 bg-surface-2/40 border-t border-[var(--border)] flex items-center justify-between text-[11px] text-3">
          <span>Click any item to navigate to its assessment workspace</span>
          <span className="hidden sm:inline">PRAMAAN Global Search</span>
        </div>
      </div>
    </div>
  );
}
