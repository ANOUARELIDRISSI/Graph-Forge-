import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import ForceGraphBase from 'react-force-graph-2d';
import type { ComponentType, Ref } from 'react';
import { fetchGraph } from '../../api/endpoints';
import type { GraphNode } from '../../api/schemas';
import { PageHeader } from '../../components/Layout';
import { EmptyState, ErrorState, Spinner } from '../../components/ui';
import { Icon } from '../../components/Icon';
import { NODE_COLORS, nodeColor, nodeRadius } from '../../config/palette';
import { useUrlState } from '../../hooks/useUrlState';

type ForceNode = GraphNode & { x?: number; y?: number };
type ForceLink = { source: string | ForceNode; target: string | ForceNode; relation: string };

interface ForceGraphHandle {
  centerAt: (x?: number, y?: number, ms?: number) => void;
  zoom: (scale: number, ms?: number) => void;
  zoomToFit: (ms?: number, padding?: number) => void;
}

interface ForceGraphProps {
  graphData: { nodes: ForceNode[]; links: ForceLink[] };
  width: number;
  height: number;
  backgroundColor?: string;
  cooldownTicks?: number;
  linkColor?: () => string;
  linkWidth?: number;
  linkDirectionalArrowLength?: number;
  linkDirectionalArrowRelPos?: number;
  nodeLabel?: (node: ForceNode) => string;
  nodeCanvasObject?: (node: ForceNode, ctx: CanvasRenderingContext2D, scale: number) => void;
  onNodeClick?: (node: ForceNode) => void;
  onBackgroundClick?: () => void;
  ref?: Ref<ForceGraphHandle>;
}

const ForceGraph = ForceGraphBase as unknown as ComponentType<ForceGraphProps>;

const LIMITS = [50, 100, 200];

export default function GraphExplorerPage() {
  const { limit, q, node: nodeParam, update } = useUrlState();
  const graph = useQuery({ queryKey: ['graph'], queryFn: ({ signal }) => fetchGraph(signal) });
  const graphRef = useRef<ForceGraphHandle>(null);
  const [size, setSize] = useState({ width: 900, height: 560 });
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const element = containerRef.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      if (width > 0 && height > 0) setSize({ width, height });
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const nodes = graph.data?.nodes ?? [];
  const edges = graph.data?.edges ?? [];

  const visible = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return nodes
      .filter((item) => !needle || `${item.name} ${item.label}`.toLowerCase().includes(needle))
      .slice(0, limit);
  }, [nodes, q, limit]);

  const graphData = useMemo(() => {
    const ids = new Set(visible.map((item) => item.id));
    return {
      nodes: visible as ForceNode[],
      links: edges.filter((edge) => ids.has(edge.source) && ids.has(edge.target)) as ForceLink[],
    };
  }, [visible, edges]);

  const selected = useMemo(
    () => nodes.find((item) => item.id === nodeParam) ?? null,
    [nodes, nodeParam],
  );

  const legend = useMemo(() => {
    const present = new Set(nodes.map((item) => item.label));
    return Object.keys(NODE_COLORS).filter((label) => present.has(label));
  }, [nodes]);

  function focus(node: ForceNode) {
    update({ node: node.id });
    if (node.x !== undefined && node.y !== undefined) {
      graphRef.current?.centerAt(node.x, node.y, 600);
      graphRef.current?.zoom(3, 600);
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="Graph explorer"
        title="Relationship map"
        description="Search entities, inspect provenance and follow typed edges across the knowledge graph."
        actions={
          <button type="button" className="ghost-button" onClick={() => graphRef.current?.zoomToFit(600, 60)}>
            Reset view
          </button>
        }
      />

      {graph.isError && <ErrorState message={String(graph.error)} onRetry={() => graph.refetch()} />}

      <div className="toolbar">
        <label className="search">
          <Icon name="search" size={16} />
          <input
            value={q}
            onChange={(event) => update({ q: event.target.value || null })}
            placeholder="Search entities, sources, sectors…"
            aria-label="Search the graph"
          />
        </label>
        <label className="select">
          Visible
          <select value={limit} onChange={(event) => update({ limit: event.target.value })}>
            {LIMITS.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>
        <span className="muted">
          {visible.length} of {nodes.length} nodes · {graphData.links.length} links
        </span>
      </div>

      <div className="explorer-grid">
        <div className="graph-card">
          {graph.isLoading ? (
            <Spinner label="Building the graph…" />
          ) : visible.length === 0 ? (
            <EmptyState
              title="No matching nodes"
              description="Adjust the search or rebuild the graph from the pipeline page."
              icon="graph"
            />
          ) : (
            <div className="graph-canvas" ref={containerRef} onDoubleClick={() => graphRef.current?.zoomToFit(600, 60)}>
              <ForceGraph
                ref={graphRef}
                graphData={graphData}
                width={size.width}
                height={size.height}
                backgroundColor="#ffffff"
                cooldownTicks={120}
                linkColor={() => '#cbd5e1'}
                linkWidth={1}
                linkDirectionalArrowLength={3}
                linkDirectionalArrowRelPos={1}
                nodeLabel={(item) => `${item.label} · ${item.name}`}
                onNodeClick={focus}
                onBackgroundClick={() => update({ node: null })}
                nodeCanvasObject={(item, ctx, scale) => {
                  const x = item.x ?? 0;
                  const y = item.y ?? 0;
                  const radius = nodeRadius(item.label) / Math.sqrt(Math.max(scale, 0.25));
                  ctx.beginPath();
                  ctx.fillStyle = '#ffffff';
                  ctx.arc(x, y, radius + 2.5, 0, 2 * Math.PI);
                  ctx.fill();
                  ctx.beginPath();
                  ctx.fillStyle = nodeColor(item.label);
                  ctx.arc(x, y, radius, 0, 2 * Math.PI);
                  ctx.fill();
                  if (scale > 1.5) {
                    ctx.font = `600 ${11 / scale}px Inter, system-ui, sans-serif`;
                    ctx.fillStyle = '#0f172a';
                    ctx.fillText(item.name.slice(0, 28), x + radius + 4, y + 3.5);
                  }
                }}
              />
              <div className="graph-legend">
                {legend.map((label) => (
                  <span key={label}>
                    <i className="swatch" style={{ background: nodeColor(label) }} />
                    {label}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        <aside className="inspector">
          {selected ? (
            <section className="card">
              <div className="card-head">
                <h2>Selected node</h2>
                <button type="button" className="icon-button" onClick={() => update({ node: null })} aria-label="Clear selection">
                  <Icon name="close" size={15} />
                </button>
              </div>
              <div className="card-body">
                <span className="type-chip" style={{ background: nodeColor(selected.label) }}>
                  {selected.label}
                </span>
                <h3 className="node-title">{selected.name}</h3>
                <dl className="kv">
                  <dt>id</dt>
                  <dd className="mono">{selected.id}</dd>
                  {Object.entries(selected.properties).map(([key, value]) => (
                    <span key={key} className="kv-row">
                      <dt>{key}</dt>
                      <dd>{String(value)}</dd>
                    </span>
                  ))}
                </dl>
                {typeof selected.properties.url === 'string' && (
                  <a className="link" href={String(selected.properties.url)} target="_blank" rel="noreferrer">
                    <Icon name="external" size={14} /> Open source
                  </a>
                )}
              </div>
            </section>
          ) : (
            <section className="card">
              <EmptyState
                title="Nothing selected"
                description="Click any node on the map to inspect its type and provenance properties."
                icon="search"
              />
            </section>
          )}
        </aside>
      </div>
    </>
  );
}
