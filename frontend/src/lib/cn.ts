import { clsx, type ClassValue } from 'clsx';

/** Utility for conditional class merging. */
export function cn(...inputs: ClassValue[]): string {
  return clsx(inputs);
}
