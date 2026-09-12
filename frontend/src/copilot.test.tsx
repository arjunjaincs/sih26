import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AnalystCopilot } from './components/AnalystCopilot';
import { Settings } from './pages/Settings';
import * as client from './api/client';

vi.mock('./api/client', async () => {
  const actual = await vi.importActual<typeof client>('./api/client');
  return {
    ...actual,
    getAIStatus: vi.fn(),
    chatWithCopilot: vi.fn(),
    testAIConnection: vi.fn(),
  };
});

describe('AnalystCopilot Component', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('does not render when isOpen is false', () => {
    render(
      <MemoryRouter>
        <AnalystCopilot
          assessmentId="asmt-1"
          isOpen={false}
          onClose={() => {}}
        />
      </MemoryRouter>,
    );
    expect(screen.queryByText('PRAMAAN Analyst Copilot')).toBeNull();
  });

  it('renders header, CLOUD AI badge, and disclosure banner when open', async () => {
    vi.mocked(client.getAIStatus).mockResolvedValueOnce({
      configured: true,
      provider: 'openrouter',
      model: 'anthropic/claude-3.5-sonnet',
      status: 'connected',
      has_api_key: true,
      privacy_disclosure: 'Cloud AI disclosure',
      available_models: ['anthropic/claude-3.5-sonnet'],
    });

    render(
      <MemoryRouter>
        <AnalystCopilot
          assessmentId="asmt-1"
          isOpen={true}
          onClose={() => {}}
        />
      </MemoryRouter>,
    );

    expect(screen.getByText('PRAMAAN Analyst Copilot')).toBeDefined();
    expect(screen.getByText('CLOUD AI')).toBeDefined();
    expect(screen.getByText(/CLOUD AI ENABLED/i)).toBeDefined();
    expect(screen.getByText(/Assessment engine remains local and authoritative/i)).toBeDefined();

    // Verify suggested question chips exist
    expect(screen.getByText('Explain the highest-risk finding')).toBeDefined();
    expect(screen.getByText('Summarize this assessment')).toBeDefined();
  });

  it('renders unconfigured guidance when status is not_configured', async () => {
    vi.mocked(client.getAIStatus).mockResolvedValueOnce({
      configured: false,
      provider: 'openrouter',
      model: 'anthropic/claude-3.5-sonnet',
      status: 'not_configured',
      has_api_key: false,
      privacy_disclosure: 'Disclosure',
      available_models: [],
    });

    render(
      <MemoryRouter>
        <AnalystCopilot
          assessmentId="asmt-1"
          isOpen={true}
          onClose={() => {}}
        />
      </MemoryRouter>,
    );

    expect(await screen.findByText('Cloud AI Not Configured')).toBeDefined();
    expect(screen.getByText(/PRAMAAN deterministic assessment execution remains 100% functional offline/i)).toBeDefined();
  });

  it('submits chat query and renders response with grounded sources', async () => {
    vi.mocked(client.getAIStatus).mockResolvedValueOnce({
      configured: true,
      provider: 'openrouter',
      model: 'anthropic/claude-3.5-sonnet',
      status: 'connected',
      has_api_key: true,
      privacy_disclosure: 'Disclosure',
      available_models: [],
    });

    vi.mocked(client.chatWithCopilot).mockResolvedValueOnce({
      answer: 'Finding PI-01 indicates duplicate samples in the dataset.',
      provider: 'openrouter',
      model: 'anthropic/claude-3.5-sonnet',
      scope: 'assessment',
      grounded: true,
      sources: [{ type: 'finding', id: 'PI-01', label: 'Finding: PI-01' }],
    });

    render(
      <MemoryRouter>
        <AnalystCopilot
          assessmentId="asmt-1"
          isOpen={true}
          onClose={() => {}}
        />
      </MemoryRouter>,
    );

    const textarea = screen.getByPlaceholderText(/Ask Copilot about this assessment/i);
    fireEvent.change(textarea, { target: { value: 'Summarize assessment' } });

    const sendBtn = screen.getByRole('button', { name: /Send message/i });
    fireEvent.click(sendBtn);

    await waitFor(() => {
      expect(screen.getByText(/Finding PI-01 indicates duplicate samples/i)).toBeDefined();
      expect(screen.getByText('PI-01')).toBeDefined();
    });
  });
});

describe('Settings Page', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('renders configuration cards and test connection button', async () => {
    vi.mocked(client.getAIStatus).mockResolvedValueOnce({
      configured: true,
      provider: 'openrouter',
      model: 'anthropic/claude-3.5-sonnet',
      status: 'connected',
      has_api_key: true,
      privacy_disclosure: 'Cloud AI privacy notice text',
      available_models: ['anthropic/claude-3.5-sonnet'],
    });

    render(
      <MemoryRouter>
        <Settings />
      </MemoryRouter>,
    );

    expect(await screen.findByText('System Settings')).toBeDefined();
    expect(screen.getByText('PRAMAAN Analyst Copilot (Cloud AI)')).toBeDefined();
    expect(screen.getByText('anthropic/claude-3.5-sonnet')).toBeDefined();
    expect(screen.getByText('Configured (Masked)')).toBeDefined();
    expect(screen.getByText('Test Connection')).toBeDefined();
  });
});
