import React, { useState, useEffect } from 'react'
import {
  X,
  RefreshCw,
  CheckCircle,
  AlertCircle,
  Cpu,
  Trash2,
  HardDrive,
  Activity,
  Layers,
  Zap,
} from 'lucide-react'
import { pingModel, unloadModel, fetchSystemResources } from '../services/api'

export default function SettingsModal({
  isOpen,
  onClose,
  config,
  onSaveConfig,
  health,
  onRefreshHealth,
}) {
  if (!isOpen) return null

  const [model, setModel] = useState(config?.ollama_model || 'gemma4:e2b')
  const [numCtx, setNumCtx] = useState(config?.num_ctx || 2048)
  const [keepAlive, setKeepAlive] = useState(config?.keep_alive || '5m')
  const [maxIterations, setMaxIterations] = useState(config?.max_iterations || 15)
  const [confirmationRequired, setConfirmationRequired] = useState(
    config?.confirmation_required ?? true
  )

  const [resources, setResources] = useState(null)
  const [unloadStatus, setUnloadStatus] = useState(null)
  const [pingStatus, setPingStatus] = useState(null)
  const [pingLoading, setPingLoading] = useState(false)

  useEffect(() => {
    loadResources()
  }, [])

  const loadResources = async () => {
    const data = await fetchSystemResources()
    if (data) setResources(data)
  }

  const handlePing = async () => {
    setPingLoading(true)
    setPingStatus(null)
    try {
      const res = await pingModel('Test ping: respond with pong')
      setPingStatus({
        success: true,
        message: `Response in ${res.total_duration_ms}ms: "${res.response}"`,
      })
      loadResources()
    } catch (err) {
      setPingStatus({
        success: false,
        message: `Inference failed: ${err.message}`,
      })
    } finally {
      setPingLoading(false)
    }
  }

  const handleUnloadModel = async () => {
    setUnloadStatus('Unloading...')
    try {
      const res = await unloadModel()
      setUnloadStatus(res.message || 'Model unloaded')
      await loadResources()
      setTimeout(() => setUnloadStatus(null), 3000)
    } catch (err) {
      setUnloadStatus(`Error: ${err.message}`)
    }
  }

  const handleSave = () => {
    onSaveConfig({
      ollama_model: model,
      num_ctx: parseInt(numCtx, 10),
      keep_alive: keepAlive,
      max_iterations: parseInt(maxIterations, 10),
      confirmation_required: confirmationRequired,
    })
    onClose()
  }

  return (
    <div className="modal-overlay">
      <div className="settings-modal" style={{ maxWidth: '580px' }}>
        <div className="modal-header">
          <div className="modal-title-wrap">
            <Cpu size={20} className="modal-header-icon" />
            <h3 className="modal-title">Hardware & Agent Settings</h3>
          </div>
          <button className="close-btn" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        <div className="modal-body" style={{ maxHeight: '72vh', overflowY: 'auto' }}>
          {/* Hardware Resource Monitor Card */}
          <div className="resource-monitor-card" style={{
            backgroundColor: 'var(--bg-tertiary)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-md)',
            padding: '12px 16px',
            display: 'flex',
            flexDirection: 'column',
            gap: '10px'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Activity size={14} className="icon-pulse" /> Live Hardware Diagnostics
              </span>
              <button
                className="btn btn-secondary icon-only"
                style={{ padding: '4px' }}
                onClick={loadResources}
                title="Refresh resource usage"
              >
                <RefreshCw size={12} />
              </button>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '10px' }}>
              {/* RAM */}
              <div style={{ backgroundColor: 'var(--bg-primary)', padding: '8px 10px', borderRadius: 'var(--radius-sm)' }}>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>System RAM (16 GB)</div>
                <div style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)', marginTop: '2px' }}>
                  {resources?.system_ram ? `${resources.system_ram.used_gb} GB used (${resources.system_ram.percent}%)` : 'Measuring...'}
                </div>
              </div>

              {/* GPU VRAM */}
              <div style={{ backgroundColor: 'var(--bg-primary)', padding: '8px 10px', borderRadius: 'var(--radius-sm)' }}>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>RTX 3050 VRAM (6 GB)</div>
                <div style={{ fontSize: '14px', fontWeight: 600, color: 'var(--accent-cyan)', marginTop: '2px' }}>
                  {resources?.gpu_vram ? `${Math.round(resources.gpu_vram.vram_used_mb)} MB / ${Math.round(resources.gpu_vram.vram_total_mb)} MB` : '39 MB (Idle)'}
                </div>
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: '4px' }}>
              <span style={{ fontSize: '11.5px', color: 'var(--text-muted)' }}>
                {unloadStatus ? unloadStatus : 'Model auto-unloads after idle period.'}
              </span>
              <button
                className="btn btn-secondary"
                style={{ fontSize: '11.5px', padding: '4px 10px' }}
                onClick={handleUnloadModel}
                title="Free GPU VRAM and process RAM immediately"
              >
                <Trash2 size={13} style={{ color: 'var(--accent-rose)' }} />
                <span>Free VRAM Now</span>
              </button>
            </div>
          </div>

          {/* Model Selection */}
          <div className="setting-group">
            <label className="setting-label">Active Local Model</label>
            <div className="input-row">
              <input
                type="text"
                className="input-field"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                placeholder="e.g. gemma4:e2b"
              />
              <button
                className="btn btn-secondary icon-only"
                onClick={onRefreshHealth}
                title="Refresh models from Ollama"
              >
                <RefreshCw size={15} />
              </button>
            </div>
            {health?.available_models && health.available_models.length > 0 && (
              <div className="available-models-chips">
                <span className="chips-label">Available:</span>
                {health.available_models.map((m) => (
                  <button
                    key={m}
                    className={`model-chip ${m === model ? 'selected' : ''}`}
                    onClick={() => setModel(m)}
                  >
                    {m}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Context Window & Memory Tuning */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '12px' }}>
            <div className="setting-group">
              <label className="setting-label">Context Window (Tokens)</label>
              <select
                className="input-field"
                value={numCtx}
                onChange={(e) => setNumCtx(parseInt(e.target.value, 10))}
              >
                <option value={2048}>2048 (Optimized for 6GB VRAM)</option>
                <option value={4096}>4096 (Standard Context)</option>
                <option value={1024}>1024 (Ultra Lightweight)</option>
              </select>
              <span className="setting-help">2048 tokens reduces memory pressure significantly.</span>
            </div>

            <div className="setting-group">
              <label className="setting-label">Idle Unload Timeout</label>
              <select
                className="input-field"
                value={keepAlive}
                onChange={(e) => setKeepAlive(e.target.value)}
              >
                <option value="2m">2 minutes (Fast VRAM release)</option>
                <option value="5m">5 minutes (Recommended balance)</option>
                <option value="15m">15 minutes (Long work session)</option>
                <option value="0s">0 seconds (Immediate unload)</option>
              </select>
              <span className="setting-help">Unloads model to free memory for games/apps.</span>
            </div>
          </div>

          <div className="setting-group">
            <label className="setting-label">Maximum Autonomous Iterations</label>
            <input
              type="number"
              min="1"
              max="50"
              className="input-field"
              value={maxIterations}
              onChange={(e) => setMaxIterations(e.target.value)}
            />
            <span className="setting-help">Caps reasoning loops per user goal.</span>
          </div>

          <div className="setting-group checkbox-group">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={confirmationRequired}
                onChange={(e) => setConfirmationRequired(e.target.checked)}
              />
              <span>Require explicit confirmation for destructive actions</span>
            </label>
            <span className="setting-help">File deletion and process termination require approval.</span>
          </div>

          <div className="setting-group diagnostic-section">
            <label className="setting-label">Model Connectivity & Latency Test</label>
            <div className="diagnostic-row">
              <button
                className="btn btn-secondary"
                onClick={handlePing}
                disabled={pingLoading}
              >
                {pingLoading ? 'Testing...' : 'Send Test Inference'}
              </button>
              {pingStatus && (
                <div className={`ping-result ${pingStatus.success ? 'success' : 'error'}`}>
                  {pingStatus.success ? <CheckCircle size={16} /> : <AlertCircle size={16} />}
                  <span>{pingStatus.message}</span>
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="modal-footer">
          <button className="btn btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button className="btn btn-primary" onClick={handleSave}>
            Save Changes
          </button>
        </div>
      </div>
    </div>
  )
}
