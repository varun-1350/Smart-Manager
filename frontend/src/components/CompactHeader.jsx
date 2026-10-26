import React, { useState } from 'react'
import {
  Settings,
  RotateCcw,
  Zap,
  Loader2,
  HardDrive,
  Cpu,
} from 'lucide-react'
import logoAsset from '../assets/logo.png'

export default function CompactHeader({
  health,
  onOpenSettings,
  onUnloadModel,
  isUnloading,
  canUndo,
  onUndo,
}) {
  const [logoError, setLogoError] = useState(false)

  const providerLabel =
    health?.active_provider_label ||
    (health?.ai_mode === 'online' ? 'Online AI' : 'Local AI') ||
    'Connecting...'

  const modelLabel = health?.active_model || ''
  const isHealthy = health?.status === 'ok' || health?.status === 'degraded'

  return (
    <header className="compact-app-header">
      {/* 1. Left: Brand Title & Logo */}
      <div className="header-brand-section">
        {!logoError ? (
          <img
            src={logoAsset}
            alt="Smart Manager"
            className="header-brand-logo"
            onError={() => setLogoError(true)}
          />
        ) : (
          <div className="header-brand-icon">SM</div>
        )}
        <div className="header-title-wrap">
          <span className="header-app-title">Smart Manager</span>
          <span className="header-app-subtitle">File Explorer</span>
        </div>
      </div>

      {/* 2. Right: AI Status & Utilities */}
      <div className="header-controls-section">
        {/* Model Status Pill */}
        <div
          className={`header-status-pill ${isHealthy ? 'status-online' : 'status-offline'}`}
          title={`Provider: ${providerLabel}${modelLabel ? ` (${modelLabel})` : ''}`}
        >
          <span className="status-indicator-dot" />
          <span className="status-provider-text">{providerLabel}</span>
          {modelLabel && <span className="status-model-text">{modelLabel}</span>}
        </div>

        {/* Undo Button (Active if operations can be reversed) */}
        {canUndo && (
          <button
            type="button"
            className="header-btn header-btn-undo"
            onClick={onUndo}
            title="Undo last file operation (Ctrl+Z)"
          >
            <RotateCcw size={14} />
            <span>Undo</span>
          </button>
        )}

        {/* Free Memory / Unload Model Button */}
        <button
          type="button"
          className="header-btn header-btn-unload"
          onClick={onUnloadModel}
          disabled={isUnloading}
          title="Unload AI model weights to free RAM/VRAM"
        >
          {isUnloading ? (
            <Loader2 size={14} className="spinning" />
          ) : (
            <Cpu size={14} />
          )}
          <span>Free Memory</span>
        </button>

        {/* Settings Button */}
        <button
          type="button"
          className="header-btn header-btn-settings"
          onClick={onOpenSettings}
          title="Open Application Settings"
          aria-label="Settings"
        >
          <Settings size={15} />
        </button>
      </div>
    </header>
  )
}
