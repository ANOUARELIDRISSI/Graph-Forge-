# Frontend architecture

## Product shape

The frontend is a React + TypeScript single-page application for the Moroccan business knowledge graph. It is divided into five product pages:

- **Overview**: corpus totals, pipeline health, and quick actions.
- **Graph Explorer**: searchable, zoomable 2D graph with 50/100/200 node limits and node inspection.
- **GraphRAG Assistant**: persistent ChatGPT-style conversation history with source citations.
- **Sources**: crawled domains, document counts, and original URLs.
- **Pipeline**: ingestion, chunking, entity extraction, and relationship verification.

## Runtime structure

`frontend/src/main.tsx` currently owns the page shell, API loading, navigation state, graph state, assistant state, and source display. The backend remains the source of truth; browser state is only used for the selected page, selected node, and locally persisted conversations.

```text
App
├── page navigation
├── Overview
│   ├── statistics cards
│   ├── pipeline summary
│   └── source summary
├── Graph Explorer
│   ├── search and node limit controls
│   ├── React Force Graph 2D canvas
│   └── selected-node provenance panel
├── GraphRAG Assistant
│   ├── conversation history
│   ├── question composer
│   └── source citations
├── Sources
└── Pipeline
```

## Libraries

- **React**: UI composition and stateful page behavior.
- **TypeScript**: typed graph, source, pipeline, and chat contracts.
- **Vite**: frontend development server and production bundling.
- **react-force-graph-2d**: interactive 2D graph rendering, zooming, panning, links, and node selection.
- **CSS**: responsive layout and ChatGPT-inspired blue/grey visual system without a heavyweight component framework.

## Backend contracts used

- `GET /graph` — graph nodes and relationships.
- `GET /sources` — source domains, document counts, and URLs.
- `GET /pipeline/status` — documents, chunks, entities, and relationship readiness.
- `POST /rag/ask` — grounded answer and source URLs.
- `GET /data-quality` — document-level authority/provenance/completeness ranking.

## Conversation persistence

Assistant conversations are stored in browser `localStorage` under `graph-rag-chats`. This keeps conversations across refreshes without sending private chat history to the backend. A future production version should replace this with authenticated server-side conversation storage.

## Graph interaction design

Nodes are sized by semantic type: sectors are larger than pages and sources. Every node has a type-specific color, white halo, shadow, label at higher zoom, and click-to-inspect behavior. Links use directional arrows and muted blue-grey lines so the graph remains readable at 50, 100, or 200 visible nodes.

## Run locally

```powershell
cd frontend
npm install
npm run dev
```

The application expects the API at `http://localhost:8000`; override it with `VITE_API_URL` when needed.
