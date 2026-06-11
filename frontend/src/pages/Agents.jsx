import { useCallback, useEffect, useState } from 'react'
import * as api from '../api/client'

const TABS = ['Fleet', 'Policies', 'Enrollment Keys']

const DEFAULT_POLICY_FORM = {
  name: '',
  description: '',
  checkin_interval_seconds: 3600,
  jitter_seconds: 300,
  command_timeout_seconds: 15,
  enabled_commands: {
    ip_neigh: true,
    ss_tunap: true,
    ip_addr: true,
    ip_route: true,
  },
  max_report_bytes: 262144,
  is_active: true,
}

const DEFAULT_ENROLLMENT_KEY_FORM = {
  name: '',
  description: '',
  default_policy_id: '',
  auto_approve: false,
  is_active: true,
  expires_at: '',
  max_registrations: '',
}

function formatDate(value) {
  return value ? new Date(value).toLocaleString() : 'Never'
}

function formatRelative(value) {
  if (!value) return 'Never'
  const diffMs = Date.now() - new Date(value).getTime()
  const diffMinutes = Math.max(0, Math.round(diffMs / 60000))
  if (diffMinutes < 1) return 'Just now'
  if (diffMinutes < 60) return `${diffMinutes}m ago`
  const diffHours = Math.round(diffMinutes / 60)
  if (diffHours < 48) return `${diffHours}h ago`
  const diffDays = Math.round(diffHours / 24)
  return `${diffDays}d ago`
}

function toDateTimeLocal(value) {
  if (!value) return ''
  return new Date(value).toISOString().slice(0, 16)
}

function fromDateTimeLocal(value) {
  return value ? new Date(value).toISOString() : null
}

function normalizeNumber(value) {
  if (value === '' || value === null || value === undefined) {
    return null
  }
  const parsed = Number(value)
  return Number.isNaN(parsed) ? null : parsed
}

function freshnessForAgent(agent) {
  const state = agent.health?.state || 'never_seen'
  const labels = {
    healthy: 'Healthy',
    stale: 'Stale',
    offline: 'Offline',
    never_seen: 'Never seen',
  }
  const tones = {
    healthy: 'green',
    stale: 'amber',
    offline: 'red',
    never_seen: 'slate',
  }
  return { label: labels[state] || state, tone: tones[state] || 'slate' }
}

function collectionRequestLabel(agent) {
  if (!agent?.collection_requested_at) return 'None pending'
  const requestedAt = new Date(agent.collection_requested_at).getTime()
  const fulfilledAt = agent.collection_request_fulfilled_at
    ? new Date(agent.collection_request_fulfilled_at).getTime()
    : null
  if (!fulfilledAt || requestedAt > fulfilledAt) {
    return `Pending since ${formatDate(agent.collection_requested_at)}`
  }
  return `Fulfilled ${formatDate(agent.collection_request_fulfilled_at)}`
}

function stateBadge(state) {
  const tones = {
    active: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300',
    pending: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
    rejected: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
    revoked: 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200',
  }
  return tones[state] || tones.revoked
}

function freshnessBadge(tone) {
  const tones = {
    green: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300',
    amber: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
    red: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
    slate: 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200',
  }
  return tones[tone] || tones.slate
}

function TabButton({ active, children, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
        active
          ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/20'
          : 'bg-white text-gray-700 hover:bg-gray-100 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700'
      }`}
    >
      {children}
    </button>
  )
}

function PolicyForm({ form, onChange, onToggleCommand, onSubmit, onReset, saving, submitLabel }) {
  return (
    <form
      className="space-y-4"
      onSubmit={(event) => {
        event.preventDefault()
        onSubmit()
      }}
    >
      <div className="grid gap-4 md:grid-cols-2">
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Name</label>
          <input className="input" value={form.name} onChange={(event) => onChange('name', event.target.value)} required />
        </div>
        <div className="flex items-end">
          <label className="flex items-center gap-2 pb-2 text-sm text-gray-700 dark:text-gray-300">
            <input type="checkbox" checked={form.is_active} onChange={(event) => onChange('is_active', event.target.checked)} />
            Active policy
          </label>
        </div>
        <div className="md:col-span-2">
          <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Description</label>
          <textarea
            className="input min-h-24"
            value={form.description}
            onChange={(event) => onChange('description', event.target.value)}
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Check-in Interval (seconds)</label>
          <input
            className="input"
            type="number"
            min="60"
            max="86400"
            value={form.checkin_interval_seconds}
            onChange={(event) => onChange('checkin_interval_seconds', Number(event.target.value))}
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Jitter (seconds)</label>
          <input
            className="input"
            type="number"
            min="0"
            max="3600"
            value={form.jitter_seconds}
            onChange={(event) => onChange('jitter_seconds', Number(event.target.value))}
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Command Timeout (seconds)</label>
          <input
            className="input"
            type="number"
            min="1"
            max="300"
            value={form.command_timeout_seconds}
            onChange={(event) => onChange('command_timeout_seconds', Number(event.target.value))}
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Max Report Bytes</label>
          <input
            className="input"
            type="number"
            min="16384"
            max={10 * 1024 * 1024}
            value={form.max_report_bytes}
            onChange={(event) => onChange('max_report_bytes', Number(event.target.value))}
          />
        </div>
      </div>

      <div>
        <p className="mb-2 text-sm font-medium text-gray-700 dark:text-gray-300">Enabled Commands</p>
        <div className="grid gap-2 md:grid-cols-2">
          {Object.entries(form.enabled_commands).map(([command, enabled]) => (
            <label
              key={command}
              className="flex items-center justify-between rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-700 dark:border-gray-700 dark:bg-gray-900/40 dark:text-gray-300"
            >
              <span className="font-mono text-xs">{command}</span>
              <input type="checkbox" checked={enabled} onChange={() => onToggleCommand(command)} />
            </label>
          ))}
        </div>
      </div>

      <div className="flex gap-3">
        <button type="submit" className="btn btn-primary" disabled={saving}>
          {saving ? 'Saving...' : submitLabel}
        </button>
        <button type="button" className="btn btn-secondary" onClick={onReset}>
          Reset
        </button>
      </div>
    </form>
  )
}

function EnrollmentKeyForm({
  form,
  policies,
  onChange,
  onSubmit,
  onReset,
  saving,
  submitLabel,
}) {
  return (
    <form
      className="space-y-4"
      onSubmit={(event) => {
        event.preventDefault()
        onSubmit()
      }}
    >
      <div className="grid gap-4 md:grid-cols-2">
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Name</label>
          <input className="input" value={form.name} onChange={(event) => onChange('name', event.target.value)} required />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Default Policy</label>
          <select className="select" value={form.default_policy_id} onChange={(event) => onChange('default_policy_id', event.target.value)}>
            <option value="">No default policy</option>
            {policies.map((policy) => (
              <option key={policy.id} value={String(policy.id)}>
                {policy.name}
              </option>
            ))}
          </select>
        </div>
        <div className="md:col-span-2">
          <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Description</label>
          <textarea
            className="input min-h-24"
            value={form.description}
            onChange={(event) => onChange('description', event.target.value)}
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Expires At</label>
          <input
            className="input"
            type="datetime-local"
            value={form.expires_at}
            onChange={(event) => onChange('expires_at', event.target.value)}
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Max Registrations</label>
          <input
            className="input"
            type="number"
            min="1"
            max="100000"
            value={form.max_registrations}
            onChange={(event) => onChange('max_registrations', event.target.value)}
            placeholder="Unlimited"
          />
        </div>
        <div className="flex items-end gap-6 md:col-span-2">
          <label className="flex items-center gap-2 pb-2 text-sm text-gray-700 dark:text-gray-300">
            <input type="checkbox" checked={form.auto_approve} onChange={(event) => onChange('auto_approve', event.target.checked)} />
            Auto-approve agents
          </label>
          <label className="flex items-center gap-2 pb-2 text-sm text-gray-700 dark:text-gray-300">
            <input type="checkbox" checked={form.is_active} onChange={(event) => onChange('is_active', event.target.checked)} />
            Key active
          </label>
        </div>
      </div>

      <div className="flex gap-3">
        <button type="submit" className="btn btn-primary" disabled={saving}>
          {saving ? 'Saving...' : submitLabel}
        </button>
        <button type="button" className="btn btn-secondary" onClick={onReset}>
          Reset
        </button>
      </div>
    </form>
  )
}

export default function Agents() {
  const [activeTab, setActiveTab] = useState(TABS[0])
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [revealedEnrollmentKey, setRevealedEnrollmentKey] = useState('')
  const [revealedApiKey, setRevealedApiKey] = useState('')

  const [agents, setAgents] = useState([])
  const [loadingAgents, setLoadingAgents] = useState(true)
  const [agentFilters, setAgentFilters] = useState({
    enrollment_state: '',
    is_active: '',
  })
  const [selectedAgentId, setSelectedAgentId] = useState(null)
  const [agentDraft, setAgentDraft] = useState({
    display_name: '',
    site_name: '',
    policy_id: '',
  })
  const [savingAgent, setSavingAgent] = useState(false)

  const [agentCheckins, setAgentCheckins] = useState([])
  const [loadingCheckins, setLoadingCheckins] = useState(false)

  const [policies, setPolicies] = useState([])
  const [loadingPolicies, setLoadingPolicies] = useState(true)
  const [savingPolicy, setSavingPolicy] = useState(false)
  const [editingPolicyId, setEditingPolicyId] = useState(null)
  const [policyForm, setPolicyForm] = useState(DEFAULT_POLICY_FORM)

  const [enrollmentKeys, setEnrollmentKeys] = useState([])
  const [loadingEnrollmentKeys, setLoadingEnrollmentKeys] = useState(true)
  const [savingEnrollmentKey, setSavingEnrollmentKey] = useState(false)
  const [editingEnrollmentKeyId, setEditingEnrollmentKeyId] = useState(null)
  const [enrollmentKeyForm, setEnrollmentKeyForm] = useState(DEFAULT_ENROLLMENT_KEY_FORM)

  const showSuccess = useCallback((message) => {
    setSuccess(message)
    window.setTimeout(() => setSuccess(''), 5000)
  }, [])

  const resetPolicyForm = useCallback(() => {
    setEditingPolicyId(null)
    setPolicyForm(DEFAULT_POLICY_FORM)
  }, [])

  const resetEnrollmentKeyForm = useCallback(() => {
    setEditingEnrollmentKeyId(null)
    setEnrollmentKeyForm(DEFAULT_ENROLLMENT_KEY_FORM)
  }, [])

  const fetchPolicies = useCallback(async () => {
    try {
      setLoadingPolicies(true)
      const response = await api.getAgentPolicies({ limit: 200 })
      setPolicies(response.items || [])
    } catch (err) {
      setError(err.message)
    } finally {
      setLoadingPolicies(false)
    }
  }, [])

  const fetchEnrollmentKeys = useCallback(async () => {
    try {
      setLoadingEnrollmentKeys(true)
      const response = await api.getAgentEnrollmentKeys({ limit: 200 })
      setEnrollmentKeys(response.items || [])
    } catch (err) {
      setError(err.message)
    } finally {
      setLoadingEnrollmentKeys(false)
    }
  }, [])

  const fetchAgents = useCallback(async () => {
    try {
      setLoadingAgents(true)
      const response = await api.getAgents({
        limit: 200,
        enrollment_state: agentFilters.enrollment_state || null,
        is_active: agentFilters.is_active === '' ? null : agentFilters.is_active,
      })
      const items = response.items || []
      setAgents(items)
      if (!items.length) {
        setSelectedAgentId(null)
        return
      }
      setSelectedAgentId((current) => {
        if (current && items.some((agent) => agent.id === current)) {
          return current
        }
        return items[0].id
      })
    } catch (err) {
      setError(err.message)
    } finally {
      setLoadingAgents(false)
    }
  }, [agentFilters])

  const fetchCheckins = useCallback(async (agentId) => {
    if (!agentId) {
      setAgentCheckins([])
      return
    }
    try {
      setLoadingCheckins(true)
      const response = await api.getAgentCheckins(agentId, { limit: 10 })
      setAgentCheckins(response.items || [])
    } catch (err) {
      setError(err.message)
    } finally {
      setLoadingCheckins(false)
    }
  }, [])

  useEffect(() => {
    fetchPolicies()
    fetchEnrollmentKeys()
  }, [fetchPolicies, fetchEnrollmentKeys])

  useEffect(() => {
    fetchAgents()
  }, [fetchAgents])

  const selectedAgent = agents.find((agent) => agent.id === selectedAgentId) || null

  useEffect(() => {
    if (!selectedAgent) {
      setAgentDraft({
        display_name: '',
        site_name: '',
        policy_id: '',
      })
      setAgentCheckins([])
      return
    }

    setAgentDraft({
      display_name: selectedAgent.display_name || '',
      site_name: selectedAgent.site_name || '',
      policy_id: selectedAgent.policy_id ? String(selectedAgent.policy_id) : '',
    })
    fetchCheckins(selectedAgent.id)
  }, [fetchCheckins, selectedAgent])

  const totalAgents = agents.length
  const activeAgents = agents.filter((agent) => agent.enrollment_state === 'active').length
  const pendingAgents = agents.filter((agent) => agent.enrollment_state === 'pending').length
  const healthyAgents = agents.filter((agent) => agent.health?.state === 'healthy').length

  const handleAgentDraftChange = (field, value) => {
    setAgentDraft((current) => ({ ...current, [field]: value }))
  }

  const handleSaveAgent = async () => {
    if (!selectedAgent) return

    try {
      setSavingAgent(true)
      setError('')
      await api.updateAgent(selectedAgent.id, {
        display_name: agentDraft.display_name || null,
        site_name: agentDraft.site_name || null,
        policy_id: normalizeNumber(agentDraft.policy_id),
      })
      showSuccess('Agent record updated')
      await fetchAgents()
      await fetchCheckins(selectedAgent.id)
    } catch (err) {
      setError(err.message)
    } finally {
      setSavingAgent(false)
    }
  }

  const handleApproveAgent = async () => {
    if (!selectedAgent) return

    try {
      setSavingAgent(true)
      setError('')
      await api.approveAgent(selectedAgent.id, {
        policy_id: normalizeNumber(agentDraft.policy_id),
        display_name: agentDraft.display_name || undefined,
      })
      showSuccess('Agent approved')
      await fetchAgents()
      await fetchCheckins(selectedAgent.id)
    } catch (err) {
      setError(err.message)
    } finally {
      setSavingAgent(false)
    }
  }

  const handleRejectAgent = async () => {
    if (!selectedAgent) return

    const reason = window.prompt('Optional rejection reason:', '')
    if (reason === null) return

    try {
      setSavingAgent(true)
      setError('')
      await api.rejectAgent(selectedAgent.id, { reason: reason || null })
      showSuccess('Agent rejected')
      await fetchAgents()
      await fetchCheckins(selectedAgent.id)
    } catch (err) {
      setError(err.message)
    } finally {
      setSavingAgent(false)
    }
  }

  const handleRevokeAgent = async () => {
    if (!selectedAgent) return

    const reason = window.prompt('Reason for revoking this agent:', 'decommissioned or compromised')
    if (reason === null) return

    try {
      setSavingAgent(true)
      setError('')
      await api.revokeAgent(selectedAgent.id, { reason: reason || null })
      showSuccess('Agent revoked and API key invalidated')
      await fetchAgents()
      await fetchCheckins(selectedAgent.id)
    } catch (err) {
      setError(err.message)
    } finally {
      setSavingAgent(false)
    }
  }

  const handleReactivateAgent = async () => {
    if (!selectedAgent) return

    const reason = window.prompt('Reason for reactivating this agent:', 'returning to service')
    if (reason === null) return

    try {
      setSavingAgent(true)
      setError('')
      await api.reactivateAgent(selectedAgent.id, { reason: reason || null })
      showSuccess('Agent reactivated and moved to pending approval')
      await fetchAgents()
      await fetchCheckins(selectedAgent.id)
    } catch (err) {
      setError(err.message)
    } finally {
      setSavingAgent(false)
    }
  }

  const handleRotateApiKey = async () => {
    if (!selectedAgent) return

    const reason = window.prompt('Reason for rotating the API key:', 'lost local key file')
    if (reason === null) return

    try {
      setSavingAgent(true)
      setError('')
      const response = await api.rotateAgentApiKey(selectedAgent.id, { reason: reason || null })
      setRevealedApiKey(response.api_key)
      showSuccess('Agent API key rotated')
      await fetchAgents()
    } catch (err) {
      setError(err.message)
    } finally {
      setSavingAgent(false)
    }
  }

  const handleRequestCollection = async () => {
    if (!selectedAgent) return

    const reason = window.prompt('Reason for requesting collection:', 'operator requested refresh')
    if (reason === null) return

    try {
      setSavingAgent(true)
      setError('')
      await api.requestAgentCollection(selectedAgent.id, { reason: reason || null })
      showSuccess('Collection requested; the agent will collect on its next timer run')
      await fetchAgents()
      await fetchCheckins(selectedAgent.id)
    } catch (err) {
      setError(err.message)
    } finally {
      setSavingAgent(false)
    }
  }

  const handlePolicyFormChange = (field, value) => {
    setPolicyForm((current) => ({ ...current, [field]: value }))
  }

  const handlePolicyCommandToggle = (command) => {
    setPolicyForm((current) => ({
      ...current,
      enabled_commands: {
        ...current.enabled_commands,
        [command]: !current.enabled_commands[command],
      },
    }))
  }

  const handleEditPolicy = (policy) => {
    setEditingPolicyId(policy.id)
    setPolicyForm({
      name: policy.name,
      description: policy.description || '',
      checkin_interval_seconds: policy.checkin_interval_seconds,
      jitter_seconds: policy.jitter_seconds,
      command_timeout_seconds: policy.command_timeout_seconds,
      enabled_commands: {
        ip_neigh: !!policy.enabled_commands?.ip_neigh,
        ss_tunap: !!policy.enabled_commands?.ss_tunap,
        ip_addr: !!policy.enabled_commands?.ip_addr,
        ip_route: !!policy.enabled_commands?.ip_route,
      },
      max_report_bytes: policy.max_report_bytes,
      is_active: policy.is_active,
    })
  }

  const handleSubmitPolicy = async () => {
    try {
      setSavingPolicy(true)
      setError('')
      const payload = {
        ...policyForm,
        description: policyForm.description || null,
      }
      if (editingPolicyId) {
        await api.updateAgentPolicy(editingPolicyId, payload)
        showSuccess('Policy updated')
      } else {
        await api.createAgentPolicy(payload)
        showSuccess('Policy created')
      }
      resetPolicyForm()
      await fetchPolicies()
      await fetchAgents()
      await fetchEnrollmentKeys()
    } catch (err) {
      setError(err.message)
    } finally {
      setSavingPolicy(false)
    }
  }

  const handleEnrollmentKeyFormChange = (field, value) => {
    setEnrollmentKeyForm((current) => ({ ...current, [field]: value }))
  }

  const handleEditEnrollmentKey = (enrollmentKey) => {
    setEditingEnrollmentKeyId(enrollmentKey.id)
    setEnrollmentKeyForm({
      name: enrollmentKey.name,
      description: enrollmentKey.description || '',
      default_policy_id: enrollmentKey.default_policy_id ? String(enrollmentKey.default_policy_id) : '',
      auto_approve: enrollmentKey.auto_approve,
      is_active: enrollmentKey.is_active,
      expires_at: toDateTimeLocal(enrollmentKey.expires_at),
      max_registrations: enrollmentKey.max_registrations || '',
    })
  }

  const handleSubmitEnrollmentKey = async () => {
    try {
      setSavingEnrollmentKey(true)
      setError('')
      const payload = {
        name: enrollmentKeyForm.name,
        description: enrollmentKeyForm.description || null,
        default_policy_id: normalizeNumber(enrollmentKeyForm.default_policy_id),
        auto_approve: enrollmentKeyForm.auto_approve,
        is_active: enrollmentKeyForm.is_active,
        expires_at: fromDateTimeLocal(enrollmentKeyForm.expires_at),
        max_registrations: normalizeNumber(enrollmentKeyForm.max_registrations),
      }

      if (editingEnrollmentKeyId) {
        await api.updateAgentEnrollmentKey(editingEnrollmentKeyId, payload)
        showSuccess('Enrollment key updated')
      } else {
        const response = await api.createAgentEnrollmentKey(payload)
        setRevealedEnrollmentKey(response.enrollment_key)
        showSuccess('Enrollment key created')
      }

      resetEnrollmentKeyForm()
      await fetchEnrollmentKeys()
      await fetchAgents()
    } catch (err) {
      setError(err.message)
    } finally {
      setSavingEnrollmentKey(false)
    }
  }

  return (
    <div className="space-y-8 p-6 lg:p-8">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100">Agents</h1>
          <p className="mt-1 text-gray-600 dark:text-gray-400">
            Fleet status, approvals, policies, and enrollment keys for passive collectors.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {TABS.map((tab) => (
            <TabButton key={tab} active={activeTab === tab} onClick={() => setActiveTab(tab)}>
              {tab}
            </TabButton>
          ))}
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/50 dark:bg-red-900/20 dark:text-red-300">
          {error}
        </div>
      )}

      {success && (
        <div className="rounded-xl border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700 dark:border-green-900/50 dark:bg-green-900/20 dark:text-green-300">
          {success}
        </div>
      )}

      {revealedEnrollmentKey && (
        <div className="rounded-xl border border-blue-200 bg-blue-50 p-4 dark:border-blue-900/50 dark:bg-blue-900/20">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 className="text-sm font-semibold text-blue-900 dark:text-blue-200">New Enrollment Key</h2>
              <p className="mt-1 text-sm text-blue-700 dark:text-blue-300">
                This secret is only returned once. Copy it to the target host workflow now.
              </p>
              <code className="mt-3 block rounded-lg bg-white px-3 py-2 font-mono text-xs text-blue-900 shadow-sm dark:bg-gray-950 dark:text-blue-200">
                {revealedEnrollmentKey}
              </code>
            </div>
            <button type="button" className="btn btn-secondary" onClick={() => setRevealedEnrollmentKey('')}>
              Dismiss
            </button>
          </div>
        </div>
      )}

      {revealedApiKey && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 dark:border-amber-900/50 dark:bg-amber-900/20">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 className="text-sm font-semibold text-amber-900 dark:text-amber-200">Rotated Agent API Key</h2>
              <p className="mt-1 text-sm text-amber-700 dark:text-amber-300">
                This raw API key will not be shown again after this view is dismissed.
              </p>
              <code className="mt-3 block rounded-lg bg-white px-3 py-2 font-mono text-xs text-amber-900 shadow-sm dark:bg-gray-950 dark:text-amber-200">
                {revealedApiKey}
              </code>
            </div>
            <button type="button" className="btn btn-secondary" onClick={() => setRevealedApiKey('')}>
              Dismiss
            </button>
          </div>
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <div className="card p-5">
          <p className="text-sm uppercase tracking-wide text-gray-500 dark:text-gray-400">Registered Agents</p>
          <p className="mt-2 text-3xl font-bold text-gray-900 dark:text-gray-100">{loadingAgents ? '...' : totalAgents}</p>
        </div>
        <div className="card p-5">
          <p className="text-sm uppercase tracking-wide text-gray-500 dark:text-gray-400">Approved</p>
          <p className="mt-2 text-3xl font-bold text-green-600 dark:text-green-400">{loadingAgents ? '...' : activeAgents}</p>
        </div>
        <div className="card p-5">
          <p className="text-sm uppercase tracking-wide text-gray-500 dark:text-gray-400">Pending Approval</p>
          <p className="mt-2 text-3xl font-bold text-amber-600 dark:text-amber-400">{loadingAgents ? '...' : pendingAgents}</p>
        </div>
        <div className="card p-5">
          <p className="text-sm uppercase tracking-wide text-gray-500 dark:text-gray-400">Healthy Check-in</p>
          <p className="mt-2 text-3xl font-bold text-blue-600 dark:text-blue-400">{loadingAgents ? '...' : healthyAgents}</p>
        </div>
      </div>

      {activeTab === 'Fleet' && (
        <div className="grid gap-6 xl:grid-cols-[1.5fr_1fr]">
          <div className="card overflow-hidden">
            <div className="card-header flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
              <div>
                <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Fleet Registry</h2>
                <p className="text-sm text-gray-500 dark:text-gray-400">Approval state, policy assignment, and check-in freshness.</p>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="text-sm text-gray-600 dark:text-gray-300">
                  <span className="mb-1 block">State</span>
                  <select
                    className="select"
                    value={agentFilters.enrollment_state}
                    onChange={(event) => setAgentFilters((current) => ({ ...current, enrollment_state: event.target.value }))}
                  >
                    <option value="">All</option>
                    <option value="pending">Pending</option>
                    <option value="active">Active</option>
                    <option value="rejected">Rejected</option>
                    <option value="revoked">Revoked</option>
                  </select>
                </label>
                <label className="text-sm text-gray-600 dark:text-gray-300">
                  <span className="mb-1 block">Activity</span>
                  <select
                    className="select"
                    value={agentFilters.is_active}
                    onChange={(event) => setAgentFilters((current) => ({ ...current, is_active: event.target.value }))}
                  >
                    <option value="">All</option>
                    <option value="true">Active records</option>
                    <option value="false">Inactive records</option>
                  </select>
                </label>
              </div>
            </div>
            <div className="table-container rounded-none border-0">
              <table className="table">
                <thead>
                  <tr>
                    <th>Agent</th>
                    <th>State</th>
                    <th>Policy</th>
                    <th>Last Seen</th>
                  </tr>
                </thead>
                <tbody>
                  {loadingAgents ? (
                    <tr>
                      <td colSpan="4" className="px-6 py-10 text-center text-gray-500 dark:text-gray-400">
                        Loading agents...
                      </td>
                    </tr>
                  ) : agents.length ? (
                    agents.map((agent) => {
                      const freshness = freshnessForAgent(agent)
                      return (
                        <tr
                          key={agent.id}
                          className={`cursor-pointer ${selectedAgentId === agent.id ? 'bg-blue-50 dark:bg-blue-900/20' : ''}`}
                          onClick={() => setSelectedAgentId(agent.id)}
                        >
                          <td>
                            <div className="font-medium text-gray-900 dark:text-gray-100">{agent.display_name || agent.hostname || agent.agent_uuid}</div>
                            <div className="text-xs text-gray-500 dark:text-gray-400">{agent.hostname || agent.agent_uuid}</div>
                            <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">{agent.site_name || 'No site'}</div>
                          </td>
                          <td>
                            <div className="flex flex-col gap-2">
                              <span className={`inline-flex w-fit rounded-full px-2.5 py-0.5 text-xs font-medium ${stateBadge(agent.enrollment_state)}`}>
                                {agent.enrollment_state}
                              </span>
                              <span className={`inline-flex w-fit rounded-full px-2.5 py-0.5 text-xs font-medium ${freshnessBadge(freshness.tone)}`}>
                                {freshness.label}
                              </span>
                            </div>
                          </td>
                          <td className="text-gray-700 dark:text-gray-300">{agent.policy?.name || 'Unassigned'}</td>
                          <td>
                            <div className="text-gray-900 dark:text-gray-100">{formatRelative(agent.last_seen_at)}</div>
                            <div className="text-xs text-gray-500 dark:text-gray-400">{formatDate(agent.last_seen_at)}</div>
                          </td>
                        </tr>
                      )
                    })
                  ) : (
                    <tr>
                      <td colSpan="4" className="px-6 py-10 text-center text-gray-500 dark:text-gray-400">
                        No agents matched the current filters.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className="card">
            <div className="card-header">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Agent Details</h2>
              <p className="text-sm text-gray-500 dark:text-gray-400">Review approval status, metadata, and recent check-ins.</p>
            </div>
            <div className="card-body space-y-6">
              {!selectedAgent ? (
                <div className="empty-state">
                  <div className="empty-state-icon">
                    <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M17 20h5V4H2v16h5m10 0v-2a4 4 0 00-4-4H9a4 4 0 00-4 4v2m12 0H7m10-11a3 3 0 11-6 0 3 3 0 016 0z" />
                    </svg>
                  </div>
                  <p>Select an agent to inspect its status.</p>
                </div>
              ) : (
                <>
                  <div className="space-y-2">
                    <div>
                      <p className="text-xl font-semibold text-gray-900 dark:text-gray-100">
                        {selectedAgent.display_name || selectedAgent.hostname || selectedAgent.agent_uuid}
                      </p>
                      <p className="text-sm text-gray-500 dark:text-gray-400">{selectedAgent.agent_uuid}</p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${stateBadge(selectedAgent.enrollment_state)}`}>
                        {selectedAgent.enrollment_state}
                      </span>
                      <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${freshnessBadge(freshnessForAgent(selectedAgent).tone)}`}>
                        {freshnessForAgent(selectedAgent).label}
                      </span>
                      <span className="inline-flex rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-700 dark:bg-slate-700 dark:text-slate-200">
                        {selectedAgent.agent_version || 'Unknown version'}
                      </span>
                    </div>
                  </div>

                  <div className="grid gap-4 sm:grid-cols-2">
                    <div>
                      <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Display Name</label>
                      <input className="input" value={agentDraft.display_name} onChange={(event) => handleAgentDraftChange('display_name', event.target.value)} />
                    </div>
                    <div>
                      <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Site</label>
                      <input className="input" value={agentDraft.site_name} onChange={(event) => handleAgentDraftChange('site_name', event.target.value)} />
                    </div>
                    <div>
                      <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Policy</label>
                      <select className="select" value={agentDraft.policy_id} onChange={(event) => handleAgentDraftChange('policy_id', event.target.value)}>
                        <option value="">No policy assigned</option>
                        {policies.map((policy) => (
                          <option key={policy.id} value={String(policy.id)}>
                            {policy.name}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Record Status</label>
                      <div className="rounded-lg bg-gray-50 px-3 py-2 text-sm text-gray-700 dark:bg-gray-900/40 dark:text-gray-300">
                        {selectedAgent.is_active ? 'Active record' : 'Inactive record'}
                      </div>
                    </div>
                  </div>

                  <div className="grid gap-3 text-sm text-gray-600 dark:text-gray-300">
                    <div className="rounded-lg bg-gray-50 px-4 py-3 dark:bg-gray-900/40">
                      <span className="font-medium text-gray-900 dark:text-gray-100">Last Seen:</span> {formatDate(selectedAgent.last_seen_at)}
                    </div>
                    <div className="rounded-lg bg-gray-50 px-4 py-3 dark:bg-gray-900/40">
                      <span className="font-medium text-gray-900 dark:text-gray-100">Backend Health:</span>{' '}
                      {selectedAgent.health?.state || 'never_seen'}
                      {selectedAgent.health?.message ? ` - ${selectedAgent.health.message}` : ''}
                    </div>
                    <div className="rounded-lg bg-gray-50 px-4 py-3 dark:bg-gray-900/40">
                      <span className="font-medium text-gray-900 dark:text-gray-100">Last Registration:</span> {formatDate(selectedAgent.last_registration_at)}
                    </div>
                    <div className="rounded-lg bg-gray-50 px-4 py-3 dark:bg-gray-900/40">
                      <span className="font-medium text-gray-900 dark:text-gray-100">Last IP Summary:</span>{' '}
                      {(selectedAgent.last_ip_addresses || []).join(', ') || 'None reported'}
                    </div>
                    <div className="rounded-lg bg-gray-50 px-4 py-3 dark:bg-gray-900/40">
                      <span className="font-medium text-gray-900 dark:text-gray-100">Collection Request:</span>{' '}
                      {collectionRequestLabel(selectedAgent)}
                    </div>
                  </div>

                  <div className="flex flex-wrap gap-3">
                    <button type="button" className="btn btn-primary" onClick={handleSaveAgent} disabled={savingAgent}>
                      {savingAgent ? 'Saving...' : 'Save Changes'}
                    </button>
                    {selectedAgent.enrollment_state === 'pending' && (
                      <button type="button" className="btn btn-secondary" onClick={handleApproveAgent} disabled={savingAgent}>
                        Approve Agent
                      </button>
                    )}
                    {selectedAgent.enrollment_state === 'pending' && (
                      <button type="button" className="btn btn-danger" onClick={handleRejectAgent} disabled={savingAgent}>
                        Reject Agent
                      </button>
                    )}
                    {selectedAgent.enrollment_state === 'active' && selectedAgent.is_active && (
                      <>
                        <button type="button" className="btn btn-primary" onClick={handleRequestCollection} disabled={savingAgent}>
                          Request Collection
                        </button>
                        <button type="button" className="btn btn-secondary" onClick={handleRotateApiKey} disabled={savingAgent}>
                          Rotate API Key
                        </button>
                        <button type="button" className="btn btn-danger" onClick={handleRevokeAgent} disabled={savingAgent}>
                          Revoke Agent
                        </button>
                      </>
                    )}
                    {(selectedAgent.enrollment_state === 'revoked' || selectedAgent.enrollment_state === 'rejected' || !selectedAgent.is_active) && (
                      <button type="button" className="btn btn-secondary" onClick={handleReactivateAgent} disabled={savingAgent}>
                        Reactivate Agent
                      </button>
                    )}
                  </div>

                  <div>
                    <div className="mb-3 flex items-center justify-between">
                      <h3 className="text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Recent Check-ins</h3>
                      <span className="text-xs text-gray-500 dark:text-gray-400">Latest 10</span>
                    </div>
                    <div className="space-y-3">
                      {loadingCheckins ? (
                        <div className="rounded-lg bg-gray-50 px-4 py-6 text-sm text-gray-500 dark:bg-gray-900/40 dark:text-gray-400">
                          Loading check-ins...
                        </div>
                      ) : agentCheckins.length ? (
                        agentCheckins.map((checkin) => (
                          <div key={checkin.id} className="rounded-lg border border-gray-200 px-4 py-3 dark:border-gray-700">
                            <div className="flex items-start justify-between gap-4">
                              <div>
                                <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{formatDate(checkin.received_at)}</p>
                                <p className="text-xs text-gray-500 dark:text-gray-400">
                                  Observed {formatDate(checkin.observed_at)} • seq {checkin.sequence_number ?? 'n/a'}
                                </p>
                              </div>
                              <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${freshnessBadge(checkin.status === 'accepted' ? 'green' : 'red')}`}>
                                {checkin.status}
                              </span>
                            </div>
                            <div className="mt-3 grid gap-2 text-xs text-gray-600 dark:text-gray-300 sm:grid-cols-2">
                              <div>Hosts: {checkin.summary?.hosts_created ?? 0}</div>
                              <div>ARP: {checkin.summary?.arp_entries_created ?? 0}</div>
                              <div>Connections: {checkin.summary?.connections_created ?? 0}</div>
                              <div>Records Created: {checkin.records_created}</div>
                            </div>
                          </div>
                        ))
                      ) : (
                        <div className="rounded-lg bg-gray-50 px-4 py-6 text-sm text-gray-500 dark:bg-gray-900/40 dark:text-gray-400">
                          No check-ins recorded yet for this agent.
                        </div>
                      )}
                    </div>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {activeTab === 'Policies' && (
        <div className="grid gap-6 xl:grid-cols-[1.2fr_1fr]">
          <div className="card overflow-hidden">
            <div className="card-header">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Policy Profiles</h2>
              <p className="text-sm text-gray-500 dark:text-gray-400">Server-controlled cadence, safeguards, and disabled commands.</p>
            </div>
            <div className="table-container rounded-none border-0">
              <table className="table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Cadence</th>
                    <th>Assigned</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {loadingPolicies ? (
                    <tr>
                      <td colSpan="4" className="px-6 py-10 text-center text-gray-500 dark:text-gray-400">
                        Loading policies...
                      </td>
                    </tr>
                  ) : policies.length ? (
                    policies.map((policy) => (
                      <tr key={policy.id} className="cursor-pointer" onClick={() => handleEditPolicy(policy)}>
                        <td>
                          <div className="font-medium text-gray-900 dark:text-gray-100">{policy.name}</div>
                          <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">{policy.description || 'No description'}</div>
                        </td>
                        <td className="text-gray-700 dark:text-gray-300">
                          {policy.checkin_interval_seconds}s + {policy.jitter_seconds}s jitter
                        </td>
                        <td className="text-gray-700 dark:text-gray-300">{policy.agent_count ?? 0}</td>
                        <td>
                          <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${policy.is_active ? freshnessBadge('green') : freshnessBadge('slate')}`}>
                            {policy.is_active ? 'Active' : 'Inactive'}
                          </span>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan="4" className="px-6 py-10 text-center text-gray-500 dark:text-gray-400">
                        No policies defined yet.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className="card">
            <div className="card-header">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                {editingPolicyId ? 'Edit Policy' : 'Create Policy'}
              </h2>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                {editingPolicyId ? 'Update an existing collection profile.' : 'Define a low-impact collection profile for deployed agents.'}
              </p>
            </div>
            <div className="card-body">
              <PolicyForm
                form={policyForm}
                onChange={handlePolicyFormChange}
                onToggleCommand={handlePolicyCommandToggle}
                onSubmit={handleSubmitPolicy}
                onReset={resetPolicyForm}
                saving={savingPolicy}
                submitLabel={editingPolicyId ? 'Update Policy' : 'Create Policy'}
              />
            </div>
          </div>
        </div>
      )}

      {activeTab === 'Enrollment Keys' && (
        <div className="grid gap-6 xl:grid-cols-[1.2fr_1fr]">
          <div className="card overflow-hidden">
            <div className="card-header">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Enrollment Keys</h2>
              <p className="text-sm text-gray-500 dark:text-gray-400">Bootstrap keys for initial agent registration and approval defaults.</p>
            </div>
            <div className="table-container rounded-none border-0">
              <table className="table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Policy</th>
                    <th>Registrations</th>
                    <th>Usage</th>
                  </tr>
                </thead>
                <tbody>
                  {loadingEnrollmentKeys ? (
                    <tr>
                      <td colSpan="4" className="px-6 py-10 text-center text-gray-500 dark:text-gray-400">
                        Loading enrollment keys...
                      </td>
                    </tr>
                  ) : enrollmentKeys.length ? (
                    enrollmentKeys.map((enrollmentKey) => (
                      <tr key={enrollmentKey.id} className="cursor-pointer" onClick={() => handleEditEnrollmentKey(enrollmentKey)}>
                        <td>
                          <div className="font-medium text-gray-900 dark:text-gray-100">{enrollmentKey.name}</div>
                          <div className="mt-1 text-xs text-gray-500 dark:text-gray-400 font-mono">{enrollmentKey.key_prefix}</div>
                        </td>
                        <td className="text-gray-700 dark:text-gray-300">{enrollmentKey.default_policy?.name || 'No default policy'}</td>
                        <td className="text-gray-700 dark:text-gray-300">
                          {enrollmentKey.registration_count}
                          {enrollmentKey.max_registrations ? ` / ${enrollmentKey.max_registrations}` : ''}
                        </td>
                        <td>
                          <div className="flex flex-col gap-2">
                            <span className={`inline-flex w-fit rounded-full px-2.5 py-0.5 text-xs font-medium ${enrollmentKey.is_active ? freshnessBadge('green') : freshnessBadge('slate')}`}>
                              {enrollmentKey.is_active ? 'Active' : 'Inactive'}
                            </span>
                            <span className="text-xs text-gray-500 dark:text-gray-400">
                              Last used {formatRelative(enrollmentKey.last_used_at)}
                            </span>
                          </div>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan="4" className="px-6 py-10 text-center text-gray-500 dark:text-gray-400">
                        No enrollment keys created yet.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className="card">
            <div className="card-header">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                {editingEnrollmentKeyId ? 'Edit Enrollment Key' : 'Create Enrollment Key'}
              </h2>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                {editingEnrollmentKeyId ? 'Update bootstrap policy or expiry settings.' : 'Generate a new bootstrap key and return its secret once.'}
              </p>
            </div>
            <div className="card-body">
              <EnrollmentKeyForm
                form={enrollmentKeyForm}
                policies={policies}
                onChange={handleEnrollmentKeyFormChange}
                onSubmit={handleSubmitEnrollmentKey}
                onReset={resetEnrollmentKeyForm}
                saving={savingEnrollmentKey}
                submitLabel={editingEnrollmentKeyId ? 'Update Enrollment Key' : 'Create Enrollment Key'}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
