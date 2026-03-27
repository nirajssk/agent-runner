import { useState, useEffect, useCallback, useRef } from 'react'
import type { Agent, AgentRun } from './types'
import { api } from './api'
import AgentList from './components/AgentList'
import RunList from './components/RunList'
import LiveStream from './components/LiveStream'
import NewAgentModal from './components/NewAgentModal'

type StatusFilter = 'all' | 'running' | 'done' | 'failed'

const FILTER_OPTIONS: { label: string; value: StatusFilter }[] = [
  { label: 'All', value: 'all' },
  { label: 'Running', value: 'running' },
  { label: 'Done', value: 'done' },
  { label: 'Failed', value: 'failed' },
]

export default function App() {
  const [agents, setAgents] = useState<Agent[]>([])
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null)
  // allRuns holds runs for the currently selected agent
  const [runs, setRuns] = useState<AgentRun[]>([])
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [showNewAgent, setShowNewAgent] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)

  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Load agents on mount
  useEffect(() => {
    api
      .getAgents()
      .then((data) => setAgents(data))
      .catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : 'Failed to load agents'
        setLoadError(msg)
      })
  }, [])

  // Load runs when selected agent changes
  const loadRuns = useCallback((agentId: string) => {
    api
      .getRuns(agentId)
      .then((data) => {
        // Most recent first
        const sorted = [...data].sort(
          (a, b) => new Date(b.started_at).getTime() - new Date(a.started_at).getTime(),
        )
        setRuns(sorted)
      })
      .catch(() => setRuns([]))
  }, [])

  useEffect(() => {
    if (!selectedAgentId) {
      setRuns([])
      setSelectedRunId(null)
      return
    }
    loadRuns(selectedAgentId)
  }, [selectedAgentId, loadRuns])

  // Poll runs while any run is active
  useEffect(() => {
    const hasActive = runs.some((r) => r.status === 'running' || r.status === 'pending')

    if (hasActive && selectedAgentId) {
      if (!pollIntervalRef.current) {
        pollIntervalRef.current = setInterval(() => {
          if (selectedAgentId) loadRuns(selectedAgentId)
        }, 3000)
      }
    } else {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current)
        pollIntervalRef.current = null
      }
    }

    return () => {
      // Cleanup is handled above; don't clear here to avoid restart loops
    }
  }, [runs, selectedAgentId, loadRuns])

  // Cleanup poll on unmount
  useEffect(() => {
    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current)
    }
  }, [])

  const selectedAgent = agents.find((a) => a.id === selectedAgentId) ?? null
  const selectedRun = runs.find((r) => r.id === selectedRunId) ?? null

  const filteredRuns =
    statusFilter === 'all'
      ? runs
      : runs.filter((r) => {
          if (statusFilter === 'running') return r.status === 'running' || r.status === 'pending'
          return r.status === statusFilter
        })

  async function handleTrigger() {
    if (!selectedAgentId) return
    try {
      const run = await api.startRun(selectedAgentId)
      setRuns((prev) => [run, ...prev])
      setSelectedRunId(run.id)
    } catch (err) {
      console.error('Failed to start run', err)
    }
  }

  async function handleStop() {
    if (!selectedRunId) return
    try {
      await api.stopRun(selectedRunId)
      if (selectedAgentId) loadRuns(selectedAgentId)
    } catch (err) {
      console.error('Failed to stop run', err)
    }
  }

  async function handleRerun() {
    if (!selectedAgentId) return
    try {
      const run = await api.startRun(selectedAgentId)
      setRuns((prev) => [run, ...prev])
      setSelectedRunId(run.id)
    } catch (err) {
      console.error('Failed to re-run', err)
    }
  }

  function handleAgentCreated(agent: Agent) {
    setAgents((prev) => [...prev, agent])
    setSelectedAgentId(agent.id)
    setShowNewAgent(false)
  }

  return (
    <div className="h-screen flex flex-col bg-gray-950 text-gray-100 overflow-hidden">
      {/* Header */}
      <header className="flex items-center justify-between px-4 py-3 border-b border-gray-800 bg-gray-900 flex-shrink-0">
        <div className="flex items-center gap-2">
          <span className="font-bold text-lg text-purple-400">Claude Agent Runner</span>
          {loadError && (
            <span className="text-xs text-red-400 bg-red-900/30 px-2 py-0.5 rounded">
              {loadError}
            </span>
          )}
        </div>
        <div className="flex gap-1">
          {FILTER_OPTIONS.map(({ label, value }) => {
            const isActive = statusFilter === value
            const activeColors: Record<StatusFilter, string> = {
              all: 'bg-purple-600 text-white',
              running: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/50',
              done: 'bg-green-500/20 text-green-300 border-green-500/50',
              failed: 'bg-red-500/20 text-red-300 border-red-500/50',
            }
            return (
              <button
                key={value}
                onClick={() => setStatusFilter(value)}
                className={`text-xs font-medium px-3 py-1.5 rounded-lg border transition-colors ${
                  isActive
                    ? activeColors[value]
                    : 'bg-transparent text-gray-400 border-gray-700 hover:border-gray-600 hover:text-gray-300'
                }`}
              >
                {label}
              </button>
            )
          })}
        </div>
      </header>

      {/* 3-panel body */}
      <div className="flex flex-1 overflow-hidden">
        <AgentList
          agents={agents}
          selectedId={selectedAgentId}
          allRuns={runs}
          onSelect={(id) => {
            setSelectedAgentId(id)
            setSelectedRunId(null)
          }}
          onNew={() => setShowNewAgent(true)}
        />

        <RunList
          runs={filteredRuns}
          selectedId={selectedRunId}
          agent={selectedAgent}
          onSelect={setSelectedRunId}
          onTrigger={handleTrigger}
        />

        <LiveStream
          runId={selectedRunId}
          run={selectedRun}
          onStop={handleStop}
          onRerun={handleRerun}
        />
      </div>

      {showNewAgent && (
        <NewAgentModal
          onClose={() => setShowNewAgent(false)}
          onCreate={handleAgentCreated}
        />
      )}
    </div>
  )
}
