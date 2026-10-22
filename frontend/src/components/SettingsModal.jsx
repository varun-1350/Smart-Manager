import React, { useState, useEffect } from 'react'
import {
  X,
  RefreshCw,
  CheckCircle,
  AlertCircle,
  Cpu,
  Trash2,
  Activity,
  Layers,
  Zap,
  Bot,
  Globe,
  Sliders,
  ShieldCheck,
  Check,
  Play,
  Key,
  Lock,
  Plus,
  ExternalLink,
  Sparkles,
} from 'lucide-react'
import {
  unloadModel,
  fetchSystemResources,
  fetchModels,
  selectModelApi,
  deleteModelApi,
  testModelApi,
  addModelApi,
} from '../services/api'

const PROVIDER_PRESETS = {
  gemini: {
    label: 'Google Gemini',
    defaultBaseUrl: 'https://generativelanguage.googleapis.com/v1beta',
    defaultModel: 'gemini-3.5-flash',
    models: ['gemini-3.5-flash', 'gemini-3.5-flash-lite', 'gemini-flash-lite-latest'],
    badgeClass: 'badge-gemini',
    keyPlaceholder: 'AQ.... or AIzaSy...',
    docUrl: 'https://aistudio.google.com/apikey',
  },
  groq: {
    label: 'Groq',
    defaultBaseUrl: 'https://api.groq.com/openai/v1',
    defaultModel: 'llama-3.3-70b-versatile',
    models: ['llama-3.3-70b-versatile', 'mixtral-8x7b-32768', 'gemma2-9b-it'],
    badgeClass: 'badge-groq',
    keyPlaceholder: 'gsk_...',
    docUrl: 'https://console.groq.com/keys',
  },
  openai: {
    label: 'OpenAI',
    defaultBaseUrl: 'https://api.openai.com/v1',
    defaultModel: 'gpt-4o-mini',
    models: ['gpt-4o-mini', 'gpt-4o'],
    badgeClass: 'badge-openai',
    keyPlaceholder: 'sk-proj-...',
    docUrl: 'https://platform.openai.com/api-keys',
  },
  custom: {
    label: 'Custom (OpenAI-compatible)',
    defaultBaseUrl: '',
    defaultModel: '',
    models: [],
    badgeClass: 'badge-custom',
    keyPlaceholder: 'API Key or Bearer Token...',
    docUrl: '',
  },
}

export default function SettingsModal({
  isOpen,
  onClose,
  config,
  onSaveConfig,
  health,
  onRefreshHealth,
}) {
  if (!isOpen) return null

  // Active Tab: 'models' or 'system'
  const [activeTab, setActiveTab] = useState('models')

  // Unified Models List States
  const [models, setModels] = useState([])
  const [loadingModels, setLoadingModels] = useState(false)
  const [selectedModelId, setSelectedModelId] = useState(config?.ollama_model || 'gemma4:e2b')
  const [modelActionStatus, setModelActionStatus] = useState(null)

  // Test Results per model: { [modelId]: { success, latency_ms, message } }
  const [testResults, setTestResults] = useState({})
  const [testingModelId, setTestingModelId] = useState(null)

  // Add Model Form State
  const [showAddForm, setShowAddForm] = useState(false)
  const [addProvider, setAddProvider] = useState('gemini')
  const [addModelName, setAddModelName] = useState('gemini-1.5-flash')
  const [addApiKey, setAddApiKey] = useState('')
  const [addBaseUrl, setAddBaseUrl] = useState('')
  const [addingLoading, setAddingLoading] = useState(false)
  const [addError, setAddError] = useState(null)

  // Delete Confirmation Dialog State
  const [deleteConfirmTarget, setDeleteConfirmTarget] = useState(null)

  // System & Hardware States
  const [numCtx, setNumCtx] = useState(config?.num_ctx || 2048)
  const [numPredict, setNumPredict] = useState(config?.num_predict || 256)
  const [keepAlive, setKeepAlive] = useState(config?.keep_alive || '5m')
  const [maxIterations, setMaxIterations] = useState(config?.max_iterations || 15)
  const [confirmationRequired, setConfirmationRequired] = useState(
    config?.confirmation_required ?? true
  )
  const [autoUnload, setAutoUnload] = useState(
    config?.auto_unload ?? true
  )

  const [resources, setResources] = useState(null)
  const [unloadStatus, setUnloadStatus] = useState(null)

  // Initial load
  useEffect(() => {
    loadResources()
    loadModels()
  }, [])

  const loadResources = async () => {
    const data = await fetchSystemResources()
    if (data) setResources(data)
  }

  const loadModels = async () => {
    setLoadingModels(true)
    try {
      const data = await fetchModels()
      if (Array.isArray(data)) {
        setModels(data)
        const active = data.find((m) => m.is_selected)
        if (active) setSelectedModelId(active.id || active.name)
      }
    } catch (e) {
      console.error('Failed to load models:', e)
    } finally {
      setLoadingModels(false)
    }
  }

  const handleSelectModel = async (modelIdentifier) => {
    try {
      setModelActionStatus(`Selecting ${modelIdentifier}...`)
      await selectModelApi(modelIdentifier)
      setSelectedModelId(modelIdentifier)
      await loadModels()
      onRefreshHealth?.()
      setModelActionStatus(`Switched active model to ${modelIdentifier}`)
      setTimeout(() => setModelActionStatus(null), 3000)
    } catch (err) {
      setModelActionStatus(`Failed to select model: ${err.message}`)
    }
  }

  const handleTestModel = async (modelIdentifier, providerType = 'local') => {
    setTestingModelId(modelIdentifier)
    try {
      const res = await testModelApi(modelIdentifier, providerType)
      setTestResults((prev) => ({
        ...prev,
        [modelIdentifier]: res,
      }))
    } catch (err) {
      setTestResults((prev) => ({
        ...prev,
        [modelIdentifier]: { success: false, message: err.message, latency_ms: 0 },
      }))
    } finally {
      setTestingModelId(null)
    }
  }

  const handleConfirmDelete = async () => {
    if (!deleteConfirmTarget) return
    const target = deleteConfirmTarget
    setDeleteConfirmTarget(null)
    try {
      setModelActionStatus(`Removing ${target.name || target.id}...`)
      await deleteModelApi(target.id || target.name)
      await loadModels()
      onRefreshHealth?.()
      setModelActionStatus(`Removed successfully`)
      setTimeout(() => setModelActionStatus(null), 3000)
    } catch (err) {
      setModelActionStatus(`Deletion error: ${err.message}`)
    }
  }

  const handleProviderPresetChange = (key) => {
    setAddProvider(key)
    const preset = PROVIDER_PRESETS[key]
    setAddModelName(preset.defaultModel)
    setAddBaseUrl(preset.defaultBaseUrl)
    setAddError(null)
  }

  const handleAddModelSubmit = async (e) => {
    e?.preventDefault()
    const cleanKey = addApiKey.trim().replace(/^["']|["']$/g, '')
    if (!addModelName.trim()) {
      setAddError('Model name is required.')
      return
    }
    if (!cleanKey) {
      setAddError('API key is required.')
      return
    }

    setAddingLoading(true)
    setAddError(null)
    try {
      const preset = PROVIDER_PRESETS[addProvider]
      const baseUrl = addBaseUrl.trim() || preset.defaultBaseUrl
      await addModelApi({
        provider: addProvider,
        model: addModelName.trim(),
        apiKey: cleanKey,
        baseUrl: baseUrl || null,
      })
      setShowAddForm(false)
      setAddApiKey('')
      await loadModels()
      onRefreshHealth?.()
      setModelActionStatus(`Added model ${addModelName.trim()} successfully!`)
      setTimeout(() => setModelActionStatus(null), 3000)
    } catch (err) {
      setAddError(err.message || 'Failed to add model')
    } finally {
      setAddingLoading(false)
    }
  }

  const handleUnloadModel = async () => {
    setUnloadStatus('Unloading...')
    try {
      const res = await unloadModel()
      setUnloadStatus(res.message || 'Model unloaded')
      await loadResources()
      await loadModels()
      setTimeout(() => setUnloadStatus(null), 3000)
    } catch (err) {
      setUnloadStatus(`Error: ${err.message}`)
    }
  }

  const handleSaveSystemConfig = () => {
    onSaveConfig({
      ollama_model: selectedModelId,
      num_ctx: parseInt(numCtx, 10),
      num_predict: parseInt(numPredict, 10),
      keep_alive: keepAlive,
      max_iterations: parseInt(maxIterations, 10),
      confirmation_required: confirmationRequired,
      auto_unload: autoUnload,
    })
    onClose()
  }

  return (
    <div className="modal-overlay">
      <div className="settings-modal" style={{ maxWidth: '680px', width: '92vw' }}>
        <div className="modal-header">
          <div className="modal-title-wrap">
            <Cpu size={20} className="modal-header-icon" />
            <h3 className="modal-title">Smart Manager Settings</h3>
          </div>
          <button className="close-btn" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        {/* Tab Navigation */}
        <div className="settings-tabs-bar">
          <button
            className={`settings-tab-btn ${activeTab === 'models' ? 'active' : ''}`}
            onClick={() => setActiveTab('models')}
          >
            <Bot size={16} />
            <span>AI Models</span>
          </button>
          <button
            className={`settings-tab-btn ${activeTab === 'system' ? 'active' : ''}`}
            onClick={() => setActiveTab('system')}
          >
            <Sliders size={16} />
            <span>System & Hardware</span>
          </button>
        </div>

        <div className="modal-body" style={{ maxHeight: '70vh', overflowY: 'auto' }}>
          {/* ================= TAB 1: AI MODELS ================= */}
          {activeTab === 'models' && (
            <div className="tab-pane-content">
              {/* Header Row */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                <div>
                  <label className="setting-label" style={{ marginBottom: '2px', display: 'block' }}>
                    Available Models ({models.length})
                  </label>
                  <span className="setting-help">
                    Select a local or online model. All requests route to your active selection.
                  </span>
                </div>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={loadModels}
                    disabled={loadingModels}
                    title="Refresh model list"
                  >
                    <RefreshCw size={13} className={loadingModels ? 'spin' : ''} />
                    <span>Refresh</span>
                  </button>
                  <button
                    className={`btn btn-sm ${showAddForm ? 'btn-secondary' : 'btn-primary'}`}
                    onClick={() => setShowAddForm(!showAddForm)}
                  >
                    {showAddForm ? <X size={13} /> : <Plus size={13} />}
                    <span>{showAddForm ? 'Cancel' : 'Add Model'}</span>
                  </button>
                </div>
              </div>

              {/* Status Banner */}
              {modelActionStatus && (
                <div className="model-action-toast">
                  <Activity size={14} className="icon-pulse" />
                  <span>{modelActionStatus}</span>
                </div>
              )}

              {/* Add Model Panel */}
              {showAddForm && (
                <form className="add-model-panel animate-fade-in" onSubmit={handleAddModelSubmit}>
                  <div className="add-model-panel-header">
                    <span className="add-model-panel-title">
                      <Sparkles size={16} className="text-amber" />
                      Add Online Model (Gemini, Groq, OpenAI, Custom)
                    </span>
                  </div>

                  {/* Provider Preset Buttons */}
                  <div className="setting-group">
                    <label className="setting-label">Select Provider</label>
                    <div className="provider-preset-tabs">
                      {Object.entries(PROVIDER_PRESETS).map(([key, p]) => (
                        <button
                          key={key}
                          type="button"
                          className={`provider-preset-btn ${addProvider === key ? `selected ${key}` : ''}`}
                          onClick={() => handleProviderPresetChange(key)}
                        >
                          <Globe size={13} />
                          <span>{p.label}</span>
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Model Identifier & Suggestions */}
                  <div className="setting-group">
                    <label className="setting-label">Model Identifier</label>
                    <input
                      type="text"
                      className="input-field"
                      value={addModelName}
                      onChange={(e) => setAddModelName(e.target.value)}
                      placeholder="e.g. gemini-1.5-flash, llama-3.3-70b-versatile"
                      required
                    />

                    {PROVIDER_PRESETS[addProvider]?.models?.length > 0 && (
                      <div className="suggested-models-chips" style={{ marginTop: '4px' }}>
                        <span className="chips-label">Popular:</span>
                        {PROVIDER_PRESETS[addProvider].models.map((m) => (
                          <button
                            key={m}
                            type="button"
                            className="model-chip"
                            onClick={() => setAddModelName(m)}
                          >
                            {m}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* API Key */}
                  <div className="setting-group">
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <label className="setting-label">API Key</label>
                      {PROVIDER_PRESETS[addProvider]?.docUrl && (
                        <a
                          href={PROVIDER_PRESETS[addProvider].docUrl}
                          target="_blank"
                          rel="noreferrer"
                          className="text-cyan"
                          style={{ fontSize: '11px', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '3px' }}
                        >
                          <span>Get API key</span>
                          <ExternalLink size={11} />
                        </a>
                      )}
                    </div>
                    <input
                      type="password"
                      className="input-field"
                      value={addApiKey}
                      onChange={(e) => setAddApiKey(e.target.value)}
                      placeholder={PROVIDER_PRESETS[addProvider]?.keyPlaceholder || 'Enter API Key...'}
                      required
                    />
                    <span className="setting-help" style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <Lock size={11} className="text-emerald" />
                      Supports Google Gemini Auth keys (AQ...) and standard keys (AIza...). Encrypted in Windows DPAPI.
                    </span>
                  </div>

                  {/* API Base URL */}
                  <div className="setting-group">
                    <label className="setting-label">API Base URL</label>
                    <input
                      type="text"
                      className="input-field"
                      value={addBaseUrl}
                      onChange={(e) => setAddBaseUrl(e.target.value)}
                      placeholder={PROVIDER_PRESETS[addProvider]?.defaultBaseUrl || 'https://api.openai.com/v1'}
                    />
                  </div>

                  {addError && (
                    <div className="pull-error-text" style={{ fontSize: '12px' }}>
                      {addError}
                    </div>
                  )}

                  <div className="add-model-actions-row">
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => setShowAddForm(false)}
                      disabled={addingLoading}
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      className="btn btn-primary btn-sm"
                      disabled={addingLoading}
                    >
                      {addingLoading ? (
                        <>
                          <RefreshCw size={13} className="spin" />
                          <span>Adding...</span>
                        </>
                      ) : (
                        <>
                          <Check size={13} />
                          <span>Save & Add Model</span>
                        </>
                      )}
                    </button>
                  </div>
                </form>
              )}

              {/* Unified Models List */}
              <div className="models-grid">
                {models.length === 0 && !loadingModels && (
                  <div className="empty-models-notice">
                    No models found. Make sure Ollama is running or click <strong>Add Model</strong> to connect Gemini, Groq, or OpenAI.
                  </div>
                )}

                {models.map((m) => {
                  const mId = m.id || m.name
                  const isCurrent = m.is_selected || mId === selectedModelId
                  const testRes = testResults[mId]
                  const isTesting = testingModelId === mId
                  const isOnline = m.type === 'online'
                  const providerKey = m.provider || (isOnline ? 'online' : 'ollama')

                  return (
                    <div key={mId} className={`model-card ${isCurrent ? 'active-model-card' : ''}`}>
                      <div className="model-card-top">
                        <div className="model-card-name-group">
                          <span className="model-name-text">{m.name}</span>
                          <div className="model-badges-row">
                            {isCurrent && <span className="badge badge-active">Active</span>}

                            {/* Provider Badge */}
                            {!isOnline ? (
                              <span className="badge badge-local">Local (Ollama)</span>
                            ) : (
                              <span className={`badge ${PROVIDER_PRESETS[providerKey]?.badgeClass || 'badge-custom'}`}>
                                {PROVIDER_PRESETS[providerKey]?.label || providerKey.toUpperCase()}
                              </span>
                            )}

                            {m.is_loaded && <span className="badge badge-loaded">Loaded in VRAM</span>}
                            {m.size_formatted && !isOnline && <span className="badge badge-size">{m.size_formatted}</span>}
                            {m.parameter_size && <span className="badge badge-param">{m.parameter_size}</span>}
                            {m.quantization && <span className="badge badge-quant">{m.quantization}</span>}
                            {isOnline && <span className="badge badge-size">Cloud API</span>}
                            {isOnline && m.has_api_key && (
                              <span className="badge" style={{ background: 'rgba(16, 185, 129, 0.1)', color: '#34d399' }}>
                                DPAPI Encrypted
                              </span>
                            )}
                          </div>
                        </div>
                      </div>

                      {/* Test Status Banner if tested */}
                      {testRes && (
                        <div className={`model-test-pill ${testRes.success ? 'success' : 'error'}`}>
                          {testRes.success ? <CheckCircle size={12} /> : <AlertCircle size={12} />}
                          <span>{testRes.message}</span>
                        </div>
                      )}

                      <div className="model-card-actions">
                        <button
                          className={`btn btn-sm ${isCurrent ? 'btn-active-disabled' : 'btn-primary'}`}
                          onClick={() => handleSelectModel(mId)}
                          disabled={isCurrent}
                        >
                          {isCurrent ? <Check size={13} /> : <Play size={13} />}
                          <span>{isCurrent ? 'Active' : 'Select'}</span>
                        </button>

                        <button
                          className="btn btn-secondary btn-sm"
                          onClick={() => handleTestModel(mId, m.type)}
                          disabled={isTesting}
                          title="Test structured JSON planning capabilities and latency"
                        >
                          <Activity size={13} className={isTesting ? 'spin' : ''} />
                          <span>{isTesting ? 'Testing...' : 'Test'}</span>
                        </button>

                        <button
                          className="btn btn-danger-subtle btn-sm icon-only"
                          onClick={() => setDeleteConfirmTarget(m)}
                          title={isOnline ? 'Remove this added model' : 'Delete local model from Ollama'}
                          disabled={isCurrent && models.length <= 1}
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* ================= TAB 2: SYSTEM & HARDWARE ================= */}
          {activeTab === 'system' && (
            <div className="tab-pane-content">
              {/* RAM & Hardware Monitoring Card */}
              <div className="system-perf-card">
                <div className="perf-header">
                  <Cpu size={16} className="text-cyan" />
                  <span className="perf-title">Live Hardware Allocation</span>
                </div>

                <div className="perf-metrics-grid">
                  <div className="stat-tile">
                    <span className="stat-tile-label">System RAM</span>
                    <div className="stat-tile-val">
                      {resources?.system_memory
                        ? `${resources.system_memory.used_gb} / ${resources.system_memory.total_gb} GB`
                        : 'Loading...'}
                    </div>
                    <div className="ram-subtext">{resources?.system_memory?.percent || 0}% Total Usage</div>
                  </div>

                  <div className="stat-tile">
                    <span className="stat-tile-label">GPU VRAM</span>
                    <div className="stat-tile-val">
                      {resources?.gpu
                        ? `${resources.gpu.used_mb} / ${resources.gpu.total_mb} MB`
                        : 'Direct / Shared'}
                    </div>
                    <div className="ram-subtext">{resources?.gpu?.name || 'NVIDIA GeForce RTX 3050'}</div>
                  </div>
                </div>

                {/* Quick Purge RAM Action */}
                <div style={{ marginTop: '12px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span className="setting-help">
                    Purge model from memory to immediately release ~3 GB system RAM when idle.
                  </span>
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={handleUnloadModel}
                    title="Force model unload"
                  >
                    <Zap size={13} className="text-amber" />
                    <span>Free 3GB RAM</span>
                  </button>
                </div>
                {unloadStatus && <div className="unload-toast">{unloadStatus}</div>}
              </div>

              {/* Execution Settings */}
              <div className="setting-group" style={{ marginTop: '14px' }}>
                <label className="setting-label">Context Size (num_ctx)</label>
                <select
                  className="input-field"
                  value={numCtx}
                  onChange={(e) => setNumCtx(e.target.value)}
                >
                  <option value={2048}>2048 tokens (Minimal RAM ~1.8 GB)</option>
                  <option value={4096}>4096 tokens (Standard ~2.9 GB RAM)</option>
                  <option value={8192}>8192 tokens (Large ~4.5 GB RAM)</option>
                </select>
                <span className="setting-help">
                  Lower context uses substantially less system RAM and GPU VRAM.
                </span>
              </div>

              <div className="setting-group">
                <label className="setting-label">Planning Response Limit</label>
                <select
                  className="input-field"
                  value={numPredict}
                  onChange={(e) => setNumPredict(e.target.value)}
                >
                  <option value={128}>128 tokens (Fastest)</option>
                  <option value={256}>256 tokens (Recommended)</option>
                  <option value={512}>512 tokens (More room for complex tasks)</option>
                </select>
                <span className="setting-help">
                  Limits each planning response. 256 is enough for normal file, app, and browser tasks.
                </span>
              </div>

              <div className="setting-group">
                <label className="setting-label">Model Idle Keep-Alive</label>
                <select
                  className="input-field"
                  value={keepAlive}
                  onChange={(e) => setKeepAlive(e.target.value)}
                >
                  <option value="0s">Unload immediately between requests (slow for multi-step tasks)</option>
                  <option value="2m">2 minutes (Recommended for low RAM)</option>
                  <option value="5m">5 minutes (Balanced)</option>
                  <option value="15m">15 minutes</option>
                </select>
              </div>

              <div className="setting-group">
                <label className="setting-label">Max Autonomous Steps per Task</label>
                <input
                  type="number"
                  className="input-field"
                  min={1}
                  max={30}
                  value={maxIterations}
                  onChange={(e) => setMaxIterations(e.target.value)}
                />
                <span className="setting-help">
                  Limits maximum reasoning iterations to prevent runaway loops.
                </span>
              </div>

              <div className="setting-group checkbox-group" style={{ marginTop: '8px' }}>
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={autoUnload}
                    onChange={(e) => setAutoUnload(e.target.checked)}
                  />
                  <span>Automatically purge model from RAM when task finishes</span>
                </label>
              </div>

              <div className="setting-group checkbox-group">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={confirmationRequired}
                    onChange={(e) => setConfirmationRequired(e.target.checked)}
                  />
                  <span>Require user confirmation before executing write or delete actions</span>
                </label>
              </div>
            </div>
          )}

          {/* Delete Confirmation Modal Overlay */}
          {deleteConfirmTarget && (
            <div className="confirmation-modal-backdrop">
              <div className="confirmation-card">
                <div className="confirm-header">
                  <AlertCircle size={20} className="text-rose" />
                  <h4>Remove Model: {deleteConfirmTarget.name}</h4>
                </div>
                <p className="confirm-desc">
                  {deleteConfirmTarget.type === 'online'
                    ? `Are you sure you want to remove the online model '${deleteConfirmTarget.name}'? Its encrypted API key will be deleted from your Windows DPAPI vault.`
                    : `Are you sure you want to permanently delete '${deleteConfirmTarget.name}' from local Ollama? This will delete local model files from disk.`}
                </p>
                <div className="confirm-actions">
                  <button className="btn btn-secondary btn-sm" onClick={() => setDeleteConfirmTarget(null)}>
                    Cancel
                  </button>
                  <button className="btn btn-danger btn-sm" onClick={handleConfirmDelete}>
                    Confirm Remove
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="modal-footer">
          <button className="btn btn-secondary" onClick={onClose}>
            Close
          </button>
          {activeTab === 'system' && (
            <button className="btn btn-primary" onClick={handleSaveSystemConfig}>
              Save System Settings
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
