import React, { useState } from 'react'
import {
  User,
  Bot,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Clock,
  ChevronDown,
  ChevronRight,
  Terminal,
  Folder,
  Globe,
  Play,
  Copy,
  Check
} from 'lucide-react'

function getActionIcon(toolName) {
  if (toolName?.startsWith('fs_')) return <Folder size={14} className="action-type-icon fs" />
  if (toolName?.startsWith('browser_')) return <Globe size={14} className="action-type-icon web" />
  if (toolName?.startsWith('proc_') || toolName?.startsWith('shell_')) return <Terminal size={14} className="action-type-icon shell" />
  return <Play size={14} className="action-type-icon default" />
}

function actionLabel(toolName) {
  const labels = {
    fs_make_dir: 'Create folder', fs_write_text_file: 'Create text file',
    fs_delete_file: 'Delete item', fs_copy_file: 'Copy item', fs_move_file: 'Move item',
    fs_rename_file: 'Rename item', proc_launch: 'Open application', proc_kill: 'Close application',
  }
  return labels[toolName] || 'System action'
}

function StatusBadge({ status }) {
  const config = {
    waiting_approval: { label: 'Approval needed', icon: AlertTriangle, tone: 'warning' },
    completed: { label: 'Completed', icon: CheckCircle2, tone: 'success' },
    success: { label: 'Completed', icon: CheckCircle2, tone: 'success' },
    failed: { label: 'Needs attention', icon: XCircle, tone: 'failed' },
    cancelled: { label: 'Stopped', icon: XCircle, tone: 'muted' },
    running: { label: 'Working', icon: Clock, tone: 'working' },
  }[status] || { label: 'Planned', icon: Clock, tone: 'muted' }
  const Icon = config.icon
  return <span className={`plan-status-badge status-${config.tone}`} title={config.label} aria-label={config.label}><Icon size={14} /></span>
}

function CopyButton({ text, label = 'Copy', className = '' }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = (e) => {
    e.stopPropagation()
    if (!text) return
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }).catch(err => {
      console.error('Failed to copy to clipboard:', err)
    })
  }

  return (
    <button
      type="button"
      className={`copy-msg-btn ${className}`}
      title="Copy to clipboard"
      aria-label={copied ? 'Copied' : 'Copy message'}
      onClick={handleCopy}
    >
      {copied ? <Check size={12} className="text-emerald" /> : <Copy size={12} />}
      <span className="copy-label sr-only">{copied ? 'Copied' : label}</span>
    </button>
  )
}

export default function MessageBubble({ message }) {
  const isUser = message.role === 'user'
  const [showDetails, setShowDetails] = useState(false)

  // Extract clean plain text for the clipboard copy action
  const getCopyableContent = () => {
    if (message.content) return message.content
    if (message.plan?.summary) {
      let text = `Plan: ${message.plan.summary}\n`
      if (message.actions?.length) {
        text += message.actions.map(a => `- ${a.tool}: ${a.summary || (typeof a.result === 'object' ? JSON.stringify(a.result) : a.result || '')}`).join('\n')
      }
      return text
    }
    return ''
  }

  const copyableText = getCopyableContent()

  return (
    <div className={`message-bubble-row ${isUser ? 'user-row' : 'agent-row'}`}>
      <div className="message-avatar">
        {isUser ? <User size={18} /> : <Bot size={18} />}
      </div>

      <div className="message-bubble-content">
        <div className="message-header">
          <span className="sender-name">{isUser ? 'You' : 'Smart Manager'}</span>
          <span className="timestamp">
            {new Date(message.timestamp || Date.now()).toLocaleTimeString([], {
              hour: '2-digit',
              minute: '2-digit'
            })}
          </span>
        </div>

        {/* User Content */}
        {isUser && <div className="user-text">{message.content}</div>}

        {/* Agent Plan / Reasoning */}
        {!isUser && message.plan && (
          <div className="agent-plan-card">
            <button
              type="button"
              className="plan-header"
              onClick={() => setShowDetails(!showDetails)}
              aria-expanded={showDetails}
              aria-label={`${showDetails ? 'Hide' : 'Show'} activity details`}
            >
              <span className="plan-title">
                {showDetails ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                Activity{message.actions?.length ? ` · ${message.actions.length}` : ''}
              </span>
              <StatusBadge status={message.status} />
            </button>
            {showDetails && (
              <div className="plan-body">
                <p className="plan-summary">{message.plan.summary}</p>
              </div>
            )}
          </div>
        )}

        {/* Action Timeline */}
        {!isUser && message.actions && message.actions.length > 0 && showDetails && (
          <div className="action-timeline">
            {message.actions.map((act, idx) => (
              <div key={idx} className={`timeline-item ${act.status}`}>
                <div className="timeline-node">
                  {act.status === 'success' && <CheckCircle2 size={15} className="status-icon success" />}
                  {act.status === 'failed' && <XCircle size={15} className="status-icon failed" />}
                  {act.status === 'pending' && <Clock size={15} className="status-icon pending" />}
                  {act.status === 'waiting_approval' && <AlertTriangle size={15} className="status-icon warning" />}
                </div>
                <div className="timeline-content">
                  <div className="timeline-title-row">
                    {getActionIcon(act.tool)}
                    <span className="action-tool-name">{actionLabel(act.tool)}</span>
                    <span className="action-time">{act.duration_ms ? `${act.duration_ms}ms` : ''}</span>
                  </div>
                  {act.summary && <div className="action-desc">{act.summary}</div>}
                  {act.result && (
                    <div className="action-result-box">
                      <div className="action-result-header">
                        <span className="action-result-tag">Result</span>
                        <CopyButton
                          text={typeof act.result === 'object' ? JSON.stringify(act.result, null, 2) : String(act.result)}
                          label="Copy"
                          className="action-copy-btn"
                        />
                      </div>
                      <pre>{typeof act.result === 'object' ? JSON.stringify(act.result, null, 2) : act.result}</pre>
                    </div>
                  )}
                  {act.error && !act.error.includes('WAITING_APPROVAL') && <div className="action-error-box">{act.error}</div>}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Agent Final Output Text */}
        {!isUser && message.content && (
          <div className="agent-text markdown-body">
            {message.content}
          </div>
        )}

        {copyableText && (
          <div className="message-actions">
            <CopyButton text={copyableText} label="Copy response" className="message-copy-btn" />
          </div>
        )}
      </div>
    </div>
  )
}
