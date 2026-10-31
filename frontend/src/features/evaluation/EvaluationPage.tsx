import { useQuery } from '@tanstack/react-query';
import { fetchEvaluation } from '../../api/endpoints';
import { PageHeader } from '../../components/Layout';
import { Badge, Card, ErrorState, Spinner, StatCard } from '../../components/ui';

export default function EvaluationPage() {
  const evaluation = useQuery({ queryKey: ['evaluation'], queryFn: ({ signal }) => fetchEvaluation(signal) });
  const data = evaluation.data;
  const strategies = (data?.retrieval.strategies ?? {}) as Record<string, Record<string, number>>;
  const ragas = data?.ragas.metrics ?? {};

  return (
    <>
      <PageHeader
        eyebrow="Evaluation"
        title="Retrieval & answer quality"
        description="Offline retrieval metrics and Ragas answer-quality scores, with the active extraction, embedding, HDFS and Spark configuration shown for reproducibility."
        actions={<button className="ghost-button" type="button" onClick={() => evaluation.refetch()}>Refresh</button>}
      />
      {evaluation.isError && <ErrorState message={String(evaluation.error)} onRetry={() => evaluation.refetch()} />}
      {evaluation.isLoading && <Spinner label="Loading evaluation…" />}
      {data && (
        <>
          <div className="stat-grid">
            <StatCard label="Evaluation cases" value={Number((data.retrieval.corpus as { cases?: number } | undefined)?.cases ?? 0)} icon="analytics" />
            <StatCard label="Ragas rows" value={data.ragas.rows} icon="layers" />
            <StatCard label="Faithfulness" value={formatMetric(ragas.faithfulness)} icon="quality" />
            <StatCard label="Answer relevance" value={formatMetric(ragas.answer_relevancy)} icon="assistant" />
          </div>
          <div className="overview-grid">
            <Card title="Retrieval comparison" subtitle="Recall@5, MRR, nDCG@5 and mean latency">
              {Object.keys(strategies).length === 0 ? <p className="muted">Run scripts/evaluate_rag.py --smoke to populate this panel.</p> : (
                <table className="table"><thead><tr><th>Strategy</th><th>Recall@5</th><th>MRR</th><th>nDCG@5</th><th>Latency</th></tr></thead>
                  <tbody>{Object.entries(strategies).map(([name, values]) => <tr key={name}><td><strong>{name}</strong></td><td>{formatMetric(values['recall@5'])}</td><td>{formatMetric(values.mrr)}</td><td>{formatMetric(values['ndcg@5'])}</td><td>{values.mean_latency_ms?.toFixed(1)} ms</td></tr>)}</tbody>
                </table>
              )}
            </Card>
            <Card title="Runtime configuration" subtitle="Providers used by the pipeline">
              <dl className="kv"><dt>Entity / relation extraction</dt><dd>{data.providers.extraction} · {data.providers.extraction_model}</dd><dt>Embeddings</dt><dd>{data.providers.embedding_model}</dd><dt>HDFS raw zone</dt><dd><Badge tone={data.providers.hdfs_enabled ? 'ok' : 'warn'}>{data.providers.hdfs_enabled ? 'enabled' : 'fallback/local'}</Badge></dd><dt>Spark ETL</dt><dd><Badge tone={data.providers.spark_enabled ? 'ok' : 'warn'}>{data.providers.spark_enabled ? 'enabled' : 'Python fallback'}</Badge></dd><dt>Context precision</dt><dd>{formatMetric(ragas.llm_context_precision_without_reference)}</dd></dl>
            </Card>
          </div>
        </>
      )}
    </>
  );
}

function formatMetric(value: number | undefined) {
  return value === undefined ? '—' : value.toFixed(3);
}
