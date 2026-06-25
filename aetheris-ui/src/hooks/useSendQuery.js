import { useChatStore } from '../store/useChatStore';
import { usePipelineStages } from './usePipelineStages';

function createId() {
  return typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID()
    : `id-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function deriveErrorMessage(error) {
  if (error?.isStreamError) {
    return `Pipeline failed at ${error.stage}: ${error.message}`;
  }
  if (!error?.response) {
    return 'Could not reach the Aetheris backend. Check that the server is running at the configured API base URL and that CORS is enabled for this origin.';
  }
  const status = error.response.status;
  if (status >= 500) return `Backend error (${status}). The orchestrator failed while processing this query.`;
  if (status === 422) return 'The backend rejected the request payload (422). Verify the query field matches the expected schema.';
  return `Request failed with status ${status}.`;
}

export function useSendQuery() {
  const addMessage = useChatStore((s) => s.addMessage);
  const updateMessage = useChatStore((s) => s.updateMessage);
  const addTelemetryEntry = useChatStore((s) => s.addTelemetryEntry);
  const getActiveConversation = useChatStore((s) => s.getActiveConversation);
  const { stage, agentStates, partialData, run, reset } = usePipelineStages();

  const send = async (conversationId, query) => {
    const trimmed = query.trim();
    if (!trimmed) return;

    const userMessage = { id: createId(), role: 'user', content: trimmed, createdAt: Date.now() };
    const assistantMessage = {
      id: createId(),
      role: 'assistant',
      status: 'pending',
      createdAt: Date.now(),
      response: null,
      error: null,
    };

    addMessage(conversationId, userMessage);
    addMessage(conversationId, assistantMessage);

    // Build history from conversation messages for multi-turn context
    const conversation = getActiveConversation();
    const history = (conversation?.messages ?? [])
      .filter((m) => m.role === 'user' || (m.role === 'assistant' && m.status === 'done'))
      .map((m) => ({
        role: m.role,
        content: m.role === 'user' ? m.content : (m.response?.answer ?? ''),
      }))
      .filter((m) => m.content)
      .slice(-10); // Last 10 messages to keep context manageable

    const { data, latencyMs, error, aborted } = await run(trimmed, history);

    if (aborted) return;

    if (error) {
      updateMessage(conversationId, assistantMessage.id, { status: 'error', error: deriveErrorMessage(error) });
      // Reset to idle after a brief delay so user sees the error state
      setTimeout(() => reset(), 100);
      return;
    }

    updateMessage(conversationId, assistantMessage.id, { status: 'done', response: data });

    addTelemetryEntry({
      id: createId(),
      timestamp: Date.now(),
      query: trimmed,
      latencyMs,
      confidence: data?.confidence_score ?? null,
      biasRisk: data?.bias_risk ?? null,
      provider: null,
      cost: null,
    });

    // Reset stage to idle after a brief delay so user sees the "done" state
    setTimeout(() => reset(), 1500);
  };

  return { send, stage, agentStates, partialData };
}
