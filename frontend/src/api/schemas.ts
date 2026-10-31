import { z } from 'zod';

export const nodeSchema = z.object({
  id: z.string(),
  label: z.string(),
  name: z.string(),
  properties: z.record(z.union([z.string(), z.number()])).default({}),
});

export const edgeSchema = z.object({
  source: z.string(),
  target: z.string(),
  relation: z.string(),
});

export const graphSchema = z.object({
  nodes: z.array(nodeSchema),
  edges: z.array(edgeSchema),
});

export const sourceSchema = z.object({
  domain: z.string(),
  documents: z.number(),
  urls: z.array(z.string()),
});

export const sourceDocumentSchema = z.object({
  id: z.string(),
  url: z.string(),
  title: z.string(),
  domain: z.string(),
  document_type: z.enum(['html', 'pdf', 'rss']),
  language: z.string(),
  crawled_at: z.string(),
  published_at: z.string().nullable(),
  source_feed_url: z.string().nullable(),
  text_chars: z.number(),
  chunks: z.number(),
});

export const sourcesSchema = z.object({
  total_documents: z.number(),
  filtered_documents: z.number(),
  page: z.number(),
  page_size: z.number(),
  total_pages: z.number(),
  format_counts: z.object({ html: z.number(), pdf: z.number(), rss: z.number() }),
  sources: z.array(sourceSchema),
  documents: z.array(sourceDocumentSchema),
});

export const pipelineSchema = z.object({
  documents: z.number(),
  chunks: z.number(),
  entities: z.number(),
  relationships: z.number(),
  document_types: z.record(z.number()).default({}),
  languages: z.record(z.number()).default({}),
  extraction_methods: z.record(z.number()).default({}),
  retry_queue: z.number().default(0),
  chunking_ready: z.boolean(),
  entity_extraction_ready: z.boolean(),
  last_ingestion: z.string().nullable().optional(),
});

export const rebuildSchema = z.object({
  status: z.string(),
  generation: z.string().nullable(),
  nodes: z.number(),
  edges: z.number(),
});

export const evidenceSchema = z.object({
  chunk_id: z.string(),
  url: z.string(),
  snippet: z.string(),
  score: z.number(),
  language: z.string().default('other'),
});

export const answerSchema = z.object({
  answer: z.string(),
  sources: z.array(z.string()),
  mode: z.string(),
  evidence: z.array(evidenceSchema).default([]),
  entities: z.array(z.string()).default([]),
  subgraph: graphSchema.nullable().optional(),
  latency_ms: z.number().default(0),
  grounded: z.boolean().default(false),
});

export const centralitySchema = z.object({
  id: z.string(),
  name: z.string(),
  label: z.string(),
  degree: z.number(),
  pagerank: z.number(),
});

export const communitySchema = z.object({
  community: z.string(),
  size: z.number(),
  members: z.array(z.string()),
});

export const analyticsSchema = z.object({
  nodes: z.number(),
  edges: z.number(),
  density: z.number(),
  components: z.number(),
  labels: z.record(z.number()),
  centrality: z.array(centralitySchema),
  communities: z.array(communitySchema),
});

export const pathSchema = z.object({
  found: z.boolean(),
  hops: z.number(),
  nodes: z.array(nodeSchema),
  edges: z.array(edgeSchema),
  message: z.string().optional(),
});

export const qualityDocumentSchema = z.object({
  url: z.string(),
  domain: z.string(),
  score: z.number(),
  tier: z.string(),
  reasons: z.record(z.number()),
});

export const qualitySchema = z.object({
  method: z.string(),
  average_score: z.number(),
  ranked_documents: z.array(qualityDocumentSchema),
});

export const healthSchema = z.object({
  status: z.string(),
  version: z.string(),
  components: z.record(
    z.object({
      ready: z.boolean().optional(),
      enabled: z.boolean().optional(),
      connected: z.boolean().optional(),
      backend: z.string().optional(),
      nodes: z.number().optional(),
      edges: z.number().optional(),
    }),
  ),
});

export const evaluationSchema = z.object({
  retrieval: z.record(z.unknown()).default({}),
  ragas: z.object({
    available: z.boolean(),
    rows: z.number(),
    metrics: z.record(z.number()),
  }),
  providers: z.object({
    extraction: z.string(),
    extraction_model: z.string(),
    embedding_model: z.string(),
    hdfs_enabled: z.boolean(),
    spark_enabled: z.boolean(),
  }),
});

export type GraphSnapshot = z.infer<typeof graphSchema>;
export type GraphNode = z.infer<typeof nodeSchema>;
export type Source = z.infer<typeof sourceSchema>;
export type SourceDocument = z.infer<typeof sourceDocumentSchema>;
export type Pipeline = z.infer<typeof pipelineSchema>;
export type Answer = z.infer<typeof answerSchema>;
export type Evidence = z.infer<typeof evidenceSchema>;
export type Analytics = z.infer<typeof analyticsSchema>;
export type Quality = z.infer<typeof qualitySchema>;
export type Health = z.infer<typeof healthSchema>;
export type GraphPath = z.infer<typeof pathSchema>;
export type Evaluation = z.infer<typeof evaluationSchema>;
