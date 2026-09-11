import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StatusBadge } from '../components/StatusBadge';

describe('StatusBadge', () => {
  it('renders risk label correctly', () => {
    render(<StatusBadge value="high" variant="risk" />);
    expect(screen.getByText('High')).toBeDefined();
  });

  it('renders "none" risk', () => {
    render(<StatusBadge value="none" variant="risk" />);
    expect(screen.getByText('None')).toBeDefined();
  });

  it('renders "critical" severity', () => {
    render(<StatusBadge value="critical" variant="severity" />);
    expect(screen.getByText('Critical')).toBeDefined();
  });

  it('renders confidence level', () => {
    render(<StatusBadge value="moderate" variant="confidence" />);
    expect(screen.getByText('Moderate')).toBeDefined();
  });

  it('renders status badge', () => {
    render(<StatusBadge value="complete" variant="status" />);
    expect(screen.getByText('Complete')).toBeDefined();
  });

  it('renders unknown value as title-cased label', () => {
    render(<StatusBadge value="custom_status" variant="neutral" />);
    expect(screen.getByText('Custom Status')).toBeDefined();
  });

  it('renders category badge', () => {
    render(<StatusBadge value="data_integrity" variant="category" />);
    expect(screen.getByText('Data Integrity')).toBeDefined();
  });
});
