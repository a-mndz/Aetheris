import { useCallback, useRef, useState } from 'react';
import { streamQuery } from '../api/client';

/**
 * Initial state for a single agent's streaming data.
 */
function createAgentState() {
  return {
    status: 'idle',          // 'idle' | 'running' | 'done' | 'error'
    progress: [],            // [{ step, total_steps, message }]
    reasoning_summary: {},   // { section: content }
    draft_answer: null,
    final_answer: null,
    confidence: null,
  };
}

/**
 * Derive a coarse pipeline stage from the per-agent states.
 * This keeps backward compatibility with PipelineStatus.
 */
function derivePipelineStage(agents) {
  if (agents.Judge.status === 'done') return 'done';
  if (agents.Judge.status === 'running') return 'judge';
  if (agents.Logician.status !== 'idle' || agents.Creative.status !== 'idle') return 'agents';
  if (agents.Breaker.status !== 'idle') return 'breaker';
  return 'idle';
}

/**
 * usePipelineStages — drives the pipeline progress indicator using
 * real-time granular per-agent SSE events from the backend.
 *
 * Returns:
 *   stage       – coarse pipeline stage ('idle' | 'breaker' | 'agents' | 'judge' | 'done' | 'error')
 *   agentStates – per-agent state object { Breaker, Logician, Creative, Judge }
 *   partialData – partial results streamed mid-pipeline (agent outputs for ReasoningPanel compatibility)
 *   run(query, history) – starts the streaming pipeline
 *   reset()     – resets everything to idle
 */
export function usePipelineStages() {
  const [stage, setStage] = useState('idle');
  const [agentStates, setAgentStates] = useState({
    Breaker: createAgentState(),
    Logician: createAgentState(),
    Creative: createAgentState(),
    Judge: createAgentState(),
  });
  const [partialData, setPartialData] = useState(null);
  const abortRef = useRef(null);

  const run = useCallback(async (query, history) => {
    // Abort any in-flight request
    if (abortRef.current) abortRef.current.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    // Reset all agent states
    const freshAgents = {
      Breaker: createAgentState(),
      Logician: createAgentState(),
      Creative: createAgentState(),
      Judge: createAgentState(),
    };
    setAgentStates(freshAgents);
    setStage('breaker');
    setPartialData(null);

    // Mutable ref for building state inside the event callback
    const agentsRef = { ...freshAgents };

    const updateAgent = (agentName, patch) => {
      if (!agentsRef[agentName]) return;
      agentsRef[agentName] = { ...agentsRef[agentName], ...patch };
      const nextAgents = { ...agentsRef };
      setAgentStates(nextAgents);
      setStage(derivePipelineStage(nextAgents));
    };

    const onEvent = (event) => {
      if (controller.signal.aborted) return;

      switch (event.event) {
        case 'agent_started': {
          updateAgent(event.agent, { status: 'running' });
          break;
        }

        case 'progress': {
          const agent = agentsRef[event.agent];
          if (!agent) break;
          const progress = [
            ...agent.progress,
            { step: event.step, total_steps: event.total_steps, message: event.message },
          ];
          updateAgent(event.agent, { progress });
          break;
        }

        case 'reasoning_summary': {
          const agent = agentsRef[event.agent];
          if (!agent) break;
          updateAgent(event.agent, {
            reasoning_summary: {
              ...agent.reasoning_summary,
              [event.section]: event.content,
            },
          });
          break;
        }

        case 'draft_answer': {
          updateAgent(event.agent, { draft_answer: event.content });
          break;
        }

        case 'agent_completed': {
          const completedStatus = event.status === 'aborted' ? 'error' : 'done';
          updateAgent(event.agent, {
            status: completedStatus,
            final_answer: event.final_answer,
            confidence: event.confidence,
          });

          // Build partial data for backward compatibility with ReasoningPanel
          // When Logician or Creative completes, add their data to partialData
          if (event.agent === 'Logician' || event.agent === 'Creative') {
            const agentKey = event.agent.toLowerCase();
            const agentData = agentsRef[event.agent];
            setPartialData((prev) => ({
              ...prev,
              agent_outputs: {
                ...(prev?.agent_outputs || {}),
                [agentKey]: {
                  reasoning_steps: agentData.reasoning_summary?.['Evidence Used'] || [],
                  answer: agentData.final_answer || agentData.draft_answer || '',
                  confidence: agentData.confidence,
                },
              },
            }));
          }
          break;
        }

        case 'error': {
          if (event.agent) {
            updateAgent(event.agent, { status: 'error' });
          }
          setStage('error');
          break;
        }

        // Legacy stage events (backward compat — kept just in case)
        case 'stage': {
          if (event.status === 'running') {
            setStage(event.stage);
          } else if (event.status === 'done') {
            if (event.partial) {
              setPartialData((prev) => ({ ...prev, ...event.partial }));
            }
          } else if (event.status === 'aborted') {
            setStage('error');
          }
          break;
        }

        default:
          break;
      }
    };

    try {
      const { data, latencyMs } = await streamQuery(query, {
        signal: controller.signal,
        history,
        onEvent,
      });
      if (controller.signal.aborted) {
        return { data: null, latencyMs: 0, error: null, aborted: true };
      }
      setStage('done');
      return { data, latencyMs, error: null, aborted: false };
    } catch (error) {
      if (controller.signal.aborted) {
        return { data: null, latencyMs: 0, error: null, aborted: true };
      }
      setStage('error');
      return { data: null, latencyMs: 0, error, aborted: false };
    }
  }, []);

  const reset = useCallback(() => {
    setStage('idle');
    setPartialData(null);
    setAgentStates({
      Breaker: createAgentState(),
      Logician: createAgentState(),
      Creative: createAgentState(),
      Judge: createAgentState(),
    });
  }, []);

  return { stage, agentStates, partialData, run, reset };
}
