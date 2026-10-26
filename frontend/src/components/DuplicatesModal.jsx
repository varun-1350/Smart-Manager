import React, { useState } from 'react'
import { X, CopyCheck, Trash2, CheckCircle2, AlertCircle } from 'lucide-react'

export default function DuplicatesModal({ duplicatesData, onClose, onCleanDuplicates }) {
  if (!duplicatesData) return null

  // By default, select all duplicate copies except the first (original) file in each group
  const [selectedToTrash, setSelectedToTrash] = useState(() => {
    const initSet = new Set()
    duplicatesData.duplicates?.forEach((group) => {
      // Keep the first file, mark the rest for cleanup
      group.files.slice(1).forEach((f) => initSet.add(f.path))
    })
    return initSet
  })

  const toggleSelect = (path) => {
    setSelectedToTrash((prev) => {
      const next = new Set(prev)
      if (next.has(path)) next.delete(path)
      else next.add(path)
      return next
    })
  }

  const handleClean = () => {
    const paths = Array.from(selectedToTrash)
    if (paths.length === 0) return
    if (window.confirm(`Move ${paths.length} duplicate file(s) to trash? You can undo this at any time.`)) {
      onCleanDuplicates(paths)
      onClose()
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-card duplicates-modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div className="title-with-icon">
            <CopyCheck size={20} className="dup-icon" />
            <div>
              <h3>Exact Duplicate Files (SHA-256)</h3>
              <span className="subtitle">
                Found {duplicatesData.duplicate_groups_count} group(s) &bull;{' '}
                <strong>{duplicatesData.total_wasted_formatted}</strong> wasted space
              </span>
            </div>
          </div>
          <button className="modal-close-btn" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        <div className="duplicates-content-area">
          {duplicatesData.duplicates?.length === 0 ? (
            <div className="no-duplicates-state">
              <CheckCircle2 size={36} className="text-success" />
              <h4>No duplicate files found in this folder!</h4>
              <p>All scanned files have unique cryptographic hashes.</p>
            </div>
          ) : (
            duplicatesData.duplicates.map((group, idx) => (
              <div key={group.hash} className="duplicate-group-card">
                <div className="duplicate-group-header">
                  <span className="group-badge">Group #{idx + 1}</span>
                  <span className="group-size">Size: {group.size_formatted} each</span>
                  <span className="group-wasted">Wastes {group.wasted_bytes > 1024 * 1024 ? `${round(group.wasted_bytes / (1024 * 1024), 1)} MB` : `${round(group.wasted_bytes / 1024, 1)} KB`}</span>
                </div>

                <div className="duplicate-files-list">
                  {group.files.map((file, fileIdx) => {
                    const isSelected = selectedToTrash.has(file.path)
                    const isOriginal = fileIdx === 0
                    return (
                      <div
                        key={file.path}
                        className={`duplicate-file-row ${isSelected ? 'marked-trash' : ''} ${isOriginal ? 'original-file' : ''}`}
                        onClick={() => !isOriginal && toggleSelect(file.path)}
                      >
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => toggleSelect(file.path)}
                          onClick={(e) => e.stopPropagation()}
                        />
                        <div className="file-info-col">
                          <span className="dup-file-name">{file.name}</span>
                          <span className="dup-file-path" title={file.path}>
                            {file.path}
                          </span>
                        </div>
                        {isOriginal && <span className="badge-original">Keep (Original)</span>}
                      </div>
                    )
                  })}
                </div>
              </div>
            ))
          )}
        </div>

        <div className="modal-actions duplicates-footer">
          <button className="btn btn-secondary" onClick={onClose}>
            Close
          </button>
          {duplicatesData.duplicates?.length > 0 && (
            <button
              className="btn btn-primary btn-danger"
              onClick={handleClean}
              disabled={selectedToTrash.size === 0}
            >
              <Trash2 size={14} />
              <span>Move {selectedToTrash.size} Duplicate(s) to Trash</span>
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

function round(val, dec) {
  return Number(Math.round(val + 'e' + dec) + 'e-' + dec)
}
