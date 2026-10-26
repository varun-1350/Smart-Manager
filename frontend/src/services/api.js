const API_BASE = window.location.port === '8765' ? '/api' : 'http://127.0.0.1:8765/api'
const desktopSession = new URLSearchParams(window.location.search).get('sm_session')

function apiFetch(url, options = {}) {
  const headers = new Headers(options.headers || {})
  if (desktopSession) headers.set('X-Smart-Manager-Session', desktopSession)
  return window.fetch(url, { ...options, headers })
}

export async function fetchHealth() {
  try {
    const res = await apiFetch(`${API_BASE}/health`)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    return await res.json()
  } catch (err) {
    return {
      status: 'offline',
      version: '0.3.0',
      ollama_connected: false,
      ollama_url: 'http://127.0.0.1:11434',
      active_model: 'unknown',
      available_models: [],
      error: err.message,
    }
  }
}

export async function fetchConfig() {
  const res = await apiFetch(`${API_BASE}/config`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return await res.json()
}

export async function updateConfig(updates) {
  const res = await apiFetch(`${API_BASE}/config`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return await res.json()
}

export async function fetchSystemResources() {
  try {
    const res = await apiFetch(`${API_BASE}/system/resources`)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    return await res.json()
  } catch (err) {
    return null
  }
}

export async function unloadModel() {
  const res = await apiFetch(`${API_BASE}/model/unload`, { method: 'POST' })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return await res.json()
}

export async function executeTaskApi(payload, signal = null) {
  const fetchOptions = {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }
  if (signal) fetchOptions.signal = signal

  const res = await apiFetch(`${API_BASE}/task/execute`, fetchOptions)
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `Server error: HTTP ${res.status}`)
  }
  return await res.json()
}

export async function approveTaskApi(taskId, approved, approvalToken) {
  const res = await apiFetch(`${API_BASE}/task/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ task_id: taskId, approved, approval_token: approvalToken }),
  })
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}))
    throw new Error(errorData.detail || `Server error: HTTP ${res.status}`)
  }
  return await res.json()
}

export async function stopTaskApi(taskId) {
  try {
    const res = await apiFetch(`${API_BASE}/task/stop`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_id: taskId }),
    })
    return await res.json()
  } catch (err) {
    console.error('Failed to stop task:', err)
    return { success: false, error: err.message }
  }
}

export async function deleteConversationApi(convId) {
  const res = await apiFetch(`${API_BASE}/conversations/${convId}`, {
    method: 'DELETE',
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return await res.json()
}

export async function clearAllConversationsApi() {
  const res = await apiFetch(`${API_BASE}/conversations`, {
    method: 'DELETE',
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return await res.json()
}

export async function fetchConversations() {
  const res = await apiFetch(`${API_BASE}/conversations`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return await res.json()
}

export async function fetchMessages(convId) {
  const res = await apiFetch(`${API_BASE}/conversations/${convId}/messages`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return await res.json()
}

export async function pingModel(prompt = 'Hello, are you operational?') {
  const res = await apiFetch(`${API_BASE}/model/ping`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt }),
  })
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}))
    throw new Error(errorData.detail || `HTTP ${res.status}`)
  }
  return await res.json()
}

export async function fetchModels() {
  const res = await apiFetch(`${API_BASE}/models`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return await res.json()
}

export async function selectModelApi(modelName) {
  const res = await apiFetch(`${API_BASE}/models/select`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: modelName }),
  })
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}))
    throw new Error(errorData.detail || `HTTP ${res.status}`)
  }
  return await res.json()
}

export async function pullModelApi(modelName) {
  const res = await apiFetch(`${API_BASE}/models/pull`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: modelName }),
  })
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}))
    throw new Error(errorData.detail || `HTTP ${res.status}`)
  }
  return await res.json()
}

export async function fetchPullStatus(modelName) {
  const res = await apiFetch(`${API_BASE}/models/pull/${encodeURIComponent(modelName)}/status`)
  if (!res.ok) {
    if (res.status === 404) return null
    throw new Error(`HTTP ${res.status}`)
  }
  return await res.json()
}

export async function cancelPullApi(modelName) {
  const res = await apiFetch(`${API_BASE}/models/pull/${encodeURIComponent(modelName)}/cancel`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return await res.json()
}

export async function deleteModelApi(modelName) {
  const res = await apiFetch(`${API_BASE}/models/${encodeURIComponent(modelName)}`, {
    method: 'DELETE',
  })
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}))
    throw new Error(errorData.detail || `HTTP ${res.status}`)
  }
  return await res.json()
}

export async function testModelApi(modelName, provider = 'local') {
  const res = await apiFetch(`${API_BASE}/models/test`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: modelName, provider }),
  })
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}))
    throw new Error(errorData.detail || `HTTP ${res.status}`)
  }
  return await res.json()
}

export async function addModelApi({ provider, model, apiKey, baseUrl }) {
  const res = await apiFetch(`${API_BASE}/models/add`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      provider,
      model,
      api_key: apiKey,
      base_url: baseUrl || null,
    }),
  })
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}))
    throw new Error(errorData.detail || `HTTP ${res.status}`)
  }
  return await res.json()
}

export async function fetchProviders() {
  const res = await apiFetch(`${API_BASE}/providers`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return await res.json()
}

export async function updateProviders(updates) {
  const res = await apiFetch(`${API_BASE}/providers`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  })
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}))
    throw new Error(errorData.detail || `HTTP ${res.status}`)
  }
  return await res.json()
}

// ============================================================================
// File Explorer API Functions
// ============================================================================

export async function fetchLocations() {
  const res = await apiFetch(`${API_BASE}/explorer/locations`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return await res.json()
}

export async function browseDirectory(path = null, sortBy = 'name', sortOrder = 'asc', showHidden = false, offset = 0, limit = 500) {
  const params = new URLSearchParams()
  if (path) params.set('path', path)
  if (sortBy) params.set('sort_by', sortBy)
  if (sortOrder) params.set('sort_order', sortOrder)
  if (showHidden) params.set('show_hidden', 'true')
  params.set('offset', String(offset))
  params.set('limit', String(limit))

  const res = await apiFetch(`${API_BASE}/explorer/browse?${params.toString()}`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  return await res.json()
}

export async function fetchFilePreview(path) {
  const res = await apiFetch(`${API_BASE}/explorer/preview?path=${encodeURIComponent(path)}`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  return await res.json()
}

export async function executeExplorerAction(payload) {
  const res = await apiFetch(`${API_BASE}/explorer/action`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  return await res.json()
}

export async function fetchDuplicates(folder, minSize = 1024) {
  const res = await apiFetch(`${API_BASE}/explorer/duplicates?folder=${encodeURIComponent(folder)}&min_size=${minSize}`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  return await res.json()
}

export async function fetchStorageAnalysis(folder) {
  const res = await apiFetch(`${API_BASE}/explorer/storage-analysis?folder=${encodeURIComponent(folder)}`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  return await res.json()
}

export async function generateExplorerPlan(folderPath, instruction, signal = null) {
  const fetchOptions = {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ folder_path: folderPath, instruction }),
  }
  if (signal) fetchOptions.signal = signal

  const res = await apiFetch(`${API_BASE}/explorer/plan`, fetchOptions)
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  return await res.json()
}

export async function executeExplorerPlan(batchId, actions, signal = null) {
  const fetchOptions = {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ batch_id: batchId, actions }),
  }
  if (signal) fetchOptions.signal = signal

  const res = await apiFetch(`${API_BASE}/explorer/execute-plan`, fetchOptions)
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  return await res.json()
}

export async function undoExplorerLastOperation() {
  const res = await apiFetch(`${API_BASE}/explorer/undo`, {
    method: 'POST',
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  return await res.json()
}

export async function fetchExplorerHistory() {
  const res = await apiFetch(`${API_BASE}/explorer/history`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return await res.json()
}



