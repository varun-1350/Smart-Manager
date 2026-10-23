import React, { useState } from 'react'
import { Check, ChevronDown, ChevronUp, FolderPlus, ShieldCheck, X } from 'lucide-react'

function describeAction(request) {
  const path = request.parameters?.path || request.parameters?.dst
  if (request.tool === 'fs_make_dir') return `Create the folder “${path?.split(/[\\/]/).pop() || 'New Folder'}”${path ? ` in ${path.replace(/[\\/][^\\/]+$/, '')}` : ''}?`
  if (request.tool === 'fs_delete_file') return `Delete “${path?.split(/[\\/]/).pop() || 'this item'}”?`
  return request.description || 'Allow Smart Manager to make this change?'
}

export default function ConfirmationModal({ request, onApprove, onReject }) {
  if (!request) return null
  const [showDetails, setShowDetails] = useState(false)

  return (
    <div className="modal-overlay">
      <section className="confirmation-modal" role="dialog" aria-modal="true" aria-labelledby="approval-title">
        <div className="approval-hero">
          <div className="modal-icon-wrap approval">
            <FolderPlus size={22} />
          </div>
          <div className="modal-title-wrap">
            <p className="eyebrow">Approval needed</p>
            <h3 className="modal-title" id="approval-title">Review this change</h3>
          </div>
        </div>

        <div className="modal-body">
          <p className="approval-question">{describeAction(request)}</p>
          <div className="approval-notice">
            <ShieldCheck size={17} />
            <span>No changes have been made yet.</span>
          </div>
          <button className="technical-details-toggle" type="button" onClick={() => setShowDetails(!showDetails)} aria-expanded={showDetails}>
            Technical details {showDetails ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </button>
          {showDetails && <pre className="approval-details">{JSON.stringify({ action: request.tool, parameters: request.parameters }, null, 2)}</pre>}
        </div>

        <div className="modal-footer">
          <button className="btn btn-secondary" onClick={onReject}>
            <X size={16} />
            <span>Cancel</span>
          </button>
          <button className="btn btn-primary" onClick={onApprove}>
            <Check size={16} />
            <span>{request.tool === 'fs_make_dir' ? 'Create folder' : 'Approve change'}</span>
          </button>
        </div>
      </section>
    </div>
  )
}
