import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchAnalytics, fetchPath } from '../../api/endpoints';
import { PageHeader } from '../../components/Layout';
import { Badge, Card, EmptyState, ErrorState, Meter, Spinner, StatCard } from '../../components/ui';
import { Icon } from '../../components/Icon';
import { nodeColor } from '../../config/palette';

export default function AnalyticsPage() {
  const [draft, setDraft] = useState({ source: '', target: '' });
  const [pair, setPair] = useState<{ source: string; target: string } | null>(null);
  const analytics = useQuery({
    queryKey: ['analytics', 12],
    queryFn: ({ signal }) => fetchAnalytics(12, signal),
  });
  const path = useQuery({
    queryKey: ['path', pair?.source, pair?.target],
    queryFn: ({ signal }) => fetchPath(pair!.source, pair!.target, signal),
    enabled: Boolean(pair),
  });

  const maxDegree = Math.max(1, ...(analytics.data?.centrality ?? []).map((item) => item.degree));

  return (
    <>
      <PageHeader
        eyebrow="Graph analytics"
        title="Structure & influence"
        description="Cypher-style structural analysis computed over the knowledge graph: density, components, PageRank, communities and shortest paths."
      />

      {analytics.isError && <ErrorState message={String(analytics.error)} onRetry={() => analytics.refetch()} />}

      <div className="stat-grid">
        <StatCard label="Nodes" value={analytics.data?.nodes ?? '—'} icon="graph" />
        <StatCard label="Edges" value={analytics.data?.edges ?? '—'} icon="route" />
        <StatCard label="Density" value={analytics.data ? analytics.data.density.toFixed(3) : '—'} icon="analytics" hint="edges / possible edges" />
        <StatCard label="Components" value={analytics.data?.components ?? '—'} icon="layers" hint="connected subgraphs" />
      </div>

      <div className="analytics-grid">
        <Card title="Influence ranking" subtitle="Degree centrality combined with PageRank">
          {analytics.isLoading && <Spinner />}
          {analytics.data && (
            <table className="table">
              <thead>
                <tr>
                  <th>Entity</th>
                  <th>Type</th>
                  <th className="num">Degree</th>
                  <th className="num">PageRank</th>
                </tr>
              </thead>
              <tbody>
                {analytics.data.centrality.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <span className="entity-cell">
                        <i className="swatch" style={{ background: nodeColor(item.label) }} />
                        {item.name}
                      </span>
                    </td>
                    <td className="muted">{item.label}</td>
                    <td className="num">
                      <Meter value={item.degree} max={maxDegree} />
                      {item.degree}
                    </td>
                    <td className="num mono">{item.pagerank.toFixed(4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>

        <div className="analytics-side">
          <Card title="Communities" subtitle="Label propagation over the graph">
            {analytics.isLoading && <Spinner />}
            {analytics.data && analytics.data.communities.length === 0 && (
              <EmptyState title="No communities detected" icon="layers" />
            )}
            {analytics.data && analytics.data.communities.length > 0 && (
              <ul className="community-list">
                {analytics.data.communities.map((community, index) => (
                  <li key={community.community}>
                    <div className="community-head">
                      <strong>Community {index + 1}</strong>
                      <Badge tone="muted">{community.size} nodes</Badge>
                    </div>
                    <p className="muted">{community.members.join(' · ')}</p>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="Shortest path" subtitle="Breadth-first search between two entities">
            <form
              className="path-form"
              onSubmit={(event) => {
                event.preventDefault();
                if (draft.source.trim() && draft.target.trim()) setPair(draft);
              }}
            >
              <input
                value={draft.source}
                onChange={(event) => setDraft((current) => ({ ...current, source: event.target.value }))}
                placeholder="From — e.g. Automotive"
                aria-label="Path source"
              />
              <input
                value={draft.target}
                onChange={(event) => setDraft((current) => ({ ...current, target: event.target.value }))}
                placeholder="To — e.g. Morocco"
                aria-label="Path target"
              />
              <button type="submit" className="button button--primary" disabled={!draft.source || !draft.target}>
                <Icon name="route" size={15} /> Find path
              </button>
            </form>

            {path.isFetching && <Spinner label="Traversing graph…" />}
            {path.data && !path.data.found && (
              <p className="muted">
                {path.data.message === 'node not found' ? 'One of the entities is not in the graph.' : 'No path links those entities.'}
              </p>
            )}
            {path.data?.found && (
              <div className="path-result">
                <Badge tone="ok">{path.data.hops} hop{path.data.hops === 1 ? '' : 's'}</Badge>
                <ol className="path-chain">
                  {path.data.nodes.map((node) => (
                    <li key={node.id}>
                      <i className="swatch" style={{ background: nodeColor(node.label) }} />
                      <span>{node.name}</span>
                    </li>
                  ))}
                </ol>
              </div>
            )}
          </Card>
        </div>
      </div>
    </>
  );
}
