// AgentPipeline — 7-node visualization driven by SSE events
import type { AgentEvent } from '../types';
import { AGENT_ORDER, AGENT_LABELS } from '../types';

interface Props {
  agentStatuses: Record<string, AgentEvent>;
  isRunning: boolean;
}

const STATUS_COLORS: Record<string, string> = {
  success: '#16a34a',
  partial: '#d97706',
  error: '#ef4444',
  fallback: '#7c3aed',
  pending: '#e5e7eb',
  running: '#3b82d4',
};

export function AgentPipeline({ agentStatuses, isRunning }: Props) {
  return (
    <div style={styles.container}>
      <div style={styles.label}>Agent Pipeline</div>
      <div style={styles.pipeline}>
        {AGENT_ORDER.map((agentId, idx) => {
          const event = agentStatuses[agentId];
          const isParallel = agentId === 'escalation' || agentId === 'parallel_analysis';
          const statusKey: string = event?.status ?? (isRunning && !event ? 'running' : 'pending');
          const color = STATUS_COLORS[statusKey] ?? STATUS_COLORS['pending'];
          const confidence = event?.confidence ?? 0;

          return (
            <div key={agentId} style={styles.nodeWrapper}>
              {idx > 0 && !isParallel && <div style={styles.connector} />}
              {agentId === 'escalation' && <div style={styles.parallelBracket}>║</div>}

              <div style={styles.node}>
                <div
                  style={{
                    ...styles.circle,
                    background: color,
                    boxShadow: statusKey === 'running' ? `0 0 0 3px ${color}44` : 'none',
                  }}
                >
                  {event ? (event.status === 'success' ? '✓' : event.status === 'error' ? '✗' : '~') : (idx + 1)}
                </div>
                <div style={styles.nodeName}>{AGENT_LABELS[agentId]}</div>
                {event && (
                  <div style={styles.confBar}>
                    <div style={{ ...styles.confFill, width: `${confidence * 100}%`, background: color }} />
                  </div>
                )}
                {event && <div style={{ ...styles.confLabel, color }}>{(confidence * 100).toFixed(0)}%</div>}
              </div>

              {agentId === 'parallel_analysis' && <div style={styles.parallelBracket}>║</div>}
            </div>
          );
        })}
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: { background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: '16px 20px', marginBottom: 20 },
  label: { fontWeight: 600, fontSize: 13, color: '#57606a', marginBottom: 12, textTransform: 'uppercase', letterSpacing: '0.05em' },
  pipeline: { display: 'flex', alignItems: 'flex-start', gap: 0, overflowX: 'auto', paddingBottom: 4 },
  nodeWrapper: { display: 'flex', alignItems: 'center', gap: 0 },
  connector: { width: 24, height: 2, background: '#e5e7eb', flexShrink: 0, marginTop: -16 },
  parallelBracket: { fontSize: 20, color: '#7c5cd8', margin: '0 2px', paddingBottom: 16 },
  node: { display: 'flex', flexDirection: 'column', alignItems: 'center', width: 68, flexShrink: 0 },
  circle: { width: 44, height: 44, borderRadius: '50%', color: '#fff', fontWeight: 700, fontSize: 13, display: 'flex', alignItems: 'center', justifyContent: 'center', transition: 'all 0.3s', marginBottom: 4 },
  nodeName: { fontSize: 10, color: '#57606a', textAlign: 'center', lineHeight: 1.3 },
  confBar: { width: 40, height: 4, background: '#e5e7eb', borderRadius: 2, marginTop: 4, overflow: 'hidden' },
  confFill: { height: '100%', borderRadius: 2, transition: 'width 0.3s' },
  confLabel: { fontSize: 10, fontWeight: 600, marginTop: 2 },
};
