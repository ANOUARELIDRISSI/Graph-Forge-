import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { fetchAnalytics, fetchPipeline, rebuildGraph } from '../../api/endpoints';
import { PageHeader } from '../../components/Layout';
import { Badge, Card, ErrorState, Meter, Spinner, StatCard } from '../../components/ui';
import { Icon } from '../../components/Icon';
import { nodeColor } from '../../config/palette';

export default function PipelinePage() {
  const queryClient = useQueryClient();
  const pipeline = useQuery({ queryKey: ['pipeline'], queryFn: ({ signal }) => fetchPipeline(signal) });
  const analytics = useQuery({
    queryKey: ['analytics', 12],
    queryFn: ({ signal }) => fetchAnalytics(12, signal),
  });

  const rebuild = useMutation({
    mutationFn: () => rebuildGraph(),
    onSuccess: () => queryClient.invalidateQueries(),
  });

  const data = pipeline.data;
  const maxEntities = Math.max(data?.entities ?? 0, data?.documents ?? 0, 1);
  const maxRelationships = Math.max(data?.relationships ?? 0, data?.chunks ?? 0, 1);
  const labels = analytics.data ? Object.entries(analytics.data.labels) : [];
  const maxLabel = labels.length ? Math.max(...labels.map(([, count]) => count)) : 1;

  const stages = data
    ? [
        { label: 'Crawl', detail: 'Documents fetched from sources', value: data.documents, max: Math.max(data.documents, 1), ready: data.documents > 0 },
        { label: 'Chunk', detail: '800/120 sliding window', value: data.chunks, max: Math.max(data.chunks, 1), ready: data.chunking_ready },
        { label: 'Extract', detail: 'Resolved entities', value: data.entities, max: maxEntities, ready: data.entity_extraction_ready },
        { label: 'Link', detail: 'Typed graph relationships', value: data.relationships, max: maxRelationships, ready: data.relationships > 0 },
      ]
    : [];

  return (
    <>
      <PageHeader
        eyebrow="Operations"
        title="Ingestion pipeline"
        description="Crawl → chunk → extract → link. Every stage is observable from the API, and the whole graph can be rebuilt deterministically."
        actions={
          <button
            type="button"
            className="button button--primary"
            onClick={() => rebuild.mutate()}
            disabled={rebuild.isPending}
          >
            <Icon name="refresh" size={15} />
            {rebuild.isPending ? 'Rebuilding…' : 'Rebuild graph'}
          </button>
        }
      />

      {pipeline.isError && <ErrorState message={String(pipeline.error)} onRetry={() => pipeline.refetch()} />}
      {rebuild.isError && <ErrorState message={String(rebuild.error)} onRetry={() => rebuild.mutate()} />}
      {rebuild.isSuccess && (
        <div className="alert alert--ok" role="status">
          <Icon name="check" size={16} />
          <span>
            Graph rebuilt · {rebuild.data.nodes} nodes / {rebuild.data.edges} edges
          </span>
        </div>
      )}

      <div className="stat-grid">
        <StatCard label="Documents" value={data?.documents ?? '—'} icon="sources" />
        <StatCard label="Chunks" value={data?.chunks ?? '—'} icon="layers" />
        <StatCard label="Entities" value={data?.entities ?? '—'} icon="graph" />
        <StatCard label="Relationships" value={data?.relationships ?? '—'} icon="route" />
      </div>

      <div className="overview-grid">
        <Card
          title="Stage readiness"
          subtitle="Documents → chunks → entities → relationships"
          actions={
            <Badge tone={data?.entity_extraction_ready ? 'ok' : 'warn'}>
              {data?.entity_extraction_ready ? 'Healthy' : 'Building'}
            </Badge>
          }
        >
          {pipeline.isLoading && <Spinner />}
          {data && (
            <ul className="stage-list">
              {stages.map((stage) => (
                <li key={stage.label}>
                  <div className="stage-head">
                    <span>
                      {stage.label}
                      <small className="stage-detail">{stage.detail}</small>
                    </span>
                    <strong>{stage.value}</strong>
                  </div>
                  <Meter value={stage.value} max={stage.max} tone={stage.ready ? 'primary' : 'warn'} />
                </li>
              ))}
            </ul>
          )}
          <dl className="kv timeline-kv">
            <dt>Last checkpoint</dt>
            <dd className="mono">{formatCheckpoint(data?.last_ingestion) ?? '—'}</dd>
          </dl>
        </Card>

        <Card title="Graph composition" subtitle="Nodes by semantic type">
          {analytics.isLoading && <Spinner />}
          {labels.length === 0 && !analytics.isLoading && <p className="muted">No nodes yet.</p>}
          <ul className="label-list">
            {labels.map(([label, count]) => (
              <li key={label}>
                <i className="swatch" style={{ background: nodeColor(label) }} />
                <span className="label-name">{label}</span>
                <Meter value={count} max={maxLabel} />
                <strong>{count}</strong>
              </li>
            ))}
          </ul>
          <div className="kpi-inline">
            <span>Density <strong>{analytics.data ? analytics.data.density.toFixed(3) : '—'}</strong></span>
            <span>Components <strong>{analytics.data?.components ?? '—'}</strong></span>
          </div>
        </Card>

        <Card title="Readiness checks" subtitle="Gates required for GraphRAG answers">
          <ul className="checklist">
            <Check label="Corpus loaded" ok={Boolean(data?.documents)} />
            <Check label="Chunking ready" ok={Boolean(data?.chunking_ready)} />
            <Check label="Entity extraction ready" ok={Boolean(data?.entity_extraction_ready)} />
            <Check label="Relationships linked" ok={Boolean(data?.relationships)} />
            <Check label="Vector index populated" ok={Boolean(data?.chunks)} />
          </ul>
        </Card>
      </div>
    </>
  );
}

function Check({ label, ok }: { label: string; ok: boolean }) {
  return (
    <li className={ok ? 'checklist-item is-ok' : 'checklist-item'}>
      <Icon name={ok ? 'check' : 'warning'} size={15} />
      <span>{label}</span>
      <Badge tone={ok ? 'ok' : 'warn'}>{ok ? 'pass' : 'pending'}</Badge>
    </li>
  );
}

function formatCheckpoint(raw?: string | null): string | null {
  if (!raw) return null;
  return raw.replace(/[{}"\s]+/g, ' ').trim().slice(0, 120);
}
