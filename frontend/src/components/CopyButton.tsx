import { useState } from 'react';
import { Copy, Check } from 'lucide-react';
import { cn } from '../lib/cn';

interface CopyButtonProps {
  value: string;
  className?: string;
  title?: string;
}

export function CopyButton({ value, className, title = 'Copy to clipboard' }: CopyButtonProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard API not available
    }
  };

  return (
    <button
      onClick={handleCopy}
      title={title}
      aria-label={title}
      className={cn(
        'inline-flex items-center justify-center w-6 h-6 rounded',
        'text-[var(--text-muted)] hover:text-[var(--text-primary)]',
        'hover:bg-[var(--surface-2)]',
        'transition-colors duration-150',
        className,
      )}
    >
      {copied ? (
        <Check className="w-3.5 h-3.5 text-[var(--risk-none)]" />
      ) : (
        <Copy className="w-3.5 h-3.5" />
      )}
    </button>
  );
}
