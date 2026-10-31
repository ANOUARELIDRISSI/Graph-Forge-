import { Suspense } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { NavLink, Outlet } from 'react-router-dom';
import type { ReactNode } from 'react';
import { fetchHealth } from '../api/endpoints';
import { Icon, type IconName } from './Icon';
import { Badge, Spinner } from './ui';

const NAV: { to: string; label: string; icon: IconName; end?: boolean }[] = [
  { to: '/', label: 'Overview', icon: 'overview', end: true },
  { to: '/graph', label: 'Graph Explorer', icon: 'graph' },
  { to: '/analytics', label: 'Analytics', icon: 'analytics' },
  { to: '/assistant', label: 'GraphRAG Assistant', icon: 'assistant' },
  { to: '/sources', label: 'Sources', icon: 'sources' },
  { to: '/quality', label: 'Data Quality', icon: 'quality' },
  { to: '/pipeline', label: 'Pipeline', icon: 'pipeline' },
  { to: '/evaluation', label: 'Evaluation', icon: 'analytics' },
];

export function Layout() {
  const queryClient = useQueryClient();
  const health = useQuery({ queryKey: ['health'], queryFn: ({ signal }) => fetchHealth(signal) });
  const online = !health.isError && health.data?.status === 'ok';
  const graphReady = health.data?.components.graph?.ready ?? false;
  const neo4j = health.data?.components.neo4j;
  const remoteAi = health.data?.components.remote_ai;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">◈</span>
          <span>
            <strong>Atlas Graph</strong>
            <small>Morocco Business Intelligence</small>
          </span>
        </div>
        <nav className="side-nav" aria-label="Workspace">
          <span className="side-nav-label">Workspace</span>
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => `side-nav-item${isActive ? ' is-active' : ''}`}
            >
              <Icon name={item.icon} size={17} />
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="side-foot">
          <span className="muted">v{health.data?.version ?? '0.2.0'}</span>
        </div>
      </aside>

      <div className="workspace">
        <header className="topbar">
          <div className="topbar-status">
            <Badge tone={online ? 'ok' : 'error'}>
              <i className={`dot${online ? ' dot--ok' : ''}`} />
              {online ? 'API online' : health.isLoading ? 'Connecting…' : 'API offline'}
            </Badge>
            <Badge tone={graphReady ? 'info' : 'warn'}>
              Graph {graphReady ? 'ready' : 'building'}
            </Badge>
            {neo4j?.enabled && <Badge tone={neo4j.connected ? 'ok' : 'warn'}>Neo4j</Badge>}
            {remoteAi?.enabled && <Badge tone="info">Remote AI</Badge>}
          </div>
          <button
            type="button"
            className="ghost-button"
            onClick={() => queryClient.invalidateQueries()}
            disabled={health.isFetching}
          >
            <Icon name="refresh" size={16} />
            {health.isFetching ? 'Refreshing…' : 'Refresh data'}
          </button>
        </header>
        <main className="content">
          <Suspense fallback={<Spinner label="Loading view…" />}>
            <Outlet />
          </Suspense>
        </main>
      </div>
    </div>
  );
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow: string;
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="page-header">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        {description && <p className="page-description">{description}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </header>
  );
}
