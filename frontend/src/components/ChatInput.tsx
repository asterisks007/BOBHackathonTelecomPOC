// ChatInput — free-text input form
import { useState, type FormEvent } from 'react';

interface Props {
  onSubmit: (message: string) => void;
  isRunning: boolean;
  onCancel: () => void;
}

const PLACEHOLDER_MSGS = [
  'Complete fiber cut at junction box BX-42, sector north, ~50000 customers affected',
  'Billing system completely down, customers cannot make payments',
  '4G signal degradation across eastern sector, multiple sites affected',
];

export function ChatInput({ onSubmit, isRunning, onCancel }: Props) {
  const [message, setMessage] = useState('');
  const [placeholder] = useState(PLACEHOLDER_MSGS[0]);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const trimmed = message.trim();
    if (!trimmed || isRunning) return;
    onSubmit(trimmed);
  };

  return (
    <form onSubmit={handleSubmit} style={styles.form}>
      <div style={styles.header}>
        <span style={styles.icon}>📡</span>
        <span style={styles.title}>Telecom Outage Resolution Copilot</span>
        <span style={styles.badge}>IBM BOB · 7-Agent Pipeline</span>
      </div>

      <textarea
        style={styles.textarea}
        value={message}
        onChange={e => setMessage(e.target.value)}
        placeholder={placeholder}
        rows={3}
        maxLength={2000}
        disabled={isRunning}
        onKeyDown={e => {
          if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) handleSubmit(e as unknown as FormEvent);
        }}
      />

      <div style={styles.footer}>
        <span style={styles.counter}>{message.length}/2000</span>
        <div style={styles.actions}>
          {isRunning ? (
            <button type="button" onClick={onCancel} style={styles.cancelBtn}>
              Cancel
            </button>
          ) : (
            <>
              <button
                type="button"
                style={styles.demoBtn}
                onClick={() => setMessage(PLACEHOLDER_MSGS[Math.floor(Math.random() * PLACEHOLDER_MSGS.length)])}
              >
                Load Demo
              </button>
              <button
                type="submit"
                style={{ ...styles.submitBtn, opacity: message.trim() ? 1 : 0.5 }}
                disabled={!message.trim()}
              >
                Analyse Outage →
              </button>
            </>
          )}
        </div>
      </div>
    </form>
  );
}

const styles: Record<string, React.CSSProperties> = {
  form: { background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: '16px 20px', marginBottom: 20 },
  header: { display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 },
  icon: { fontSize: 18 },
  title: { fontWeight: 600, fontSize: 15, color: '#1f2328' },
  badge: { marginLeft: 'auto', background: '#dbeafe', color: '#1d4ed8', padding: '2px 8px', borderRadius: 10, fontSize: 11, fontWeight: 600 },
  textarea: { width: '100%', border: '1px solid #e5e7eb', borderRadius: 6, padding: '10px 12px', resize: 'vertical', outline: 'none', color: '#1f2328', background: '#f7f8fa', lineHeight: 1.5 },
  footer: { display: 'flex', alignItems: 'center', marginTop: 8, gap: 8 },
  counter: { fontSize: 11, color: '#8b949e', marginRight: 'auto' },
  actions: { display: 'flex', gap: 8 },
  submitBtn: { background: '#3b82d4', color: '#fff', border: 'none', borderRadius: 6, padding: '7px 18px', fontWeight: 600, transition: 'opacity 0.15s' },
  cancelBtn: { background: '#ef4444', color: '#fff', border: 'none', borderRadius: 6, padding: '7px 14px', fontWeight: 600 },
  demoBtn: { background: '#f7f8fa', color: '#57606a', border: '1px solid #e5e7eb', borderRadius: 6, padding: '7px 14px' },
};
