import React from 'react'
import {
  Plus,
  MessageSquare,
  Settings,
  Terminal,
  Trash2,
  Zap,
  Sparkles,
} from 'lucide-react'

export default function Sidebar({
  conversations,
  activeId,
  onSelectConversation,
  onNewConversation,
  onDeleteConversation,
  onClearAllConversations,
  onOpenSettings,
  health,
  onUnloadModel,
  isUnloading,
}) {
  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <div className="app-branding">
          <div className="app-logo">
            <img src="/logo.png" alt="Smart Manager Logo" className="app-logo-img" />
          </div>
          <div className="app-title-group">
            <h1 className="app-title">Smart Manager</h1>
            <span className="app-badge">Autonomous Agent</span>
          </div>
        </div>
        <button
          className="new-chat-btn"
          onClick={onNewConversation}
          title="Start new task"
        >
          <Plus size={16} />
          <span>New Task</span>
        </button>
      </div>

      <div className="sidebar-history-container">
        <div className="history-header-row">
          <div className="history-label">Tasks & History</div>
          {conversations.length > 0 && (
            <button
              className="history-clear-btn"
              onClick={onClearAllConversations}
              title="Clear all tasks"
            >
              <Trash2 size={12} />
              <span>Clear all</span>
            </button>
          )}
        </div>

        <div className="history-list">
          {conversations.length === 0 ? (
            <div className="empty-history">No tasks yet</div>
          ) : (
            conversations.map((conv) => (
              <div
                key={conv.id}
                className={`history-item-wrapper ${
                  conv.id === activeId ? 'active' : ''
                }`}
              >
                <button
                  className="history-item-btn"
                  onClick={() => onSelectConversation(conv.id)}
                  title={conv.title || 'Untitled Task'}
                >
                  <MessageSquare size={14} className="history-icon" />
                  <span className="history-title">
                    {conv.title || 'Untitled Task'}
                  </span>
                </button>
                <button
                  className="history-delete-btn"
                  onClick={(e) => {
                    e.stopPropagation()
                    onDeleteConversation(conv.id)
                  }}
                  title="Delete this task"
                >
                  <Trash2 size={13} />
                </button>
              </div>
            ))
          )}
        </div>
      </div>

      <div className="sidebar-footer">
        {/* RAM Minimizer Widget */}
        <div className="ram-optimizer-card">
          <div className="ram-status-row">
            <div className="ram-label-wrap">
              <Zap size={14} className="ram-zap-icon" />
              <span className="ram-label">RAM Minimizer</span>
            </div>
            <button
              className={`ram-purge-quick-btn ${isUnloading ? 'loading' : ''}`}
              onClick={onUnloadModel}
              disabled={isUnloading}
              title="Purge model from memory to free ~3 GB RAM immediately"
            >
              <span>{isUnloading ? 'Freeing...' : 'Free 3GB RAM'}</span>
            </button>
          </div>
          <div className="ram-subtext">Auto-unload active for minimal memory</div>
        </div>

        {/* Model Status Card */}
        <div className="model-status-card">
          <div className="status-indicator-row">
            <span
              className={`status-dot ${
                health?.ollama_connected || health?.provider_mode === 'online' ? 'online pulse-green' : 'offline'
              }`}
            />
            <span className="status-text" title={health?.active_provider_label || health?.active_model}>
              {health?.active_provider_label || health?.active_model || 'Local Engine'}
            </span>
          </div>
          <div className="status-subtext">
            {health?.active_provider_label ? 'ACTIVE MODEL' : 'LOCAL AI READY'}
          </div>
        </div>

        <div className="footer-actions">
          <button
            className="footer-btn"
            onClick={onOpenSettings}
            title="Settings & Hardware"
          >
            <Settings size={16} />
            <span>Settings</span>
          </button>
        </div>
      </div>
    </aside>
  )
}
