import { useState, useEffect, useCallback } from 'react'
import * as api from '../api/client'

const TABS = ['Providers', 'Role Mappings', 'Users']

// Reusable inline edit/add form for providers
// Well-known OAuth2 endpoint presets
const OAUTH2_PRESETS = {
  github: {
    issuer_url: 'https://github.com',
    authorization_endpoint: 'https://github.com/login/oauth/authorize',
    token_endpoint: 'https://github.com/login/oauth/access_token',
    userinfo_endpoint: 'https://api.github.com/user',
    scope: 'read:user user:email',
  },
}

function ProviderForm({ initial, onSave, onCancel, saving }) {
  const [form, setForm] = useState(initial || {
    provider_name: '', display_name: '', provider_type: 'oidc',
    issuer_url: '', client_id: '', client_secret: '',
    scope: 'openid profile email',
    authorization_endpoint: '', token_endpoint: '', userinfo_endpoint: '',
    display_order: 0, is_enabled: true,
  })
  const set = (k, v) => setForm(prev => ({ ...prev, [k]: v }))
  const isOAuth2 = form.provider_type === 'oauth2'

  const applyPreset = (presetKey) => {
    const preset = OAUTH2_PRESETS[presetKey]
    if (preset) setForm(prev => ({ ...prev, ...preset }))
  }

  const inputClass = "w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-blue-500 outline-none"

  return (
    <div className="space-y-4 p-4 bg-gray-50 dark:bg-gray-800/50 rounded-xl border border-gray-200 dark:border-gray-700">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Provider Name (slug)</label>
          <input className={inputClass} value={form.provider_name} onChange={e => set('provider_name', e.target.value)} placeholder="e.g. okta, github" disabled={!!initial} />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Display Name</label>
          <input className={inputClass} value={form.display_name} onChange={e => set('display_name', e.target.value)} placeholder="e.g. Okta SSO" />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Type</label>
          <select className={inputClass} value={form.provider_type} onChange={e => set('provider_type', e.target.value)}>
            <option value="oidc">OIDC</option>
            <option value="oauth2">OAuth2</option>
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{isOAuth2 ? 'Base URL' : 'Issuer URL'}</label>
          <input className={inputClass} value={form.issuer_url} onChange={e => set('issuer_url', e.target.value)} placeholder={isOAuth2 ? 'https://github.com' : 'https://your-idp.example.com'} />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Client ID</label>
          <input className={inputClass} value={form.client_id} onChange={e => set('client_id', e.target.value)} />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Client Secret</label>
          <input type="password" className={inputClass} value={form.client_secret} onChange={e => set('client_secret', e.target.value)} />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Scope</label>
          <input className={inputClass} value={form.scope} onChange={e => set('scope', e.target.value)} />
        </div>
        <div className="flex items-end gap-4">
          <div className="flex-1">
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Display Order</label>
            <input type="number" className={inputClass} value={form.display_order} onChange={e => set('display_order', parseInt(e.target.value) || 0)} />
          </div>
          <label className="flex items-center gap-2 pb-2 cursor-pointer">
            <input type="checkbox" checked={form.is_enabled} onChange={e => set('is_enabled', e.target.checked)} className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500" />
            <span className="text-sm text-gray-700 dark:text-gray-300">Enabled</span>
          </label>
        </div>
      </div>

      {/* Endpoint URLs — required for OAuth2, optional for OIDC (auto-discovered) */}
      <div>
        <div className="flex items-center gap-2 mb-2">
          <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300">
            Endpoint URLs
            {isOAuth2 ? <span className="text-red-500 ml-1">*</span> : null}
          </h4>
          {isOAuth2 && (
            <span className="text-xs text-amber-600 dark:text-amber-400">Required for OAuth2 — no auto-discovery</span>
          )}
          {!isOAuth2 && (
            <span className="text-xs text-gray-400 dark:text-gray-500">Optional — auto-populated by OIDC discovery</span>
          )}
        </div>
        {isOAuth2 && !initial && (
          <div className="flex gap-2 mb-3">
            <span className="text-xs text-gray-500 dark:text-gray-400 self-center">Quick fill:</span>
            {Object.keys(OAUTH2_PRESETS).map(key => (
              <button key={key} type="button" onClick={() => applyPreset(key)} className="px-2 py-1 text-xs rounded border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors capitalize">{key}</button>
            ))}
          </div>
        )}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Authorization Endpoint</label>
            <input className={inputClass} value={form.authorization_endpoint || ''} onChange={e => set('authorization_endpoint', e.target.value)} placeholder="https://..." />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Token Endpoint</label>
            <input className={inputClass} value={form.token_endpoint || ''} onChange={e => set('token_endpoint', e.target.value)} placeholder="https://..." />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Userinfo Endpoint</label>
            <input className={inputClass} value={form.userinfo_endpoint || ''} onChange={e => set('userinfo_endpoint', e.target.value)} placeholder="https://..." />
          </div>
        </div>
      </div>

      <div className="flex gap-2 pt-2">
        <button onClick={() => onSave(form)} disabled={saving || !form.provider_name || !form.client_id || (isOAuth2 && (!form.authorization_endpoint || !form.token_endpoint))} className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors">
          {saving ? 'Saving...' : initial ? 'Update Provider' : 'Create Provider'}
        </button>
        <button onClick={onCancel} className="px-4 py-2 rounded-lg border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 text-sm font-medium hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors">Cancel</button>
      </div>
    </div>
  )
}

// Reusable form for role mappings
function MappingForm({ initial, onSave, onCancel, saving }) {
  const [form, setForm] = useState(initial || {
    idp_claim_path: 'groups', idp_claim_value: '', app_role: 'viewer', is_enabled: true,
  })
  const set = (k, v) => setForm(prev => ({ ...prev, [k]: v }))

  return (
    <div className="space-y-4 p-4 bg-gray-50 dark:bg-gray-800/50 rounded-xl border border-gray-200 dark:border-gray-700">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Claim Path</label>
          <input className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-blue-500 outline-none" value={form.idp_claim_path} onChange={e => set('idp_claim_path', e.target.value)} placeholder="e.g. groups, resource_access.app.roles" />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Claim Value</label>
          <input className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-blue-500 outline-none" value={form.idp_claim_value} onChange={e => set('idp_claim_value', e.target.value)} placeholder="e.g. net-admins" />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">App Role</label>
          <select className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-blue-500 outline-none" value={form.app_role} onChange={e => set('app_role', e.target.value)}>
            <option value="admin">Admin</option>
            <option value="editor">Editor</option>
            <option value="viewer">Viewer</option>
          </select>
        </div>
        <div className="flex items-end">
          <label className="flex items-center gap-2 pb-2 cursor-pointer">
            <input type="checkbox" checked={form.is_enabled} onChange={e => set('is_enabled', e.target.checked)} className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500" />
            <span className="text-sm text-gray-700 dark:text-gray-300">Enabled</span>
          </label>
        </div>
      </div>
      <div className="flex gap-2 pt-2">
        <button onClick={() => onSave(form)} disabled={saving || !form.idp_claim_path || !form.idp_claim_value} className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors">
          {saving ? 'Saving...' : initial ? 'Update Mapping' : 'Create Mapping'}
        </button>
        <button onClick={onCancel} className="px-4 py-2 rounded-lg border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 text-sm font-medium hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors">Cancel</button>
      </div>
    </div>
  )
}

const roleBadge = (role) => {
  const colors = {
    admin: 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300',
    editor: 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300',
    viewer: 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300',
  }
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${colors[role] || colors.viewer}`}>
      {role}
    </span>
  )
}

export default function AuthAdmin() {
  const [activeTab, setActiveTab] = useState(0)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [saving, setSaving] = useState(false)

  // Providers state
  const [providers, setProviders] = useState([])
  const [loadingProviders, setLoadingProviders] = useState(true)
  const [showProviderForm, setShowProviderForm] = useState(false)
  const [editingProvider, setEditingProvider] = useState(null)
  const [discovering, setDiscovering] = useState(null)

  // Mappings state
  const [selectedProviderId, setSelectedProviderId] = useState(null)
  const [mappings, setMappings] = useState([])
  const [loadingMappings, setLoadingMappings] = useState(false)
  const [showMappingForm, setShowMappingForm] = useState(false)
  const [editingMapping, setEditingMapping] = useState(null)

  // Users state
  const [users, setUsers] = useState([])
  const [loadingUsers, setLoadingUsers] = useState(true)

  const showSuccess = (msg) => {
    setSuccess(msg)
    setTimeout(() => setSuccess(''), 4000)
  }

  // ── Fetch providers ───
  const fetchProviders = useCallback(async () => {
    try {
      setLoadingProviders(true)
      const data = await api.getAdminProviders()
      setProviders(data)
      if (data.length > 0 && !selectedProviderId) {
        setSelectedProviderId(data[0].id)
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setLoadingProviders(false)
    }
  }, [selectedProviderId])

  // ── Fetch mappings ───
  const fetchMappings = useCallback(async () => {
    if (!selectedProviderId) { setMappings([]); return }
    try {
      setLoadingMappings(true)
      const data = await api.getRoleMappings(selectedProviderId)
      setMappings(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoadingMappings(false)
    }
  }, [selectedProviderId])

  // ── Fetch users ───
  const fetchUsers = useCallback(async () => {
    try {
      setLoadingUsers(true)
      const data = await api.getUsers()
      setUsers(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoadingUsers(false)
    }
  }, [])

  useEffect(() => { fetchProviders() }, [fetchProviders])
  useEffect(() => { fetchMappings() }, [fetchMappings])
  useEffect(() => { fetchUsers() }, [fetchUsers])

  // ── Provider CRUD ───
  const handleSaveProvider = async (form) => {
    setSaving(true)
    setError('')
    try {
      if (editingProvider) {
        await api.updateAuthProvider(editingProvider.id, form)
        showSuccess('Provider updated')
      } else {
        await api.createAuthProvider(form)
        showSuccess('Provider created')
      }
      setShowProviderForm(false)
      setEditingProvider(null)
      fetchProviders()
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  const handleDeleteProvider = async (id, name) => {
    if (!window.confirm(`Delete provider "${name}" and all its role mappings?`)) return
    try {
      await api.deleteAuthProvider(id)
      showSuccess('Provider deleted')
      if (selectedProviderId === id) setSelectedProviderId(null)
      fetchProviders()
    } catch (err) {
      setError(err.message)
    }
  }

  const handleDiscover = async (id) => {
    setDiscovering(id)
    try {
      const result = await api.discoverProviderEndpoints(id)
      showSuccess(`Discovery successful — found ${result.authorization_endpoint ? 'all' : 'some'} endpoints`)
      fetchProviders()
    } catch (err) {
      setError(`Discovery failed: ${err.message}`)
    } finally {
      setDiscovering(null)
    }
  }

  // ── Mapping CRUD ───
  const handleSaveMapping = async (form) => {
    setSaving(true)
    setError('')
    try {
      if (editingMapping) {
        await api.updateRoleMapping(editingMapping.id, form)
        showSuccess('Mapping updated')
      } else {
        await api.createRoleMapping(selectedProviderId, form)
        showSuccess('Mapping created')
      }
      setShowMappingForm(false)
      setEditingMapping(null)
      fetchMappings()
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  const handleDeleteMapping = async (id) => {
    if (!window.confirm('Delete this role mapping?')) return
    try {
      await api.deleteRoleMapping(id)
      showSuccess('Mapping deleted')
      fetchMappings()
    } catch (err) {
      setError(err.message)
    }
  }

  // ── User actions ───
  const handleRoleChange = async (userId, newRole) => {
    try {
      await api.updateUserRole(userId, newRole)
      showSuccess('Role updated')
      fetchUsers()
    } catch (err) {
      setError(err.message)
    }
  }

  const handleToggleActive = async (userId, isActive) => {
    try {
      await api.updateUserActiveStatus(userId, isActive)
      showSuccess(isActive ? 'User activated' : 'User deactivated')
      fetchUsers()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div className="p-6 lg:p-8 max-w-7xl mx-auto">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100">Identity & Access</h1>
        <p className="mt-1 text-gray-500 dark:text-gray-400">Configure authentication providers, role mappings, and manage users</p>
      </div>

      {/* Messages */}
      {error && (
        <div className="mb-6 p-4 rounded-xl bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 flex items-start gap-3">
          <svg className="w-5 h-5 text-red-500 mt-0.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
          <div className="flex-1">
            <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
          </div>
          <button onClick={() => setError('')} className="text-red-400 hover:text-red-600"><svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg></button>
        </div>
      )}
      {success && (
        <div className="mb-6 p-4 rounded-xl bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 flex items-center gap-3">
          <svg className="w-5 h-5 text-green-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>
          <p className="text-sm text-green-700 dark:text-green-300">{success}</p>
        </div>
      )}

      {/* Tabs */}
      <div className="border-b border-gray-200 dark:border-gray-700 mb-6">
        <div className="flex gap-1">
          {TABS.map((tab, i) => (
            <button key={tab} onClick={() => setActiveTab(i)} className={`px-4 py-2.5 text-sm font-medium rounded-t-lg transition-colors ${activeTab === i ? 'bg-white dark:bg-gray-800 text-blue-600 dark:text-blue-400 border border-b-0 border-gray-200 dark:border-gray-700 -mb-px' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'}`}>
              {tab}
            </button>
          ))}
        </div>
      </div>

      {/* ═══ Providers Tab ═══ */}
      {activeTab === 0 && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Authentication Providers</h2>
            {!showProviderForm && (
              <button onClick={() => { setEditingProvider(null); setShowProviderForm(true) }} className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 transition-colors">
                + Add Provider
              </button>
            )}
          </div>

          {showProviderForm && (
            <ProviderForm
              initial={editingProvider ? { ...editingProvider, client_secret: '' } : null}
              onSave={handleSaveProvider}
              onCancel={() => { setShowProviderForm(false); setEditingProvider(null) }}
              saving={saving}
            />
          )}

          {loadingProviders ? (
            <div className="text-center py-8"><p className="text-gray-500 dark:text-gray-400">Loading providers...</p></div>
          ) : providers.length === 0 ? (
            <div className="text-center py-12 card">
              <svg className="w-12 h-12 text-gray-400 mx-auto mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" /></svg>
              <p className="text-gray-500 dark:text-gray-400">No providers configured yet</p>
              <p className="text-sm text-gray-400 dark:text-gray-500 mt-1">Add an OIDC provider to enable SSO</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-gray-200 dark:border-gray-700">
                    <th className="text-left py-3 px-4 text-sm font-medium text-gray-500 dark:text-gray-400">Provider</th>
                    <th className="text-left py-3 px-4 text-sm font-medium text-gray-500 dark:text-gray-400">Type</th>
                    <th className="text-left py-3 px-4 text-sm font-medium text-gray-500 dark:text-gray-400">Issuer</th>
                    <th className="text-left py-3 px-4 text-sm font-medium text-gray-500 dark:text-gray-400">Status</th>
                    <th className="text-left py-3 px-4 text-sm font-medium text-gray-500 dark:text-gray-400">Discovery</th>
                    <th className="text-right py-3 px-4 text-sm font-medium text-gray-500 dark:text-gray-400">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {providers.map(p => (
                    <tr key={p.id} className="border-b border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors">
                      <td className="py-3 px-4">
                        <div className="font-medium text-gray-900 dark:text-gray-100">{p.display_name}</div>
                        <div className="text-xs text-gray-500 dark:text-gray-400 font-mono">{p.provider_name}</div>
                      </td>
                      <td className="py-3 px-4">
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300 uppercase">{p.provider_type}</span>
                      </td>
                      <td className="py-3 px-4 text-sm text-gray-600 dark:text-gray-400 max-w-xs truncate">{p.issuer_url}</td>
                      <td className="py-3 px-4">
                        {p.is_enabled ? (
                          <span className="inline-flex items-center gap-1 text-xs font-medium text-green-700 dark:text-green-400"><span className="w-1.5 h-1.5 rounded-full bg-green-500"></span>Enabled</span>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-xs font-medium text-gray-500 dark:text-gray-400"><span className="w-1.5 h-1.5 rounded-full bg-gray-400"></span>Disabled</span>
                        )}
                      </td>
                      <td className="py-3 px-4">
                        {p.authorization_endpoint ? (
                          <span className="text-xs text-green-600 dark:text-green-400">Cached</span>
                        ) : (
                          <span className="text-xs text-yellow-600 dark:text-yellow-400">Not cached</span>
                        )}
                      </td>
                      <td className="py-3 px-4 text-right">
                        <div className="flex items-center justify-end gap-1">
                          {p.provider_type === 'oidc' && (
                          <button onClick={() => handleDiscover(p.id)} disabled={discovering === p.id} className="px-2 py-1 text-xs rounded border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50 transition-colors" title="Test OIDC Discovery">
                            {discovering === p.id ? '...' : 'Discover'}
                          </button>
                          )}
                          <button onClick={() => { setEditingProvider(p); setShowProviderForm(true) }} className="px-2 py-1 text-xs rounded border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors">
                            Edit
                          </button>
                          <button onClick={() => handleDeleteProvider(p.id, p.display_name)} className="px-2 py-1 text-xs rounded border border-red-300 dark:border-red-700 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors">
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ═══ Role Mappings Tab ═══ */}
      {activeTab === 1 && (
        <div className="space-y-4">
          <div className="flex items-center justify-between flex-wrap gap-3">
            <div className="flex items-center gap-3">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Role Mappings</h2>
              {providers.length > 0 && (
                <select value={selectedProviderId || ''} onChange={e => setSelectedProviderId(Number(e.target.value))} className="px-3 py-1.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-blue-500 outline-none">
                  {providers.map(p => (
                    <option key={p.id} value={p.id}>{p.display_name}</option>
                  ))}
                </select>
              )}
            </div>
            {selectedProviderId && !showMappingForm && (
              <button onClick={() => { setEditingMapping(null); setShowMappingForm(true) }} className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 transition-colors">
                + Add Mapping
              </button>
            )}
          </div>

          {providers.length === 0 ? (
            <div className="text-center py-12 card">
              <p className="text-gray-500 dark:text-gray-400">Add a provider first to configure role mappings</p>
            </div>
          ) : (
            <>
              {showMappingForm && (
                <MappingForm
                  initial={editingMapping}
                  onSave={handleSaveMapping}
                  onCancel={() => { setShowMappingForm(false); setEditingMapping(null) }}
                  saving={saving}
                />
              )}

              <div className="card">
                <div className="card-header">
                  <h3 className="font-medium text-gray-900 dark:text-gray-100">
                    Claim-to-Role Mappings
                  </h3>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">When a user authenticates, the highest-privilege matching role wins (admin &gt; editor &gt; viewer)</p>
                </div>
                <div className="card-body p-0">
                  {loadingMappings ? (
                    <div className="text-center py-8"><p className="text-gray-500 dark:text-gray-400 text-sm">Loading mappings...</p></div>
                  ) : mappings.length === 0 ? (
                    <div className="text-center py-8">
                      <p className="text-gray-500 dark:text-gray-400 text-sm">No mappings configured for this provider</p>
                      <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">All users from this provider will default to "viewer" role</p>
                    </div>
                  ) : (
                    <table className="w-full">
                      <thead>
                        <tr className="border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50">
                          <th className="text-left py-2.5 px-4 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Claim Path</th>
                          <th className="text-left py-2.5 px-4 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Claim Value</th>
                          <th className="text-left py-2.5 px-4 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">App Role</th>
                          <th className="text-left py-2.5 px-4 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Status</th>
                          <th className="text-right py-2.5 px-4 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {mappings.map(m => (
                          <tr key={m.id} className="border-b border-gray-100 dark:border-gray-800">
                            <td className="py-2.5 px-4 text-sm font-mono text-gray-900 dark:text-gray-100">{m.idp_claim_path}</td>
                            <td className="py-2.5 px-4 text-sm text-gray-700 dark:text-gray-300">{m.idp_claim_value}</td>
                            <td className="py-2.5 px-4">{roleBadge(m.app_role)}</td>
                            <td className="py-2.5 px-4">
                              {m.is_enabled ? (
                                <span className="text-xs text-green-600 dark:text-green-400">Active</span>
                              ) : (
                                <span className="text-xs text-gray-500 dark:text-gray-400">Disabled</span>
                              )}
                            </td>
                            <td className="py-2.5 px-4 text-right">
                              <div className="flex items-center justify-end gap-1">
                                <button onClick={() => { setEditingMapping(m); setShowMappingForm(true) }} className="px-2 py-1 text-xs rounded border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors">Edit</button>
                                <button onClick={() => handleDeleteMapping(m.id)} className="px-2 py-1 text-xs rounded border border-red-300 dark:border-red-700 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors">Delete</button>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {/* ═══ Users Tab ═══ */}
      {activeTab === 2 && (
        <div className="space-y-4">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">User Management</h2>

          {loadingUsers ? (
            <div className="text-center py-8"><p className="text-gray-500 dark:text-gray-400">Loading users...</p></div>
          ) : users.length === 0 ? (
            <div className="text-center py-12 card">
              <p className="text-gray-500 dark:text-gray-400">No users yet</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-gray-200 dark:border-gray-700">
                    <th className="text-left py-3 px-4 text-sm font-medium text-gray-500 dark:text-gray-400">User</th>
                    <th className="text-left py-3 px-4 text-sm font-medium text-gray-500 dark:text-gray-400">Provider</th>
                    <th className="text-left py-3 px-4 text-sm font-medium text-gray-500 dark:text-gray-400">Role</th>
                    <th className="text-left py-3 px-4 text-sm font-medium text-gray-500 dark:text-gray-400">Active</th>
                    <th className="text-left py-3 px-4 text-sm font-medium text-gray-500 dark:text-gray-400">Last Login</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map(u => (
                    <tr key={u.id} className="border-b border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors">
                      <td className="py-3 px-4">
                        <div className="font-medium text-gray-900 dark:text-gray-100">{u.username}</div>
                        <div className="text-xs text-gray-500 dark:text-gray-400">{u.email}</div>
                      </td>
                      <td className="py-3 px-4 text-sm text-gray-600 dark:text-gray-400">{u.oidc_provider || 'Local'}</td>
                      <td className="py-3 px-4">
                        <select value={u.role} onChange={e => handleRoleChange(u.id, e.target.value)} className="px-2 py-1 rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-blue-500 outline-none">
                          <option value="admin">Admin</option>
                          <option value="editor">Editor</option>
                          <option value="viewer">Viewer</option>
                        </select>
                      </td>
                      <td className="py-3 px-4">
                        <label className="relative inline-flex items-center cursor-pointer">
                          <input type="checkbox" checked={u.is_active} onChange={e => handleToggleActive(u.id, e.target.checked)} className="sr-only peer" />
                          <div className="w-9 h-5 bg-gray-200 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-blue-300 dark:peer-focus:ring-blue-800 rounded-full peer dark:bg-gray-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all dark:border-gray-600 peer-checked:bg-blue-600"></div>
                        </label>
                      </td>
                      <td className="py-3 px-4 text-sm text-gray-500 dark:text-gray-400">
                        {u.last_login_at ? new Date(u.last_login_at).toLocaleDateString() : 'Never'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
