import React, { useState, useEffect, useRef } from 'react'
import {
  Check,
  AlertCircle,
  Zap,
} from 'lucide-react'
import CompactHeader from './components/CompactHeader'
import FileExplorer from './components/FileExplorer'
import AiChatAssistant from './components/AiChatAssistant'
import FilePreviewModal from './components/FilePreviewModal'
import DuplicatesModal from './components/DuplicatesModal'
import StorageAnalysisModal from './components/StorageAnalysisModal'
import ConfirmationModal from './components/ConfirmationModal'
import SettingsModal from './components/SettingsModal'
import {
  fetchHealth,
  fetchConfig,
  updateConfig,
  executeTaskApi,
  approveTaskApi,
  stopTaskApi,
  unloadModel,
  deleteConversationApi,
  clearAllConversationsApi,
  fetchConversations,
  fetchMessages,
  fetchLocations,
  browseDirectory,
  fetchFilePreview,
  executeExplorerAction,
  fetchDuplicates,
  fetchStorageAnalysis,
  generateExplorerPlan,
  executeExplorerPlan,
  undoExplorerLastOperation,
  fetchExplorerHistory,
} from './services/api'

export default function App() {
  // 60:40 Horizontal Split Ratio (persisted in localStorage)
  const [splitPercent, setSplitPercent] = useState(() => {
    try {
      const saved = localStorage.getItem('smart_manager_split_ratio')
      return saved ? Math.min(Math.max(parseFloat(saved), 35), 75) : 60
    } catch {
      return 60
    }
  })
  const [isDragging, setIsDragging] = useState(false)

  // File Explorer State
  const [locations, setLocations] = useState([])
  const [currentPath, setCurrentPath] = useState('')
  const [browseData, setBrowseData] = useState(null)
  const [isBrowsing, setIsBrowsing] = useState(false)
  const [selectedPaths, setSelectedPaths] = useState(new Set())
  const [previewData, setPreviewData] = useState(null)
  const [duplicatesData, setDuplicatesData] = useState(null)
  const [storageData, setStorageData] = useState(null)
  const [canUndo, setCanUndo] = useState(false)

  // AI Structured File Plan States
  const [planPreview, setPlanPreview] = useState(null)
  const [isGeneratingPlan, setIsGeneratingPlan] = useState(false)
  const [isExecutingPlan, setIsExecutingPlan] = useState(false)
  const [executionResult, setExecutionResult] = useState(null)

  // Conversational Assistant State
  const [conversations, setConversations] = useState([
    {
      id: 'default',
      title: 'Current Session',
      messages: [],
    },
  ])
  const [activeId, setActiveId] = useState('default')
  const [health, setHealth] = useState(null)
  const [config, setConfig] = useState(null)
  const [isSettingsOpen, setIsSettingsOpen] = useState(false)
  const [pendingApproval, setPendingApproval] = useState(null)
  const [isLoading, setIsLoading] = useState(false)
  const [isUnloading, setIsUnloading] = useState(false)
  const [toastMessage, setToastMessage] = useState(null)

  const abortControllerRef = useRef(null)
  const activeTaskIdRef = useRef(null)

  const activeConv =
    conversations.find((c) => c.id === activeId) || conversations[0]

  // Initialization
  useEffect(() => {
    refreshHealth()
    fetchConfig().then(setConfig).catch(() => {})
    loadSavedConversations()
    initExplorer()

    const interval = setInterval(refreshHealth, 8000)
    return () => clearInterval(interval)
  }, [])

  // Draggable Split Divider Handlers
  const handleDividerMouseDown = (e) => {
    e.preventDefault()
    setIsDragging(true)
  }

  useEffect(() => {
    if (!isDragging) return

    const handleMouseMove = (e) => {
      const containerWidth = window.innerWidth
      if (containerWidth <= 0) return
      const newPercent = (e.clientX / containerWidth) * 100
      const clamped = Math.min(Math.max(newPercent, 35), 75)
      setSplitPercent(clamped)
      try {
        localStorage.setItem('smart_manager_split_ratio', String(clamped))
      } catch {}
    }

    const handleMouseUp = () => {
      setIsDragging(false)
    }

    window.addEventListener('mousemove', handleMouseMove)
    window.addEventListener('mouseup', handleMouseUp)
    return () => {
      window.removeEventListener('mousemove', handleMouseMove)
      window.removeEventListener('mouseup', handleMouseUp)
    }
  }, [isDragging])

  const handleResetDivider = () => {
    setSplitPercent(60)
    try {
      localStorage.setItem('smart_manager_split_ratio', '60')
    } catch {}
  }

  const showToast = (text, type = 'info') => {
    setToastMessage({ text, type })
    setTimeout(() => setToastMessage(null), 3500)
  }

  const refreshHealth = async () => {
    const h = await fetchHealth()
    setHealth(h)
  }

  // ==========================================================================
  // File Explorer Handlers
  // ==========================================================================
  const initExplorer = async () => {
    try {
      const locs = await fetchLocations()
      setLocations(locs)
      if (locs && locs.length > 0) {
        const defaultLoc = locs.find((l) => l.category === 'desktop') || locs[0]
        loadDirectory(defaultLoc.path)
      }
      checkUndoStatus()
    } catch (err) {
      console.error('Failed to init explorer locations:', err)
    }
  }

  const loadDirectory = async (path, sortBy = 'name', sortOrder = 'asc') => {
    setIsBrowsing(true)
    setSelectedPaths(new Set())
    try {
      const data = await browseDirectory(path, sortBy, sortOrder)
      setBrowseData(data)
      setCurrentPath(data.current_path)
    } catch (err) {
      showToast(`Cannot open folder: ${err.message}`, 'error')
    } finally {
      setIsBrowsing(false)
    }
  }

  const handleRefreshDirectory = () => {
    if (currentPath) loadDirectory(currentPath)
  }

  const handleExplorerAction = async (payload) => {
    try {
      const res = await executeExplorerAction(payload)
      if (payload.action === 'mkdir') {
        showToast('Folder created successfully', 'success')
      } else if (payload.action === 'rename') {
        showToast('Item renamed successfully', 'success')
      } else if (payload.action === 'trash') {
        showToast('Moved to trash (undo available)', 'success')
        setCanUndo(true)
      } else if (payload.action === 'open') {
        showToast('Opened with system handler', 'info')
      }
      handleRefreshDirectory()
      checkUndoStatus()
    } catch (err) {
      showToast(`Action failed: ${err.message}`, 'error')
    }
  }

  const handlePreviewFile = async (path) => {
    try {
      const preview = await fetchFilePreview(path)
      setPreviewData(preview)
    } catch (err) {
      showToast(`Preview failed: ${err.message}`, 'error')
    }
  }

  const handleScanDuplicates = async () => {
    if (!currentPath) return
    showToast('Scanning for duplicate files via SHA-256...', 'info')
    try {
      const dups = await fetchDuplicates(currentPath)
      setDuplicatesData(dups)
    } catch (err) {
      showToast(`Duplicate scan error: ${err.message}`, 'error')
    }
  }

  const handleAnalyzeStorage = async () => {
    if (!currentPath) return
    showToast('Analyzing storage and large files...', 'info')
    try {
      const analysis = await fetchStorageAnalysis(currentPath)
      setStorageData(analysis)
    } catch (err) {
      showToast(`Storage analysis error: ${err.message}`, 'error')
    }
  }

  const handleCleanDuplicates = async (paths) => {
    try {
      await executeExplorerAction({ action: 'trash', paths })
      showToast(`Moved ${paths.length} duplicate file(s) to trash`, 'success')
      setCanUndo(true)
      handleRefreshDirectory()
    } catch (err) {
      showToast(`Failed to clean duplicates: ${err.message}`, 'error')
    }
  }

  const handleCleanStorageItems = async (paths) => {
    try {
      await executeExplorerAction({ action: 'trash', paths })
      showToast(`Cleaned up ${paths.length} item(s)`, 'success')
      setCanUndo(true)
      handleRefreshDirectory()
    } catch (err) {
      showToast(`Failed to clean items: ${err.message}`, 'error')
    }
  }

  const checkUndoStatus = async () => {
    try {
      const history = await fetchExplorerHistory()
      const hasUndoable = history?.some((b) => !b.undone)
      setCanUndo(hasUndoable)
    } catch {
      setCanUndo(false)
    }
  }

  const handleUndo = async () => {
    try {
      const res = await undoExplorerLastOperation()
      if (res.success) {
        showToast(`Undone! Restored ${res.undone_count} item(s)`, 'success')
        handleRefreshDirectory()
        checkUndoStatus()
      } else {
        showToast(res.message || 'No operations available to undo', 'info')
      }
    } catch (err) {
      showToast(`Undo failed: ${err.message}`, 'error')
    }
  }

  // ==========================================================================
  // AI Planning & Execution Handlers
  // ==========================================================================
  // ==========================================================================
  // AI Planning & Execution Handlers
  // ==========================================================================
  const handleGeneratePlan = async (instruction, signal = null) => {
    if (!currentPath) return null
    setIsGeneratingPlan(true)
    setPlanPreview(null)
    setExecutionResult(null)
    try {
      const plan = await generateExplorerPlan(currentPath, instruction, signal)
      setPlanPreview(plan)
      return plan
    } catch (err) {
      if (err.name !== 'AbortError') {
        showToast(`Failed to generate plan: ${err.message}`, 'error')
      }
      throw err
    } finally {
      setIsGeneratingPlan(false)
    }
  }

  const handleExecutePlan = async () => {
    if (!planPreview || !planPreview.actions?.length || isExecutingPlan) return
    setIsExecutingPlan(true)
    const folderName = currentPath ? currentPath.split('\\').pop() || currentPath : 'current folder'
    try {
      const batchId = `plan-${Date.now()}`
      const result = await executeExplorerPlan(batchId, planPreview.actions)
      setExecutionResult(result)

      const successCount = result.executed_count || 0
      const errorCount = result.errors?.length || 0

      // Add completion record to conversation
      const summaryMsg = {
        id: `msg-${Date.now()}`,
        role: 'agent',
        content: errorCount > 0
          ? `Executed ${successCount} file operation(s) with ${errorCount} error(s) in **${folderName}**.\n\n${result.errors.map((e) => `- ${e.action?.tool || 'action'}: ${e.error}`).join('\n')}`
          : `Successfully completed all ${successCount} file operation(s) in **${folderName}**.`,
        status: errorCount > 0 ? 'failed' : 'success',
        timestamp: Date.now(),
      }
      setConversations((prev) =>
        prev.map((c) =>
          c.id === activeId ? { ...c, messages: [...c.messages, summaryMsg] } : c
        )
      )

      setPlanPreview(null)
      if (errorCount === 0) {
        showToast(`Successfully organized ${successCount} file(s)!`, 'success')
      } else {
        showToast(`Executed ${successCount} operations with ${errorCount} errors`, 'warning')
      }
      setCanUndo(true)
      handleRefreshDirectory()
    } catch (err) {
      showToast(`Failed to execute plan: ${err.message}`, 'error')
      const errorMsg = {
        id: `msg-${Date.now()}`,
        role: 'agent',
        content: `Error executing file operations: ${err.message}`,
        status: 'failed',
        timestamp: Date.now(),
      }
      setConversations((prev) =>
        prev.map((c) =>
          c.id === activeId ? { ...c, messages: [...c.messages, errorMsg] } : c
        )
      )
    } finally {
      setIsExecutingPlan(false)
    }
  }

  // ==========================================================================
  // Unified Chat & Task Execution
  // ==========================================================================
  const handleSendMessage = async (prompt) => {
    const trimmed = prompt ? prompt.trim() : ''
    // Guard against empty input or repeated submission while busy
    if (!trimmed || isLoading || isExecutingPlan || isGeneratingPlan) return

    const userMsg = {
      id: `msg-${Date.now()}`,
      role: 'user',
      content: trimmed,
      timestamp: Date.now(),
    }

    setConversations((prev) =>
      prev.map((c) => {
        if (c.id === activeId) {
          const isFirstMessage = c.messages.length === 0
          return {
            ...c,
            title: isFirstMessage ? trimmed.slice(0, 24) : c.title,
            messages: [...c.messages, userMsg],
          }
        }
        return c
      })
    )

    // Check if the prompt is asking for file organization/cleanup in current folder
    const lower = trimmed.toLowerCase()
    const isFileOrgIntent =
      lower.includes('organize') ||
      lower.includes('group') ||
      lower.includes('sort') ||
      lower.includes('cleanup') ||
      lower.includes('clean up') ||
      lower.includes('duplicate') ||
      lower.includes('temporary') ||
      selectedPaths.size > 0

    if (isFileOrgIntent && currentPath) {
      const planId = `plan-${Date.now()}`
      activeTaskIdRef.current = planId
      const controller = new AbortController()
      abortControllerRef.current = controller
      const timeoutId = setTimeout(() => {
        controller.abort()
      }, 60000)

      setIsLoading(true)
      try {
        const plan = await handleGeneratePlan(trimmed, controller.signal)
        if (plan) {
          const planSummary = plan.summary || `Proposed ${plan.actions?.length || 0} file operation(s).`
          const agentMsg = {
            id: `msg-${Date.now() + 1}`,
            role: 'agent',
            content:
              plan.actions && plan.actions.length > 0
                ? `${planSummary}\n\nPlease review the proposed file operations below and click **Approve & Execute** to apply them.`
                : `${planSummary}\n\nNo file changes were required for this folder.`,
            plan: { summary: planSummary },
            actions: plan.actions || [],
            status: 'success',
            timestamp: Date.now(),
          }
          setConversations((prev) =>
            prev.map((c) =>
              c.id === activeId ? { ...c, messages: [...c.messages, agentMsg] } : c
            )
          )
        }
      } catch (err) {
        const isAbort = err.name === 'AbortError'
        const errorMsg = {
          id: `msg-${Date.now() + 1}`,
          role: 'agent',
          content: isAbort
            ? 'Request was stopped or timed out after 60 seconds.'
            : `Failed to prepare file operations: ${err.message}. Please check your active AI model in Settings or ensure the target directory is accessible.`,
          status: isAbort ? 'cancelled' : 'failed',
          timestamp: Date.now(),
        }
        setConversations((prev) =>
          prev.map((c) =>
            c.id === activeId ? { ...c, messages: [...c.messages, errorMsg] } : c
          )
        )
      } finally {
        clearTimeout(timeoutId)
        setIsLoading(false)
        setIsGeneratingPlan(false)
        abortControllerRef.current = null
        activeTaskIdRef.current = null
        refreshHealth()
      }
      return
    }

    // Otherwise, route to general agent loop
    const taskId = `task-${Date.now()}`
    activeTaskIdRef.current = taskId
    const controller = new AbortController()
    abortControllerRef.current = controller
    const timeoutId = setTimeout(() => {
      controller.abort()
    }, 60000)

    setIsLoading(true)

    try {
      const result = await executeTaskApi(
        {
          task_id: taskId,
          prompt: trimmed,
          conversation_id: activeId,
        },
        controller.signal
      )

      const agentMsg = {
        id: `msg-${Date.now() + 1}`,
        role: 'agent',
        content:
          result.response ||
          result.summary ||
          (result.status === 'waiting_approval'
            ? 'Awaiting your authorization. No action has been performed yet.'
            : 'Task completed.'),
        plan: result.plan,
        actions: result.actions || [],
        status: result.status || 'success',
        timestamp: Date.now(),
      }

      setConversations((prev) =>
        prev.map((c) =>
          c.id === activeId ? { ...c, messages: [...c.messages, agentMsg] } : c
        )
      )

      if (result.pending_approval) {
        setPendingApproval({ ...result.pending_approval, conversation_id: activeId })
      }
    } catch (err) {
      const isAbort = err.name === 'AbortError'
      const errorMsg = {
        id: `msg-${Date.now() + 1}`,
        role: 'agent',
        content: isAbort
          ? 'Task was stopped or timed out after 60 seconds.'
          : `Error executing task: ${err.message}. Please verify your AI provider status in Settings.`,
        status: isAbort ? 'cancelled' : 'failed',
        timestamp: Date.now(),
      }
      setConversations((prev) =>
        prev.map((c) =>
          c.id === activeId ? { ...c, messages: [...c.messages, errorMsg] } : c
        )
      )
    } finally {
      clearTimeout(timeoutId)
      setIsLoading(false)
      abortControllerRef.current = null
      activeTaskIdRef.current = null
      refreshHealth()
    }
  }

  const handleStopTask = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }
    if (activeTaskIdRef.current && !activeTaskIdRef.current.startsWith('plan-')) {
      stopTaskApi(activeTaskIdRef.current).catch(() => {})
    }
    setIsLoading(false)
    setIsGeneratingPlan(false)
  }

  const handleApproval = async (approved) => {
    if (!pendingApproval) return
    const approval = pendingApproval
    setIsLoading(true)
    setPendingApproval(null)
    try {
      const result = await approveTaskApi(approval.task_id, approved, approval.approval_token)
      const agentMsg = {
        id: `msg-${Date.now()}`,
        role: 'agent',
        content: result.response || (approved ? 'Action processed.' : 'Action cancelled.'),
        actions: result.actions || [],
        status: result.status || 'completed',
        timestamp: Date.now(),
      }
      setConversations((prev) =>
        prev.map((c) =>
          c.id === approval.conversation_id ? { ...c, messages: [...c.messages, agentMsg] } : c
        )
      )
      if (result.pending_approval) {
        setPendingApproval({ ...result.pending_approval, conversation_id: approval.conversation_id })
      }
      handleRefreshDirectory()
    } catch (err) {
      showToast(`Error processing approval: ${err.message}`, 'error')
    } finally {
      setIsLoading(false)
    }
  }

  const loadSavedConversations = async () => {
    try {
      const list = await fetchConversations()
      if (list && list.length > 0) {
        const loaded = await Promise.all(
          list.map(async (c) => {
            try {
              const msgs = await fetchMessages(c.id)
              return {
                id: c.id,
                title: c.title,
                messages: msgs.map((m) => ({
                  id: m.id,
                  role: m.role,
                  content: m.content,
                  status: m.status,
                  timestamp: new Date(m.created_at).getTime(),
                })),
              }
            } catch {
              return { id: c.id, title: c.title, messages: [] }
            }
          })
        )
        setConversations(loaded)
        if (loaded.length > 0) setActiveId(loaded[0].id)
      }
    } catch {}
  }

  const handleNewConversation = () => {
    const newId = `conv-${Date.now()}`
    const newConv = {
      id: newId,
      title: 'New Task',
      messages: [],
    }
    setConversations((prev) => [newConv, ...prev])
    setActiveId(newId)
    setPlanPreview(null)
  }

  const handleUnloadModel = async () => {
    setIsUnloading(true)
    try {
      const res = await unloadModel()
      if (res.success) {
        showToast('Model unloaded: RAM/VRAM freed', 'success')
      } else {
        showToast('Unload signal acknowledged', 'info')
      }
      refreshHealth()
    } catch (err) {
      showToast(`Failed to unload: ${err.message}`, 'error')
    } finally {
      setIsUnloading(false)
    }
  }

  const handleSaveConfig = async (newCfg) => {
    try {
      const res = await updateConfig(newCfg)
      if (res?.config) setConfig(res.config)
      refreshHealth()
      showToast('Settings saved successfully', 'success')
    } catch (err) {
      showToast(`Failed to update config: ${err.message}`, 'error')
    }
  }

  return (
    <div className={`app-root-shell ${isDragging ? 'resizing-active' : ''}`}>
      {/* Toast Notification */}
      {toastMessage && (
        <div className={`app-toast animate-slide-down ${toastMessage.type}`}>
          {toastMessage.type === 'success' && <Check size={15} />}
          {toastMessage.type === 'error' && <AlertCircle size={15} />}
          {toastMessage.type === 'info' && <Zap size={15} />}
          <span>{toastMessage.text}</span>
        </div>
      )}

      {/* 1. Compact Application Header */}
      <CompactHeader
        health={health}
        onOpenSettings={() => setIsSettingsOpen(true)}
        onUnloadModel={handleUnloadModel}
        isUnloading={isUnloading}
        canUndo={canUndo}
        onUndo={handleUndo}
      />

      {/* 2. Horizontal 60:40 Split Workspace */}
      <main className="app-workspace-split">
        {/* Left Panel (~60%): File Explorer */}
        <div
          className="workspace-left-panel"
          style={{ width: `${splitPercent}%` }}
        >
          <FileExplorer
            currentPath={currentPath}
            browseData={browseData}
            locations={locations}
            isLoading={isBrowsing}
            onNavigate={(p) => loadDirectory(p)}
            onRefresh={handleRefreshDirectory}
            onAction={handleExplorerAction}
            onPreview={handlePreviewFile}
            onAskAiAboutSelection={(prompt) => handleSendMessage(prompt)}
            onScanDuplicates={handleScanDuplicates}
            onAnalyzeStorage={handleAnalyzeStorage}
            selectedPaths={selectedPaths}
            setSelectedPaths={setSelectedPaths}
          />
        </div>

        {/* Draggable Vertical Divider */}
        <div
          className={`workspace-split-resizer ${isDragging ? 'dragging' : ''}`}
          onMouseDown={handleDividerMouseDown}
          onDoubleClick={handleResetDivider}
          title="Drag to resize panels (Double click to reset to 60:40)"
        >
          <div className="resizer-handle-grip" />
        </div>

        {/* Right Panel (~40%): AI Chat Assistant */}
        <div
          className="workspace-right-panel"
          style={{ width: `${100 - splitPercent}%` }}
        >
          <AiChatAssistant
            currentPath={currentPath}
            selectedPaths={selectedPaths}
            onClearSelectedPaths={() => setSelectedPaths(new Set())}
            conversations={conversations}
            activeId={activeId}
            onSelectConversation={setActiveId}
            onNewConversation={handleNewConversation}
            onClearAllConversations={() => setConversations([{ id: `conv-${Date.now()}`, title: 'Current Session', messages: [] }])}
            messages={activeConv?.messages || []}
            onSendMessage={handleSendMessage}
            isLoading={isLoading || isGeneratingPlan}
            onStopTask={handleStopTask}
            health={health}
            planPreview={planPreview}
            onExecutePlan={handleExecutePlan}
            onClearPlan={() => setPlanPreview(null)}
            isExecutingPlan={isExecutingPlan}
            executionResult={executionResult}
            canUndo={canUndo}
            onUndo={handleUndo}
          />
        </div>
      </main>

      {/* Modals */}
      {previewData && (
        <FilePreviewModal
          previewData={previewData}
          onClose={() => setPreviewData(null)}
          onOpenWithSystem={(p) => executeExplorerAction({ action: 'open', path: p })}
        />
      )}

      {duplicatesData && (
        <DuplicatesModal
          duplicatesData={duplicatesData}
          onClose={() => setDuplicatesData(null)}
          onCleanDuplicates={handleCleanDuplicates}
        />
      )}

      {storageData && (
        <StorageAnalysisModal
          storageData={storageData}
          onClose={() => setStorageData(null)}
          onCleanItems={handleCleanStorageItems}
          onOpenFile={(p) => executeExplorerAction({ action: 'open', path: p })}
        />
      )}

      {pendingApproval && (
        <ConfirmationModal
          approval={pendingApproval}
          onApprove={() => handleApproval(true)}
          onReject={() => handleApproval(false)}
        />
      )}

      {isSettingsOpen && (
        <SettingsModal
          config={config}
          onSave={handleSaveConfig}
          onClose={() => setIsSettingsOpen(false)}
          health={health}
          onRefreshHealth={refreshHealth}
          onUnloadModel={handleUnloadModel}
          isUnloading={isUnloading}
        />
      )}
    </div>
  )
}
