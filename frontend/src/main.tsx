import React, { lazy } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { Providers } from './app/providers';
import { Layout } from './components/Layout';
import './style.css';

// Route-level code splitting: the force-directed graph canvas and the markdown
// renderer are only downloaded when their route is visited, keeping the
// initial JavaScript payload small.
const OverviewPage = lazy(() => import('./features/overview/OverviewPage'));
const GraphExplorerPage = lazy(() => import('./features/graph/GraphExplorerPage'));
const AnalyticsPage = lazy(() => import('./features/analytics/AnalyticsPage'));
const AssistantPage = lazy(() => import('./features/assistant/AssistantPage'));
const SourcesPage = lazy(() => import('./features/sources/SourcesPage'));
const QualityPage = lazy(() => import('./features/quality/QualityPage'));
const PipelinePage = lazy(() => import('./features/pipeline/PipelinePage'));
const EvaluationPage = lazy(() => import('./features/evaluation/EvaluationPage'));
const NotFound = lazy(() => import('./components/NotFound'));

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Providers>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<OverviewPage />} />
            <Route path="graph" element={<GraphExplorerPage />} />
            <Route path="analytics" element={<AnalyticsPage />} />
            <Route path="assistant" element={<AssistantPage />} />
            <Route path="assistant/:chatId" element={<AssistantPage />} />
            <Route path="sources" element={<SourcesPage />} />
            <Route path="quality" element={<QualityPage />} />
            <Route path="pipeline" element={<PipelinePage />} />
            <Route path="evaluation" element={<EvaluationPage />} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </Providers>
    </BrowserRouter>
  </React.StrictMode>,
);
