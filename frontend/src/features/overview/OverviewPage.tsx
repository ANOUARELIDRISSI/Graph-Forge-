import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { fetchAnalytics, fetchPipeline, fetchSources } from '../../api/endpoints';
import { PageHeader } from '../../components/Layout';
import { Badge, Card, ErrorState, Meter, Spinner, StatCard } from '../../components/ui';
import { nodeColor } from '../../config/palette';

export default function OverviewPage() {
  const pipeline = useQuery({ queryKey: ['pipeline'], queryFn: ({ signal }) => fetchPipeline(signal) });
  const sources = useQuery({ queryKey: ['sources'], queryFn: ({ signal }) => fetchSources({}, signal) });
  const analytics = useQuery({
    queryKey: ['analytics', 12],
    queryFn: ({ signal }) => fetchAnalytics(12, signal),
  });

  const failed = pipeline.error ?? sources.error ?? analytics.error;

  return (
    <>
      <PageHeader
        eyebrow="Workspace overview"
        title="Knowledge graph control centre"
        description="Evidence-first discovery across crawled Moroccan business sources, from raw documents to grounded answers."
        actions={
          <>
            <Link className="button" to="/graph">
              Open explorer
            </Link>
            <Link className="button button--primary" to="/assistant">
              Ask GraphRAG
            </Link>
          </>
        }
      />

      {failed && <ErrorState message={String(failed.message ?? failed)} onRetry={() => pipeline.refetch()} />}

      <div className="stat-grid">
        <StatCard label="Documents" value={pipeline.data?.documents ?? '—'} icon="sources" hint="Provenance-tracked" />
        <StatCard label="Chunks" value={pipeline.data?.chunks ?? '—'} icon="layers" hint="800/120 window" />
        <StatCard label="Entities" value={pipeline.data?.entities ?? '—'} icon="graph" hint="Resolved & deduplicated" />
        <StatCard label="Relationships" value={pipeline.data?.relationships ?? '—'} icon="route" hint="Typed graph edges" />
      </div>

      <div className="overview-grid">
        <Card
          title="Ingestion pipeline"
          subtitle="Every stage is verifiable from the API"
          actions={<Badge tone={pipeline.data?.entity_extraction_ready ? 'ok' : 'warn'}>
            {pipeline.data?.entity_extraction_ready ? 'Healthy' : 'Building'}
          </Badge>}
        >
          {pipeline.isLoading && <Spinner />}
          {pipeline.data && (
            <ul className="stage-list">
              <Stage label="Documents crawled" value={pipeline.data.documents} max={pipeline.data.documents} ready />
              <Stage label="Chunks created" value={pipeline.data.chunks} max={pipeline.data.chunks} ready={pipeline.data.chunking_ready} />
              <Stage label="Entities extracted" value={pipeline.data.entities} max={Math.max(pipeline.data.entities, pipeline.data.documents)} ready={pipeline.data.entity_extraction_ready} />
              <Stage label="Graph relationships" value={pipeline.data.relationships} max={Math.max(pipeline.data.relationships, pipeline.data.chunks)} ready={pipeline.data.relationships > 0} />
            </ul>
          )}
          {pipeline.data?.last_ingestion && (
            <p className="muted mono">
              last checkpoint · {pipeline.data.last_ingestion.replace(/[{}"\s]/g, ' ').slice(0, 80)}
            </p>
          )}
        </Card>

        <Card title="Graph composition" subtitle="Nodes by semantic type">
          {analytics.isLoading && <Spinner />}
          {analytics.data && (
            <ul className="label-list">
              {Object.entries(analytics.data.labels).map(([label, count]) => (
                <li key={label}>
                  <i className="swatch" style={{ background: nodeColor(label) }} />
                  <span className="label-name">{label}</span>
                  <Meter value={count} max={Math.max(...Object.values(analytics.data!.labels))} />
                  <strong>{count}</strong>
                </li>
              ))}
            </ul>
          )}
          <div className="kpi-inline">
            <span>Density <strong>{analytics.data ? analytics.data.density.toFixed(3) : '—'}</strong></span>
            <span>Components <strong>{analytics.data?.components ?? '—'}</strong></span>
          </div>
        </Card>

        <Card
          title="Source coverage"
          subtitle={`${sources.data?.total_documents ?? 0} documents indexed`}
          actions={<Link className="link" to="/sources">View all</Link>}
        >
          {sources.isLoading && <Spinner />}
          <ul className="source-mini">
            {(sources.data?.sources ?? []).slice(0, 6).map((source) => (
              <li key={source.domain}>
                <span className="source-domain">{source.domain}</span>
                <Badge tone="muted">{source.documents} docs</Badge>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </>
  );
}

function Stage({ label, value, max, ready }: { label: string; value: number; max: number; ready: boolean }) {
  return (
    <li>
      <div className="stage-head">
        <span>{label}</span>
        <strong>{value}</strong>
      </div>
      <Meter value={value} max={max} tone={ready ? 'primary' : 'warn'} />
    </li>
  );
}
