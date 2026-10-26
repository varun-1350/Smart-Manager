import React, { useState } from 'react'
import { X, PieChart, Trash2, Folder, File, ExternalLink, AlertTriangle } from 'lucide-react'

export default function StorageAnalysisModal({ storageData, onClose, onCleanItems, onOpenFile }) {
  if (!storageData) return null

  const [activeTab, setActiveTab] = useState('large') // 'large' | 'empty' | 'temp'

  const handleCleanTemp = () => {
    const paths = storageData.temp_files.map((f) => f.path)
    if (paths.length === 0) return
    if (window.confirm(`Move ${paths.length} temporary file(s) to trash? You can undo this.`)) {
      onCleanItems(paths)
      onClose()
    }
  }

  const handleCleanEmpty = () => {
    const paths = storageData.empty_folders.map((f) => f.path)
    if (paths.length === 0) return
    if (window.confirm(`Delete ${paths.length} empty folder(s)?`)) {
      onCleanItems(paths)
      onClose()
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-card storage-modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div className="title-with-icon">
            <PieChart size={20} className="storage-icon" />
            <div>
              <h3>Storage & Cleanup Analysis</h3>
              <span className="subtitle">Scope: {storageData.folder}</span>
            </div>
          </div>
          <button className="modal-close-btn" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        {/* Tab Headers */}
        <div className="storage-tabs-bar">
          <button
            className={`storage-tab ${activeTab === 'large' ? 'active' : ''}`}
            onClick={() => setActiveTab('large')}
          >
            <span>Large Files</span>
            <span className="tab-badge">{storageData.summary?.large_file_count || 0}</span>
          </button>
          <button
            className={`storage-tab ${activeTab === 'empty' ? 'active' : ''}`}
            onClick={() => setActiveTab('empty')}
          >
            <span>Empty Folders</span>
            <span className="tab-badge">{storageData.summary?.empty_folder_count || 0}</span>
          </button>
          <button
            className={`storage-tab ${activeTab === 'temp' ? 'active' : ''}`}
            onClick={() => setActiveTab('temp')}
          >
            <span>Temporary Files</span>
            <span className="tab-badge">{storageData.summary?.temp_file_count || 0}</span>
          </button>
        </div>

        <div className="storage-content-area">
          {activeTab === 'large' && (
            <div className="storage-list">
              {storageData.large_files?.length === 0 ? (
                <div className="empty-storage-tab">No files over 50 MB found.</div>
              ) : (
                storageData.large_files.map((file) => (
                  <div key={file.path} className="storage-item-row">
                    <File size={16} className="item-icon" />
                    <div className="item-details">
                      <span className="item-name">{file.name}</span>
                      <span className="item-path">{file.path}</span>
                    </div>
                    <span className="item-size-badge">{file.size_formatted}</span>
                    <button
                      className="btn-icon"
                      onClick={() => onOpenFile(file.path)}
                      title="Open file"
                    >
                      <ExternalLink size={14} />
                    </button>
                  </div>
                ))
              )}
            </div>
          )}

          {activeTab === 'empty' && (
            <div className="storage-list">
              {storageData.empty_folders?.length === 0 ? (
                <div className="empty-storage-tab">No empty folders found.</div>
              ) : (
                <>
                  <div className="tab-action-bar">
                    <span>{storageData.empty_folders.length} empty directory candidate(s)</span>
                    <button className="btn btn-secondary btn-sm" onClick={handleCleanEmpty}>
                      <Trash2 size={13} />
                      <span>Delete All Empty Folders</span>
                    </button>
                  </div>
                  {storageData.empty_folders.map((folder) => (
                    <div key={folder.path} className="storage-item-row">
                      <Folder size={16} className="item-icon text-muted" />
                      <div className="item-details">
                        <span className="item-name">{folder.name}</span>
                        <span className="item-path">{folder.path}</span>
                      </div>
                      <span className="item-empty-badge">Empty</span>
                    </div>
                  ))}
                </>
              )}
            </div>
          )}

          {activeTab === 'temp' && (
            <div className="storage-list">
              {storageData.temp_files?.length === 0 ? (
                <div className="empty-storage-tab">No temporary or cache files found.</div>
              ) : (
                <>
                  <div className="tab-action-bar">
                    <span>{storageData.temp_files.length} temporary file(s) found</span>
                    <button className="btn btn-secondary btn-sm" onClick={handleCleanTemp}>
                      <Trash2 size={13} />
                      <span>Move All Temp Files to Trash</span>
                    </button>
                  </div>
                  {storageData.temp_files.map((file) => (
                    <div key={file.path} className="storage-item-row">
                      <AlertTriangle size={15} className="item-icon text-warning" />
                      <div className="item-details">
                        <span className="item-name">{file.name}</span>
                        <span className="item-path">{file.path}</span>
                      </div>
                      <span className="item-size-badge">{file.size_formatted}</span>
                    </div>
                  ))}
                </>
              )}
            </div>
          )}
        </div>

        <div className="modal-actions storage-footer">
          <button className="btn btn-secondary" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
