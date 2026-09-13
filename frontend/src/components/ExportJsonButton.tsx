import { useState } from 'react';
import { FileJson, Loader2 } from 'lucide-react';
import { exportAssessmentJson } from '../api/client';
import { cn } from '../lib/cn';

interface ExportJsonButtonProps {
  assessmentId: string;
  className?: string;
  variant?: 'primary' | 'secondary' | 'outline' | 'ghost';
  size?: 'sm' | 'md';
  label?: string;
}

export function ExportJsonButton({
  assessmentId,
  className,
  variant = 'outline',
  size = 'md',
  label = 'Export JSON',
}: ExportJsonButtonProps) {
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleExport = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (exporting) return;

    setExporting(true);
    setError(null);

    try {
      await exportAssessmentJson(assessmentId);
    } catch (err) {
      console.error('Failed to export machine-readable JSON package:', err);
      setError('Export failed');
      setTimeout(() => setError(null), 3000);
    } finally {
      setExporting(false);
    }
  };

  const baseStyle =
    'inline-flex items-center justify-center gap-1.5 font-semibold rounded-lg transition-all duration-150 select-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent';

  const sizeStyle =
    size === 'sm'
      ? 'px-2.5 py-1 text-xs'
      : 'px-3.5 py-2 text-xs sm:text-sm';

  const variantStyle =
    variant === 'primary'
      ? 'bg-accent hover:bg-[var(--accent-2)] text-white shadow-sm active:scale-[0.98]'
      : variant === 'outline'
      ? 'border border-[var(--border)] bg-surface hover:bg-surface-2 text-1 hover:border-accent/40 shadow-sm'
      : variant === 'secondary'
      ? 'bg-surface-2 hover:bg-surface text-1 border border-[var(--border)]'
      : 'text-2 hover:text-1 hover:bg-surface-2';

  return (
    <button
      type="button"
      onClick={handleExport}
      disabled={exporting}
      title="Export Machine-Readable JSON Assurance Package"
      aria-label="Export Machine-Readable JSON Assurance Package"
      className={cn(baseStyle, sizeStyle, variantStyle, className)}
    >
      {exporting ? (
        <>
          <Loader2 className="w-3.5 h-3.5 animate-spin text-inherit" />
          <span>Exporting…</span>
        </>
      ) : error ? (
        <span className="text-[var(--red)]">{error}</span>
      ) : (
        <>
          <FileJson className="w-3.5 h-3.5 text-inherit" />
          <span>{label}</span>
        </>
      )}
    </button>
  );
}
