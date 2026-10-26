import React from 'react'
import { X, FileText, Calendar, HardDrive, Tag, ExternalLink } from 'lucide-react'

export default function FilePreviewModal({ previewData, onClose, onOpenWithSystem }) {
  if (!previewData) return null

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-card preview-modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="preview-modal-header">
          <div className="preview-title-wrap">
            <FileText size={20} className="preview-file-icon" />
            <div>
              <h3>{previewData.name}</h3>
              <span className="preview-path-text" title={previewData.path}>
                {previewData.path}
              </span>
            </div>
          </div>
          <button className="modal-close-btn" onClick={onClose} title="Close preview">
            <X size={18} />
          </button>
        </div>

        {/* Metadata badges */}
        <div className="preview-meta-row">
          <div className="meta-pill">
            <HardDrive size={13} />
            <span>{previewData.size_formatted}</span>
          </div>
          <div className="meta-pill">
            <Tag size={13} />
            <span>{previewData.category?.toUpperCase() || 'FILE'}</span>
          </div>
          <div className="meta-pill">
            <Calendar size={13} />
            <span>{previewData.modified ? new Date(previewData.modified).toLocaleString() : '--'}</span>
          </div>
        </div>

        {/* Content Area */}
        <div className="preview-content-box">
          {previewData.preview_type === 'text' && previewData.content ? (
            <pre className="preview-text-pre">{previewData.content}</pre>
          ) : (
            <div className="preview-binary-placeholder">
              <FileText size={48} />
              <p>Binary or media file preview is not displayed directly in text mode.</p>
              <button
                className="btn btn-primary"
                onClick={() => {
                  onOpenWithSystem(previewData.path)
                  onClose()
                }}
              >
                <ExternalLink size={14} />
                <span>Open in Default Windows App</span>
              </button>
            </div>
          )}
        </div>

        <div className="modal-actions preview-footer">
          <button className="btn btn-secondary" onClick={onClose}>
            Close
          </button>
          <button
            className="btn btn-primary"
            onClick={() => {
              onOpenWithSystem(previewData.path)
              onClose()
            }}
          >
            <ExternalLink size={14} />
            <span>Open File</span>
          </button>
        </div>
      </div>
    </div>
  )
}
