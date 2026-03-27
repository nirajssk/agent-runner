import type { Agent, AgentRun, RunMessage, AgentCreateForm } from './types'

const BASE = '/api'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`)
  return res.json() as Promise<T>
}

export const api = {
  getAgents: () => request<Agent[]>('/agents'),
  createAgent: (body: AgentCreateForm) =>
    request<Agent>('/agents', { method: 'POST', body: JSON.stringify(body) }),
  updateAgent: (id: string, body: Partial<AgentCreateForm>) =>
    request<Agent>(`/agents/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteAgent: (id: string) =>
    request<{ ok: boolean }>(`/agents/${id}`, { method: 'DELETE' }),
  getRuns: (agentId: string) => request<AgentRun[]>(`/agents/${agentId}/runs`),
  startRun: (agentId: string, promptOverride?: string) =>
    request<AgentRun>('/runs', {
      method: 'POST',
      body: JSON.stringify({ agent_id: agentId, prompt_override: promptOverride ?? null }),
    }),
  getRun: (id: string) => request<AgentRun>(`/runs/${id}`),
  getMessages: (runId: string) => request<RunMessage[]>(`/runs/${runId}/messages`),
  stopRun: (id: string) =>
    request<{ ok: boolean }>(`/runs/${id}/stop`, { method: 'POST' }),
}
