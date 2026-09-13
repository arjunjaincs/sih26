import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';
import { MetricTooltip, AssuranceInterpretationGuide, METRIC_SEMANTICS } from './components/MetricTooltip';
import { MetricTriad } from './components/MetricTriad';
import { FindingCard } from './components/FindingCard';
import type { FindingSchema } from './types/api';

describe('MetricTooltip component semantics & accessibility', () => {
  it('renders risk tooltip with strict ADR-003 semantics', async () => {
    render(<MetricTooltip metric="risk" />);
    const trigger = screen.getByRole('button', { name: /Semantics for Overall Risk/i });
    expect(trigger).toBeInTheDocument();
    expect(trigger).toHaveAttribute('aria-expanded', 'false');

    // Click to open
    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute('aria-expanded', 'true');

    // Dialog contents
    const dialog = screen.getByRole('dialog', { name: /Overall Risk Semantics/i });
    expect(dialog).toBeInTheDocument();
    expect(dialog).toHaveTextContent(/Risk is NOT confidence/i);
    expect(dialog).toHaveTextContent(/INCONCLUSIVE/i);
    expect(dialog).toHaveTextContent(/Never treat low risk as proof of safety/i);
  });

  it('renders confidence tooltip with strict ADR-003 semantics', () => {
    render(<MetricTooltip metric="confidence" />);
    const trigger = screen.getByRole('button', { name: /Semantics for Confidence Level/i });
    fireEvent.click(trigger);

    const dialog = screen.getByRole('dialog', { name: /Confidence Level Semantics/i });
    expect(dialog).toBeInTheDocument();
    expect(dialog).toHaveTextContent(/Confidence is NOT risk/i);
    expect(dialog).toHaveTextContent(/NEVER indicates safety/i);
    expect(dialog).toHaveTextContent(/INVESTIGATION IS WARRANTED/i);
  });

  it('renders coverage tooltip emphasizing no composite trust score and explicit gaps', () => {
    render(<MetricTooltip metric="coverage" />);
    const trigger = screen.getByRole('button', { name: /Semantics for Coverage/i });
    fireEvent.click(trigger);

    const dialog = screen.getByRole('dialog', { name: /Coverage Semantics/i });
    expect(dialog).toBeInTheDocument();
    expect(dialog).toHaveTextContent(/Coverage is NOT a trust score/i);
    expect(dialog).toHaveTextContent(/reduces assurance by leaving uninspected blind spots/i);
    expect(dialog).toHaveTextContent(/No single composite trust score exists/i);
  });

  it('renders severity tooltip explaining defect impact', () => {
    render(<MetricTooltip metric="severity" />);
    const trigger = screen.getByRole('button', { name: /Semantics for Finding Severity/i });
    fireEvent.click(trigger);

    const dialog = screen.getByRole('dialog', { name: /Finding Severity Semantics/i });
    expect(dialog).toBeInTheDocument();
    expect(dialog).toHaveTextContent(/Potential consequence and operational impact/i);
    expect(dialog).toHaveTextContent(/graded from Info to Critical independently of overall confidence/i);
    expect(dialog).toHaveTextContent(/Critical or High severity findings require prompt remediation/i);
  });

  it('supports keyboard navigation: Enter/Space to open, Escape to close', async () => {
    const user = userEvent.setup();
    render(<MetricTooltip metric="risk" />);
    const trigger = screen.getByRole('button', { name: /Semantics for Overall Risk/i });

    // Focus via keyboard
    trigger.focus();
    expect(trigger).toHaveFocus();

    // Open via Enter
    await user.keyboard('{Enter}');
    expect(screen.getByRole('dialog', { name: /Overall Risk Semantics/i })).toBeInTheDocument();

    // Close via Escape
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog', { name: /Overall Risk Semantics/i })).not.toBeInTheDocument();

    // Open via Space
    await user.keyboard(' ');
    expect(screen.getByRole('dialog', { name: /Overall Risk Semantics/i })).toBeInTheDocument();
  });

  it('closes when clicking outside the tooltip', () => {
    render(
      <div>
        <MetricTooltip metric="confidence" />
        <button type="button" data-testid="outside-button">Outside</button>
      </div>
    );

    const trigger = screen.getByRole('button', { name: /Semantics for Confidence Level/i });
    fireEvent.click(trigger);
    expect(screen.getByRole('dialog')).toBeInTheDocument();

    // Click outside
    fireEvent.pointerDown(screen.getByTestId('outside-button'));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});

describe('AssuranceInterpretationGuide', () => {
  it('renders decoupled matrix explaining low risk + low conf, high risk + low conf, and coverage', () => {
    render(<AssuranceInterpretationGuide />);

    // Check initial closed state
    expect(screen.getByText(/Assurance Metric Semantics \(ADR-003\)/i)).toBeInTheDocument();
    const toggleBtn = screen.getByRole('button', { name: /Explain Decoupled Matrix/i });

    // Expand
    fireEvent.click(toggleBtn);
    expect(screen.getByText(/LOW RISK \+ LOW CONFIDENCE/i)).toBeInTheDocument();
    expect(screen.getByText(/HIGH RISK \+ LOW CONFIDENCE/i)).toBeInTheDocument();
    expect(screen.getByText(/INCOMPLETE COVERAGE/i)).toBeInTheDocument();
    expect(screen.getByText(/Inconclusive:/i)).toBeInTheDocument();
    expect(screen.getByText(/Investigation Warranted:/i)).toBeInTheDocument();
    expect(screen.getByText(/Reduces Assurance:/i)).toBeInTheDocument();
    expect(screen.getByText(/Never collapse metrics into a single "trust score"/i)).toBeInTheDocument();
  });
});

describe('MetricTriad integration with tooltips', () => {
  it('renders full mode with tooltips for risk, confidence, coverage and interpretation guide', () => {
    render(
      <MetricTriad
        overallRisk="low"
        overallConfidence="low"
        coverageFraction={0.75}
        detectorsExecutedCount={3}
        totalDetectorsCount={4}
      />
    );

    // Cards should render
    expect(screen.getByText('Overall Risk')).toBeInTheDocument();
    expect(screen.getByText('Confidence')).toBeInTheDocument();
    expect(screen.getByText('Coverage')).toBeInTheDocument();

    // Tooltip triggers should exist for all 3 metrics
    const triggers = screen.getAllByRole('button', { name: /Semantics for/i });
    expect(triggers.length).toBeGreaterThanOrEqual(3);

    // Guide is rendered
    expect(screen.getByText(/Assurance Metric Semantics \(ADR-003\)/i)).toBeInTheDocument();
  });

  it('renders compact mode with accessible tooltip affordances', () => {
    render(
      <MetricTriad
        overallRisk="high"
        overallConfidence="moderate"
        coverageFraction={0.88}
        compact
      />
    );

    expect(screen.getByText('RISK:')).toBeInTheDocument();
    expect(screen.getByText('HIGH')).toBeInTheDocument();
    expect(screen.getByText('CONFIDENCE:')).toBeInTheDocument();
    expect(screen.getByText('MODERATE')).toBeInTheDocument();
    expect(screen.getByText('COVERAGE:')).toBeInTheDocument();
    expect(screen.getByText('88%')).toBeInTheDocument();

    // Compact badges contain tooltip triggers
    const triggers = screen.getAllByRole('button', { name: /Semantics for/i });
    expect(triggers.length).toBe(3);
  });
});

describe('FindingCard integration with severity tooltip', () => {
  const sampleFinding: FindingSchema = {
    finding_id: 'FIND-001',
    assessment_id: 'ASM-123',
    detector_id: 'DI01',
    category: 'data_integrity',
    subcategory: 'duplicates',
    severity: 'high',
    title: 'Perceptual Duplicate Anomaly',
    description: 'Near-duplicate image assets discovered in validation split.',
    created_at: '2026-09-13T10:00:00Z',
    confidence_score: 0.85,
    asset_id: 'dataset/img_1.jpg',
    detection_method: 'Perceptual Hash Centroid',
    limitations: ['Small sample size'],
    recommended_disposition: 'Inspect and deduplicate',
    evidence_ids: ['EVD-001'],
  };

  it('renders severity tooltip trigger alongside severity badge', () => {
    render(<FindingCard finding={sampleFinding} />);
    expect(screen.getByText('High')).toBeInTheDocument();

    const severityTrigger = screen.getByRole('button', { name: /Semantics for Finding Severity/i });
    expect(severityTrigger).toBeInTheDocument();

    fireEvent.click(severityTrigger);
    expect(screen.getByRole('dialog', { name: /Finding Severity Semantics/i })).toBeInTheDocument();
  });
});
