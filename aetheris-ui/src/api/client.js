import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 900000,
  headers: { 'Content-Type': 'application/json' },
});

// Attach Authorization header if JWT token is found
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Redirect to login on 401 Unauthorized responses
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('access_token');
      localStorage.removeItem('user_email');
      // Only redirect if not already on the login page
      if (!window.location.pathname.startsWith('/login')) {
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

/**
 * Posts a query to aetheris's POST /api/query endpoint.
 *
 * Now supports sending conversation history for multi-turn context.
 */
export async function postQuery(query, { signal, history } = {}) {
  const startedAt = performance.now();
  const payload = { query };
  if (Array.isArray(history) && history.length > 0) {
    payload.history = history;
  }
  const response = await apiClient.post('/api/query', payload, { signal });
  const latencyMs = Math.round(performance.now() - startedAt);
  return { data: response.data, latencyMs };
}

/**
 * Streams a query via SSE from POST /api/query/stream.
 *
 * Uses fetch() + ReadableStream (not EventSource, which only supports GET).
 * Calls `onEvent(eventObj)` for each parsed SSE data line.
 *
 * Returns a Promise that resolves with { data, latencyMs } when the
 * final "result" event arrives, or rejects on error.
 */
export function streamQuery(query, { signal, history, onEvent } = {}) {
  const startedAt = performance.now();
  const payload = { query };
  if (Array.isArray(history) && history.length > 0) {
    payload.history = history;
  }

  return new Promise(async (resolve, reject) => {
    try {
      const token = localStorage.getItem('access_token');
      const headers = { 'Content-Type': 'application/json' };
      if (token) {
        headers.Authorization = `Bearer ${token}`;
      }

      const response = await fetch(`${API_BASE_URL}/api/query/stream`, {
        method: 'POST',
        headers,
        body: JSON.stringify(payload),
        signal,
      });

      if (!response.ok) {
        const text = await response.text().catch(() => '');
        reject(new Error(`Stream request failed (${response.status}): ${text}`));
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // Parse SSE lines: each message is "data: {...}\n\n"
        const lines = buffer.split('\n');
        buffer = lines.pop() || ''; // Keep incomplete line in buffer

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed || !trimmed.startsWith('data: ')) continue;

          try {
            const event = JSON.parse(trimmed.slice(6));
            if (onEvent) onEvent(event);

            if (event.event === 'result') {
              const latencyMs = Math.round(performance.now() - startedAt);
              resolve({ data: event.payload, latencyMs });
            } else if (event.event === 'error') {
              const latencyMs = Math.round(performance.now() - startedAt);
              reject({
                isStreamError: true,
                stage: event.stage,
                message: event.message,
                latencyMs,
              });
            }
          } catch {
            // Skip malformed JSON lines
          }
        }
      }

      // If we reach end-of-stream without a result event, resolve with null
      const latencyMs = Math.round(performance.now() - startedAt);
      resolve({ data: null, latencyMs });
    } catch (err) {
      if (signal?.aborted) {
        reject(err);
      } else {
        reject(err);
      }
    }
  });
}

/**
 * Fetches real provider health + telemetry from GET /api/status.
 * Falls back gracefully if the endpoint is unavailable.
 */
export async function fetchProviderStatus({ signal } = {}) {
  try {
    const response = await apiClient.get('/api/status', { signal });
    return response.data;
  } catch {
    return null;
  }
}
