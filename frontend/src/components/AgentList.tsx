import type { Agent, AgentRun } from '../types'

interface Props {
  agents: Agent[]
  selectedId: string | null
  allRuns: AgentRun[]
  onSelect: (id: string) => void
  onNew: () => void
}

type AgentStatus = 'running' | 'failed' | 'idle'

function getAgentStatus(agentId: string, allRuns: AgentRun[]): AgentStatus {
  const agentRuns = allRuns.filter((r) => r.agent_id === agentId)
  if (agentRuns.some((r) => r.status === 'running')) return 'running'
  const sorted = [...agentRuns].sort(
    (a, b) => new Date(b.started_at).getTime() - new Date(a.started_at).getTime(),
  )
  if (sorted.length > 0 && sorted[0].status === 'failed') return 'failed'
  return 'idle'
}

function getLastSevenRuns(agentId: string, allRuns: AgentRun[]): AgentRun[] {
  return [...allRuns.filter((r) => r.agent_id === agentId)]
    .sort((a, b) => new Date(a.started_at).getTime() - new Date(b.started_at).getTime())
    .slice(-7)
}

function SparkDot({ status }: { status: AgentRun['status'] | 'empty' }) {
  const colorMap: Record<string, string> = {
    done: 'bg-green-500',
    failed: 'bg-red-500',
    running: 'bg-yellow-400',
    pending: 'bg-yellow-400',
    cancelled: 'bg-gray-600',
    empty: 'bg-gray-700',
  }
  return (
    <div
      className={`w-1.5 h-1.5 rounded-sm flex-shrink-0 ${colorMap[status] ?? 'bg-gray-700'}`}
      title={status}
    />
  )
}

function Sparkline({ agentId, allRuns }: { agentId: string; allRuns: AgentRun[] }) {
  const last7 = getLastSevenRuns(agentId, allRuns)
  const dots: Array<AgentRun['status'] | 'empty'> = Array(7).fill('empty')
  last7.forEach((run, i) => {
    dots[i] = run.status
  })
  return (
    <div className="flex items-center gap-0.5">
      {dots.map((status, i) => (
        <SparkDot key={i} status={status} />
      ))}
    </div>
  )
}

function StatusDot({ status }: { status: AgentStatus }) {
  const colorMap: Record<AgentStatus, string> = {
    running: 'bg-green-400 animate-pulse',
    failed: 'bg-red-400',
    idle: 'bg-gray-500',
  }
  return <div className={`w-2 h-2 rounded-full flex-shrink-0 ${colorMap[status]}`} />
}

export default function AgentList({ agents, selectedId, allRuns, onSelect, onNew }: Props) {
  return (
    <div className="flex flex-col w-56 flex-shrink-0 border-r border-gray-800 bg-gray-900 overflow-hidden">
      {/* Panel header */}
      <div className="px-3 py-2.5 border-b border-gray-800">
        <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
          Agents ({agents.length})
        </span>
      </div>

      {/* Agent list */}
      <div className="flex-1 overflow-y-auto">
        {agents.length === 0 ? (
          <div className="px-3 py-6 text-center text-gray-500 text-sm">No agents defined</div>
        ) : (
          agents.map((agent) => {
            const status = getAgentStatus(agent.id, allRuns)
            const isSelected = agent.id === selectedId
            return (
              <button
                key={agent.id}
                onClick={() => onSelect(agent.id)}
                className={`w-full text-left px-3 py-2.5 flex flex-col gap-1.5 border-b border-gray-800/50 transition-colors ${
                  isSelected
                    ? 'bg-purple-900/30 border-l-2 border-l-purple-500'
                    : 'hover:bg-gray-800/60 border-l-2 border-l-transparent'
                }`}
              >
                <div className="flex items-center gap-2 min-w-0">
                  <StatusDot status={status} />
                  <span
                    className={`text-sm font-medium truncate ${isSelected ? 'text-purple-300' : 'text-gray-200'}`}
                  >
                    {agent.name}
                  </span>
                </div>
                {agent.description && (
                  <p className="text-xs text-gray-500 truncate pl-4">{agent.description}</p>
                )}
                <div className="pl-4">
                  <Sparkline agentId={agent.id} allRuns={allRuns} />
                </div>
              </button>
            )
          })
        )}
      </div>

      {/* New Agent button */}
      <div className="p-3 border-t border-gray-800">
        <button
          onClick={onNew}
          className="w-full bg-purple-600 hover:bg-purple-700 text-white text-sm font-medium py-2 px-3 rounded-lg transition-colors"
        >
          + New Agent
        </button>
      </div>
    </div>
  )
}
