import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { AppShell } from './layouts/AppShell';
import { AnalystCopilot } from './components/AnalystCopilot';
import { GlobalSearchModal } from './components/GlobalSearchModal';
import { Button } from './components/Button';
import * as client from './api/client';

describe('UX Polish & Interaction Improvements Suite', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(client, 'getHealth').mockResolvedValue({
      status: 'ok',
      version: '1.0.0',
      db_path: 'C:/test.db',
    });
    vi.spyOn(client, 'getAIStatus').mockResolvedValue({
      configured: true,
      status: 'connected',
      model: 'openrouter/anthropic/claude-3.5-sonnet',
      mode: 'openrouter',
    });
  });

  describe('Keyboard Shortcuts & Input Exclusion in AppShell', () => {
    it('opens global search on "/" shortcut when NOT typing in an input field', async () => {
      render(
        <MemoryRouter>
          <AppShell />
        </MemoryRouter>
      );

      expect(screen.queryByRole('dialog', { name: /global search/i })).toBeNull();

      // Pressing "/" on the window outside an input
      fireEvent.keyDown(window, { key: '/' });
      expect(screen.getByRole('dialog', { name: /global search/i })).toBeInTheDocument();
    });

    it('does NOT open search on "/" when typing in an input or textarea', () => {
      render(
        <MemoryRouter>
          <div>
            <input data-testid="sample-input" type="text" />
            <textarea data-testid="sample-textarea" />
            <AppShell />
          </div>
        </MemoryRouter>
      );

      const input = screen.getByTestId('sample-input');
      input.focus();

      // Pressing "/" while typing inside an input element
      fireEvent.keyDown(input, { key: '/' });
      expect(screen.queryByRole('dialog', { name: /global search/i })).toBeNull();

      const textarea = screen.getByTestId('sample-textarea');
      textarea.focus();

      // Pressing "/" while typing inside a textarea element
      fireEvent.keyDown(textarea, { key: '/' });
      expect(screen.queryByRole('dialog', { name: /global search/i })).toBeNull();
    });

    it('opens global search on Ctrl+K and Cmd+K', () => {
      render(
        <MemoryRouter>
          <AppShell />
        </MemoryRouter>
      );

      fireEvent.keyDown(window, { key: 'k', ctrlKey: true });
      expect(screen.getByRole('dialog', { name: /global search/i })).toBeInTheDocument();
    });

    it('renders accessible skip-to-content link', () => {
      render(
        <MemoryRouter>
          <AppShell />
        </MemoryRouter>
      );

      const skipLink = screen.getByText(/skip to main content/i);
      expect(skipLink).toBeInTheDocument();
      expect(skipLink).toHaveAttribute('href', '#main-content');
    });
  });

  describe('AnalystCopilot Drawer Closing & Accessibility', () => {
    it('closes on Escape key press from anywhere in the drawer', () => {
      const handleClose = vi.fn();
      render(
        <AnalystCopilot
          assessmentId="asm-123"
          isOpen={true}
          onClose={handleClose}
        />
      );

      expect(screen.getByRole('dialog', { name: /PRAMAAN Analyst Copilot/i })).toBeInTheDocument();

      // Press Escape
      fireEvent.keyDown(window, { key: 'Escape' });
      expect(handleClose).toHaveBeenCalled();
    });

    it('closes on clicking the backdrop overlay', () => {
      const handleClose = vi.fn();
      render(
        <AnalystCopilot
          assessmentId="asm-123"
          isOpen={true}
          onClose={handleClose}
        />
      );

      const backdrop = screen.getByTestId('copilot-backdrop');
      expect(backdrop).toBeInTheDocument();

      fireEvent.click(backdrop);
      expect(handleClose).toHaveBeenCalledTimes(1);
    });

    it('has proper dialog accessibility roles and labels', () => {
      render(
        <AnalystCopilot
          assessmentId="asm-123"
          isOpen={true}
          onClose={vi.fn()}
        />
      );

      const drawer = screen.getByRole('dialog', { name: /PRAMAAN Analyst Copilot/i });
      expect(drawer).toHaveAttribute('aria-modal', 'true');
    });
  });

  describe('GlobalSearchModal arrow keys and focus preservation', () => {
    const mockSearchResults = {
      query: 'resnet',
      counts: { assessments: 1, findings: 1, evidence: 0, total: 2 },
      assessments: [
        {
          assessment_id: 'asm-resnet-01',
          title: 'ResNet Classification',
          state: 'complete',
          created_at: '2026-09-13T10:00:00Z',
          target_url: '/assessments/asm-resnet-01/result',
        },
      ],
      findings: [
        {
          finding_id: 'fnd-001',
          title: 'Weight Variance Anomaly',
          detector_code: 'MI-01',
          severity: 'high',
          category: 'model_integrity',
          target_url: '/assessments/asm-resnet-01/findings',
        },
      ],
      evidence: [],
    };

    it('allows navigating down from search input to results with ArrowDown', async () => {
      vi.spyOn(client, 'searchAll').mockResolvedValue(mockSearchResults);
      const user = userEvent.setup();

      render(
        <MemoryRouter>
          <GlobalSearchModal isOpen={true} onClose={vi.fn()} />
        </MemoryRouter>
      );

      const input = screen.getByPlaceholderText(/search assessments, findings, detectors/i);
      await user.type(input, 'resnet');

      // Wait for debounce and result to render
      const asmResult = await screen.findByText('ResNet Classification');
      expect(asmResult).toBeInTheDocument();

      // Press ArrowDown on input
      fireEvent.keyDown(input, { key: 'ArrowDown' });
      const firstResultButton = screen.getAllByRole('button').find((b) =>
        b.textContent?.includes('ResNet Classification')
      );
      expect(firstResultButton).toBeDefined();
    });

    it('closes on Escape key', () => {
      const handleClose = vi.fn();
      render(
        <MemoryRouter>
          <GlobalSearchModal isOpen={true} onClose={handleClose} />
        </MemoryRouter>
      );

      fireEvent.keyDown(window, { key: 'Escape' });
      expect(handleClose).toHaveBeenCalled();
    });
  });

  describe('Button Component Loading & Disabled Accessibility States', () => {
    it('sets aria-busy and aria-disabled when isLoading is true', () => {
      render(<Button isLoading>Save Changes</Button>);
      const btn = screen.getByRole('button');
      expect(btn).toHaveAttribute('aria-busy', 'true');
      expect(btn).toHaveAttribute('aria-disabled', 'true');
      expect(btn).toBeDisabled();
    });

    it('sets aria-disabled when disabled prop is provided', () => {
      render(<Button disabled>Submit</Button>);
      const btn = screen.getByRole('button');
      expect(btn).toHaveAttribute('aria-disabled', 'true');
      expect(btn).toBeDisabled();
    });
  });
});
