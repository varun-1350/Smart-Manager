import React from 'react'
import { Plus, MessageSquare, Shield, Settings, HardDrive, Terminal } from 'lucide-react'

export default function Sidebar({
  conversations,
  activeId,
  onSelectConversation,
  onNewConversation,
  onOpenSettings,
  health
}) {
  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <div className="app-branding">
          <div className="app-logo">
            <Terminal size={20} className="logo-icon" />
          </div>
          <div className="app-title-group">
            <h1 className="app-title">Smart Manager</h1>
            <span className="app-badge">Local Agent</span>
          </div>
        </div>
        <button className="new-chat-btn" onClick={onNewConversation} title="Start new conversation">
          <Plus size={16} />
          <span>New Task</span>
        </button>
      </div>

      <div className="sidebar-history-container">
        <div className="history-label">Tasks & History</div>
        <div className="history-list">
          {conversations.length === 0 ? (
            <div className="empty-history">No conversations yet</div>
          ) : (
            conversations.map((conv) => (
              <button
                key={conv.id}
                className={`history-item ${conv.id === activeId ? 'active' : ''}`}
                onClick={() => onSelectConversation(conv.id)}
              >
                <MessageSquare size={15} className="history-icon" />
                <span className="history-title">{conv.title || 'Untitled Task'}</span>
              </button>
            ))
          )}
        </div>
      </div>

      <div className="sidebar-footer">
        <div className="model-status-card">
          <div className="status-indicator-row">
            <span
              className={`status-dot ${health?.ollama_connected ? 'online' : 'offline'}`}
            />
            <span className="status-text">
              {health?.ollama_connected ? health.active_model : 'Ollama Offline'}
            </span>
          </div>
          <div className="status-subtext">
            {health?.ollama_connected ? 'Local Engine Ready' : 'Daemon unreachable'}
          </div>
        </div>

        <div className="footer-actions">
          <button className="footer-btn" onClick={onOpenSettings} title="Settings">
            <Settings size={17} />
            <span>Settings</span>
          </button>
        </div>
      </div>
    </aside>
  )
}
