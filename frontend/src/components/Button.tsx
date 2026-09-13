import { forwardRef } from 'react';
import { cn } from '../lib/cn';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger';
type Size = 'sm' | 'md' | 'lg';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  isLoading?: boolean;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
}

const VARIANT_CLASSES: Record<Variant, string> = {
  primary: [
    'bg-[var(--accent)] text-white border-transparent',
    'hover:bg-[var(--accent-hover)]',
    'disabled:opacity-50 disabled:cursor-not-allowed',
    'active:scale-[0.97]',
  ].join(' '),
  secondary: [
    'bg-transparent text-[var(--text-primary)] border-[var(--border)]',
    'hover:bg-[var(--surface-2)]',
    'disabled:opacity-50 disabled:cursor-not-allowed',
    'active:scale-[0.97]',
  ].join(' '),
  ghost: [
    'bg-transparent text-[var(--text-secondary)] border-transparent',
    'hover:bg-[var(--surface-2)] hover:text-[var(--text-primary)]',
    'disabled:opacity-50 disabled:cursor-not-allowed',
    'active:scale-[0.97]',
  ].join(' '),
  danger: [
    'bg-[var(--risk-critical)] text-white border-transparent',
    'hover:opacity-90',
    'disabled:opacity-50 disabled:cursor-not-allowed',
    'active:scale-[0.97]',
  ].join(' '),
};

const SIZE_CLASSES: Record<Size, string> = {
  sm: 'text-xs px-3 py-1.5 gap-1.5',
  md: 'text-sm px-4 py-2 gap-2',
  lg: 'text-sm px-5 py-2.5 gap-2',
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = 'primary', size = 'md', isLoading, leftIcon, rightIcon, children, className, disabled, ...props }, ref) => {
    return (
      <button
        ref={ref}
        disabled={disabled || isLoading}
        aria-busy={isLoading}
        aria-disabled={disabled || isLoading}
        className={cn(
          'inline-flex items-center justify-center font-medium rounded border',
          'transition-all duration-150 cursor-pointer',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-1',
          VARIANT_CLASSES[variant],
          SIZE_CLASSES[size],
          (disabled || isLoading) && 'opacity-60 cursor-not-allowed active:scale-100',
          className,
        )}
        {...props}
      >
        {isLoading ? (
          <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
        ) : leftIcon}
        {children}
        {!isLoading && rightIcon}
      </button>
    );
  },
);
Button.displayName = 'Button';
