const API_BASE = '/api'

// Utility function for making API requests
async function apiCall(method, endpoint, body = null, params = null) {
  const token = localStorage.getItem('auth_token')
  const options = {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  }

  if (body) {
    options.body = JSON.stringify(body)
  }

  // Build URL with query params
  let url = `${API_BASE}${endpoint}`
  if (params) {
    const searchParams = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        searchParams.append(key, value)
      }
    })
    const paramString = searchParams.toString()
    if (paramString) {
      url += `?${paramString}`
    }
  }

  const response = await fetch(url, options)

  if (!response.ok) {
    if (response.status === 401) {
      localStorage.removeItem('auth_token')
      window.location.href = '/login'
      throw new Error('Session expired. Please log in again.')
    }
    const error = await response.json().catch(() => ({}))
    throw new Error(error.detail || `API error: ${response.status} ${response.statusText}`)
  }

  return response.json()
}

// ============================================
// Host endpoints
// ============================================

export async function getHosts(params = {}) {
  return apiCall('GET', '/hosts', null, params)
}

export async function getHost(id) {
  return apiCall('GET', `/hosts/${id}`)
}

export async function createHost(data) {
  return apiCall('POST', '/hosts', data)
}

export async function updateHost(id, data) {
  return apiCall('PUT', `/hosts/${id}`, data)
}

export async function deleteHost(id) {
  return apiCall('DELETE', `/hosts/${id}`)
}

// ============================================
// Import endpoints
// ============================================

export async function importRaw(sourceType, sourceHost, rawData) {
  const formData = new FormData()
  formData.append('source_type', sourceType)
  formData.append('raw_data', rawData)
  if (sourceHost) {
    formData.append('source_host', sourceHost)
  }

  const token = localStorage.getItem('auth_token')
  const response = await fetch(`${API_BASE}/imports/raw`, {
    method: 'POST',
    body: formData,
    ...(token ? { headers: { Authorization: `Bearer ${token}` } } : {}),
    // Note: Don't set Content-Type header - browser will set it with boundary
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({}))
    throw new Error(error.detail || `API error: ${response.status}`)
  }

  return response.json()
}

export async function importFile(file, sourceType, sourceHost) {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('source_type', sourceType)
  formData.append('source_host', sourceHost)

  const token = localStorage.getItem('auth_token')
  const response = await fetch(`${API_BASE}/imports/file`, {
    method: 'POST',
    body: formData,
    ...(token ? { headers: { Authorization: `Bearer ${token}` } } : {}),
  })

  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`)
  }

  return response.json()
}

export async function getImports(params = {}) {
  return apiCall('GET', '/imports', null, params)
}

// ============================================
// Connection endpoints
// ============================================

export async function getConnections(params = {}) {
  return apiCall('GET', '/connections', null, params)
}

// ============================================
// ARP endpoints
// ============================================

export async function getArpEntries(params = {}) {
  return apiCall('GET', '/arp', null, params)
}

export async function getImport(id) {
  return apiCall('GET', `/imports/${id}`)
}

export async function reparseImport(id) {
  return apiCall('POST', `/imports/${id}/reparse`)
}

// ============================================
// Network visualization endpoints
// ============================================

export async function getNetworkMap(params = {}) {
  return apiCall('GET', '/network/map', null, params)
}

export async function getNetworkRoutes(params = {}) {
  return apiCall('GET', '/network/routes', null, params)
}

export async function getSubnets(params = {}) {
  return apiCall('GET', '/network/subnets', null, params)
}

// ============================================
// VLAN endpoints
// ============================================

export async function getVlans() {
  return apiCall('GET', '/vlans')
}

export async function getVlan(vlanId) {
  return apiCall('GET', `/vlans/${vlanId}`)
}

export async function createVlan(params = {}) {
  return apiCall('POST', '/vlans', null, params)
}

export async function updateVlan(vlanId, params = {}) {
  return apiCall('PUT', `/vlans/${vlanId}`, null, params)
}

export async function deleteVlan(vlanId) {
  return apiCall('DELETE', `/vlans/${vlanId}`)
}

export async function autoAssignVlans() {
  return apiCall('POST', '/vlans/auto-assign')
}

// ============================================
// Correlation endpoints
// ============================================

export async function runCorrelation() {
  return apiCall('POST', '/correlate')
}

export async function getConflicts(params = {}) {
  return apiCall('GET', '/correlate/conflicts', null, params)
}

export async function getConflict(id) {
  return apiCall('GET', `/correlate/conflicts/${id}`)
}

export async function resolveConflict(id, resolution, resolvedBy = 'manual') {
  return apiCall('POST', `/correlate/conflicts/${id}/resolve`, null, {
    resolution,
    resolved_by: resolvedBy,
  })
}

export async function mergeHosts(primaryId, secondaryId, resolvedBy = 'manual_merge') {
  return apiCall('POST', `/correlate/hosts/${primaryId}/merge/${secondaryId}`, null, {
    resolved_by: resolvedBy,
  })
}

export async function getHostUnifiedView(id) {
  return apiCall('GET', `/correlate/hosts/${id}/unified`)
}

// ============================================
// Search endpoints
// ============================================

export async function search(query, types = null, limit = 50) {
  return apiCall('GET', '/search', null, { q: query, types, limit })
}

export async function getSearchSuggestions(query) {
  return apiCall('GET', '/search/suggestions', null, { q: query })
}

// ============================================
// Export endpoints
// ============================================

export async function exportHosts(format = 'csv', includePorts = false, activeOnly = true) {
  const params = new URLSearchParams({
    format,
    include_ports: includePorts,
    active_only: activeOnly,
  })
  const token = localStorage.getItem('auth_token')
  const response = await fetch(`${API_BASE}/export/hosts?${params}`, {
    ...(token ? { headers: { Authorization: `Bearer ${token}` } } : {}),
  })
  if (!response.ok) {
    throw new Error(`Export error: ${response.status}`)
  }
  return response
}

export async function exportPorts(format = 'csv', openOnly = true) {
  const params = new URLSearchParams({
    format,
    open_only: openOnly,
  })
  const token = localStorage.getItem('auth_token')
  const response = await fetch(`${API_BASE}/export/ports?${params}`, {
    ...(token ? { headers: { Authorization: `Bearer ${token}` } } : {}),
  })
  if (!response.ok) {
    throw new Error(`Export error: ${response.status}`)
  }
  return response
}

export async function exportConnections(format = 'csv', state = null) {
  const params = new URLSearchParams({ format })
  if (state) params.append('state', state)
  const token = localStorage.getItem('auth_token')
  const response = await fetch(`${API_BASE}/export/connections?${params}`, {
    ...(token ? { headers: { Authorization: `Bearer ${token}` } } : {}),
  })
  if (!response.ok) {
    throw new Error(`Export error: ${response.status}`)
  }
  return response
}

export async function exportAll(format = 'json') {
  const token = localStorage.getItem('auth_token')
  const response = await fetch(`${API_BASE}/export/all?format=${format}`, {
    ...(token ? { headers: { Authorization: `Bearer ${token}` } } : {}),
  })
  if (!response.ok) {
    throw new Error(`Export error: ${response.status}`)
  }
  return response
}

// ============================================
// Network topology graph exports
// ============================================

export async function exportNetworkGraphML(subnetFilter = null, showInternet = 'cloud') {
  const params = new URLSearchParams()
  if (subnetFilter) params.append('subnet_filter', subnetFilter)
  if (showInternet) params.append('show_internet', showInternet)
  const paramStr = params.toString()
  const url = `${API_BASE}/export/network/graphml${paramStr ? '?' + paramStr : ''}`
  const token = localStorage.getItem('auth_token')
  const response = await fetch(url, {
    ...(token ? { headers: { Authorization: `Bearer ${token}` } } : {}),
  })
  if (!response.ok) {
    throw new Error(`Export error: ${response.status}`)
  }
  return response
}

export async function exportNetworkDrawio(subnetFilter = null, showInternet = 'cloud') {
  const params = new URLSearchParams()
  if (subnetFilter) params.append('subnet_filter', subnetFilter)
  if (showInternet) params.append('show_internet', showInternet)
  const paramStr = params.toString()
  const url = `${API_BASE}/export/network/drawio${paramStr ? '?' + paramStr : ''}`
  const token = localStorage.getItem('auth_token')
  const response = await fetch(url, {
    ...(token ? { headers: { Authorization: `Bearer ${token}` } } : {}),
  })
  if (!response.ok) {
    throw new Error(`Export error: ${response.status}`)
  }
  return response
}

// ============================================
// Maintenance endpoints
// ============================================

export async function getDatabaseStats() {
  return apiCall('GET', '/maintenance/stats')
}

export async function previewCleanup(daysOld = 90) {
  return apiCall('GET', '/maintenance/cleanup/preview', null, { days_old: daysOld })
}

export async function runCleanup(daysOld = 90) {
  return apiCall('POST', '/maintenance/cleanup', null, { days_old: daysOld })
}

// Vendor lookup
export async function updateVendorInfo() {
  return apiCall('POST', '/maintenance/vendor-lookup')
}

export async function lookupMacVendor(mac) {
  return apiCall('GET', `/maintenance/vendor-lookup/${encodeURIComponent(mac)}`)
}

// Database backup/restore
export async function createBackup() {
  return apiCall('POST', '/maintenance/backup')
}

export async function listBackups() {
  return apiCall('GET', '/maintenance/backup/list')
}

export async function downloadBackup(filename) {
  const token = localStorage.getItem('auth_token')
  const response = await fetch(`${API_BASE}/maintenance/backup/download/${encodeURIComponent(filename)}`, {
    ...(token ? { headers: { Authorization: `Bearer ${token}` } } : {}),
  })
  if (!response.ok) {
    throw new Error(`Download error: ${response.status}`)
  }
  return response
}

export async function restoreBackup(filename) {
  return apiCall('POST', `/maintenance/restore/${encodeURIComponent(filename)}`)
}

export async function deleteBackup(filename) {
  return apiCall('DELETE', `/maintenance/backup/${encodeURIComponent(filename)}`)
}

export async function uploadBackup(file) {
  const formData = new FormData()
  formData.append('file', file)

  const response = await fetch(`${API_BASE}/maintenance/backup/upload`, {
    method: 'POST',
    body: formData,
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({}))
    throw new Error(error.detail || `Upload error: ${response.status}`)
  }

  return response.json()
}

export async function seedDemoData(append = false) {
  return apiCall('POST', '/maintenance/seed-demo', null, { append })
}

// ============================================
// Bulk import
// ============================================

export async function importBulk(files, sourceType, sourceHost) {
  const formData = new FormData()
  files.forEach(file => formData.append('files', file))
  formData.append('source_type', sourceType)
  if (sourceHost) {
    formData.append('source_host', sourceHost)
  }

  const token = localStorage.getItem('auth_token')
  const response = await fetch(`${API_BASE}/imports/bulk`, {
    method: 'POST',
    body: formData,
    ...(token ? { headers: { Authorization: `Bearer ${token}` } } : {}),
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({}))
    throw new Error(error.detail || `API error: ${response.status}`)
  }

  return response.json()
}

// ============================================
// Health check
// ============================================

export async function healthCheck() {
  return apiCall('GET', '/health')
}

export async function getBackendInfo() {
  return apiCall('GET', '/info')
}

// ============================================
// Update check endpoints
// ============================================

export async function checkForUpdates(force = false) {
  return apiCall('GET', '/updates', null, force ? { force: true } : null)
}

export async function triggerUpgrade() {
  return apiCall('POST', '/updates/upgrade')
}

export async function getUpgradeStatus() {
  return apiCall('GET', '/updates/status')
}

// ============================================
// Device Identities endpoints
// ============================================

export async function getDeviceIdentities(params = {}) {
  return apiCall('GET', '/device-identities', null, params)
}

export async function getDeviceIdentity(id) {
  return apiCall('GET', `/device-identities/${id}`)
}

export async function createDeviceIdentity(data) {
  return apiCall('POST', '/device-identities', data)
}

export async function updateDeviceIdentity(id, data) {
  return apiCall('PUT', `/device-identities/${id}`, data)
}

export async function deleteDeviceIdentity(id) {
  return apiCall('DELETE', `/device-identities/${id}`)
}

export async function linkHostsToDevice(deviceId, hostIds) {
  return apiCall('POST', `/device-identities/${deviceId}/link-hosts`, { host_ids: hostIds })
}

export async function unlinkHostFromDevice(deviceId, hostId) {
  return apiCall('POST', `/device-identities/${deviceId}/unlink-host/${hostId}`)
}

// ============================================
// Auth endpoints
// ============================================

export async function getProviders() {
  return apiCall('GET', '/auth/providers')
}

export async function authCallback(data) {
  return apiCall('POST', '/auth/callback', data)
}

export async function localLogin(username, password) {
  return apiCall('POST', '/auth/login/local', { username, password })
}

export async function getCurrentUser() {
  return apiCall('GET', '/auth/me')
}

export async function authLogout() {
  return apiCall('POST', '/auth/logout')
}

export async function getUsers() {
  return apiCall('GET', '/auth/users')
}

export async function updateUserRole(userId, role) {
  return apiCall('PATCH', `/auth/users/${userId}/role`, { role })
}

// ── Auth Admin - Provider management ─────────────────────────────────

export async function getAdminProviders() {
  return apiCall('GET', '/auth/admin/providers')
}

export async function createAuthProvider(data) {
  return apiCall('POST', '/auth/admin/providers', data)
}

export async function updateAuthProvider(id, data) {
  return apiCall('PATCH', `/auth/admin/providers/${id}`, data)
}

export async function deleteAuthProvider(id) {
  return apiCall('DELETE', `/auth/admin/providers/${id}`)
}

export async function discoverProviderEndpoints(id) {
  return apiCall('POST', `/auth/admin/providers/${id}/discover`)
}

// ── Auth Admin - Role mapping management ─────────────────────────────

export async function getRoleMappings(providerId) {
  return apiCall('GET', `/auth/admin/providers/${providerId}/mappings`)
}

export async function createRoleMapping(providerId, data) {
  return apiCall('POST', `/auth/admin/providers/${providerId}/mappings`, data)
}

export async function updateRoleMapping(id, data) {
  return apiCall('PATCH', `/auth/admin/mappings/${id}`, data)
}

export async function deleteRoleMapping(id) {
  return apiCall('DELETE', `/auth/admin/mappings/${id}`)
}

// ── Auth Admin - User management ─────────────────────────────────────

export async function updateUserActiveStatus(userId, isActive) {
  return apiCall('PATCH', `/auth/users/${userId}/active`, { is_active: isActive })
}
