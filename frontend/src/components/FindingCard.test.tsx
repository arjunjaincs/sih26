import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { FindingCard } from '../components/FindingCard';
import type { FindingSchema } from '../types/api';

const MOCK_FINDING: FindingSchema = {
  finding_id: 'f-001',
  assessment_id: 'a-001',
  asset_id: 'dataset-001',
  category: 'data_integrity',
  subcategory: 'near_duplicate',
  severity: 'medium',
  title: 'Near-duplicate images detected',
  description: 'DI-01 found clusters of perceptually similar images.',
  detection_method: 'Perceptual hashing (pHash + dHash)',
  detector_id: 'DI-01',
  limitations: ['Only detects visual similarity, not semantic.'],
  recommended_disposition: 'Review and de-duplicate the affected images.',
  created_at: '2026-09-11T10:00:00Z',
};

describe('FindingCard', () => {
  it('renders title and category', () => {
    render(<FindingCard finding={MOCK_FINDING} />);
    expect(screen.getByText('Near-duplicate images detected')).toBeDefined();
    expect(screen.getByText('Data Integrity')).toBeDefined();
  });

  it('renders severity badge', () => {
    render(<FindingCard finding={MOCK_FINDING} />);
    expect(screen.getByText('Medium')).toBeDefined();
  });

  it('expands to show detailed fields on click', async () => {
    const user = userEvent.setup();
    render(<FindingCard finding={MOCK_FINDING} />);
    const button = screen.getByRole('button');
    await user.click(button);
    expect(screen.getByText('near_duplicate')).toBeDefined();
    expect(screen.getByText('DI-01')).toBeDefined();
  });

  it('shows recommended disposition when expanded', async () => {
    const user = userEvent.setup();
    render(<FindingCard finding={MOCK_FINDING} />);
    await user.click(screen.getByRole('button'));
    expect(screen.getByText('Review and de-duplicate the affected images.')).toBeDefined();
  });
});
