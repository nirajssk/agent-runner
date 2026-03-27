import { useState, useEffect, useRef, useCallback } from 'react'
import type { AgentRun, MessageContent, ContentBlock } from '../types'

interface Props {
  runId: string | null
  run: AgentRun | null
  onStop: () => void
  onRerun: () => void
}

type WsStatus = 'connecting' | 'connected' | 'disconnected'

function formatDuration(startedAt: string, finishedAt?: string): string {
  const start = new Date(startedAt).getTime()
  const end = finishedAt ? new Date(finishedAt).getTime() : Date.now()
  const seconds = Math.floor((end - start) / 1000)
  if (seconds < 60) return `${seconds}s`
  const mins = Math.floor(seconds / 60)
  const secs = seconds % 60
  return `${mins}m ${secs}s`
}

function ToolUseBlock({ name, input }: { name: string; input: Record<string, unknown> }) {
  const [expanded, setExpanded] = useState(false)
  const inputStr = JSON.stringify(input, null, 2)
  const shortInput =
    inputStr.length > 120 ? inputStr.slice(0, 120) + '…' : inputStr

  return (
    <div className="font-mono text-xs bg-gray-800 rounded px-3 py-2 text-purple-300 border border-gray-700">
      <button
        className="flex items-center gap-2 w-full text-left"
        onClick={() => setExpanded((e) => !e)}
      >
        <span className="text-purple-400">🔧</span>
        <span className="font-semibold text-purple-200">{name}</span>
        <span className="text-gray-500 ml-auto">{expanded ? '▲' : '▼'}</span>
      </button>
      {expanded ? (
        <pre className="mt-2 text-gray-300 whitespace-pre-wrap break-all overflow-x-auto text-[11px]">
          {inputStr}
        </pre>
      ) : (
        <p className="mt-1 text-gray-400 truncate">{shortInput}</p>
      )}
    </div>
  )
}

function ContentBlockView({ block }: { block: ContentBlock }) {
  if (block.type === 'text') {
    return (
      <p className="text-gray-200 text-sm whitespace-pre-wrap leading-relaxed">{block.text}</p>
    )
  }
  if (block.type === 'tool_use') {
    return <ToolUseBlock name={block.name} input={block.input} />
  }
  return (
    <pre className="text-gray-500 text-xs font-mono bg-gray-800 rounded px-2 py-1 whitespace-pre-wrap">
      {block.repr}
    </pre>
  )
}

function MessageView({ msg }: { msg: MessageContent }) {
  if (msg.type === 'system') return null

  if (msg.type === 'assistant') {
    return (
      <div className="flex flex-col gap-2">
        {msg.content.map((block, i) => (
          <ContentBlockView key={i} block={block} />
        ))}
        {(msg.usage.input_tokens !== undefined || msg.usage.output_tokens !== undefined) && (
          <p className="text-[11px] text-gray-600 font-mono">
            tokens: in={msg.usage.input_tokens ?? 0} out={msg.usage.output_tokens ?? 0}
          </p>
        )}
      </div>
    )
  }

  if (msg.type === 'result') {
    return (
      <div className="border border-green-700 bg-green-950/50 rounded-lg p-3">
        <p className="text-xs font-semibold text-green-500 mb-1 uppercase tracking-wide">
          Result — {msg.stop_reason}
        </p>
        <p className="text-green-300 text-sm whitespace-pre-wrap">{msg.result}</p>
      </div>
    )
  }

  if (msg.type === 'run_status') {
    if (msg.status === 'failed' && msg.error) {
      return (
        <div className="border border-red-700 bg-red-950/50 rounded-lg p-3">
          <p className="text-xs font-semibold text-red-400 mb-1 uppercase tracking-wide">Error</p>
          <p className="text-red-300 text-sm font-mono whitespace-pre-wrap">{msg.error}</p>
        </div>
      )
    }
    return (
      <p className="text-xs text-gray-500 font-mono">
        status: {msg.status}
      </p>
    )
  }

  if (msg.type === 'rate_limit') {
    return (
      <div className="border border-yellow-700 bg-yellow-950/50 rounded-lg p-2">
        <p className="text-xs text-yellow-400">⏳ Rate limited — waiting…</p>
      </div>
    )
  }

  if (msg.type === 'unknown') {
    return (
      <pre className="text-gray-500 text-xs font-mono bg-gray-800 rounded px-2 py-1 whitespace-pre-wrap">
        {msg.repr}
      </pre>
    )
  }

  return null
}

function RunStatusBadge({ status }: { status: AgentRun['status'] }) {
  const config: Record<AgentRun['status'], { label: string; className: string }> = {
    running: { label: 'Running', className: 'text-yellow-400 bg-yellow-400/10' },
    pending: { label: 'Pending', className: 'text-yellow-400 bg-yellow-400/10' },
    done: { label: 'Done', className: 'text-green-400 bg-green-400/10' },
    failed: { label: 'Failed', className: 'text-red-400 bg-red-400/10' },
    cancelled: { label: 'Cancelled', className: 'text-gray-400 bg-gray-400/10' },
  }
  const { label, className } = config[status]
  return (
    <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${className}`}>{label}</span>
  )
}

function LiveElapsed({ startedAt }: { startedAt: string }) {
  const [elapsed, setElapsed] = useState(() => formatDuration(startedAt))
  useEffect(() => {
    const id = setInterval(() => setElapsed(formatDuration(startedAt)), 1000)
    return () => clearInterval(id)
  }, [startedAt])
  return <span>{elapsed}</span>
}

export default function LiveStream({ runId, run, onStop, onRerun }: Props) {
  const [messages, setMessages] = useState<MessageContent[]>([])
  const [wsStatus, setWsStatus] = useState<WsStatus>('disconnected')
  const bottomRef = useRef<HTMLDivElement>(null)
  const wsRef = useRef<WebSocket | null>(null)

  const connect = useCallback((id: string) => {
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
    setMessages([])
    setWsStatus('connecting')

    const ws = new WebSocket(`ws://localhost:8000/ws/runs/${id}`)
    wsRef.current = ws

    ws.onopen = () => setWsStatus('connected')

    ws.onmessage = (event: MessageEvent<string>) => {
      try {
        const data = JSON.parse(event.data) as MessageContent
        setMessages((prev) => [...prev, data])
      } catch {
        // ignore parse errors
      }
    }

    ws.onerror = () => setWsStatus('disconnected')
    ws.onclose = () => setWsStatus('disconnected')
  }, [])

  useEffect(() => {
    if (!runId) {
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
      setMessages([])
      setWsStatus('disconnected')
      return
    }
    connect(runId)
    return () => {
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [runId, connect])

  // Auto-scroll to bottom
  useEffect(() => {
    if (bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages])

  if (!runId || !run) {
    return (
      <div className="flex flex-col w-80 flex-shrink-0 bg-gray-950 items-center justify-center">
        <p className="text-gray-500 text-sm">Select a run to view details</p>
      </div>
    )
  }

  const totalTokens = run.total_input_tokens + run.total_output_tokens
  const isActive = run.status === 'running' || run.status === 'pending'

  const wsIndicator = {
    connecting: 'text-yellow-500',
    connected: 'text-green-500',
    disconnected: 'text-gray-600',
  }[wsStatus]

  return (
    <div className="flex flex-col w-80 flex-shrink-0 bg-gray-950 border-l border-gray-800 overflow-hidden">
      {/* Header */}
      <div className="px-3 py-2.5 border-b border-gray-800 flex-shrink-0">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <span
              className={`w-2 h-2 rounded-full flex-shrink-0 ${wsIndicator} bg-current`}
              title={`WS: ${wsStatus}`}
            />
            <span className="text-xs font-mono text-gray-400 truncate">
              {run.id.slice(0, 8)}…
            </span>
          </div>
          <RunStatusBadge status={run.status} />
        </div>
        <div className="mt-1 text-xs text-gray-500">
          {isActive ? (
            <LiveElapsed startedAt={run.started_at} />
          ) : (
            <span>{formatDuration(run.started_at, run.finished_at)}</span>
          )}
        </div>
        {run.prompt && (
          <p className="mt-1.5 text-xs text-gray-400 line-clamp-2">{run.prompt}</p>
        )}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-3 py-3 flex flex-col gap-3">
        {messages.length === 0 ? (
          <p className="text-gray-600 text-xs text-center mt-4">
            {wsStatus === 'connecting' ? 'Connecting…' : 'No messages'}
          </p>
        ) : (
          messages.map((msg, i) => <MessageView key={i} msg={msg} />)
        )}
        <div ref={bottomRef} />
      </div>

      {/* Footer */}
      <div className="px-3 py-2.5 border-t border-gray-800 flex-shrink-0">
        <div className="flex items-center justify-between mb-2">
          <div className="text-xs text-gray-500 font-mono">
            <span className="text-gray-400">↑</span> {run.total_input_tokens.toLocaleString()}
            {' '}
            <span className="text-gray-400">↓</span> {run.total_output_tokens.toLocaleString()}
            {' '}
            <span className="text-gray-500">={totalTokens >= 1000 ? `${(totalTokens / 1000).toFixed(1)}k` : totalTokens}</span>
          </div>
        </div>
        <div className="flex gap-2">
          <button
            onClick={onRerun}
            className="flex-1 bg-purple-600 hover:bg-purple-700 text-white text-xs font-medium py-1.5 px-2 rounded-lg transition-colors"
          >
            ▶ Re-run
          </button>
          {isActive && (
            <button
              onClick={onStop}
              className="flex-1 bg-gray-700 hover:bg-red-900 text-gray-200 hover:text-red-200 text-xs font-medium py-1.5 px-2 rounded-lg transition-colors"
            >
              ⏹ Stop
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
