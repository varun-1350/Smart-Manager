import React from 'react'
import { AlertTriangle, ShieldAlert, Check, X } from 'lucide-react'

export default function ConfirmationModal({ request, onApprove, onReject }) {
  if (!request) return null

  return (
    <div className="modal-overlay">
      <div className="confirmation-modal">
        <div className="modal-header warning">
          <div className="modal-icon-wrap warning">
            <AlertTriangle size={24} />
          </div>
          <div className="modal-title-wrap">
            <h3 className="modal-title">Action Approval Required</h3>
            <span className="risk-level-badge risk-high">
              {request.risk_level || 'HIGH RISK'}
            </span>
          </div>
        </div>

        <div className="modal-body">
          <p className="modal-description">
            The agent proposes to execute an action that modifies your system:
          </p>
          <div className="action-details-card">
            <div className="detail-row">
              <span className="detail-label">Action:</span>
              <span className="detail-value tool-tag">{request.tool}</span>
            </div>
            <div className="detail-row">
              <span className="detail-label">Description:</span>
              <span className="detail-value">{request.description || 'No description provided'}</span>
            </div>
            <div className="detail-row parameters">
              <span className="detail-label">Parameters:</span>
              <div className="params-code-block">
                <pre>{JSON.stringify(request.parameters, null, 2)}</pre>
              </div>
            </div>
          </div>
          <div className="modal-warning-notice">
            <ShieldAlert size={16} />
            <span>Review parameters carefully before authorizing execution.</span>
          </div>
        </div>

        <div className="modal-footer">
          <button className="btn btn-secondary" onClick={() => onReject(request.id)}>
            <X size={16} />
            <span>Deny & Cancel</span>
          </button>
          <button className="btn btn-danger" onClick={() => onApprove(request.id)}>
            <Check size={16} />
            <span>Authorize Action</span>
          </button>
        </div>
      </div>
    </div>
  )
}
