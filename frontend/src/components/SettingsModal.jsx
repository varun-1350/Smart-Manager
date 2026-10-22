import React, { useState } from 'react'
import { X, RefreshCw, CheckCircle, AlertCircle, Cpu } from 'lucide-react'
import { pingModel } from '../services/api'

export default function SettingsModal({
  isOpen,
  onClose,
  config,
  onSaveConfig,
  health,
  onRefreshHealth
}) {
  if (!isOpen) return null

  const [model, setModel] = useState(config?.ollama_model || 'gemma2:2b')
  const [maxIterations, setMaxIterations] = useState(config?.max_iterations || 15)
  const [confirmationRequired, setConfirmationRequired] = useState(
    config?.confirmation_required ?? true
  )
  const [pingStatus, setPingStatus] = useState(null)
  const [pingLoading, setPingLoading] = useState(false)

  const handlePing = async () => {
    setPingLoading(true)
    setPingStatus(null)
    try {
      const res = await pingModel('Test ping: respond with pong')
      setPingStatus({
        success: true,
        message: `Response in ${res.total_duration_ms}ms: "${res.response}"`
      })
    } catch (err) {
      setPingStatus({
        success: false,
        message: `Inference failed: ${err.message}`
      })
    } finally {
      setPingLoading(false)
    }
  }

  const handleSave = () => {
    onSaveConfig({
      ollama_model: model,
      max_iterations: parseInt(maxIterations, 10),
      confirmation_required: confirmationRequired
    })
    onClose()
  }

  return (
    <div className="modal-overlay">
      <div className="settings-modal">
        <div className="modal-header">
          <div className="modal-title-wrap">
            <Cpu size={20} className="modal-header-icon" />
            <h3 className="modal-title">Agent Settings</h3>
          </div>
          <button className="close-btn" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        <div className="modal-body">
          <div className="setting-group">
            <label className="setting-label">Active Local Model</label>
            <div className="input-row">
              <input
                type="text"
                className="input-field"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                placeholder="e.g. gemma2:2b, qwen2.5:3b"
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
                <span className="chips-label">Available on system:</span>
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
            <span className="setting-help">
              Prevents endless loops by capping reasoning iterations per user goal.
            </span>
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
            <span className="setting-help">
              When checked, actions like file deletion or process termination require approval.
            </span>
          </div>

          <div className="setting-group diagnostic-section">
            <label className="setting-label">Model Connectivity & Ping</label>
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
