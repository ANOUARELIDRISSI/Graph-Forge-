export const env = {
  apiUrl: import.meta.env.VITE_API_URL ?? 'http://localhost:8000',
  apiTimeoutMs: Number(import.meta.env.VITE_API_TIMEOUT_MS ?? 30000),
};
