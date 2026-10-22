import React, { useState, useEffect, useRef } from 'react'
import {
  Send,
  Sparkles,
  Search,
  FolderOpen,
  HardDrive,
  Globe,
  Loader2,
  Square,
  Zap,
  Check,
  AlertCircle,
  Cpu,
} from 'lucide-react'
import Sidebar from './components/Sidebar'
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
} from './services/api'

export default function App() {
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

  const messagesEndRef = useRef(null)
  const abortControllerRef = useRef(null)
  const activeTaskIdRef = useRef(null)

  const activeConv =
    conversations.find((c) => c.id === activeId) || conversations[0]

  useEffect(() => {
    refreshHealth()
    fetchConfig().then(setConfig).catch(() => {})
    loadSavedConversations()

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

  const loadSavedConversations = async () => {
    try {
      const list = await fetchConversations()
      if (list && list.length > 0) {
        // Load messages for each conversation
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
  }

  const handleSelectConversation = (id) => {
    setActiveId(id)
  }

  const handleDeleteConversation = async (convId) => {
    try {
      await deleteConversationApi(convId)
      setConversations((prev) => {
        const filtered = prev.filter((c) => c.id !== convId)
        if (filtered.length === 0) {
          const fresh = { id: 'default', title: 'New Task', messages: [] }
          setActiveId('default')
          return [fresh]
        }
        if (activeId === convId) {
          setActiveId(filtered[0].id)
        }
        return filtered
      })
      showToast('Task deleted successfully', 'success')
    } catch (err) {
      showToast(`Failed to delete: ${err.message}`, 'error')
    }
  }

  const handleClearAllConversations = async () => {
    if (!window.confirm('Are you sure you want to delete all tasks and chat history?')) {
      return
    }
    try {
      await clearAllConversationsApi()
      const fresh = { id: 'default', title: 'New Task', messages: [] }
      setConversations([fresh])
      setActiveId('default')
      showToast('All tasks cleared', 'success')
    } catch (err) {
      showToast(`Failed to clear: ${err.message}`, 'error')
    }
  }

  const handleUnloadModel = async () => {
    setIsUnloading(true)
    try {
      await unloadModel()
      await refreshHealth()
      showToast('⚡ 3.0 GB RAM freed! Model unloaded.', 'success')
    } catch (err) {
      showToast(`Error freeing RAM: ${err.message}`, 'error')
    } finally {
      setIsUnloading(false)
    }
  }

  const handleStopTask = async () => {
    if (!isLoading) return

    const taskId = activeTaskIdRef.current
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }

    if (taskId) {
      await stopTaskApi(taskId)
    }

    // Immediately free RAM from llama-server
    try {
      await unloadModel()
    } catch {}

    setIsLoading(false)

    // Append stop notice in active conversation
    const stoppedMsg = {
      id: `msg-${Date.now()}`,
      role: 'agent',
      content: '⏹️ Task was stopped by the user. llama-server memory (~3GB) released.',
      status: 'cancelled',
      timestamp: Date.now(),
    }

    setConversations((prev) =>
      prev.map((c) =>
        c.id === activeId
          ? { ...c, messages: [...c.messages, stoppedMsg] }
          : c
      )
    )

    showToast('Task stopped. Memory freed.', 'info')
    refreshHealth()
  }

  const handleSendPrompt = async (textToSend) => {
    const prompt = (textToSend || inputPrompt).trim()
    if (!prompt || isLoading) return

    setInputPrompt('')
    setIsLoading(true)

    const taskId = `task-${Date.now()}`
    activeTaskIdRef.current = taskId
    const controller = new AbortController()
    abortControllerRef.current = controller

    // Add user message
    const userMsg = {
      id: `msg-${Date.now()}`,
      role: 'user',
      content: prompt,
      timestamp: Date.now(),
    }

    setConversations((prev) =>
      prev.map((c) => {
        if (c.id === activeId) {
          const updatedTitle =
            c.messages.length === 0 ? prompt.slice(0, 28) : c.title
          return {
            ...c,
            title: updatedTitle,
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
        content: result.response || result.summary || (
          result.status === 'waiting_approval'
            ? 'Awaiting your authorization. No action has been performed yet.'
            : 'Task completed.'
        ),
        plan: result.plan,
        actions: result.actions || [],
        status: result.status || 'success',
        timestamp: Date.now(),
      }

      setConversations((prev) =>
        prev.map((c) =>
          c.id === activeId
            ? { ...c, messages: [...c.messages, agentMsg] }
            : c
        )
      )
      if (result.pending_approval) {
        setPendingApproval({ ...result.pending_approval, conversation_id: activeId })
      }
    } catch (err) {
      if (err.name === 'AbortError') {
        // Handled by handleStopTask
        return
      }

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

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSendPrompt()
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
    if (!pendingApproval || isLoading) return

    const approval = pendingApproval
    setIsLoading(true)
    setPendingApproval(null)
    try {
      const result = await approveTaskApi(approval.task_id, approved)
      const agentMsg = {
        id: `msg-${Date.now()}`,
        role: 'agent',
        content: result.response || (approved ? 'Action processed.' : 'Action cancelled.'),
        actions: result.actions || [],
        status: result.status || 'completed',
        timestamp: Date.now(),
      }
      setConversations((prev) => prev.map((c) =>
        c.id === approval.conversation_id ? { ...c, messages: [...c.messages, agentMsg] } : c
      ))
      if (result.pending_approval) {
        setPendingApproval({ ...result.pending_approval, conversation_id: approval.conversation_id })
      }
    } catch (err) {
      showToast(`Error processing approval: ${err.message}`, 'error')
    } finally {
      setIsLoading(false)
    }
  }

  const handleApprove = () => handleApproval(true)
  const handleReject = () => handleApproval(false)

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

      <Sidebar
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

      <main className="main-chat-area">
        <header className="chat-header">
          <div className="chat-header-title-wrap">
            <h2 className="chat-header-title">
              {activeConv?.title || 'Smart Manager'}
            </h2>
            <span className="task-count-pill">
              {activeConv?.messages?.length || 0} messages
            </span>
          </div>

          <div className="header-actions-group">
            {/* Quick RAM Minimizer Button */}
            <button
              className="quick-ram-btn"
              onClick={handleUnloadModel}
              disabled={isUnloading}
              title="Release ~3GB RAM by unloading llama-server now"
            >
              <Zap size={13} className="ram-bolt" />
              <span>{isUnloading ? 'Freeing...' : 'Free RAM'}</span>
            </button>

            <div className="chat-header-model-pill">
              <span className="pulse-dot" />
              <span>
                {health?.active_provider_label || health?.active_model || 'Connecting...'}
              </span>
            </div>
          </div>
        </header>

        {/* Shimmer progress line when executing */}
        {isLoading && <div className="shimmer-progress-bar animate-shimmer" />}

        <div className="messages-stream-container">
          {activeConv?.messages.length === 0 ? (
            <div className="welcome-screen animate-fade-in">
              <div className="welcome-hero-logo animate-bounce-subtle">
                <img src="/logo.png" alt="Smart Manager" className="welcome-logo-img" />
              </div>
              <h2 className="welcome-title">What can I do for you today?</h2>
              <p className="welcome-subtitle">
                Describe any Windows task in plain English. Smart Manager plans and
                executes approved filesystem, process, and browser operations locally.
              </p>

              <div className="suggestions-grid">
                <button
                  className="suggestion-chip hover-scale"
                  onClick={() =>
                    handleSendPrompt(
                      'open pdf: Litrature_Review in downloads folder in d drive'
                    )
                  }
                >
                  <Search size={16} />
                  <span>"Open Literature Review PDF in D:\Downloads"</span>
                </button>
                <button
                  className="suggestion-chip hover-scale"
                  onClick={() =>
                    handleSendPrompt('Find Cat.png in D drive and open it.')
                  }
                >
                  <FolderOpen size={16} />
                  <span>"Find Cat.png in D drive and open it."</span>
                </button>
                <button
                  className="suggestion-chip hover-scale"
                  onClick={() =>
                    handleSendPrompt('Find large files and help me free storage.')
                  }
                >
                  <HardDrive size={16} />
                  <span>"Find large files to free storage."</span>
                </button>
                <button
                  className="suggestion-chip hover-scale"
                  onClick={() =>
                    handleSendPrompt('Search for Python tutorials on Google.')
                  }
                >
                  <Globe size={16} />
                  <span>"Search for Python tutorials on Google."</span>
                </button>
              </div>
            </div>
          ) : (
            activeConv.messages.map((m) => (
              <MessageBubble key={m.id} message={m} />
            ))
          )}

          {/* Running State Card with Micro-Animations */}
          {isLoading && (
            <div className="thinking-card-wrapper animate-slide-up">
              <div className="thinking-card">
                <div className="thinking-spinner-ring">
                  <Loader2 size={18} className="spin text-accent" />
                </div>
                <div className="thinking-text-group">
                  <div className="thinking-heading">
                    Smart Manager is executing your task...
                  </div>
                  <div className="thinking-subheading">
                    Reasoning, dispatching OS tools, and validating outcome
                  </div>
                </div>
                <button
                  className="thinking-stop-btn animate-pulse-glow"
                  onClick={handleStopTask}
                  title="Stop task and release memory"
                >
                  <Square size={13} fill="currentColor" />
                  <span>Stop</span>
                </button>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        <div className="chat-input-container">
          <div className="chat-input-box">
            <textarea
              className="chat-textarea"
              placeholder="Ask Smart Manager to perform any Windows task..."
              value={inputPrompt}
              onChange={(e) => setInputPrompt(e.target.value)}
              onKeyDown={handleKeyDown}
              rows={1}
            />

            <div className="input-button-group">
              {/* Animated Stop Button when active */}
              {isLoading ? (
                <button
                  className="chat-stop-btn animate-pulse-glow"
                  onClick={handleStopTask}
                  title="Stop Task & Free Memory"
                >
                  <Square size={15} fill="currentColor" />
                  <span>Stop</span>
                </button>
              ) : (
                <button
                  className="chat-send-btn hover-scale"
                  onClick={() => handleSendPrompt()}
                  disabled={!inputPrompt.trim()}
                  title="Send Prompt (Enter)"
                >
                  <Send size={18} />
                </button>
              )}
            </div>
          </div>
        </div>
      </main>

      {/* Confirmation Modal */}
      <ConfirmationModal
        request={pendingApproval}
        onApprove={handleApprove}
        onReject={handleReject}
      />

      {/* Settings Modal */}
      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
        config={config}
        onSaveConfig={handleSaveConfig}
        health={health}
        onRefreshHealth={refreshHealth}
      />
    </div>
  )
}
