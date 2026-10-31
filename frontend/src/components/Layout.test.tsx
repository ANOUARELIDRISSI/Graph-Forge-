import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { Layout } from './Layout';
import * as endpoints from '../api/endpoints';

vi.mock('../api/endpoints');

const health = (overrides: Record<string, unknown> = {}) =>
  ({
    status: 'ok',
    version: '0.2.0',
    components: { graph: { ready: true }, neo4j: { enabled: false }, remote_ai: { enabled: false } },
    ...overrides,
  }) as never;

function renderLayout() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<p>outlet-content</p>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.resetAllMocks());

describe('Layout', () => {
  it('shows the online badge and renders the routed outlet when healthy', async () => {
    vi.mocked(endpoints.fetchHealth).mockResolvedValue(health());
    renderLayout();
    expect(await screen.findByText('API online')).toBeInTheDocument();
    expect(screen.getByText('outlet-content')).toBeInTheDocument();
    expect(screen.getByText('Graph ready')).toBeInTheDocument();
    expect(screen.getByText('v0.2.0')).toBeInTheDocument();
  });

  it('surfaces optional Neo4j and Remote AI badges only when enabled', async () => {
    vi.mocked(endpoints.fetchHealth).mockResolvedValue(
      health({
        components: {
          graph: { ready: true },
          neo4j: { enabled: true, connected: true },
          remote_ai: { enabled: true },
        },
      }),
    );
    renderLayout();
    expect(await screen.findByText('Neo4j')).toBeInTheDocument();
    expect(screen.getByText('Remote AI')).toBeInTheDocument();
  });

  it('falls back to the offline badge when the health request fails', async () => {
    vi.mocked(endpoints.fetchHealth).mockRejectedValue(new Error('connection refused'));
    renderLayout();
    expect(await screen.findByText('API offline')).toBeInTheDocument();
    expect(screen.queryByText('API online')).toBeNull();
  });

  it('marks the graph as building when it is not ready', async () => {
    vi.mocked(endpoints.fetchHealth).mockResolvedValue(
      health({ components: { graph: { ready: false } } }),
    );
    renderLayout();
    await waitFor(() => expect(screen.getByText('Graph building')).toBeInTheDocument());
  });
});
