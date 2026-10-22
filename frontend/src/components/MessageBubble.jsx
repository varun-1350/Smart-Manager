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
  Play
} from 'lucide-react'

function getActionIcon(toolName) {
  if (toolName?.startsWith('fs_')) return <Folder size={14} className="action-type-icon fs" />
  if (toolName?.startsWith('browser_')) return <Globe size={14} className="action-type-icon web" />
  if (toolName?.startsWith('proc_') || toolName?.startsWith('shell_')) return <Terminal size={14} className="action-type-icon shell" />
  return <Play size={14} className="action-type-icon default" />
}

export default function MessageBubble({ message }) {
  const isUser = message.role === 'user'
  const [showDetails, setShowDetails] = useState(true)

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
            <div className="plan-header" onClick={() => setShowDetails(!showDetails)}>
              <span className="plan-title">
                {showDetails ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                Execution Plan ({message.actions?.length || 0} actions)
              </span>
              <span className="plan-status-badge">{message.status || 'in_progress'}</span>
            </div>
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
                    <span className="action-tool-name">{act.tool}</span>
                    <span className="action-time">{act.duration_ms ? `${act.duration_ms}ms` : ''}</span>
                  </div>
                  {act.summary && <div className="action-desc">{act.summary}</div>}
                  {act.result && (
                    <div className="action-result-box">
                      <pre>{typeof act.result === 'object' ? JSON.stringify(act.result, null, 2) : act.result}</pre>
                    </div>
                  )}
                  {act.error && <div className="action-error-box">{act.error}</div>}
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
      </div>
    </div>
  )
}
