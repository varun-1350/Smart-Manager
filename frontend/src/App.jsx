import React, { useState, useEffect, useRef } from 'react'
import {
  Send,
  Sparkles,
  Loader2,
  Square,
  Zap,
  Check,
  AlertCircle,
  Cpu,
  FolderOpen,
  MessageSquare,
} from 'lucide-react'
import Sidebar from './components/Sidebar'
import FileBrowser from './components/FileBrowser'
import AiCommandPanel from './components/AiCommandPanel'
import FilePreviewModal from './components/FilePreviewModal'
import DuplicatesModal from './components/DuplicatesModal'
import StorageAnalysisModal from './components/StorageAnalysisModal'
import MessageBubble from './components/MessageBubble'
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
import logoAsset from './assets/logo.png'

export default function App() {
  // Top-level Navigation Mode ('explorer' by default, 'chat' for conversation history)
  const [activeView, setActiveView] = useState('explorer')

  // File Explorer States
  const [locations, setLocations] = useState([])
  const [currentPath, setCurrentPath] = useState('')
  const [browseData, setBrowseData] = useState(null)
  const [isBrowsing, setIsBrowsing] = useState(false)
  const [previewData, setPreviewData] = useState(null)
  const [duplicatesData, setDuplicatesData] = useState(null)
  const [storageData, setStorageData] = useState(null)

  // AI File Organization Plan States
  const [planPreview, setPlanPreview] = useState(null)
  const [isGeneratingPlan, setIsGeneratingPlan] = useState(false)
  const [isExecutingPlan, setIsExecutingPlan] = useState(false)
  const [executionResult, setExecutionResult] = useState(null)
  const [canUndo, setCanUndo] = useState(false)

  // Conversational Task States
  const [conversations, setConversations] = useState([
    {
      id: 'default',
      title: 'Current Session',
      messages: [],
    },
  ])
  const [activeId, setActiveId] = useState('default')
  const [inputPrompt, setInputPrompt] = useState('')
  const [health, setHealth] = useState(null)
  const [config, setConfig] = useState(null)
  const [isSettingsOpen, setIsSettingsOpen] = useState(false)
  const [pendingApproval, setPendingApproval] = useState(null)
  const [isLoading, setIsLoading] = useState(false)
  const [isUnloading, setIsUnloading] = useState(false)
  const [toastMessage, setToastMessage] = useState(null)
  const [hasWelcomeLogoError, setHasWelcomeLogoError] = useState(false)

  const messagesEndRef = useRef(null)
  const abortControllerRef = useRef(null)
  const activeTaskIdRef = useRef(null)

  const activeConv =
    conversations.find((c) => c.id === activeId) || conversations[0]
  const isAwaitingApproval = Boolean(pendingApproval)
  const isBusy = isLoading && !isAwaitingApproval

  // Initialization
  useEffect(() => {
    refreshHealth()
    fetchConfig().then(setConfig).catch(() => {})
    loadSavedConversations()
    initExplorer()

    const interval = setInterval(refreshHealth, 8000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [activeConv?.messages, isLoading])

  const showToast = (text, type = 'info') => {
    setToastMessage({ text, type })
    setTimeout(() => setToastMessage(null), 3500)
  }

  const refreshHealth = async () => {
    const h = await fetchHealth()
    setHealth(h)
  }

  // ==========================================================================
  // File Explorer Lifecycle & Handlers
  // ==========================================================================
  const initExplorer = async () => {
    try {
      const locs = await fetchLocations()
      setLocations(locs)
      if (locs && locs.length > 0) {
        // Default to Desktop or first location
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
        showToast('Folder created', 'success')
      } else if (payload.action === 'rename') {
        showToast('Item renamed', 'success')
      } else if (payload.action === 'trash') {
        showToast('Moved to trash (undo available)', 'success')
        setCanUndo(true)
      } else if (payload.action === 'open') {
        showToast('Opening with default Windows app', 'info')
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
    showToast('Scanning directory for duplicate files...', 'info')
    try {
      const dups = await fetchDuplicates(currentPath)
      setDuplicatesData(dups)
    } catch (err) {
      showToast(`Duplicate scan error: ${err.message}`, 'error')
    }
  }

  const handleAnalyzeStorage = async () => {
    if (!currentPath) return
    showToast('Analyzing folder storage and large files...', 'info')
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

  // ==========================================================================
  // AI Batch Action Planning & Execution
  // ==========================================================================
  const handleGeneratePlan = async (instruction) => {
    if (!currentPath) return
    setIsGeneratingPlan(true)
    setPlanPreview(null)
    setExecutionResult(null)
    try {
      const plan = await generateExplorerPlan(currentPath, instruction)
      setPlanPreview(plan)
    } catch (err) {
      showToast(`Failed to generate plan: ${err.message}`, 'error')
    } finally {
      setIsGeneratingPlan(false)
    }
  }

  const handleExecutePlan = async () => {
    if (!planPreview || !planPreview.actions?.length) return
    setIsExecutingPlan(true)
    try {
      const batchId = `plan-${Date.now()}`
      const result = await executeExplorerPlan(batchId, planPreview.actions)
      setExecutionResult(result)
      setPlanPreview(null)
      showToast(`Successfully organized ${result.executed_count} file(s)!`, 'success')
      setCanUndo(true)
      handleRefreshDirectory()
    } catch (err) {
      showToast(`Failed to execute plan: ${err.message}`, 'error')
    } finally {
      setIsExecutingPlan(false)
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
  // Conversational Task Chat Handlers
  // ==========================================================================
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
    } catch {
      // Keep default conversation
    }
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
    setActiveView('chat')
  }

  const handleSelectConversation = (id) => {
    setActiveId(id)
    setActiveView('chat')
  }

  const handleDeleteConversation = async (id) => {
    try {
      await deleteConversationApi(id)
      setConversations((prev) => prev.filter((c) => c.id !== id))
      if (activeId === id) {
        const remaining = conversations.filter((c) => c.id !== id)
        if (remaining.length > 0) setActiveId(remaining[0].id)
        else handleNewConversation()
      }
    } catch (err) {
      showToast(`Failed to delete task: ${err.message}`, 'error')
    }
  }

  const handleClearAllConversations = async () => {
    try {
      await clearAllConversationsApi()
      const newId = `conv-${Date.now()}`
      setConversations([{ id: newId, title: 'Current Session', messages: [] }])
      setActiveId(newId)
      showToast('All tasks cleared', 'info')
    } catch (err) {
      showToast(`Failed to clear tasks: ${err.message}`, 'error')
    }
  }

  const handleUnloadModel = async () => {
    setIsUnloading(true)
    try {
      const res = await unloadModel()
      if (res.success) {
        showToast('Model unloaded: VRAM freed', 'success')
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

  const handleSendPrompt = async () => {
    if (!inputPrompt.trim() || isLoading) return

    const prompt = inputPrompt.trim()
    setInputPrompt('')

    const userMsg = {
      id: `msg-${Date.now()}`,
      role: 'user',
      content: prompt,
      timestamp: Date.now(),
    }

    const taskId = `task-${Date.now()}`
    activeTaskIdRef.current = taskId

    const controller = new AbortController()
    abortControllerRef.current = controller

    setIsLoading(true)

    setConversations((prev) =>
      prev.map((c) => {
        if (c.id === activeId) {
          const isFirstMessage = c.messages.length === 0
          return {
            ...c,
            title: isFirstMessage ? prompt.slice(0, 24) : c.title,
            messages: [...c.messages, userMsg],
          }
        }
        return c
      })
    )

    try {
      const result = await executeTaskApi(
        {
          task_id: taskId,
          prompt: prompt,
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
      if (err.name === 'AbortError') return

      const errorMsg = {
        id: `msg-${Date.now() + 1}`,
        role: 'agent',
        content: `Error executing task: ${err.message}`,
        status: 'failed',
        timestamp: Date.now(),
      }
      setConversations((prev) =>
        prev.map((c) =>
          c.id === activeId ? { ...c, messages: [...c.messages, errorMsg] } : c
        )
      )
    } finally {
      setIsLoading(false)
      abortControllerRef.current = null
      activeTaskIdRef.current = null
      refreshHealth()
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
    } catch (err) {
      showToast(`Error processing approval: ${err.message}`, 'error')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="app-container">
      {/* Toast Notification */}
      {toastMessage && (
        <div className={`app-toast animate-slide-down ${toastMessage.type}`}>
          {toastMessage.type === 'success' && <Check size={16} />}
          {toastMessage.type === 'error' && <AlertCircle size={16} />}
          {toastMessage.type === 'info' && <Zap size={16} />}
          <span>{toastMessage.text}</span>
        </div>
      )}

      {/* Left Sidebar (Locations, Drives, Tasks, Settings) */}
      <Sidebar
        activeView={activeView}
        onSwitchView={setActiveView}
        locations={locations}
        currentPath={currentPath}
        onNavigate={(p) => loadDirectory(p)}
        onUndo={handleUndo}
        canUndo={canUndo}
        conversations={conversations}
        activeId={activeId}
        onSelectConversation={handleSelectConversation}
        onNewConversation={handleNewConversation}
        onDeleteConversation={handleDeleteConversation}
        onClearAllConversations={handleClearAllConversations}
        onOpenSettings={() => setIsSettingsOpen(true)}
        health={health}
        onUnloadModel={handleUnloadModel}
        isUnloading={isUnloading}
      />

      {/* Main Workspace Area */}
      {activeView === 'explorer' ? (
        <main className="main-explorer-area">
          {/* File Browser Grid/List */}
          <FileBrowser
            currentPath={currentPath}
            browseData={browseData}
            isLoading={isBrowsing}
            onNavigate={(p) => loadDirectory(p)}
            onRefresh={handleRefreshDirectory}
            onAction={handleExplorerAction}
            onPreview={handlePreviewFile}
            onSendToAi={(promptText) => handleGeneratePlan(promptText)}
            onScanDuplicates={handleScanDuplicates}
            onAnalyzeStorage={handleAnalyzeStorage}
          />

          {/* AI Command & Structured Plan Decision Panel */}
          <AiCommandPanel
            currentPath={currentPath}
            onGeneratePlan={handleGeneratePlan}
            onExecutePlan={handleExecutePlan}
            onUndo={handleUndo}
            isGeneratingPlan={isGeneratingPlan}
            isExecutingPlan={isExecutingPlan}
            planPreview={planPreview}
            onClearPlan={() => setPlanPreview(null)}
            executionResult={executionResult}
          />
        </main>
      ) : (
        /* Traditional Chat & Task History Area */
        <main className="main-chat-area">
          <header className="chat-header">
            <div className="chat-header-title-wrap">
              <h2 className="chat-header-title">
                {activeConv?.title || 'Smart Manager Tasks'}
              </h2>
            </div>
            <div className="header-actions-group">
              <div className="chat-header-model-pill" aria-live="polite">
                <span className="pulse-dot" aria-hidden="true" />
                <span className="chat-header-model-label">
                  {health?.active_provider_label || health?.active_model || 'Connecting...'}
                </span>
              </div>
            </div>
          </header>

          {isBusy && <div className="shimmer-progress-bar animate-shimmer" />}

          <div className="messages-stream-container">
            {activeConv?.messages.length === 0 ? (
              <div className="welcome-screen animate-fade-in">
                <div className="welcome-hero-logo animate-bounce-subtle">
                  {hasWelcomeLogoError ? (
                    <span className="welcome-logo-fallback" aria-label="Smart Manager">
                      <Sparkles size={32} aria-hidden="true" />
                    </span>
                  ) : (
                    <img
                      src={logoAsset}
                      alt="Smart Manager"
                      className="welcome-logo-img"
                      onError={() => setHasWelcomeLogoError(true)}
                    />
                  )}
                </div>
                <h2 className="welcome-title">AI File Task Console</h2>
                <p className="welcome-subtitle">
                  Describe a task to run through the autonomous agent loop.
                </p>
              </div>
            ) : (
              activeConv.messages.map((m) => <MessageBubble key={m.id} message={m} />)
            )}

            {isBusy && (
              <div className="thinking-card-wrapper animate-slide-up">
                <div className="thinking-card">
                  <div className="thinking-spinner-ring">
                    <Loader2 size={18} className="spin text-accent" />
                  </div>
                  <div className="thinking-text-group">
                    <div className="thinking-heading">Executing Action</div>
                    <div className="thinking-subtext">Operating on local Windows system...</div>
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          <div className="chat-input-container">
            <div className="chat-input-card">
              <textarea
                className="chat-textarea"
                rows={1}
                placeholder="Type a general agent command..."
                value={inputPrompt}
                onChange={(e) => setInputPrompt(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    handleSendPrompt()
                  }
                }}
                disabled={isLoading}
              />
              <button
                className="btn-send-message"
                onClick={handleSendPrompt}
                disabled={!inputPrompt.trim() || isLoading}
              >
                <Send size={15} />
              </button>
            </div>
          </div>
        </main>
      )}

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
