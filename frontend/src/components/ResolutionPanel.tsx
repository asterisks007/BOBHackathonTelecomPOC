// ResolutionPanel — shows resolution steps, customer message, ticket info
import type { CompleteEvent } from '../types';

interface Props {
  completeEvent: CompleteEvent | null;
  resolutionSummary: Record<string, unknown> | null;
  ticketSummary: Record<string, unknown> | null;
  rcaSummary: Record<string, unknown> | null;
  escalationSummary: Record<string, unknown> | null;
}

export function ResolutionPanel({ completeEvent, resolutionSummary, ticketSummary, rcaSummary, escalationSummary }: Props) {
  if (!completeEvent) return null;

  const steps = (resolutionSummary?.resolution_steps as string[]) ?? [];
  const customerMessage = resolutionSummary?.customer_message as string ?? '';
  const automationScore = (resolutionSummary?.automation_score as number ?? 0) * 100;
  const severity = ticketSummary?.severity as string ?? '';
  const queue = ticketSummary?.queue as string ?? '';
  const rootCause = rcaSummary?.root_cause as string ?? '';
  const escalated = escalationSummary?.escalate as boolean ?? false;
  const escalationLevel = escalationSummary?.escalation_level as string ?? '';

  const severityColor = severity === 'P1' ? '#ef4444' : severity === 'P2' ? '#d97706' : '#16a34a';

  return (
    <div style={styles.container}>
      {/* Header */}
      <div style={styles.header}>
        <div style={styles.ticketRow}>
          <span style={styles.ticketId}>{completeEvent.ticket_id ?? 'N/A'}</span>
          <span style={{ ...styles.severityBadge, background: severityColor }}>{severity}</span>
          {escalated && <span style={styles.escalatedBadge}>⚠ Escalated — {escalationLevel}</span>}
        </div>
        <div style={styles.meta}>{queue} · {completeEvent.total_execution_ms.toFixed(0)}ms · {completeEvent.agents_completed.length}/7 agents</div>
      </div>

      {/* Root Cause */}
      {rootCause && (
        <div style={styles.section}>
          <div style={styles.sectionLabel}>Root Cause Analysis</div>
          <div style={styles.rcaText}>{rootCause}</div>
        </div>
      )}

      {/* Resolution Steps */}
      {steps.length > 0 && (
        <div style={styles.section}>
          <div style={styles.sectionLabel}>
            Resolution Steps
            <span style={{ ...styles.autoBadge, background: automationScore >= 60 ? '#dcfce7' : '#fef9c3', color: automationScore >= 60 ? '#16a34a' : '#854d0e' }}>
              Auto-score: {automationScore.toFixed(0)}%
            </span>
          </div>
          <ol style={styles.stepList}>
            {steps.map((step, i) => (
              <li key={i} style={styles.stepItem}>{step}</li>
            ))}
          </ol>
        </div>
      )}

      {/* Customer Message */}
      {customerMessage && (
        <div style={styles.section}>
          <div style={styles.sectionLabel}>Customer Communication</div>
          <div style={styles.customerMsg}>{customerMessage}</div>
        </div>
      )}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: { background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: '16px 20px', marginBottom: 20 },
  header: { marginBottom: 16, paddingBottom: 12, borderBottom: '1px solid #e5e7eb' },
  ticketRow: { display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 },
  ticketId: { fontFamily: 'monospace', fontWeight: 700, fontSize: 15, color: '#1f2328' },
  severityBadge: { color: '#fff', padding: '1px 8px', borderRadius: 10, fontSize: 12, fontWeight: 700 },
  escalatedBadge: { background: '#fef9c3', color: '#854d0e', padding: '1px 8px', borderRadius: 10, fontSize: 12, fontWeight: 600 },
  meta: { fontSize: 12, color: '#57606a' },
  section: { marginBottom: 16 },
  sectionLabel: { fontWeight: 600, fontSize: 12, color: '#57606a', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 8 },
  autoBadge: { padding: '1px 8px', borderRadius: 10, fontSize: 11, fontWeight: 600, textTransform: 'none', letterSpacing: 'normal' },
  rcaText: { background: '#f7f8fa', border: '1px solid #e5e7eb', borderRadius: 6, padding: '10px 12px', fontSize: 13, lineHeight: 1.6, color: '#1f2328' },
  stepList: { paddingLeft: 20 },
  stepItem: { marginBottom: 6, lineHeight: 1.5, color: '#1f2328', fontSize: 13 },
  customerMsg: { background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: 6, padding: '10px 12px', fontSize: 13, lineHeight: 1.6, color: '#1e40af', fontStyle: 'italic' },
};
