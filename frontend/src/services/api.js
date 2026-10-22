const API_BASE = 'http://127.0.0.1:8765/api'

export async function fetchHealth() {
  try {
    const res = await fetch(`${API_BASE}/health`)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    return await res.json()
  } catch (err) {
    return {
      status: 'offline',
      version: '0.2.0',
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
