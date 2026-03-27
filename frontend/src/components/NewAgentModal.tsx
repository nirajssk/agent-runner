import { useState } from 'react'
import type { Agent, AgentCreateForm } from '../types'
import { api } from '../api'

interface Props {
  onClose: () => void
  onCreate: (agent: Agent) => void
}

const ALL_TOOLS = ['Read', 'Write', 'Edit', 'Bash', 'Glob', 'Grep', 'WebSearch', 'WebFetch']
const DEFAULT_TOOLS = ['Read', 'Glob', 'Grep']

export default function NewAgentModal({ onClose, onCreate }: Props) {
  const [form, setForm] = useState<AgentCreateForm>({
    name: '',
    description: '',
    prompt: '',
    tools: DEFAULT_TOOLS,
    max_turns: 20,
    permission_mode: 'acceptEdits',
  })
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function toggleTool(tool: string) {
    setForm((prev) => ({
      ...prev,
      tools: prev.tools.includes(tool)
        ? prev.tools.filter((t) => t !== tool)
        : [...prev.tools, tool],
    }))
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!form.name.trim() || !form.prompt.trim()) {
      setError('Name and prompt are required.')
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      const agent = await api.createAgent(form)
      onCreate(agent)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create agent')
      setSubmitting(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 max-w-2xl w-full mx-4 max-h-[90vh] flex flex-col shadow-2xl">
        {/* Modal header */}
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-lg font-bold text-gray-100">New Agent</h2>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-gray-300 text-xl leading-none w-8 h-8 flex items-center justify-center rounded hover:bg-gray-800 transition-colors"
          >
            ×
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4 overflow-y-auto flex-1">
          {/* Name */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Name <span className="text-red-400">*</span>
            </label>
            <input
              type="text"
              value={form.name}
              onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))}
              placeholder="e.g. Code Reviewer"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:border-purple-500 transition-colors"
            />
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">Description</label>
            <input
              type="text"
              value={form.description}
              onChange={(e) => setForm((p) => ({ ...p, description: e.target.value }))}
              placeholder="Optional short description"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:border-purple-500 transition-colors"
            />
          </div>

          {/* Prompt */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Prompt <span className="text-red-400">*</span>
            </label>
            <textarea
              value={form.prompt}
              onChange={(e) => setForm((p) => ({ ...p, prompt: e.target.value }))}
              placeholder="Describe what this agent should do…"
              rows={6}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:border-purple-500 transition-colors resize-y font-mono"
            />
          </div>

          {/* Tools */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Tools</label>
            <div className="flex flex-wrap gap-2">
              {ALL_TOOLS.map((tool) => {
                const checked = form.tools.includes(tool)
                return (
                  <button
                    key={tool}
                    type="button"
                    onClick={() => toggleTool(tool)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                      checked
                        ? 'bg-purple-600/30 border-purple-500 text-purple-300'
                        : 'bg-gray-800 border-gray-700 text-gray-400 hover:border-gray-600'
                    }`}
                  >
                    {checked ? '✓ ' : ''}{tool}
                  </button>
                )
              })}
            </div>
          </div>

          {/* Max turns + Permission mode row */}
          <div className="flex gap-4">
            {/* Max turns */}
            <div className="flex-1">
              <label className="block text-sm font-medium text-gray-300 mb-1">Max Turns</label>
              <input
                type="number"
                min={1}
                max={100}
                value={form.max_turns}
                onChange={(e) =>
                  setForm((p) => ({ ...p, max_turns: parseInt(e.target.value, 10) || 1 }))
                }
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-purple-500 transition-colors"
              />
            </div>

            {/* Permission mode */}
            <div className="flex-1">
              <label className="block text-sm font-medium text-gray-300 mb-1">
                Permission Mode
              </label>
              <div className="relative">
                <select
                  value={form.permission_mode}
                  onChange={(e) => setForm((p) => ({ ...p, permission_mode: e.target.value }))}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-purple-500 transition-colors appearance-none"
                >
                  <option value="acceptEdits">acceptEdits</option>
                  <option value="bypassPermissions">bypassPermissions</option>
                </select>
                {form.permission_mode === 'bypassPermissions' && (
                  <span
                    className="absolute right-8 top-1/2 -translate-y-1/2 text-yellow-400 text-sm"
                    title="Bypasses all permission checks — use with caution"
                  >
                    ⚠
                  </span>
                )}
              </div>
              {form.permission_mode === 'bypassPermissions' && (
                <p className="mt-1 text-xs text-yellow-500">
                  Bypasses all permission checks. Use with caution.
                </p>
              )}
            </div>
          </div>

          {/* Error */}
          {error && (
            <div className="border border-red-700 bg-red-950/50 rounded-lg p-3">
              <p className="text-sm text-red-400">{error}</p>
            </div>
          )}

          {/* Footer buttons */}
          <div className="flex gap-3 justify-end pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm text-gray-400 hover:text-gray-200 bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="px-4 py-2 text-sm font-medium text-white bg-purple-600 hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg transition-colors"
            >
              {submitting ? 'Creating…' : 'Create Agent'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
