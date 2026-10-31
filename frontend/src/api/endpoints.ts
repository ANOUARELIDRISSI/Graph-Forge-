import { api } from './client';
import {
  analyticsSchema,
  answerSchema,
  graphSchema,
  healthSchema,
  pathSchema,
  pipelineSchema,
  qualitySchema,
  rebuildSchema,
  sourcesSchema,
  evaluationSchema,
} from './schemas';
import { env } from '../config/env';

export const fetchGraph = (signal?: AbortSignal) => api('/graph', { signal }, graphSchema);
export type SourceFilters = {
  page?: number;
  pageSize?: number;
  documentType?: 'html' | 'pdf' | 'rss';
  domain?: string;
  search?: string;
};

export const fetchSources = (filters: SourceFilters = {}, signal?: AbortSignal) => {
  const params = new URLSearchParams({
    page: String(filters.page ?? 1),
    page_size: String(filters.pageSize ?? 10),
  });
  if (filters.documentType) params.set('document_type', filters.documentType);
  if (filters.domain) params.set('domain', filters.domain);
  if (filters.search) params.set('search', filters.search);
  return api(`/sources?${params}`, { signal }, sourcesSchema);
};
export const pdfViewerUrl = (url: string) =>
  `${env.apiUrl}/sources/pdf?url=${encodeURIComponent(url)}`;
export const fetchPipeline = (signal?: AbortSignal) =>
  api('/pipeline/status', { signal }, pipelineSchema);
export const fetchHealth = (signal?: AbortSignal) => api('/health', { signal }, healthSchema);
export const rebuildGraph = (signal?: AbortSignal) =>
  api('/graph/rebuild', { method: 'POST', signal }, rebuildSchema);
export const fetchAnalytics = (limit = 12, signal?: AbortSignal) =>
  api(`/analytics/graph?limit=${limit}`, { signal }, analyticsSchema);
export const fetchQuality = (signal?: AbortSignal) =>
  api('/data-quality', { signal }, qualitySchema);
export const fetchPath = (source: string, target: string, signal?: AbortSignal) =>
  api(
    `/analytics/paths?source=${encodeURIComponent(source)}&target=${encodeURIComponent(target)}`,
    { signal },
    pathSchema,
  );
export const fetchSubgraph = (node: string, hops = 2, signal?: AbortSignal) =>
  api(`/graph/subgraph?node=${encodeURIComponent(node)}&hops=${hops}`, { signal }, graphSchema);
export const askRag = (question: string, signal?: AbortSignal) =>
  api('/rag/ask', { method: 'POST', signal, body: JSON.stringify({ question }) }, answerSchema);
export const fetchEvaluation = (signal?: AbortSignal) =>
  api('/evaluation', { signal }, evaluationSchema);
