const API_BASE = window.location.port === '8765' ? '/api' : 'http://127.0.0.1:8765/api'

export async function fetchHealth() {
  try {
    const res = await fetch(`${API_BASE}/health`)
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
  const res = await fetch(`${API_BASE}/config`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return await res.json()
}

export async function updateConfig(updates) {
  const res = await fetch(`${API_BASE}/config`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return await res.json()
}

export async function fetchSystemResources() {
  try {
    const res = await fetch(`${API_BASE}/system/resources`)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    return await res.json()
  } catch (err) {
    return null
  }
}

export async function unloadModel() {
  const res = await fetch(`${API_BASE}/model/unload`, { method: 'POST' })
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

  const res = await fetch(`${API_BASE}/task/execute`, fetchOptions)
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `Server error: HTTP ${res.status}`)
  }
  return await res.json()
}

// Backwards-compatible names used by the main chat screen.
export function executeTask(payload) {
  return executeTaskApi(payload)
}

export async function approveTask(taskId, approved) {
  const res = await fetch(`${API_BASE}/task/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ task_id: taskId, approved }),
  })
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}))
    throw new Error(errorData.detail || `Server error: HTTP ${res.status}`)
  }
  return await res.json()
}

export async function stopTaskApi(taskId) {
  try {
    const res = await fetch(`${API_BASE}/task/stop`, {
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
  const res = await fetch(`${API_BASE}/conversations/${convId}`, {
    method: 'DELETE',
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return await res.json()
}

export async function clearAllConversationsApi() {
  const res = await fetch(`${API_BASE}/conversations`, {
    method: 'DELETE',
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return await res.json()
}

export async function fetchConversations() {
  const res = await fetch(`${API_BASE}/conversations`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return await res.json()
}

export async function fetchMessages(convId) {
  const res = await fetch(`${API_BASE}/conversations/${convId}/messages`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return await res.json()
}

export async function pingModel(prompt = 'Hello, are you operational?') {
  const res = await fetch(`${API_BASE}/model/ping`, {
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
  const res = await fetch(`${API_BASE}/models`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return await res.json()
}

export async function selectModelApi(modelName) {
  const res = await fetch(`${API_BASE}/models/select`, {
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
  const res = await fetch(`${API_BASE}/models/pull`, {
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
  const res = await fetch(`${API_BASE}/models/pull/${encodeURIComponent(modelName)}/status`)
  if (!res.ok) {
    if (res.status === 404) return null
    throw new Error(`HTTP ${res.status}`)
  }
  return await res.json()
}

export async function cancelPullApi(modelName) {
  const res = await fetch(`${API_BASE}/models/pull/${encodeURIComponent(modelName)}/cancel`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return await res.json()
}

export async function deleteModelApi(modelName) {
  const res = await fetch(`${API_BASE}/models/${encodeURIComponent(modelName)}`, {
    method: 'DELETE',
  })
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}))
    throw new Error(errorData.detail || `HTTP ${res.status}`)
  }
  return await res.json()
}

export async function testModelApi(modelName, provider = 'local') {
  const res = await fetch(`${API_BASE}/models/test`, {
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
  const res = await fetch(`${API_BASE}/models/add`, {
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
  const res = await fetch(`${API_BASE}/providers`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return await res.json()
}

export async function updateProviders(updates) {
  const res = await fetch(`${API_BASE}/providers`, {
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
