import { useState } from 'react';
import { FileDown, Loader2 } from 'lucide-react';
import { downloadReport } from '../api/client';
import { cn } from '../lib/cn';

interface ReportDownloadButtonProps {
  assessmentId: string;
  className?: string;
  variant?: 'primary' | 'secondary' | 'outline' | 'ghost';
  size?: 'sm' | 'md';
}

export function ReportDownloadButton({
  assessmentId,
  className,
  variant = 'primary',
  size = 'md',
}: ReportDownloadButtonProps) {
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleDownload = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (downloading) return;

    setDownloading(true);
    setError(null);

    try {
      await downloadReport(assessmentId);
    } catch (err) {
      console.error('Failed to download PDF assurance report:', err);
      setError('Download failed');
      setTimeout(() => setError(null), 3000);
    } finally {
      setDownloading(false);
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
      onClick={handleDownload}
      disabled={downloading}
      title="Download Official PDF Assurance Report"
      aria-label="Download Official PDF Assurance Report"
      className={cn(baseStyle, sizeStyle, variantStyle, className)}
    >
      {downloading ? (
        <>
          <Loader2 className="w-3.5 h-3.5 animate-spin text-inherit" />
          <span>Generating PDF…</span>
        </>
      ) : error ? (
        <span className="text-[var(--red)]">{error}</span>
      ) : (
        <>
          <FileDown className="w-3.5 h-3.5 text-inherit" />
          <span>Download Assurance Report</span>
        </>
      )}
    </button>
  );
}
