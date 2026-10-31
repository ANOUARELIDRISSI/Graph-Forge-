from __future__ import annotations

from collections import Counter, deque

from moroccan_crawler.domain.models import GraphNode, GraphSnapshot


def _adjacency(snapshot: GraphSnapshot) -> dict[str, set[str]]:
    """Undirected adjacency so analytics work regardless of edge direction."""
    graph: dict[str, set[str]] = {node.id: set() for node in snapshot.nodes}
    for edge in snapshot.edges:
        if edge.source in graph and edge.target in graph:
            graph[edge.source].add(edge.target)
            graph[edge.target].add(edge.source)
    return graph


def graph_summary(snapshot: GraphSnapshot) -> dict[str, object]:
    graph = _adjacency(snapshot)
    nodes = len(graph)
    edges = len(snapshot.edges)
    possible = nodes * (nodes - 1) / 2 if nodes > 1 else 0
    by_label: Counter[str] = Counter(node.label for node in snapshot.nodes)
    return {
        "nodes": nodes,
        "edges": edges,
        "density": round(edges / possible, 4) if possible else 0.0,
        "components": len(connected_components(snapshot)),
        "labels": dict(by_label.most_common()),
    }


def degree_centrality(snapshot: GraphSnapshot) -> dict[str, int]:
    return {node_id: len(neighbours) for node_id, neighbours in _adjacency(snapshot).items()}


def pagerank(
    snapshot: GraphSnapshot, damping: float = 0.85, iterations: int = 40
) -> dict[str, float]:
    graph = _adjacency(snapshot)
    if not graph:
        return {}
    size = len(graph)
    rank = {node_id: 1.0 / size for node_id in graph}
    for _ in range(iterations):
        updated: dict[str, float] = {}
        for node_id, neighbours in graph.items():
            inflow = sum(rank[other] / len(graph[other]) for other in neighbours if graph[other])
            updated[node_id] = (1 - damping) / size + damping * inflow
        total = sum(updated.values()) or 1.0
        rank = {node_id: value / total for node_id, value in updated.items()}
    return rank


def ranked_nodes(snapshot: GraphSnapshot, limit: int = 15) -> list[dict[str, object]]:
    """Combine degree and PageRank into a single explainable influence ranking."""
    degree = degree_centrality(snapshot)
    ranks = pagerank(snapshot)
    ranked = sorted(
        snapshot.nodes,
        key=lambda node: (ranks.get(node.id, 0.0), degree.get(node.id, 0)),
        reverse=True,
    )
    return [
        {
            "id": node.id,
            "name": node.name,
            "label": node.label,
            "degree": degree.get(node.id, 0),
            "pagerank": round(ranks.get(node.id, 0.0), 6),
        }
        for node in ranked[:limit]
    ]


def connected_components(snapshot: GraphSnapshot) -> list[list[str]]:
    graph = _adjacency(snapshot)
    seen: set[str] = set()
    components: list[list[str]] = []
    for start in graph:
        if start in seen:
            continue
        queue = deque([start])
        seen.add(start)
        component: list[str] = []
        while queue:
            node_id = queue.popleft()
            component.append(node_id)
            for neighbour in sorted(graph[node_id]):
                if neighbour not in seen:
                    seen.add(neighbour)
                    queue.append(neighbour)
        components.append(component)
    return sorted(components, key=len, reverse=True)


def detect_communities(snapshot: GraphSnapshot, iterations: int = 25) -> list[dict[str, object]]:
    """Deterministic label propagation: cheap community detection, no GDS needed."""
    graph = _adjacency(snapshot)
    labels = {node_id: node_id for node_id in graph}
    for _ in range(iterations):
        changed = False
        for node_id in sorted(graph):
            neighbours = graph[node_id]
            if not neighbours:
                continue
            counts = Counter(labels[other] for other in neighbours)
            best = min(counts, key=lambda label: (-counts[label], label))
            if labels[node_id] != best:
                labels[node_id] = best
                changed = True
        if not changed:
            break
    grouped: dict[str, list[str]] = {}
    for node_id, label in labels.items():
        grouped.setdefault(label, []).append(node_id)
    by_id = {node.id: node for node in snapshot.nodes}
    communities = []
    for label, members in grouped.items():
        names = sorted(by_id[member].name for member in members if member in by_id)
        communities.append({"community": label, "size": len(members), "members": names[:12]})
    return sorted(communities, key=lambda item: item["size"], reverse=True)


def find_node(snapshot: GraphSnapshot, query: str) -> GraphNode | None:
    needle = query.strip().casefold()
    for node in snapshot.nodes:
        if node.id.casefold() == needle:
            return node
    for node in snapshot.nodes:
        if node.name.casefold() == needle or needle in node.name.casefold():
            return node
    return None


def neighborhood(snapshot: GraphSnapshot, seeds: set[str], hops: int = 2) -> GraphSnapshot:
    """Return the induced subgraph within ``hops`` of the seed node ids."""
    graph = _adjacency(snapshot)
    frontier = {seed for seed in seeds if seed in graph}
    visited = set(frontier)
    for _ in range(max(hops, 1)):
        frontier = {n for node_id in frontier for n in graph[node_id]} - visited
        visited |= frontier
    nodes = [node for node in snapshot.nodes if node.id in visited]
    edges = [edge for edge in snapshot.edges if edge.source in visited and edge.target in visited]
    return GraphSnapshot(nodes=nodes, edges=edges)


def shortest_path(snapshot: GraphSnapshot, source: str, target: str) -> dict[str, object]:
    start = find_node(snapshot, source)
    end = find_node(snapshot, target)
    if start is None or end is None:
        return {"found": False, "hops": 0, "nodes": [], "edges": [], "message": "node not found"}
    if start.id == end.id:
        return {"found": True, "hops": 0, "nodes": [start.model_dump()], "edges": []}
    graph = _adjacency(snapshot)
    previous: dict[str, str] = {}
    queue = deque([start.id])
    seen = {start.id}
    while queue:
        node_id = queue.popleft()
        if node_id == end.id:
            break
        for neighbour in sorted(graph[node_id]):
            if neighbour not in seen:
                seen.add(neighbour)
                previous[neighbour] = node_id
                queue.append(neighbour)
    if end.id not in previous and end.id != start.id:
        return {"found": False, "hops": 0, "nodes": [], "edges": [], "message": "no path"}
    path = [end.id]
    while path[-1] != start.id:
        path.append(previous[path[-1]])
    path.reverse()
    path_set = set(path)
    by_id = {node.id: node for node in snapshot.nodes}
    edges = [
        edge.model_dump()
        for edge in snapshot.edges
        if edge.source in path_set and edge.target in path_set
    ]
    return {
        "found": True,
        "hops": len(path) - 1,
        "nodes": [by_id[node_id].model_dump() for node_id in path],
        "edges": edges,
    }


def analytics_report(snapshot: GraphSnapshot, limit: int = 15) -> dict[str, object]:
    return {
        **graph_summary(snapshot),
        "centrality": ranked_nodes(snapshot, limit=limit),
        "communities": detect_communities(snapshot)[:limit],
    }
