import { useState, useEffect, useRef } from 'react'
import type { Agent, AgentRun } from '../types'

interface Props {
  runs: AgentRun[]
  selectedId: string | null
  agent: Agent | null
  onSelect: (id: string) => void
  onTrigger: () => void
}

function formatDuration(startedAt: string, finishedAt?: string): string {
  const start = new Date(startedAt).getTime()
  const end = finishedAt ? new Date(finishedAt).getTime() : Date.now()
  const seconds = Math.floor((end - start) / 1000)
  if (seconds < 60) return `${seconds}s`
  const mins = Math.floor(seconds / 60)
  const secs = seconds % 60
  return `${mins}m ${secs}s`
}

function formatTokens(total: number): string {
  if (total >= 1000) return `${(total / 1000).toFixed(1)}k`
  return String(total)
}

function formatTime(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function StatusBadge({ status }: { status: AgentRun['status'] }) {
  const config: Record<AgentRun['status'], { icon: string; className: string }> = {
    running: { icon: '◌', className: 'text-yellow-400 animate-spin' },
    pending: { icon: '◌', className: 'text-yellow-400' },
    done: { icon: '✓', className: 'text-green-400' },
    failed: { icon: '✗', className: 'text-red-400' },
    cancelled: { icon: '—', className: 'text-gray-500' },
  }
  const { icon, className } = config[status]
  return (
    <span className={`font-mono text-sm font-bold ${className}`} title={status}>
      {icon}
    </span>
  )
}

function LiveDuration({ startedAt }: { startedAt: string }) {
  const [elapsed, setElapsed] = useState(() => formatDuration(startedAt))

  useEffect(() => {
    const id = setInterval(() => setElapsed(formatDuration(startedAt)), 1000)
    return () => clearInterval(id)
  }, [startedAt])

  return <span className="text-yellow-400">{elapsed}</span>
}

export default function RunList({ runs, selectedId, agent, onSelect, onTrigger }: Props) {
  const doneCount = runs.filter((r) => r.status === 'done').length
  const totalCount = runs.length
  const successPct = totalCount > 0 ? Math.round((doneCount / totalCount) * 100) : 0

  const tableBodyRef = useRef<HTMLDivElement>(null)

  return (
    <div className="flex flex-col flex-1 border-r border-gray-800 bg-gray-900 overflow-hidden min-w-0">
      {/* Panel header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-800 flex-shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Runs</span>
          {agent && (
            <span className="text-sm text-purple-300 font-medium truncate">— {agent.name}</span>
          )}
        </div>
        {agent && (
          <button
            onClick={onTrigger}
            className="flex items-center gap-1.5 bg-purple-600 hover:bg-purple-700 text-white text-xs font-medium py-1.5 px-3 rounded-lg transition-colors flex-shrink-0"
          >
            <span>▶</span>
            <span>Run</span>
          </button>
        )}
      </div>

      {!agent ? (
        <div className="flex-1 flex items-center justify-center text-gray-500 text-sm">
          Select an agent to view runs
        </div>
      ) : (
        <>
          {/* Table header */}
          <div className="grid grid-cols-[28px_40px_80px_90px_70px] gap-2 px-4 py-2 border-b border-gray-800 flex-shrink-0">
            {['#', 'Status', 'Started', 'Duration', 'Tokens'].map((h) => (
              <span key={h} className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                {h}
              </span>
            ))}
          </div>

          {/* Table rows */}
          <div ref={tableBodyRef} className="flex-1 overflow-y-auto">
            {runs.length === 0 ? (
              <div className="px-4 py-8 text-center text-gray-500 text-sm">No runs yet</div>
            ) : (
              runs.map((run, idx) => {
                const isSelected = run.id === selectedId
                return (
                  <button
                    key={run.id}
                    onClick={() => onSelect(run.id)}
                    className={`w-full text-left grid grid-cols-[28px_40px_80px_90px_70px] gap-2 px-4 py-2.5 border-b border-gray-800/50 transition-colors ${
                      isSelected
                        ? 'bg-purple-900/20 border-l-2 border-l-purple-500'
                        : 'hover:bg-gray-800/50 border-l-2 border-l-transparent'
                    }`}
                  >
                    <span className="text-gray-500 text-xs font-mono self-center">
                      {runs.length - idx}
                    </span>
                    <span className="self-center">
                      <StatusBadge status={run.status} />
                    </span>
                    <span className="text-gray-300 text-xs self-center font-mono">
                      {formatTime(run.started_at)}
                    </span>
                    <span className="text-gray-300 text-xs self-center">
                      {run.status === 'running' || run.status === 'pending' ? (
                        <LiveDuration startedAt={run.started_at} />
                      ) : (
                        formatDuration(run.started_at, run.finished_at)
                      )}
                    </span>
                    <span className="text-gray-300 text-xs self-center font-mono">
                      {formatTokens(run.total_input_tokens + run.total_output_tokens)}
                    </span>
                  </button>
                )
              })
            )}
          </div>

          {/* Footer: success rate */}
          {totalCount > 0 && (
            <div className="px-4 py-2.5 border-t border-gray-800 flex-shrink-0">
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-400">
                  {doneCount}/{totalCount} ok
                </span>
                <div className="flex-1 h-1.5 bg-gray-700 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-green-500 rounded-full transition-all"
                    style={{ width: `${successPct}%` }}
                  />
                </div>
                <span className="text-xs text-gray-400">{successPct}%</span>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
