// Shared TypeScript types matching the FastAPI response schemas

export interface AgentEvent {
  stage: string;
  agent: string;
  status: 'success' | 'partial' | 'error' | 'fallback';
  confidence: number;
  partial_result: Record<string, unknown>;
}

export interface CompleteEvent {
  stage: 'complete';
  agent: string;
  status: string;
  total_execution_ms: number;
  ticket_id: string | null;
  agents_completed: string[];
  agents_failed: string[];
}

export type SSEPayload = AgentEvent | CompleteEvent;

export interface OrchestrationResult {
  session_id: string;
  ticket_id: string | null;
  intent_summary: Record<string, unknown> | null;
  ticket_summary: Record<string, unknown> | null;
  rca_summary: Record<string, unknown> | null;
  escalation_summary: Record<string, unknown> | null;
  analysis_summary: Record<string, unknown> | null;
  resolution_summary: Record<string, unknown> | null;
  feedback_summary: Record<string, unknown> | null;
  total_execution_ms: number;
  agents_completed: string[];
  agents_failed: string[];
}

export type AgentName =
  | 'intent_recognition'
  | 'ticket_classification'
  | 'rca_analysis'
  | 'escalation'
  | 'parallel_analysis'
  | 'response_generation'
  | 'feedback';

export const AGENT_LABELS: Record<AgentName, string> = {
  intent_recognition: 'Intent',
  ticket_classification: 'Ticket',
  rca_analysis: 'RCA',
  escalation: 'Escalation',
  parallel_analysis: 'Parallel',
  response_generation: 'Resolution',
  feedback: 'Feedback',
};

export const AGENT_ORDER: AgentName[] = [
  'intent_recognition',
  'ticket_classification',
  'rca_analysis',
  'escalation',
  'parallel_analysis',
  'response_generation',
  'feedback',
];
