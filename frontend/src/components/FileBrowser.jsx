import React, { useState, useMemo, useEffect, useRef } from 'react'
import {
  Folder,
  File,
  FileText,
  FileSpreadsheet,
  FileCode,
  FileArchive,
  Image,
  Video,
  Music,
  ArrowUp,
  RefreshCw,
  Search,
  Grid,
  List,
  Plus,
  Trash2,
  Copy,
  Move,
  Eye,
  ExternalLink,
  Edit2,
  Sparkles,
  ChevronRight,
  SlidersHorizontal,
  HardDrive,
  CopyCheck,
  PieChart,
  CheckSquare,
  Square,
} from 'lucide-react'

export default function FileBrowser({
  currentPath,
  browseData,
  isLoading,
  onNavigate,
  onRefresh,
  onAction,
  onPreview,
  onSendToAi,
  onScanDuplicates,
  onAnalyzeStorage,
}) {
  const [viewMode, setViewMode] = useState('list') // 'list' | 'grid'
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedPaths, setSelectedPaths] = useState(new Set())
  const [contextMenu, setContextMenu] = useState(null)
  const [newFolderName, setNewFolderName] = useState('')
  const [isNewFolderOpen, setIsNewFolderOpen] = useState(false)
  const [renamingItem, setRenamingItem] = useState(null)
  const [renameValue, setRenameValue] = useState('')
  const containerRef = useRef(null)

  // Clear selections when navigating
  useEffect(() => {
    setSelectedPaths(new Set())
    setSearchQuery('')
    setContextMenu(null)
  }, [currentPath])

  // Close context menu on outside click
  useEffect(() => {
    const handleOutsideClick = (e) => {
      if (contextMenu && !e.target.closest('.explorer-context-menu')) {
        setContextMenu(null)
      }
    }
    window.addEventListener('click', handleOutsideClick)
    return () => window.removeEventListener('click', handleOutsideClick)
  }, [contextMenu])

  const entries = browseData?.entries || []

  // Filter entries in current directory based on search query
  const filteredEntries = useMemo(() => {
    if (!searchQuery.trim()) return entries
    const q = searchQuery.toLowerCase()
    return entries.filter(
      (e) =>
        e.name.toLowerCase().includes(q) ||
        (e.extension && e.extension.toLowerCase().includes(q)) ||
        (e.category && e.category.toLowerCase().includes(q))
    )
  }, [entries, searchQuery])

  // Category Icon Resolver
  const renderCategoryIcon = (category, isDir, size = 18) => {
    if (isDir) return <Folder size={size} className="cat-icon cat-folder" />
    switch (category) {
      case 'documents':
      case 'text':
        return <FileText size={size} className="cat-icon cat-document" />
      case 'spreadsheets':
        return <FileSpreadsheet size={size} className="cat-icon cat-spreadsheet" />
      case 'code':
        return <FileCode size={size} className="cat-icon cat-code" />
      case 'images':
        return <Image size={size} className="cat-icon cat-image" />
      case 'videos':
        return <Video size={size} className="cat-icon cat-video" />
      case 'audio':
        return <Music size={size} className="cat-icon cat-audio" />
      case 'archives':
        return <FileArchive size={size} className="cat-icon cat-archive" />
      default:
        return <File size={size} className="cat-icon cat-other" />
    }
  }

  // Multi-selection helpers
  const toggleSelect = (path, e) => {
    e.stopPropagation()
    setSelectedPaths((prev) => {
      const next = new Set(prev)
      if (next.has(path)) next.delete(path)
      else next.add(path)
      return next
    })
  }

  const selectAll = () => {
    if (selectedPaths.size === filteredEntries.length) {
      setSelectedPaths(new Set())
    } else {
      setSelectedPaths(new Set(filteredEntries.map((e) => e.path)))
    }
  }

  const handleItemClick = (item, e) => {
    if (e.ctrlKey || e.metaKey) {
      toggleSelect(item.path, e)
    } else if (item.is_dir) {
      onNavigate(item.path)
    } else {
      // Toggle selection for single click on file
      toggleSelect(item.path, e)
    }
  }

  const handleItemDoubleClick = (item) => {
    if (item.is_dir) {
      onNavigate(item.path)
    } else {
      onAction({ action: 'open', path: item.path })
    }
  }

  const handleContextMenu = (e, item) => {
    e.preventDefault()
    e.stopPropagation()
    if (!selectedPaths.has(item.path)) {
      setSelectedPaths(new Set([item.path]))
    }
    setContextMenu({
      x: Math.min(e.clientX, window.innerWidth - 220),
      y: Math.min(e.clientY, window.innerHeight - 280),
      item,
    })
  }

  const handleCreateFolder = () => {
    if (!newFolderName.trim()) return
    onAction({
      action: 'mkdir',
      path: currentPath,
      folder_name: newFolderName.trim(),
    })
    setNewFolderName('')
    setIsNewFolderOpen(false)
  }

  const handleRenameSubmit = () => {
    if (!renameValue.trim() || !renamingItem) return
    onAction({
      action: 'rename',
      path: renamingItem.path,
      new_name: renameValue.trim(),
    })
    setRenamingItem(null)
    setRenameValue('')
  }

  const handleBulkTrash = () => {
    const paths = Array.from(selectedPaths)
    if (paths.length === 0) return
    if (window.confirm(`Move ${paths.length} selected item(s) to trash? You can undo this.`)) {
      onAction({ action: 'trash', paths })
      setSelectedPaths(new Set())
    }
  }

  return (
    <div className="file-browser-container" ref={containerRef}>
      {/* 1. Explorer Top Toolbar & Breadcrumbs */}
      <div className="explorer-toolbar-wrapper">
        <div className="breadcrumbs-row">
          <div className="nav-buttons-group">
            <button
              className="explorer-nav-btn"
              onClick={() => browseData?.parent_path && onNavigate(browseData.parent_path)}
              disabled={!browseData?.parent_path}
              title="Go to parent directory"
            >
              <ArrowUp size={16} />
            </button>
            <button
              className="explorer-nav-btn"
              onClick={onRefresh}
              disabled={isLoading}
              title="Refresh directory"
            >
              <RefreshCw size={15} className={isLoading ? 'spinning' : ''} />
            </button>
          </div>

          <div className="breadcrumbs-trail">
            {browseData?.breadcrumbs?.map((crumb, idx) => (
              <React.Fragment key={crumb.path}>
                {idx > 0 && <ChevronRight size={13} className="crumb-separator" />}
                <button
                  className={`crumb-btn ${idx === browseData.breadcrumbs.length - 1 ? 'current' : ''}`}
                  onClick={() => onNavigate(crumb.path)}
                  title={crumb.path}
                >
                  {crumb.name}
                </button>
              </React.Fragment>
            ))}
          </div>
        </div>

        <div className="explorer-actions-row">
          <div className="explorer-search-box">
            <Search size={15} className="search-icon" />
            <input
              type="text"
              placeholder="Filter files in this folder..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
            {searchQuery && (
              <button className="clear-search-btn" onClick={() => setSearchQuery('')}>
                ×
              </button>
            )}
          </div>

          <div className="toolbar-btn-group">
            <button
              className="explorer-tool-btn"
              onClick={() => setIsNewFolderOpen(true)}
              title="Create new folder"
            >
              <Plus size={15} />
              <span>New Folder</span>
            </button>

            <button
              className="explorer-tool-btn"
              onClick={onScanDuplicates}
              title="Find duplicate files via cryptographic SHA-256"
            >
              <CopyCheck size={15} />
              <span>Duplicates</span>
            </button>

            <button
              className="explorer-tool-btn"
              onClick={onAnalyzeStorage}
              title="Analyze large files and empty folders"
            >
              <PieChart size={15} />
              <span>Storage</span>
            </button>

            <div className="view-mode-toggle">
              <button
                className={`view-btn ${viewMode === 'list' ? 'active' : ''}`}
                onClick={() => setViewMode('list')}
                title="List View"
              >
                <List size={16} />
              </button>
              <button
                className={`view-btn ${viewMode === 'grid' ? 'active' : ''}`}
                onClick={() => setViewMode('grid')}
                title="Grid View"
              >
                <Grid size={16} />
              </button>
            </div>
          </div>
        </div>

        {/* Multi-selection Floating Action Bar */}
        {selectedPaths.size > 0 && (
          <div className="selection-action-bar">
            <div className="selection-count">
              <span>{selectedPaths.size} item(s) selected</span>
            </div>
            <div className="selection-actions">
              <button
                className="sel-btn sel-trash"
                onClick={handleBulkTrash}
                title="Move selected items to recoverable trash"
              >
                <Trash2 size={14} />
                <span>Move to Trash</span>
              </button>
              <button
                className="sel-btn"
                onClick={() => {
                  const names = Array.from(selectedPaths).map((p) => p.split('\\').pop()).join(', ')
                  onSendToAi(`Organize or clean up these selected files: ${names}`)
                }}
                title="Ask AI to process selected files"
              >
                <Sparkles size={14} />
                <span>Ask AI</span>
              </button>
              <button
                className="sel-btn sel-clear"
                onClick={() => setSelectedPaths(new Set())}
              >
                Deselect All
              </button>
            </div>
          </div>
        )}
      </div>

      {/* 2. Main File Area (List or Grid) */}
      <div className="explorer-view-area">
        {filteredEntries.length === 0 ? (
          <div className="empty-folder-state">
            <Folder size={48} className="empty-folder-icon" />
            <h3>This folder is empty</h3>
            <p>
              {searchQuery
                ? `No files match "${searchQuery}"`
                : 'Drag files here or use AI to organize files into this folder.'}
            </p>
          </div>
        ) : viewMode === 'list' ? (
          <div className="file-list-view">
            <div className="file-list-header">
              <div className="col-checkbox" onClick={selectAll}>
                {selectedPaths.size === filteredEntries.length && filteredEntries.length > 0 ? (
                  <CheckSquare size={15} className="checkbox-active" />
                ) : (
                  <Square size={15} />
                )}
              </div>
              <div className="col-name">Name</div>
              <div className="col-size">Size</div>
              <div className="col-type">Type</div>
              <div className="col-date">Date Modified</div>
              <div className="col-actions"></div>
            </div>

            <div className="file-list-body">
              {filteredEntries.map((item) => {
                const isSelected = selectedPaths.has(item.path)
                return (
                  <div
                    key={item.path}
                    className={`file-list-row ${isSelected ? 'selected' : ''}`}
                    onClick={(e) => handleItemClick(item, e)}
                    onDoubleClick={() => handleItemDoubleClick(item)}
                    onContextMenu={(e) => handleContextMenu(e, item)}
                  >
                    <div
                      className="col-checkbox"
                      onClick={(e) => toggleSelect(item.path, e)}
                    >
                      {isSelected ? (
                        <CheckSquare size={15} className="checkbox-active" />
                      ) : (
                        <Square size={15} />
                      )}
                    </div>

                    <div className="col-name">
                      <span className="file-icon-wrap">
                        {renderCategoryIcon(item.category, item.is_dir)}
                      </span>
                      <span className="file-name-text" title={item.name}>
                        {item.name}
                      </span>
                    </div>

                    <div className="col-size">{item.size_formatted}</div>
                    <div className="col-type">
                      <span className="type-badge">{item.is_dir ? 'Folder' : item.category}</span>
                    </div>
                    <div className="col-date">
                      {item.modified ? new Date(item.modified).toLocaleDateString() : '--'}
                    </div>

                    <div className="col-actions">
                      {!item.is_dir && (
                        <button
                          className="row-action-btn"
                          onClick={(e) => {
                            e.stopPropagation()
                            onPreview(item.path)
                          }}
                          title="Preview file"
                        >
                          <Eye size={14} />
                        </button>
                      )}
                      <button
                        className="row-action-btn"
                        onClick={(e) => {
                          e.stopPropagation()
                          onAction({ action: 'open', path: item.path })
                        }}
                        title="Open with system default application"
                      >
                        <ExternalLink size={14} />
                      </button>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        ) : (
          <div className="file-grid-view">
            {filteredEntries.map((item) => {
              const isSelected = selectedPaths.has(item.path)
              return (
                <div
                  key={item.path}
                  className={`file-grid-card ${isSelected ? 'selected' : ''}`}
                  onClick={(e) => handleItemClick(item, e)}
                  onDoubleClick={() => handleItemDoubleClick(item)}
                  onContextMenu={(e) => handleContextMenu(e, item)}
                >
                  <div className="grid-card-checkbox" onClick={(e) => toggleSelect(item.path, e)}>
                    {isSelected ? (
                      <CheckSquare size={14} className="checkbox-active" />
                    ) : (
                      <Square size={14} />
                    )}
                  </div>
                  <div className="grid-icon-wrap">
                    {renderCategoryIcon(item.category, item.is_dir, 38)}
                  </div>
                  <div className="grid-name" title={item.name}>
                    {item.name}
                  </div>
                  <div className="grid-meta">
                    <span>{item.is_dir ? 'Folder' : item.size_formatted}</span>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* 3. Right-Click Context Menu */}
      {contextMenu && (
        <div
          className="explorer-context-menu"
          style={{ top: `${contextMenu.y}px`, left: `${contextMenu.x}px` }}
        >
          <div className="context-menu-header">{contextMenu.item.name}</div>
          <button
            className="context-menu-item"
            onClick={() => {
              onAction({ action: 'open', path: contextMenu.item.path })
              setContextMenu(null)
            }}
          >
            <ExternalLink size={14} />
            <span>Open</span>
          </button>

          {!contextMenu.item.is_dir && (
            <button
              className="context-menu-item"
              onClick={() => {
                onPreview(contextMenu.item.path)
                setContextMenu(null)
              }}
            >
              <Eye size={14} />
              <span>Preview Content</span>
            </button>
          )}

          <button
            className="context-menu-item"
            onClick={() => {
              setRenamingItem(contextMenu.item)
              setRenameValue(contextMenu.item.name)
              setContextMenu(null)
            }}
          >
            <Edit2 size={14} />
            <span>Rename</span>
          </button>

          <button
            className="context-menu-item context-danger"
            onClick={() => {
              if (window.confirm(`Move "${contextMenu.item.name}" to trash? You can undo this.`)) {
                onAction({ action: 'trash', paths: [contextMenu.item.path] })
              }
              setContextMenu(null)
            }}
          >
            <Trash2 size={14} />
            <span>Move to Trash</span>
          </button>

          <div className="context-menu-divider" />

          <button
            className="context-menu-item context-ai"
            onClick={() => {
              onSendToAi(`Analyze or organize this file: ${contextMenu.item.name}`)
              setContextMenu(null)
            }}
          >
            <Sparkles size={14} />
            <span>Ask AI About This</span>
          </button>
        </div>
      )}

      {/* 4. New Folder Modal */}
      {isNewFolderOpen && (
        <div className="modal-backdrop">
          <div className="modal-card">
            <h3>Create New Folder</h3>
            <p>Enter the name of the new folder in {currentPath}:</p>
            <input
              type="text"
              className="text-input"
              placeholder="e.g. Invoices 2026"
              value={newFolderName}
              onChange={(e) => setNewFolderName(e.target.value)}
              autoFocus
              onKeyDown={(e) => e.key === 'Enter' && handleCreateFolder()}
            />
            <div className="modal-actions">
              <button className="btn btn-secondary" onClick={() => setIsNewFolderOpen(false)}>
                Cancel
              </button>
              <button className="btn btn-primary" onClick={handleCreateFolder}>
                Create Folder
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 5. Rename Modal */}
      {renamingItem && (
        <div className="modal-backdrop">
          <div className="modal-card">
            <h3>Rename Item</h3>
            <p>New name for "{renamingItem.name}":</p>
            <input
              type="text"
              className="text-input"
              value={renameValue}
              onChange={(e) => setRenameValue(e.target.value)}
              autoFocus
              onKeyDown={(e) => e.key === 'Enter' && handleRenameSubmit()}
            />
            <div className="modal-actions">
              <button className="btn btn-secondary" onClick={() => setRenamingItem(null)}>
                Cancel
              </button>
              <button className="btn btn-primary" onClick={handleRenameSubmit}>
                Rename
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
