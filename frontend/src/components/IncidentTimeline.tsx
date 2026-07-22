// IncidentTimeline — chronological agent event log with timestamps
import type { AgentEvent } from '../types';
import { AGENT_LABELS } from '../types';

interface TimelineEntry { stage: string; event: AgentEvent; timestamp: Date; }

interface Props { events: TimelineEntry[]; }

const STATUS_ICONS: Record<string, string> = {
  success: '✓', partial: '~', error: '✗', fallback: '↩',
};

export function IncidentTimeline({ events }: Props) {
  if (events.length === 0) return null;

  return (
    <div style={styles.container}>
      <div style={styles.label}>Incident Timeline</div>
      {events.map((entry, idx) => (
        <div key={idx} style={styles.entry}>
          <div style={styles.dot} />
          {idx < events.length - 1 && <div style={styles.line} />}
          <div style={styles.content}>
            <div style={styles.row}>
              <span style={styles.agentName}>
                {STATUS_ICONS[entry.event.status] ?? '·'}{' '}
                {AGENT_LABELS[entry.stage as keyof typeof AGENT_LABELS] ?? entry.stage}
              </span>
              <span style={styles.time}>{entry.timestamp.toLocaleTimeString()}</span>
            </div>
            <div style={styles.detail}>
              status: {entry.event.status} · confidence: {(entry.event.confidence * 100).toFixed(0)}%
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: { background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: '16px 20px', marginBottom: 20 },
  label: { fontWeight: 600, fontSize: 13, color: '#57606a', marginBottom: 12, textTransform: 'uppercase', letterSpacing: '0.05em' },
  entry: { display: 'flex', gap: 12, position: 'relative', paddingBottom: 12 },
  dot: { width: 10, height: 10, borderRadius: '50%', background: '#3b82d4', flexShrink: 0, marginTop: 4 },
  line: { position: 'absolute', left: 4, top: 14, bottom: 0, width: 2, background: '#e5e7eb' },
  content: { flex: 1 },
  row: { display: 'flex', justifyContent: 'space-between', marginBottom: 2 },
  agentName: { fontWeight: 600, fontSize: 13, color: '#1f2328' },
  time: { fontSize: 11, color: '#8b949e' },
  detail: { fontSize: 12, color: '#57606a' },
};
