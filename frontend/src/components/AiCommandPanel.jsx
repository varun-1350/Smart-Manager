import React, { useState } from 'react'
import {
  Sparkles,
  Send,
  Loader2,
  CheckCircle2,
  AlertTriangle,
  RotateCcw,
  ArrowRight,
  ShieldAlert,
  FileQuestion,
  X,
  Play,
  Layers,
} from 'lucide-react'

export default function AiCommandPanel({
  currentPath,
  onGeneratePlan,
  onExecutePlan,
  onUndo,
  isGeneratingPlan,
  isExecutingPlan,
  planPreview,
  onClearPlan,
  lastOperation,
  executionResult,
}) {
  const [prompt, setPrompt] = useState('')

  const quickPrompts = [
    'Organize files by file type',
    'Find duplicate files in this folder',
    'Find large files taking up space',
    'Clean up empty folders and temp files',
  ]

  const handleSubmit = (e) => {
    e?.preventDefault()
    if (!prompt.trim() || isGeneratingPlan) return
    onGeneratePlan(prompt.trim())
  }

  const handleQuickPrompt = (q) => {
    setPrompt(q)
    onGeneratePlan(q)
  }

  return (
    <div className="ai-command-panel">
      {/* 1. Header & Context */}
      <div className="command-panel-header">
        <div className="command-title-wrap">
          <Sparkles size={16} className="sparkle-icon" />
          <h3>AI File Assistant</h3>
        </div>
        <div className="current-scope-badge" title={currentPath}>
          Scope: <span>{currentPath ? currentPath.split('\\').pop() || currentPath : 'Current Folder'}</span>
        </div>
      </div>

      {/* 2. Natural Language Prompt Bar */}
      <form onSubmit={handleSubmit} className="command-input-form">
        <div className="command-input-wrap">
          <input
            type="text"
            className="command-input"
            placeholder="Describe a file task (e.g. 'Organize this folder by type', 'Find duplicates')..."
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            disabled={isGeneratingPlan || isExecutingPlan}
          />
          <button
            type="submit"
            className="command-submit-btn"
            disabled={!prompt.trim() || isGeneratingPlan || isExecutingPlan}
            title="Generate Action Plan"
          >
            {isGeneratingPlan ? <Loader2 size={16} className="spinning" /> : <Send size={15} />}
          </button>
        </div>

        {/* Quick Suggestion Chips */}
        {!planPreview && (
          <div className="quick-prompts-row">
            {quickPrompts.map((q) => (
              <button
                key={q}
                type="button"
                className="prompt-chip"
                onClick={() => handleQuickPrompt(q)}
                disabled={isGeneratingPlan || isExecutingPlan}
              >
                {q}
              </button>
            ))}
          </div>
        )}
      </form>

      {/* 3. Generating Plan Loading State */}
      {isGeneratingPlan && (
        <div className="plan-loading-card">
          <Loader2 size={24} className="spinning plan-spinner" />
          <div className="plan-loading-text">
            <strong>Analyzing directory & preparing action plan...</strong>
            <span>Validating paths and security risk levels</span>
          </div>
        </div>
      )}

      {/* 4. Structured Plan Preview Card (Human-in-the-Loop Decision) */}
      {planPreview && (
        <div className="plan-preview-card">
          <div className="plan-header">
            <div className="plan-header-title">
              <Layers size={18} className="plan-icon" />
              <h4>Proposed Action Plan</h4>
            </div>
            <button className="plan-close-btn" onClick={onClearPlan} title="Dismiss plan">
              <X size={15} />
            </button>
          </div>

          <p className="plan-summary">{planPreview.summary}</p>

          {/* Conflict Warning if any */}
          {planPreview.conflicts?.length > 0 && (
            <div className="plan-alert-box conflict-alert">
              <AlertTriangle size={16} className="alert-icon" />
              <div>
                <strong>{planPreview.conflicts.length} destination conflict(s) detected:</strong>
                <ul>
                  {planPreview.conflicts.map((c, i) => (
                    <li key={i}>{c.conflict || c.destination}</li>
                  ))}
                </ul>
              </div>
            </div>
          )}

          {/* Action List Preview Table */}
          <div className="plan-actions-list">
            <div className="plan-actions-header">
              <span>Proposed Changes ({planPreview.actions?.length || 0})</span>
            </div>
            <div className="plan-actions-scroll">
              {planPreview.actions?.map((act) => (
                <div key={act.id} className="plan-action-row">
                  <div className="action-type-badge">{act.tool.replace('fs_', '').replace('_file', '')}</div>
                  <div className="action-paths">
                    <span className="source-path" title={act.source}>
                      {act.source.split('\\').pop()}
                    </span>
                    {act.destination && (
                      <>
                        <ArrowRight size={13} className="arrow-icon" />
                        <span className="dest-path" title={act.destination}>
                          {act.destination.split('\\').slice(-2).join('/')}
                        </span>
                      </>
                    )}
                  </div>
                  <div className={`risk-badge risk-${act.risk_level}`}>{act.risk_level}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Skipped Files */}
          {planPreview.skipped_files?.length > 0 && (
            <div className="plan-skipped-section">
              <div className="skipped-header">
                <FileQuestion size={14} />
                <span>Unchanged Files ({planPreview.skipped_files.length})</span>
              </div>
              <div className="skipped-list">
                {planPreview.skipped_files.slice(0, 5).map((s, idx) => (
                  <span key={idx} className="skipped-item" title={s.reason}>
                    {s.file}
                  </span>
                ))}
                {planPreview.skipped_files.length > 5 && (
                  <span className="skipped-more">+{planPreview.skipped_files.length - 5} more</span>
                )}
              </div>
            </div>
          )}

          {/* Plan Approval Actions */}
          <div className="plan-decision-actions">
            <button
              className="btn btn-secondary"
              onClick={onClearPlan}
              disabled={isExecutingPlan}
            >
              Cancel
            </button>
            <button
              className="btn btn-primary btn-execute"
              onClick={onExecutePlan}
              disabled={isExecutingPlan || planPreview.actions?.length === 0}
            >
              {isExecutingPlan ? (
                <>
                  <Loader2 size={15} className="spinning" />
                  <span>Executing Plan...</span>
                </>
              ) : (
                <>
                  <Play size={14} />
                  <span>Approve & Execute ({planPreview.actions?.length || 0} changes)</span>
                </>
              )}
            </button>
          </div>
        </div>
      )}

      {/* 5. Last Execution Result & Undo Status */}
      {executionResult && (
        <div className="execution-result-card">
          <div className="result-header">
            <CheckCircle2 size={16} className="result-success-icon" />
            <span>Operation Complete ({executionResult.executed_count} files processed)</span>
          </div>
          <button className="btn-undo-action" onClick={onUndo} title="Undo this batch operation">
            <RotateCcw size={14} />
            <span>Undo Changes</span>
          </button>
        </div>
      )}
    </div>
  )
}
