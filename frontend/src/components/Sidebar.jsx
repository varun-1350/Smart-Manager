import React, { useState } from 'react'
import {
  Folder,
  HardDrive,
  Monitor,
  Download,
  Image,
  Video,
  Music,
  FileText,
  RotateCcw,
  Settings,
  Zap,
  Plus,
  MessageSquare,
  Trash2,
  FolderOpen,
} from 'lucide-react'
import logoAsset from '../assets/logo.png'

export default function Sidebar({
  activeView,
  onSwitchView,
  locations,
  currentPath,
  onNavigate,
  onUndo,
  canUndo,
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
  const [hasLogoError, setHasLogoError] = useState(false)

  const quickFolders = locations?.filter((l) => l.type === 'folder') || []
  const drives = locations?.filter((l) => l.type === 'drive') || []

  const getLocationIcon = (category) => {
    switch (category) {
      case 'desktop':
        return <Monitor size={15} className="loc-icon loc-desktop" />
      case 'downloads':
        return <Download size={15} className="loc-icon loc-downloads" />
      case 'documents':
        return <FileText size={15} className="loc-icon loc-documents" />
      case 'pictures':
        return <Image size={15} className="loc-icon loc-pictures" />
      case 'videos':
        return <Video size={15} className="loc-icon loc-videos" />
      case 'music':
        return <Music size={15} className="loc-icon loc-music" />
      default:
        return <Folder size={15} className="loc-icon" />
    }
  }

  return (
    <aside className="sidebar">
      {/* 1. Header & App Branding */}
      <div className="sidebar-header">
        <div className="app-branding">
          <div className="app-logo">
            {hasLogoError ? (
              <span className="app-logo-fallback" aria-label="Smart Manager">
                SM
              </span>
            ) : (
              <img
                src={logoAsset}
                alt="Smart Manager"
                className="app-logo-img"
                onError={() => setHasLogoError(true)}
              />
            )}
          </div>
          <div className="app-title-group">
            <h1 className="app-title">Smart Manager</h1>
            <span className="app-badge">AI File Explorer</span>
          </div>
        </div>

        {/* View Switcher Tabs (Explorer vs Tasks) */}
        <div className="sidebar-view-toggle">
          <button
            className={`view-tab-btn ${activeView === 'explorer' ? 'active' : ''}`}
            onClick={() => onSwitchView('explorer')}
          >
            <FolderOpen size={14} />
            <span>Files</span>
          </button>
          <button
            className={`view-tab-btn ${activeView === 'chat' ? 'active' : ''}`}
            onClick={() => onSwitchView('chat')}
          >
            <MessageSquare size={14} />
            <span>Tasks</span>
          </button>
        </div>
      </div>

      {/* 2. Main Sidebar Content */}
      <div className="sidebar-history-container">
        {activeView === 'explorer' ? (
          <div className="explorer-sidebar-nav">
            {/* Quick Access */}
            <div className="nav-section-title">Quick Access</div>
            <div className="locations-list">
              {quickFolders.map((loc) => {
                const isActive = currentPath && currentPath.toLowerCase() === loc.path.toLowerCase()
                return (
                  <button
                    key={loc.id}
                    className={`loc-nav-item ${isActive ? 'active' : ''}`}
                    onClick={() => onNavigate(loc.path)}
                    title={loc.path}
                  >
                    {getLocationIcon(loc.category)}
                    <span className="loc-label">{loc.label}</span>
                  </button>
                )
              })}
            </div>

            {/* Storage Drives */}
            {drives.length > 0 && (
              <>
                <div className="nav-section-title">Drives & Partitions</div>
                <div className="drives-list">
                  {drives.map((drive) => {
                    const isActive = currentPath && currentPath.toLowerCase().startsWith(drive.path.toLowerCase())
                    return (
                      <button
                        key={drive.id}
                        className={`drive-nav-item ${isActive ? 'active' : ''}`}
                        onClick={() => onNavigate(drive.path)}
                        title={`${drive.path} - ${drive.free_gb} GB free of ${drive.total_gb} GB`}
                      >
                        <div className="drive-top-row">
                          <HardDrive size={15} className="drive-icon" />
                          <span className="drive-label">{drive.label}</span>
                        </div>
                        <div className="drive-progress-bar">
                          <div
                            className="drive-progress-fill"
                            style={{
                              width: `${drive.percent_used || 0}%`,
                              backgroundColor: drive.percent_used > 88 ? '#f43f5e' : '#3b82f6',
                            }}
                          />
                        </div>
                        <div className="drive-meta-text">
                          {drive.free_gb} GB free of {drive.total_gb} GB
                        </div>
                      </button>
                    )
                  })}
                </div>
              </>
            )}

            {/* Undo Available Banner */}
            {canUndo && (
              <div className="sidebar-undo-box">
                <div className="undo-box-header">
                  <RotateCcw size={14} className="text-primary" />
                  <span>Undo Available</span>
                </div>
                <p>Revert the last file organization or rename operation.</p>
                <button className="btn-undo-sidebar" onClick={onUndo}>
                  <RotateCcw size={13} />
                  <span>Undo Last Action</span>
                </button>
              </div>
            )}
          </div>
        ) : (
          /* Task / Conversation History View */
          <div className="task-history-view">
            <div className="history-header-row">
              <div className="history-label">AI Tasks</div>
              {conversations.length > 0 && (
                <button
                  className="history-clear-btn"
                  onClick={onClearAllConversations}
                  title="Clear all tasks"
                >
                  <Trash2 size={12} />
                  <span>Clear</span>
                </button>
              )}
            </div>

            <button
              className="new-chat-btn sidebar-action"
              onClick={onNewConversation}
              title="Start new task"
            >
              <Plus size={16} />
              <span>New Task</span>
            </button>

            <div className="history-list">
              {conversations.length === 0 ? (
                <div className="empty-history">No tasks yet</div>
              ) : (
                conversations.map((conv) => (
                  <div
                    key={conv.id}
                    className={`history-item-wrapper ${conv.id === activeId ? 'active' : ''}`}
                  >
                    <button
                      className="history-item-btn"
                      onClick={() => onSelectConversation(conv.id)}
                      title={conv.title || 'Untitled Task'}
                    >
                      <MessageSquare size={14} className="history-icon" />
                      <span className="history-title">{conv.title || 'Untitled Task'}</span>
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
        )}
      </div>

      {/* 3. Footer: Memory optimizer & Settings */}
      <div className="sidebar-footer">
        <div className="ram-optimizer-card">
          <div className="ram-status-row">
            <div className="ram-label-wrap">
              <Zap size={14} className="ram-zap-icon" />
              <span className="ram-label">Memory</span>
            </div>
            <button
              className={`ram-purge-quick-btn sidebar-action ${isUnloading ? 'loading' : ''}`}
              onClick={onUnloadModel}
              disabled={isUnloading}
              title="Release the local model from memory"
            >
              <span>{isUnloading ? 'Releasing…' : 'Release memory'}</span>
            </button>
          </div>
        </div>

        <div className="model-status-card model-badge">
          <div className="status-indicator-row">
            <span
              className={`status-dot ${
                health?.ollama_connected || health?.provider_mode === 'online'
                  ? 'online pulse-green'
                  : 'offline'
              }`}
            />
            <span
              className="status-text"
              title={health?.active_provider_label || health?.active_model}
            >
              {health?.active_provider_label || health?.active_model || 'Local Engine'}
            </span>
          </div>
        </div>

        <div className="footer-actions">
          <button
            className="footer-btn sidebar-action"
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
