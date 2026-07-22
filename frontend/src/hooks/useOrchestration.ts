// SSE orchestration hook — streams per-agent events from POST /orchestrate/stream
import { useState, useCallback, useRef } from 'react';
import type { AgentEvent, CompleteEvent, SSEPayload } from '../types';

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

export interface OrchestrationState {
  isRunning: boolean;
  agentStatuses: Record<string, AgentEvent>;
  completeEvent: CompleteEvent | null;
  error: string | null;
  sessionId: string | null;
}

export function useOrchestration() {
  const [state, setState] = useState<OrchestrationState>({
    isRunning: false,
    agentStatuses: {},
    completeEvent: null,
    error: null,
    sessionId: null,
  });

  const abortRef = useRef<AbortController | null>(null);

  const run = useCallback(async (message: string, customerId = 'UI-USER') => {
    // Reset state
    const newSessionId = crypto.randomUUID();
    setState({ isRunning: true, agentStatuses: {}, completeEvent: null, error: null, sessionId: newSessionId });

    abortRef.current?.abort();
    abortRef.current = new AbortController();

    try {
      const resp = await fetch(`${API_URL}/orchestrate/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: newSessionId, customer_id: customerId, message }),
        signal: abortRef.current.signal,
      });

      if (!resp.ok || !resp.body) {
        throw new Error(`Server error ${resp.status}`);
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n\n');
        buffer = lines.pop() ?? '';

        for (const chunk of lines) {
          const line = chunk.trim();
          if (!line.startsWith('data: ')) continue;
          try {
            const payload = JSON.parse(line.slice(6)) as SSEPayload;

            if (payload.stage === 'complete') {
              setState(prev => ({
                ...prev,
                isRunning: false,
                completeEvent: payload as CompleteEvent,
              }));
            } else {
              const ev = payload as AgentEvent;
              setState(prev => ({
                ...prev,
                agentStatuses: { ...prev.agentStatuses, [ev.stage]: ev },
              }));
            }
          } catch {
            // skip malformed event
          }
        }
      }
    } catch (err: unknown) {
      if ((err as Error).name !== 'AbortError') {
        setState(prev => ({ ...prev, isRunning: false, error: (err as Error).message }));
      }
    }
  }, []);

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    setState(prev => ({ ...prev, isRunning: false }));
  }, []);

  return { ...state, run, cancel };
}
