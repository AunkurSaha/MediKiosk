import { ApiError } from './client';

export type AlertPriority = 'emergency' | 'urgent' | 'priority';
export type AlertStatus = 'new' | 'acknowledged' | 'resolved';

export interface TriggeringFact {
  question_id: string;
  field: string;
  value: unknown;
  raw_value?: string | null;
  label?: string | Record<string, string> | null;
}

export interface AlertItem {
  id: string;
  session_id: string;
  rule_id: string;
  rule_version: string;
  priority: AlertPriority;
  category: string;
  reason: string;
  triggering_facts: TriggeringFact[];
  status: AlertStatus;
  acknowledged_at: string | null;
  acknowledged_by: string | null;
  acknowledgement_note: string | null;
  created_at: string;
  updated_at: string | null;
  hospital_token: string | null;
  patient_name: string | null;
}

export interface AlertList {
  items: AlertItem[];
  total: number;
  emergency_count: number;
  urgent_count: number;
  acknowledged_count: number;
}

export interface AlertAcknowledgeRequest {
  acknowledged_by: string;
  note?: string | null;
}

const base = import.meta.env.VITE_API_BASE_URL || '/api';

async function request<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch(base + path, {
      method,
      signal: controller.signal,
      headers: {
        ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
      },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    if (!response.ok) {
      const result = await response.json().catch(() => null);
      throw new ApiError(result?.error?.code || 'REQUEST_FAILED', response.status);
    }
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError('NETWORK_ERROR', 0);
  } finally {
    window.clearTimeout(timeout);
  }
}

export const triageApi = {
  getAlerts: (params?: { status?: AlertStatus; priority?: AlertPriority }) => {
    const searchParams = new URLSearchParams();
    if (params?.status) searchParams.set('status', params.status);
    if (params?.priority) searchParams.set('priority', params.priority);
    const qs = searchParams.toString();
    return request<AlertList>(`/triage/alerts${qs ? `?${qs}` : ''}`);
  },

  acknowledgeAlert: (alertId: string, payload: AlertAcknowledgeRequest) =>
    request<AlertItem>(`/triage/alerts/${alertId}/acknowledge`, 'POST', payload),

  getSessionAlerts: (sessionId: string) =>
    request<AlertItem[]>(`/sessions/${sessionId}/alerts`),

  getWebSocketUrl: () => {
    const loc = window.location;
    const protocol = loc.protocol === 'https:' ? 'wss:' : 'ws:';
    if (import.meta.env.VITE_API_BASE_URL) {
      const apiUrl = new URL(import.meta.env.VITE_API_BASE_URL, loc.origin);
      const wsProto = apiUrl.protocol === 'https:' ? 'wss:' : 'ws:';
      return `${wsProto}//${apiUrl.host}${apiUrl.pathname.replace(/\/$/, '')}/triage/ws`;
    }
    return `${protocol}//${loc.host}/api/triage/ws`;
  },
};
