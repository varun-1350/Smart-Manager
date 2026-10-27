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
  HardDrive,
  CopyCheck,
  PieChart,
  CheckSquare,
  Square,
  Monitor,
  Download,
  PanelLeftClose,
  PanelLeft,
  ArrowUpDown,
  ArrowUpNarrowWide,
  ArrowDownWideNarrow,
  X,
  Check,
} from 'lucide-react'

export default function FileExplorer({
  currentPath,
  browseData,
  locations,
  isLoading,
  onNavigate,
  onRefresh,
  onAction,
  onPreview,
  onAskAiAboutSelection,
  onScanDuplicates,
  onAnalyzeStorage,
  selectedPaths,
  setSelectedPaths,
}) {
  const [viewMode, setViewMode] = useState('list') // 'list' | 'grid'
  const [searchQuery, setSearchQuery] = useState('')
  const [isSidebarOpen, setIsSidebarOpen] = useState(true)
  const [sortField, setSortField] = useState('name') // 'name' | 'modified' | 'size' | 'type'
  const [sortDirection, setSortDirection] = useState('asc') // 'asc' | 'desc'
  const [contextMenu, setContextMenu] = useState(null)
  const [isNewFolderOpen, setIsNewFolderOpen] = useState(false)
  const [newFolderName, setNewFolderName] = useState('')
  const [renamingItem, setRenamingItem] = useState(null)
  const [renameValue, setRenameValue] = useState('')
  const [focusedPath, setFocusedPath] = useState(null)

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

  // Clear search on path change
  useEffect(() => {
    setSearchQuery('')
    setContextMenu(null)
    setRenamingItem(null)
    setFocusedPath(null)
  }, [currentPath])

  const entries = browseData?.entries || []

  // Sorting and Filtering
  const processedEntries = useMemo(() => {
    let result = [...entries]

    // Search filter
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      result = result.filter(
        (e) =>
          e.name.toLowerCase().includes(q) ||
          (e.extension && e.extension.toLowerCase().includes(q)) ||
          (e.category && e.category.toLowerCase().includes(q))
      )
    }

    // Sort: directories first, then files
    result.sort((a, b) => {
      if (a.is_dir && !b.is_dir) return -1
      if (!a.is_dir && b.is_dir) return 1

      let comp = 0
      if (sortField === 'name') {
        comp = a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: 'base' })
      } else if (sortField === 'size') {
        comp = (a.size_bytes || 0) - (b.size_bytes || 0)
      } else if (sortField === 'modified') {
        comp = (a.modified_timestamp || 0) - (b.modified_timestamp || 0)
      } else if (sortField === 'type') {
        const catA = a.is_dir ? 'Folder' : a.category || a.extension || ''
        const catB = b.is_dir ? 'Folder' : b.category || b.extension || ''
        comp = catA.localeCompare(catB)
      }

      return sortDirection === 'asc' ? comp : -comp
    })

    return result
  }, [entries, searchQuery, sortField, sortDirection])

  const handleSort = (field) => {
    if (sortField === field) {
      setSortDirection((prev) => (prev === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortField(field)
      setSortDirection('asc')
    }
  }

  // Multi-selection
  const toggleSelect = (path, e) => {
    e?.stopPropagation()
    setSelectedPaths((prev) => {
      const next = new Set(prev)
      if (next.has(path)) next.delete(path)
      else next.add(path)
      return next
    })
  }

  const selectAll = () => {
    if (selectedPaths.size === processedEntries.length && processedEntries.length > 0) {
      setSelectedPaths(new Set())
    } else {
      setSelectedPaths(new Set(processedEntries.map((e) => e.path)))
    }
  }

  const handleRowClick = (item, e) => {
    setFocusedPath(item.path)
  }

  const handleRowDoubleClick = (item) => {
    if (item.is_dir) {
      onNavigate(item.path)
    } else {
      onAction({ action: 'open', path: item.path })
    }
  }

  const handleContextMenu = (e, item) => {
    e.preventDefault()
    e.stopPropagation()
    setContextMenu({
      x: Math.min(e.clientX, window.innerWidth - 220),
      y: Math.min(e.clientY, window.innerHeight - 260),
      item,
    })
  }

  const handleCreateFolder = (e) => {
    e?.preventDefault()
    if (!newFolderName.trim()) return
    onAction({
      action: 'mkdir',
      path: currentPath,
      folder_name: newFolderName.trim(),
    })
    setNewFolderName('')
    setIsNewFolderOpen(false)
  }

  const handleRenameSubmit = (e) => {
    e?.preventDefault()
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
    if (window.confirm(`Move ${paths.length} selected item(s) to trash? (You can undo this)`)) {
      onAction({ action: 'trash', paths })
      setSelectedPaths(new Set())
    }
  }

  // Category Icon Resolver
  const renderCategoryIcon = (category, isDir, size = 16) => {
    if (isDir) return <Folder size={size} className="file-icon icon-folder" />
    switch (category) {
      case 'documents':
      case 'text':
        return <FileText size={size} className="file-icon icon-document" />
      case 'spreadsheets':
        return <FileSpreadsheet size={size} className="file-icon icon-spreadsheet" />
      case 'code':
        return <FileCode size={size} className="file-icon icon-code" />
      case 'images':
        return <Image size={size} className="file-icon icon-image" />
      case 'videos':
        return <Video size={size} className="file-icon icon-video" />
      case 'audio':
        return <Music size={size} className="file-icon icon-audio" />
      case 'archives':
        return <FileArchive size={size} className="file-icon icon-archive" />
      default:
        return <File size={size} className="file-icon icon-generic" />
    }
  }

  const getLocationIcon = (category) => {
    switch (category) {
      case 'desktop':
        return <Monitor size={14} />
      case 'downloads':
        return <Download size={14} />
      case 'documents':
        return <FileText size={14} />
      case 'pictures':
        return <Image size={14} />
      case 'videos':
        return <Video size={14} />
      case 'music':
        return <Music size={14} />
      default:
        return <Folder size={14} />
    }
  }

  const quickFolders = locations?.filter((l) => l.type === 'folder') || []
  const drives = locations?.filter((l) => l.type === 'drive') || []

  return (
    <div className="file-explorer-root">
      {/* 1. Internal Locations Navigation Pane (Collapsible) */}
      {isSidebarOpen && (
        <aside className="explorer-nav-sidebar">
          <div className="nav-sidebar-section">
            <span className="nav-sidebar-heading">Quick Access</span>
            <div className="nav-sidebar-list">
              {quickFolders.map((loc) => {
                const isActive = currentPath && currentPath.toLowerCase() === loc.path.toLowerCase()
                return (
                  <button
                    key={loc.path}
                    className={`nav-location-item ${isActive ? 'active' : ''}`}
                    onClick={() => onNavigate(loc.path)}
                    title={loc.path}
                  >
                    {getLocationIcon(loc.category)}
                    <span className="nav-location-name">{loc.name}</span>
                  </button>
                )
              })}
            </div>
          </div>

          <div className="nav-sidebar-section">
            <span className="nav-sidebar-heading">This PC</span>
            <div className="nav-sidebar-list">
              {drives.map((drive) => {
                const isActive = currentPath && currentPath.toLowerCase().startsWith(drive.path.toLowerCase())
                return (
                  <button
                    key={drive.path}
                    className={`nav-location-item ${isActive ? 'active' : ''}`}
                    onClick={() => onNavigate(drive.path)}
                    title={`${drive.path} (${drive.free_formatted || ''} free)`}
                  >
                    <HardDrive size={14} />
                    <div className="drive-info-col">
                      <div className="drive-name-row">
                        <span className="nav-location-name">{drive.name}</span>
                        {drive.free_formatted && (
                          <span className="drive-free-badge">{drive.free_formatted}</span>
                        )}
                      </div>
                      {typeof drive.percent_used === 'number' && (
                        <div className="drive-progress-track">
                          <div
                            className={`drive-progress-bar ${drive.percent_used > 85 ? 'high' : ''}`}
                            style={{ width: `${Math.min(drive.percent_used, 100)}%` }}
                          />
                        </div>
                      )}
                    </div>
                  </button>
                )
              })}
            </div>
          </div>
        </aside>
      )}

      {/* 2. Main File Browser Area */}
      <section className="explorer-main-content">
        {/* Toolbar */}
        <div className="explorer-toolbar">
          <div className="toolbar-nav-group">
            <button
              type="button"
              className="toolbar-btn icon-only"
              onClick={() => setIsSidebarOpen(!isSidebarOpen)}
              title={isSidebarOpen ? 'Hide Quick Access' : 'Show Quick Access'}
            >
              {isSidebarOpen ? <PanelLeftClose size={15} /> : <PanelLeft size={15} />}
            </button>

            <button
              type="button"
              className="toolbar-btn icon-only"
              onClick={() => browseData?.parent_path && onNavigate(browseData.parent_path)}
              disabled={!browseData?.parent_path}
              title="Go to parent folder (Alt+Up)"
            >
              <ArrowUp size={15} />
            </button>

            <button
              type="button"
              className="toolbar-btn icon-only"
              onClick={onRefresh}
              disabled={isLoading}
              title="Refresh (F5)"
            >
              <RefreshCw size={14} className={isLoading ? 'spinning' : ''} />
            </button>

            {/* Breadcrumb Trail */}
            <div className="breadcrumbs-trail">
              {browseData?.breadcrumbs?.map((crumb, idx) => (
                <React.Fragment key={crumb.path}>
                  {idx > 0 && <ChevronRight size={12} className="crumb-separator" />}
                  <button
                    type="button"
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

          <div className="toolbar-controls-group">
            {/* Search Filter */}
            <div className="explorer-search-input-wrap">
              <Search size={14} className="search-icon" />
              <input
                type="text"
                placeholder="Filter files..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
              {searchQuery && (
                <button
                  type="button"
                  className="search-clear-btn"
                  onClick={() => setSearchQuery('')}
                  title="Clear filter"
                >
                  <X size={12} />
                </button>
              )}
            </div>

            {/* Action Buttons */}
            <button
              type="button"
              className="toolbar-btn"
              onClick={() => setIsNewFolderOpen(true)}
              title="Create a new folder"
            >
              <Plus size={14} />
              <span>New Folder</span>
            </button>

            <button
              type="button"
              className="toolbar-btn"
              onClick={onScanDuplicates}
              title="Find exact duplicate files using SHA-256"
            >
              <CopyCheck size={14} />
              <span>Duplicates</span>
            </button>

            <button
              type="button"
              className="toolbar-btn"
              onClick={onAnalyzeStorage}
              title="Storage diagnostics (large files, empty folders)"
            >
              <PieChart size={14} />
              <span>Storage</span>
            </button>

            {/* View Mode Toggle */}
            <div className="view-mode-group">
              <button
                type="button"
                className={`view-toggle-btn ${viewMode === 'list' ? 'active' : ''}`}
                onClick={() => setViewMode('list')}
                title="Table List View"
              >
                <List size={14} />
              </button>
              <button
                type="button"
                className={`view-toggle-btn ${viewMode === 'grid' ? 'active' : ''}`}
                onClick={() => setViewMode('grid')}
                title="Grid View"
              >
                <Grid size={14} />
              </button>
            </div>
          </div>
        </div>

        {/* New Folder Inline Bar */}
        {isNewFolderOpen && (
          <form className="inline-creator-bar" onSubmit={handleCreateFolder}>
            <Folder size={15} className="file-icon icon-folder" />
            <input
              type="text"
              autoFocus
              placeholder="Folder name..."
              value={newFolderName}
              onChange={(e) => setNewFolderName(e.target.value)}
            />
            <button type="submit" className="inline-btn primary" disabled={!newFolderName.trim()}>
              <Check size={13} />
              <span>Create</span>
            </button>
            <button
              type="button"
              className="inline-btn secondary"
              onClick={() => {
                setIsNewFolderOpen(false)
                setNewFolderName('')
              }}
            >
              <X size={13} />
              <span>Cancel</span>
            </button>
          </form>
        )}

        {/* Floating Contextual Selection Bar */}
        {selectedPaths.size > 0 && (
          <div className="explorer-selection-bar">
            <span className="selection-count-badge">
              {selectedPaths.size} {selectedPaths.size === 1 ? 'item' : 'items'} selected
            </span>

            <div className="selection-actions-wrap">
              <button
                type="button"
                className="selection-btn selection-btn-ai"
                onClick={() => {
                  const items = Array.from(selectedPaths).map((p) => p.split('\\').pop()).join(', ')
                  onAskAiAboutSelection?.(`Help me organize or clean up these selected files: ${items}`)
                }}
                title="Ask AI Assistant about selected files"
              >
                <Sparkles size={13} />
                <span>Ask AI</span>
              </button>

              {selectedPaths.size === 1 && (
                <button
                  type="button"
                  className="selection-btn"
                  onClick={() => onPreview(Array.from(selectedPaths)[0])}
                  title="Preview file contents"
                >
                  <Eye size={13} />
                  <span>Preview</span>
                </button>
              )}

              <button
                type="button"
                className="selection-btn selection-btn-trash"
                onClick={handleBulkTrash}
                title="Move selected items to recoverable trash"
              >
                <Trash2 size={13} />
                <span>Move to Trash</span>
              </button>

              <button
                type="button"
                className="selection-btn selection-btn-clear"
                onClick={() => setSelectedPaths(new Set())}
                title="Clear selection"
              >
                Deselect
              </button>
            </div>
          </div>
        )}

        {/* File Listing Container */}
        <div className="explorer-listing-viewport">
          {processedEntries.length === 0 ? (
            <div className="empty-listing-state">
              <Folder size={40} className="empty-icon" />
              <p className="empty-title">This folder is empty</p>
              <p className="empty-subtitle">
                {searchQuery
                  ? `No items match "${searchQuery}"`
                  : 'Drag files here or ask AI to organize files into this directory.'}
              </p>
            </div>
          ) : viewMode === 'list' ? (
            /* Table View */
            <div className="file-table-wrapper">
              <table className="file-data-table">
                <thead>
                  <tr>
                    <th className="th-checkbox">
                      <div className="checkbox-wrap" onClick={selectAll}>
                        {selectedPaths.size === processedEntries.length && processedEntries.length > 0 ? (
                          <CheckSquare size={14} className="checkbox-icon checked" />
                        ) : (
                          <Square size={14} className="checkbox-icon" />
                        )}
                      </div>
                    </th>
                    <th className="th-name" onClick={() => handleSort('name')}>
                      <div className="th-content">
                        <span>Name</span>
                        {sortField === 'name' && (
                          sortDirection === 'asc' ? <ArrowUpNarrowWide size={13} /> : <ArrowDownWideNarrow size={13} />
                        )}
                      </div>
                    </th>
                    <th className="th-date" onClick={() => handleSort('modified')}>
                      <div className="th-content">
                        <span>Date modified</span>
                        {sortField === 'modified' && (
                          sortDirection === 'asc' ? <ArrowUpNarrowWide size={13} /> : <ArrowDownWideNarrow size={13} />
                        )}
                      </div>
                    </th>
                    <th className="th-type" onClick={() => handleSort('type')}>
                      <div className="th-content">
                        <span>Type</span>
                        {sortField === 'type' && (
                          sortDirection === 'asc' ? <ArrowUpNarrowWide size={13} /> : <ArrowDownWideNarrow size={13} />
                        )}
                      </div>
                    </th>
                    <th className="th-size" onClick={() => handleSort('size')}>
                      <div className="th-content">
                        <span>Size</span>
                        {sortField === 'size' && (
                          sortDirection === 'asc' ? <ArrowUpNarrowWide size={13} /> : <ArrowDownWideNarrow size={13} />
                        )}
                      </div>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {processedEntries.map((item) => {
                    const isSelected = selectedPaths.has(item.path)
                    const isRenaming = renamingItem?.path === item.path

                    return (
                      <tr
                        key={item.path}
                        className={`file-table-row ${isSelected ? 'selected' : ''} ${focusedPath === item.path ? 'focused' : ''}`}
                        onClick={(e) => handleRowClick(item, e)}
                        onDoubleClick={() => handleRowDoubleClick(item)}
                        onContextMenu={(e) => handleContextMenu(e, item)}
                      >
                        <td className="td-checkbox" onClick={(e) => toggleSelect(item.path, e)}>
                          <div className="checkbox-wrap">
                            {isSelected ? (
                              <CheckSquare size={14} className="checkbox-icon checked" />
                            ) : (
                              <Square size={14} className="checkbox-icon" />
                            )}
                          </div>
                        </td>

                        <td className="td-name">
                          <div className="file-name-cell">
                            {renderCategoryIcon(item.category, item.is_dir)}
                            {isRenaming ? (
                              <form className="inline-rename-form" onSubmit={handleRenameSubmit} onClick={(e) => e.stopPropagation()}>
                                <input
                                  type="text"
                                  autoFocus
                                  value={renameValue}
                                  onChange={(e) => setRenameValue(e.target.value)}
                                  onBlur={handleRenameSubmit}
                                  onKeyDown={(e) => {
                                    if (e.key === 'Escape') setRenamingItem(null)
                                  }}
                                />
                              </form>
                            ) : (
                              <span className="file-name-text" title={item.name}>
                                {item.name}
                              </span>
                            )}
                            {!item.is_dir && item.category && (
                              <span className={`file-category-badge cat-${item.category}`}>
                                {item.category}
                              </span>
                            )}
                          </div>
                        </td>

                        <td className="td-date">
                          <span className="meta-text">{item.modified_formatted || '-'}</span>
                        </td>

                        <td className="td-type">
                          <span className="meta-text">
                            {item.is_dir ? 'File folder' : item.extension ? `${item.extension.toUpperCase()} file` : 'File'}
                          </span>
                        </td>

                        <td className="td-size">
                          <span className="meta-text">{item.is_dir ? '-' : item.size_formatted}</span>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            /* Grid View */
            <div className="file-grid-wrapper">
              {processedEntries.map((item) => {
                const isSelected = selectedPaths.has(item.path)
                return (
                  <div
                    key={item.path}
                    className={`file-grid-card ${isSelected ? 'selected' : ''} ${focusedPath === item.path ? 'focused' : ''}`}
                    onClick={(e) => handleRowClick(item, e)}
                    onDoubleClick={() => handleRowDoubleClick(item)}
                    onContextMenu={(e) => handleContextMenu(e, item)}
                    title={item.name}
                  >
                    <div
                      className="grid-card-checkbox"
                      onClick={(e) => toggleSelect(item.path, e)}
                      title="Select item"
                    >
                      {isSelected ? (
                        <CheckSquare size={13} className="checkbox-icon checked" />
                      ) : (
                        <Square size={13} className="checkbox-icon" />
                      )}
                    </div>
                    <div className="grid-icon-wrap">
                      {renderCategoryIcon(item.category, item.is_dir, 32)}
                    </div>
                    <span className="grid-file-name">{item.name}</span>
                    <span className="grid-file-size">
                      {item.is_dir ? 'Folder' : item.size_formatted}
                    </span>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Footer Status Bar */}
        <footer className="explorer-status-bar">
          <div className="status-bar-left">
            <span>{processedEntries.length} items</span>
            {selectedPaths.size > 0 && (
              <span className="status-selected-count">
                • {selectedPaths.size} selected
              </span>
            )}
          </div>
          <div className="status-bar-right" title={currentPath}>
            <span>{currentPath}</span>
          </div>
        </footer>
      </section>

      {/* Right-click Context Menu */}
      {contextMenu && (
        <div
          className="explorer-context-menu"
          style={{ top: `${contextMenu.y}px`, left: `${contextMenu.x}px` }}
        >
          <div className="context-menu-header">
            <span className="context-target-name">{contextMenu.item.name}</span>
          </div>
          <div className="context-menu-divider" />

          <button
            type="button"
            className="context-menu-item"
            onClick={() => {
              if (contextMenu.item.is_dir) onNavigate(contextMenu.item.path)
              else onAction({ action: 'open', path: contextMenu.item.path })
              setContextMenu(null)
            }}
          >
            <ExternalLink size={14} />
            <span>{contextMenu.item.is_dir ? 'Open folder' : 'Open file'}</span>
          </button>

          {!contextMenu.item.is_dir && (
            <button
              type="button"
              className="context-menu-item"
              onClick={() => {
                onPreview(contextMenu.item.path)
                setContextMenu(null)
              }}
            >
              <Eye size={14} />
              <span>Preview content</span>
            </button>
          )}

          <button
            type="button"
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
            type="button"
            className="context-menu-item context-menu-ai"
            onClick={() => {
              onAskAiAboutSelection?.(`Tell me about this file and how to organize it: ${contextMenu.item.name}`)
              setContextMenu(null)
            }}
          >
            <Sparkles size={14} />
            <span>Ask AI about this</span>
          </button>

          <div className="context-menu-divider" />

          <button
            type="button"
            className="context-menu-item context-menu-danger"
            onClick={() => {
              onAction({ action: 'trash', paths: [contextMenu.item.path] })
              setContextMenu(null)
            }}
          >
            <Trash2 size={14} />
            <span>Move to Trash</span>
          </button>
        </div>
      )}
    </div>
  )
}
