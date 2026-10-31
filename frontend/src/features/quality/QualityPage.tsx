import { useQuery } from '@tanstack/react-query';
import { fetchQuality } from '../../api/endpoints';
import { PageHeader } from '../../components/Layout';
import { Badge, Card, EmptyState, ErrorState, Meter, Spinner, StatCard } from '../../components/ui';
import { Icon } from '../../components/Icon';

const TIER_TONE: Record<string, 'ok' | 'warn' | 'error' | 'muted'> = {
  high: 'ok',
  medium: 'warn',
  low: 'error',
};

export default function QualityPage() {
  const quality = useQuery({ queryKey: ['quality'], queryFn: ({ signal }) => fetchQuality(signal) });
  const documents = quality.data?.ranked_documents ?? [];
  const counts = documents.reduce<Record<string, number>>((acc, item) => {
    acc[item.tier] = (acc[item.tier] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <>
      <PageHeader
        eyebrow="Trust signals"
        title="Data quality"
        description="Each document is scored on authority, provenance, completeness and freshness so downstream answers can be weighted by source trust."
        actions={
          <button type="button" className="ghost-button" onClick={() => quality.refetch()} disabled={quality.isFetching}>
            <Icon name="refresh" size={16} />
            {quality.isFetching ? 'Scoring…' : 'Re-score'}
          </button>
        }
      />

      {quality.isError && <ErrorState message={String(quality.error)} onRetry={() => quality.refetch()} />}

      <div className="stat-grid">
        <StatCard
          label="Average score"
          value={quality.data ? quality.data.average_score.toFixed(1) : '—'}
          icon="quality"
          hint="out of 100"
        />
        <StatCard label="High trust" value={counts.high ?? 0} icon="check" hint="score ≥ 75" />
        <StatCard label="Medium" value={counts.medium ?? 0} icon="warning" hint="50 – 74" />
        <StatCard label="Low" value={counts.low ?? 0} icon="warning" hint="below 50" />
      </div>

      <Card
        title="Ranked documents"
        subtitle={quality.data?.method ? `Scoring model · ${quality.data.method}` : 'Scoring model'}
        actions={<Badge tone="muted">{documents.length} documents</Badge>}
      >
        {quality.isLoading && <Spinner label="Scoring documents…" />}
        {quality.data && documents.length === 0 && (
          <EmptyState title="No documents to score" description="Ingest sources first." icon="quality" />
        )}
        {documents.length > 0 && (
          <table className="table">
            <thead>
              <tr>
                <th>Document</th>
                <th>Domain</th>
                <th>Tier</th>
                <th>Score</th>
                <th className="num">A / P / C / F</th>
              </tr>
            </thead>
            <tbody>
              {documents.map((document) => (
                <tr key={document.url}>
                  <td>
                    <a className="link truncate" href={document.url} target="_blank" rel="noreferrer" title={document.url}>
                      <Icon name="external" size={13} />
                      {document.url}
                    </a>
                  </td>
                  <td className="muted">{document.domain}</td>
                  <td>
                    <Badge tone={TIER_TONE[document.tier] ?? 'muted'}>{document.tier}</Badge>
                  </td>
                  <td className="score-cell">
                    <Meter value={document.score} max={100} tone={document.score >= 75 ? 'primary' : 'warn'} />
                    <span className="mono">{document.score}</span>
                  </td>
                  <td className="num mono muted">
                    {document.reasons.authority ?? 0} / {document.reasons.provenance ?? 0} /{' '}
                    {document.reasons.completeness ?? 0} / {document.reasons.freshness ?? 0}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </>
  );
}
