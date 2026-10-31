import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

// Vitest runs with `globals: false`, so Testing Library cannot auto-register its
// own cleanup hook; unmount between tests explicitly to avoid DOM leakage.
afterEach(() => {
  cleanup();
});
