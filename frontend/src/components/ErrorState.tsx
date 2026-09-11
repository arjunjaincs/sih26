import { AlertTriangle, WifiOff } from 'lucide-react';
import { cn } from '../lib/cn';
import { Button } from './Button';

interface ErrorStateProps {
  title?: string;
  message: string;
  isNetwork?: boolean;
  onRetry?: () => void;
  className?: string;
}

export function ErrorState({
  title,
  message,
  isNetwork,
  onRetry,
  className,
}: ErrorStateProps) {
  const Icon = isNetwork ? WifiOff : AlertTriangle;
  const heading = title ?? (isNetwork ? 'Backend Unavailable' : 'Error');

  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center gap-3 py-12 px-6 text-center',
        className,
      )}
      role="alert"
    >
      <div className="flex items-center justify-center w-10 h-10 rounded-full bg-[var(--risk-critical-bg)]">
        <Icon className="w-5 h-5 text-[var(--risk-critical)]" />
      </div>
      <div>
        <p className="text-sm font-semibold text-[var(--text-primary)]">{heading}</p>
        <p className="mt-1 text-xs text-[var(--text-muted)] max-w-sm leading-relaxed">{message}</p>
        {isNetwork && (
          <p className="mt-1 text-xs text-[var(--text-muted)]">
            Start the local assurance service to continue.
          </p>
        )}
      </div>
      {onRetry && (
        <Button variant="secondary" size="sm" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}
