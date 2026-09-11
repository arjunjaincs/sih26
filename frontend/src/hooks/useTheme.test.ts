import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock localStorage and matchMedia for ThemeProvider
beforeEach(() => {
  Object.defineProperty(window, 'localStorage', {
    value: {
      getItem: vi.fn(() => null),
      setItem: vi.fn(),
      removeItem: vi.fn(),
    },
    writable: true,
  });
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  });
});

describe('useTheme', () => {
  it('defaults to dark theme when no stored preference', async () => {
    const { ThemeProvider, useTheme } = await import('../hooks/useTheme');
    const { render, screen } = await import('@testing-library/react');
    const { createElement } = await import('react');

    function Probe() {
      const { theme } = useTheme();
      return createElement('div', { 'data-testid': 'theme' }, theme);
    }
    render(createElement(ThemeProvider, null, createElement(Probe)));
    expect(screen.getByTestId('theme').textContent).toBe('dark');
  });
});
