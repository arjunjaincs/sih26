import { cn } from '../lib/cn';

interface MetricBlockProps {
  label: string;
  value: React.ReactNode;
  description?: string;
  emphasis?: boolean;
  className?: string;
}

/**
 * Displays a single analyst metric: Risk / Confidence / Coverage etc.
 * Deliberately simple — no sparklines, no fake progress bars.
 */
export function MetricBlock({ label, value, description, emphasis, className }: MetricBlockProps) {
  return (
    <div
      className={cn(
        'flex flex-col gap-1 p-4 rounded-lg border bg-[var(--surface-1)]',
        'border-[var(--border)]',
        emphasis && 'border-[var(--accent)] bg-[var(--accent-light)]',
        className,
      )}
    >
      <span className="text-[10px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">
        {label}
      </span>
      <span className="text-xl font-bold text-[var(--text-primary)] leading-tight">
        {value}
      </span>
      {description && (
        <span className="text-xs text-[var(--text-muted)] leading-snug">{description}</span>
      )}
    </div>
  );
}
