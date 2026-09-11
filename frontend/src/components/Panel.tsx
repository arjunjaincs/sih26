import { cn } from '../lib/cn';

interface PanelProps {
  title?: string;
  description?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  noPadding?: boolean;
}

export function Panel({ title, description, actions, children, className, noPadding }: PanelProps) {
  return (
    <section
      className={cn(
        'rounded-lg border bg-[var(--surface-elevated)] shadow-[var(--shadow-sm)]',
        'border-[var(--border)]',
        className,
      )}
    >
      {(title || actions) && (
        <div className="flex items-start justify-between gap-4 px-5 py-4 border-b border-[var(--border)]">
          <div>
            {title && (
              <h2 className="text-sm font-semibold text-[var(--text-primary)] tracking-tight">
                {title}
              </h2>
            )}
            {description && (
              <p className="mt-0.5 text-xs text-[var(--text-muted)]">{description}</p>
            )}
          </div>
          {actions && <div className="flex items-center gap-2 flex-shrink-0">{actions}</div>}
        </div>
      )}
      <div className={cn(!noPadding && 'px-5 py-4')}>{children}</div>
    </section>
  );
}
