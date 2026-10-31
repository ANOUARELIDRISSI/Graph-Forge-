import { Fragment, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchSources } from '../../api/endpoints';
import { PageHeader } from '../../components/Layout';
import { Badge, Card, EmptyState, ErrorState, Meter, Spinner, StatCard } from '../../components/ui';
import { Icon } from '../../components/Icon';

export default function SourcesPage() {
  const [page, setPage] = useState(1);
  const sources = useQuery({ queryKey: ['sources', page], queryFn: ({ signal }) => fetchSources({ page, pageSize: 10 }, signal) });
  const [openDomain, setOpenDomain] = useState<string | null>(null);

  const total = sources.data?.total_documents ?? 0;
  const domains = sources.data?.sources ?? [];
  const maxDocs = useMemo(() => Math.max(1, ...domains.map((item) => item.documents)), [domains]);

  return (
    <>
      <PageHeader
        eyebrow="Provenance"
        title="Sources & coverage"
        description="Every crawled document is tracked back to its origin domain, so each graph assertion can be traced to a verifiable source."
        actions={
          <button type="button" className="ghost-button" onClick={() => sources.refetch()} disabled={sources.isFetching}>
            <Icon name="refresh" size={16} />
            {sources.isFetching ? 'Refreshing…' : 'Refresh'}
          </button>
        }
      />

      {sources.isError && <ErrorState message={String(sources.error)} onRetry={() => sources.refetch()} />}

      <div className="stat-grid">
        <StatCard label="Domains" value={domains.length} icon="sources" hint="Distinct origins" />
        <StatCard label="Documents" value={total} icon="layers" hint="Indexed pages" />
        <StatCard
          label="Avg per domain"
          value={domains.length ? (total / domains.length).toFixed(1) : '—'}
          icon="analytics"
          hint="Coverage balance"
        />
        <StatCard
          label="Total URLs"
          value={domains.reduce((sum, item) => sum + item.urls.length, 0)}
          icon="route"
          hint="Traceable links"
        />
      </div>

      <Card
        title="Crawl sources"
        subtitle="Grouped by source domain, most covered first"
        actions={<Badge tone="muted">{domains.length} domains</Badge>}
      >
        {sources.isLoading && <Spinner label="Loading sources…" />}
        {sources.data && domains.length === 0 && (
          <EmptyState
            title="No sources indexed"
            description="Run the ingestion pipeline to crawl Moroccan business sources."
            icon="sources"
          />
        )}
        {domains.length > 0 && (
          <table className="table">
            <thead>
              <tr>
                <th>Domain</th>
                <th className="num">Documents</th>
                <th>Share</th>
                <th className="num">URLs</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {domains.map((source) => {
                const isOpen = openDomain === source.domain;
                return (
                  <Fragment key={source.domain}>
                    <tr>
                      <td>
                        <span className="entity-cell">
                          <Icon name="sources" size={15} />
                          <strong>{source.domain}</strong>
                        </span>
                      </td>
                      <td className="num">{source.documents}</td>
                      <td>
                        <Meter value={source.documents} max={maxDocs} />
                      </td>
                      <td className="num muted">{source.urls.length}</td>
                      <td className="num">
                        <button
                          type="button"
                          className="icon-button"
                          aria-expanded={isOpen}
                          aria-label={`${isOpen ? 'Hide' : 'Show'} URLs for ${source.domain}`}
                          onClick={() => setOpenDomain(isOpen ? null : source.domain)}
                        >
                          <Icon name={isOpen ? 'close' : 'plus'} size={14} />
                        </button>
                      </td>
                    </tr>
                    {isOpen && (
                      <tr className="table-detail">
                        <td colSpan={5}>
                          <ul className="url-list">
                            {source.urls.map((url) => (
                              <li key={url}>
                                <a className="link" href={url} target="_blank" rel="noreferrer">
                                  <Icon name="external" size={13} />
                                  <span className="truncate">{url}</span>
                                </a>
                              </li>
                            ))}
                          </ul>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        )}
        {sources.data && sources.data.total_pages > 1 && (
          <div className="page-controls">
            <button className="ghost-button" type="button" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}>Previous</button>
            <span className="muted">Page {sources.data.page} of {sources.data.total_pages} · {sources.data.filtered_documents} documents</span>
            <button className="ghost-button" type="button" disabled={page >= sources.data.total_pages} onClick={() => setPage((value) => value + 1)}>Next</button>
          </div>
        )}
        {sources.data && sources.data.documents.length > 0 && (
          <div className="source-document-list">
            <h3>Indexed documents</h3>
            {sources.data.documents.map((document) => (
              <div className="source-document" key={document.id}>
                <div><Badge tone="muted">{document.document_type}</Badge> <strong>{document.title}</strong><p className="muted">{document.domain} · {document.chunks} chunks · {document.text_chars.toLocaleString()} chars</p></div>
                <a className="link" href={document.url} target="_blank" rel="noreferrer">Open</a>
              </div>
            ))}
          </div>
        )}
      </Card>
    </>
  );
}
