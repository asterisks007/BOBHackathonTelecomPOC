// Dashboard — main page composing all components
import { useState, useEffect } from 'react';
import { ChatInput } from '../components/ChatInput';
import { AgentPipeline } from '../components/AgentPipeline';
import { ResolutionPanel } from '../components/ResolutionPanel';
import { IncidentTimeline } from '../components/IncidentTimeline';
import { useOrchestration } from '../hooks/useOrchestration';
import type { AgentEvent } from '../types';

interface TimelineEntry { stage: string; event: AgentEvent; timestamp: Date; }

export function Dashboard() {
  const { isRunning, agentStatuses, completeEvent, error, run, cancel } = useOrchestration();
  const [timeline, setTimeline] = useState<TimelineEntry[]>([]);
  const [result, setResult] = useState<Record<string, Record<string, unknown>>>({});

  const [useMock, setUseMock] = useState<boolean | null>(null);

  // Fetch live system health & use_mock status from backend
  useEffect(() => {
    const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';
    fetch(`${API_URL}/health`)
      .then(res => res.json())
      .then(data => setUseMock(data.use_mock))
      .catch(() => setUseMock(false));
  }, []);

  // Track timeline entries as SSE events arrive
  useEffect(() => {
    const entries = Object.entries(agentStatuses);
    if (entries.length > 0) {
      const [stage, event] = entries[entries.length - 1];
      setTimeline(t => {
        if (t.some(e => e.stage === stage)) return t;
        return [...t, { stage, event, timestamp: new Date() }];
      });
    }
  }, [agentStatuses]);

  const handleSubmit = async (message: string) => {
    setTimeline([]);
    setResult({});

    // Fetch the non-streaming result separately for structured summaries
    const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';
    run(message);

    try {
      const resp = await fetch(`${API_URL}/orchestrate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: crypto.randomUUID(), customer_id: 'UI-USER', message }),
      });
      if (resp.ok) {
        const data = await resp.json();
        setResult({
          ticket_summary: data.ticket_summary ?? {},
          rca_summary: data.rca_summary ?? {},
          resolution_summary: data.resolution_summary ?? {},
          escalation_summary: data.escalation_summary ?? {},
          feedback_summary: data.feedback_summary ?? {},
        });
      }
    } catch {
      // streaming path will surface the error
    }
  };

  return (
    <div style={styles.page}>
      <div style={styles.container}>
        {/* Input */}
        <ChatInput onSubmit={handleSubmit} isRunning={isRunning} onCancel={cancel} />

        {/* Error */}
        {error && (
          <div style={styles.errorBox}>
            ⚠ {error}
            <button style={styles.retryBtn} onClick={() => window.location.reload()}>Retry</button>
          </div>
        )}

        {/* Pipeline visualization */}
        {(isRunning || Object.keys(agentStatuses).length > 0) && (
          <AgentPipeline agentStatuses={agentStatuses} isRunning={isRunning} />
        )}

        {/* Two-column: resolution + timeline */}
        {completeEvent && (
          <div style={styles.cols}>
            <div style={styles.colMain}>
              <ResolutionPanel
                completeEvent={completeEvent}
                resolutionSummary={result.resolution_summary ?? null}
                ticketSummary={result.ticket_summary ?? null}
                rcaSummary={result.rca_summary ?? null}
                escalationSummary={result.escalation_summary ?? null}
              />
            </div>
            <div style={styles.colSide}>
              <IncidentTimeline events={timeline} />
            </div>
          </div>
        )}

        <div style={styles.footer}>
          Made with IBM Bob · IBM BOB Hackathon 2026 · USE_MOCK={useMock === null ? 'false' : String(useMock)}
        </div>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  page: { minHeight: '100vh', background: '#f0f2f5', padding: '24px 16px' },
  container: { maxWidth: 1100, margin: '0 auto' },
  errorBox: { background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 6, padding: '10px 14px', color: '#991b1b', marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' },
  retryBtn: { background: '#ef4444', color: '#fff', border: 'none', borderRadius: 5, padding: '4px 12px', fontSize: 12 },
  cols: { display: 'flex', gap: 16, alignItems: 'flex-start' },
  colMain: { flex: 2 },
  colSide: { flex: 1 },
  footer: { textAlign: 'center', fontSize: 11, color: '#8b949e', marginTop: 24, padding: '12px 0', borderTop: '1px solid #e5e7eb' },
};
