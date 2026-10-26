import React, { useState, useRef, useEffect } from 'react'
import {
  Send,
  Loader2,
  Square,
  Sparkles,
  Plus,
  Trash2,
  RotateCcw,
  CheckCircle2,
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  ShieldAlert,
  ArrowRight,
  X,
  Bot,
  User,
  Check,
  Copy,
  Layers,
  Folder,
} from 'lucide-react'
import MessageBubble from './MessageBubble'

export default function AiChatAssistant({
  currentPath,
  selectedPaths,
  onClearSelectedPaths,
  conversations,
  activeId,
  onSelectConversation,
  onNewConversation,
  onClearAllConversations,
  messages,
  onSendMessage,
  isLoading,
  onStopTask,
  health,
  planPreview,
  onExecutePlan,
  onClearPlan,
  isExecutingPlan,
  executionResult,
  canUndo,
  onUndo,
}) {
  const [inputPrompt, setInputPrompt] = useState('')
  const [showPlanDetails, setShowPlanDetails] = useState(false)
  const [showSessionPicker, setShowSessionPicker] = useState(false)
  const textareaRef = useRef(null)
  const messagesEndRef = useRef(null)

  // Auto-scroll to bottom of conversation
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, planPreview, isLoading, isExecutingPlan])

  const handleSubmit = (e) => {
    e?.preventDefault()
    if (!inputPrompt.trim() || isLoading || isExecutingPlan) return
    onSendMessage(inputPrompt.trim())
    setInputPrompt('')
  }

  // Adjust textarea height dynamically
  const handleTextareaChange = (e) => {
    setInputPrompt(e.target.value)
    const el = textareaRef.current
    if (el) {
      el.style.height = 'auto'
      el.style.height = `${Math.min(el.scrollHeight, 120)}px`
    }
  }

  const activeFolderName = currentPath ? currentPath.split('\\').pop() || currentPath : 'Workspace'
  const selectedCount = selectedPaths?.size || 0

  return (
    <div className="ai-chat-assistant-root">
      {/* 1. Compact Panel Header */}
      <header className="assistant-panel-header">
        <div className="assistant-header-title-wrap">
          <Sparkles size={15} className="assistant-header-sparkle" />
          <h2 className="assistant-header-title">AI Assistant</h2>
          <span className="assistant-scope-tag" title={currentPath}>
            {activeFolderName}
          </span>
        </div>

        <div className="assistant-header-actions">
          {/* New Conversation Button */}
          <button
            type="button"
            className="assistant-header-btn"
            onClick={onNewConversation}
            title="Start a new task or conversation"
          >
            <Plus size={14} />
            <span>New Task</span>
          </button>
        </div>
      </header>

      {/* 2. Scrollable Conversation Thread */}
      <div className="assistant-thread-viewport">
        {messages.length === 0 && !planPreview ? (
          /* Clean Professional Empty State without Suggested Chips */
          <div className="assistant-empty-state">
            <div className="empty-state-icon">
              <Bot size={28} />
            </div>
            <h3 className="empty-state-title">How can I help with your files?</h3>
            <p className="empty-state-subtitle">
              Ask questions, summarize, search, or request file operations in <strong>{activeFolderName}</strong> using natural language.
            </p>
          </div>
        ) : (
          /* Messages List */
          <div className="assistant-messages-list">
            {messages.map((m) => (
              <MessageBubble key={m.id || m.timestamp} message={m} />
            ))}
          </div>
        )}

        {/* Structured File Operation Review Card */}
        {planPreview && (
          <div className="file-plan-review-card">
            <div className="plan-card-header">
              <div className="plan-card-title-group">
                <Layers size={16} className="plan-title-icon" />
                <div>
                  <h4 className="plan-card-title">{planPreview.summary || 'Proposed File Operations'}</h4>
                  <span className="plan-scope-text">
                    Target: {planPreview.target_directory || currentPath}
                  </span>
                </div>
              </div>

              <div className="plan-badge-group">
                <span className={`plan-risk-badge risk-${planPreview.risk_level || 'medium'}`}>
                  {planPreview.risk_level?.toUpperCase() || 'MEDIUM'} RISK
                </span>
                <span className="plan-count-badge">
                  {planPreview.total_affected || planPreview.actions?.length || 0} files
                </span>
              </div>
            </div>

            {/* Conflict or Warning Alert */}
            {planPreview.conflicts?.length > 0 && (
              <div className="plan-alert-banner warning">
                <AlertTriangle size={15} />
                <span>
                  {planPreview.conflicts.length} naming collision(s) detected. Collision counters will be applied safely.
                </span>
              </div>
            )}

            {/* Proposed Category Breakdown Summary */}
            {planPreview.actions?.length > 0 && (
              <div className="plan-summary-list">
                {/* Group actions by destination folder for clean overview */}
                {Object.entries(
                  planPreview.actions.reduce((acc, act) => {
                    const destDir = act.dest_path ? act.dest_path.substring(0, act.dest_path.lastIndexOf('\\')) : 'Target'
                    const folderName = destDir.split('\\').pop() || 'Target'
                    acc[folderName] = (acc[folderName] || 0) + 1
                    return acc
                  }, {})
                ).map(([folder, count]) => (
                  <div key={folder} className="plan-summary-row">
                    <span className="plan-summary-count">{count} {count === 1 ? 'file' : 'files'}</span>
                    <ArrowRight size={12} className="plan-arrow-icon" />
                    <span className="plan-summary-dest">/{folder}/</span>
                  </div>
                ))}
              </div>
            )}

            {/* Expandable File-by-File Details */}
            <div className="plan-details-toggle-row">
              <button
                type="button"
                className="plan-details-btn"
                onClick={() => setShowPlanDetails(!showPlanDetails)}
              >
                {showPlanDetails ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                <span>{showPlanDetails ? 'Hide file details' : 'View affected files'}</span>
              </button>
            </div>

            {showPlanDetails && (
              <div className="plan-file-details-table">
                {planPreview.actions?.map((act, i) => (
                  <div key={i} className="plan-file-item-row">
                    <span className="plan-action-badge">{act.action_type || 'move'}</span>
                    <span className="plan-file-name" title={act.src_path}>
                      {act.src_path.split('\\').pop()}
                    </span>
                    <ArrowRight size={12} className="plan-arrow-icon" />
                    <span className="plan-file-dest" title={act.dest_path}>
                      {act.dest_path.split('\\').pop()}
                    </span>
                  </div>
                ))}
              </div>
            )}

            {/* Execution / Result Feedback */}
            {executionResult && (
              <div className="plan-result-banner">
                <CheckCircle2 size={16} className="text-emerald" />
                <span>{executionResult.message || `Successfully processed ${executionResult.count || 'all'} files`}</span>
              </div>
            )}

            {/* Action Buttons */}
            <div className="plan-card-actions">
              <button
                type="button"
                className="plan-btn plan-btn-cancel"
                onClick={onClearPlan}
                disabled={isExecutingPlan}
              >
                Cancel
              </button>

              <button
                type="button"
                className="plan-btn plan-btn-approve"
                onClick={onExecutePlan}
                disabled={isExecutingPlan}
              >
                {isExecutingPlan ? (
                  <>
                    <Loader2 size={14} className="spinning" />
                    <span>Executing changes...</span>
                  </>
                ) : (
                  <>
                    <Check size={14} />
                    <span>Approve & Execute</span>
                  </>
                )}
              </button>
            </div>
          </div>
        )}

        {/* Working / Spinner State */}
        {isLoading && (
          <div className="assistant-busy-row">
            <div className="busy-spinner-wrap">
              <Loader2 size={16} className="spinning text-accent" />
            </div>
            <div className="busy-text-wrap">
              <span className="busy-title">Processing request</span>
              <span className="busy-subtitle">Analyzing files in {activeFolderName}...</span>
            </div>
            {onStopTask && (
              <button type="button" className="busy-stop-btn" onClick={onStopTask} title="Stop execution">
                <Square size={12} />
                <span>Stop</span>
              </button>
            )}
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* 3. Fixed Bottom Composer */}
      <footer className="assistant-composer-wrapper">
        {/* Context Attachment Indicator */}
        <div className="composer-context-bar">
          <div className="context-chip" title={`Current browsing folder: ${currentPath}`}>
            <Folder size={12} />
            <span className="context-chip-name">{activeFolderName}</span>
          </div>

          {selectedCount > 0 && (
            <div className="context-chip selection">
              <span>{selectedCount} selected</span>
              <button
                type="button"
                className="context-clear-btn"
                onClick={onClearSelectedPaths}
                title="Clear selected file context"
              >
                <X size={11} />
              </button>
            </div>
          )}
        </div>

        {/* Text Input Container */}
        <form className="composer-form" onSubmit={handleSubmit}>
          <textarea
            ref={textareaRef}
            className="composer-textarea"
            rows={1}
            placeholder={
              selectedCount > 0
                ? `Ask about ${selectedCount} selected files or describe what to do...`
                : `Describe a file task for ${activeFolderName}...`
            }
            value={inputPrompt}
            onChange={handleTextareaChange}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                handleSubmit()
              }
            }}
            disabled={isLoading || isExecutingPlan}
          />

          <button
            type="submit"
            className="composer-send-btn"
            disabled={!inputPrompt.trim() || isLoading || isExecutingPlan}
            title="Send message (Enter)"
          >
            {isLoading || isExecutingPlan ? (
              <Loader2 size={15} className="spinning" />
            ) : (
              <Send size={15} />
            )}
          </button>
        </form>
      </footer>
    </div>
  )
}
