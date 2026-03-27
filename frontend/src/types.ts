export interface Agent {
  id: string
  name: string
  description?: string
  prompt: string
  tools: string[]
  max_turns: number
  permission_mode: string
  created_at: string
  updated_at: string
}

export interface AgentRun {
  id: string
  agent_id: string
  session_id?: string
  status: 'pending' | 'running' | 'done' | 'failed' | 'cancelled'
  prompt: string
  result?: string
  stop_reason?: string
  error?: string
  total_input_tokens: number
  total_output_tokens: number
  started_at: string
  finished_at?: string
}

export interface RunMessage {
  id: number
  run_id: string
  sequence: number
  msg_type: string
  content: MessageContent
  created_at: string
}

export type MessageContent =
  | { type: 'system'; subtype: string; data: Record<string, unknown>; sequence: number; timestamp: string }
  | { type: 'assistant'; content: ContentBlock[]; usage: UsageInfo; sequence: number; timestamp: string }
  | { type: 'result'; result: string; stop_reason: string; sequence: number; timestamp: string }
  | { type: 'run_status'; status: string; error?: string }
  | { type: 'rate_limit'; status: string; sequence: number; timestamp: string }
  | { type: 'unknown'; repr: string; sequence: number; timestamp: string }

export type ContentBlock =
  | { type: 'text'; text: string }
  | { type: 'tool_use'; id: string; name: string; input: Record<string, unknown> }
  | { type: 'unknown'; repr: string }

export interface UsageInfo {
  input_tokens?: number
  output_tokens?: number
}

export interface AgentCreateForm {
  name: string
  description: string
  prompt: string
  tools: string[]
  max_turns: number
  permission_mode: string
}
