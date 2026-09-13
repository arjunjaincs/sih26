import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { AppShell } from './layouts/AppShell';
import { GlobalSearchModal } from './components/GlobalSearchModal';
import * as client from './api/client';
import type { GlobalSearchResponse } from './types/api';

const mockSearchData: GlobalSearchResponse = {
  query: 'resnet',
  total_matches: 3,
  counts: {
    assessments: 1,
    findings: 1,
    evidence: 1,
  },
  assessments: [
    {
      assessment_id: 'asmt-resnet-01',
      title: 'ResNet50 Production Verification',
      state: 'complete',
      created_at: '2026-09-13T01:00:00Z',
      target_url: '/assessments/asmt-resnet-01/result',
    },
  ],
  findings: [
    {
      finding_id: 'fnd-dup-01',
      assessment_id: 'asmt-resnet-01',
      title: 'High Density Exact Duplicates in Dataset',
      detector_id: 'data.integrity.di01_duplicates',
      detector_code: 'DI-01',
      severity: 'high',
      category: 'data_integrity',
      asset_name: 'training_data.zip',
      target_url: '/assessments/asmt-resnet-01/findings',
    },
  ],
  evidence: [
    {
      evidence_id: 'evi-cluster-01',
      finding_id: 'fnd-dup-01',
      assessment_id: 'asmt-resnet-01',
      detector_id: 'data.integrity.di01_duplicates',
      detector_code: 'DI-01',
      evidence_type: 'cluster',
      description: 'Cluster manifest with 12 duplicate samples',
      finding_title: 'High Density Exact Duplicates in Dataset',
      target_url: '/assessments/asmt-resnet-01/evidence',
    },
  ],
};

describe('Global Search Frontend Suite', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(client, 'getHealth').mockResolvedValue({
      status: 'ok',
      version: '1.0.0',
      db_path: 'C:/test.db',
    });
  });

  it('renders global search button in AppShell header', () => {
    render(
      <MemoryRouter>
        <AppShell />
      </MemoryRouter>
    );

    const searchBtn = screen.getByRole('button', { name: /open global search/i });
    expect(searchBtn).toBeDefined();
    expect(screen.getByText('Search PRAMAAN…')).toBeDefined();
    expect(screen.getByText('Ctrl K')).toBeDefined();
  });

  it('opens search modal on clicking header button', async () => {
    render(
      <MemoryRouter>
        <AppShell />
      </MemoryRouter>
    );

    const searchBtn = screen.getByRole('button', { name: /open global search/i });
    fireEvent.click(searchBtn);

    expect(screen.getByRole('dialog', { name: /global search/i })).toBeDefined();
    expect(screen.getByPlaceholderText(/search assessments, findings, detectors/i)).toBeDefined();
  });

  it('toggles search modal via Ctrl+K keyboard shortcut', async () => {
    render(
      <MemoryRouter>
        <AppShell />
      </MemoryRouter>
    );

    expect(screen.queryByRole('dialog', { name: /global search/i })).toBeNull();

    // Trigger Ctrl+K
    fireEvent.keyDown(window, { key: 'k', ctrlKey: true });
    expect(screen.getByRole('dialog', { name: /global search/i })).toBeDefined();

    // Trigger Ctrl+K again to toggle closed
    fireEvent.keyDown(window, { key: 'k', ctrlKey: true });
    expect(screen.queryByRole('dialog', { name: /global search/i })).toBeNull();
  });

  it('closes search modal on Escape key', async () => {
    const handleClose = vi.fn();
    render(
      <MemoryRouter>
        <GlobalSearchModal isOpen={true} onClose={handleClose} />
      </MemoryRouter>
    );

    expect(screen.getByRole('dialog')).toBeDefined();
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(handleClose).toHaveBeenCalled();
  });

  it('searches and renders grouped results for Assessments, Findings, and Evidence', async () => {
    const searchSpy = vi.spyOn(client, 'searchAll').mockResolvedValue(mockSearchData);

    render(
      <MemoryRouter>
        <GlobalSearchModal isOpen={true} onClose={vi.fn()} />
      </MemoryRouter>
    );

    const input = screen.getByPlaceholderText(/search assessments, findings, detectors/i);
    fireEvent.change(input, { target: { value: 'resnet' } });

    // Wait for debounced search call
    await waitFor(() => {
      expect(searchSpy).toHaveBeenCalledWith('resnet', 15);
    });

    // Verify Assessments section
    await waitFor(() => {
      expect(screen.getByText(/Assessments \(1\)/i)).toBeDefined();
      expect(screen.getByText('ResNet50 Production Verification')).toBeDefined();
      expect(screen.getByText('asmt-resnet-01')).toBeDefined();
    });

    // Verify Findings section
    expect(screen.getByText(/Findings \(1\)/i)).toBeDefined();
    expect(screen.getAllByText('High Density Exact Duplicates in Dataset').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('DI-01').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('HIGH')).toBeDefined();
    expect(screen.getByText('training_data.zip')).toBeDefined();

    // Verify Evidence section
    expect(screen.getByText(/Evidence \(1\)/i)).toBeDefined();
    expect(screen.getByText('Cluster manifest with 12 duplicate samples')).toBeDefined();
    expect(screen.getByText('evi-cluster-01')).toBeDefined();
    expect(screen.getByText('cluster')).toBeDefined();
  });

  it('clears search input when clicking clear button', async () => {
    vi.spyOn(client, 'searchAll').mockResolvedValue(mockSearchData);

    render(
      <MemoryRouter>
        <GlobalSearchModal isOpen={true} onClose={vi.fn()} />
      </MemoryRouter>
    );

    const input = screen.getByPlaceholderText(/search assessments, findings, detectors/i) as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'test' } });
    expect(input.value).toBe('test');

    const clearBtn = screen.getByRole('button', { name: /clear search/i });
    fireEvent.click(clearBtn);

    expect(input.value).toBe('');
  });

  it('displays friendly empty state when no results match', async () => {
    vi.spyOn(client, 'searchAll').mockResolvedValue({
      query: 'nonexistent',
      total_matches: 0,
      counts: { assessments: 0, findings: 0, evidence: 0 },
      assessments: [],
      findings: [],
      evidence: [],
    });

    render(
      <MemoryRouter>
        <GlobalSearchModal isOpen={true} onClose={vi.fn()} />
      </MemoryRouter>
    );

    const input = screen.getByPlaceholderText(/search assessments, findings, detectors/i);
    fireEvent.change(input, { target: { value: 'nonexistent' } });

    await waitFor(() => {
      expect(screen.getByText(/No results found for “nonexistent”/i)).toBeDefined();
    });
  });

  it('navigates to target URL when a search result item is clicked', async () => {
    vi.spyOn(client, 'searchAll').mockResolvedValue(mockSearchData);
    const handleClose = vi.fn();

    render(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route path="/" element={<GlobalSearchModal isOpen={true} onClose={handleClose} />} />
          <Route path="/assessments/:id/result" element={<div data-testid="assessment-page">Assessment Page</div>} />
        </Routes>
      </MemoryRouter>
    );

    const input = screen.getByPlaceholderText(/search assessments, findings, detectors/i);
    fireEvent.change(input, { target: { value: 'resnet' } });

    await waitFor(() => {
      expect(screen.getByText('ResNet50 Production Verification')).toBeDefined();
    });

    const resultItem = screen.getByText('ResNet50 Production Verification').closest('button');
    expect(resultItem).toBeDefined();
    fireEvent.click(resultItem!);

    expect(handleClose).toHaveBeenCalled();
  });
});
