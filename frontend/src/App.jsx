import React, { useState, useEffect, useRef } from 'react'
import {
  Send,
  Sparkles,
  Search,
  FolderOpen,
  HardDrive,
  Globe,
  Loader2
} from 'lucide-react'
import Sidebar from './components/Sidebar'
import MessageBubble from './components/MessageBubble'
import ConfirmationModal from './components/ConfirmationModal'
import SettingsModal from './components/SettingsModal'
import { fetchHealth, fetchConfig } from './services/api'

export default function App() {
  const [conversations, setConversations] = useState([
    {
      id: 'default',
      title: 'Current Session',
      messages: []
    }
  ])
  const [activeId, setActiveId] = useState('default')
  const [inputPrompt, setInputPrompt] = useState('')
  const [health, setHealth] = useState(null)
  const [config, setConfig] = useState(null)
  const [isSettingsOpen, setIsSettingsOpen] = useState(false)
  const [pendingApproval, setPendingApproval] = useState(null)
  const [isLoading, setIsLoading] = useState(false)

  const messagesEndRef = useRef(null)

  const activeConv = conversations.find((c) => c.id === activeId) || conversations[0]

  useEffect(() => {
    refreshHealth()
    fetchConfig().then(setConfig).catch(() => {})
    const interval = setInterval(refreshHealth, 8000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [activeConv?.messages])

  const refreshHealth = async () => {
    const h = await fetchHealth()
    setHealth(h)
  }

  const handleNewConversation = () => {
    const newId = `conv-${Date.now()}`
    const newConv = {
      id: newId,
      title: 'New Task',
      messages: []
    }
    setConversations((prev) => [newConv, ...prev])
    setActiveId(newId)
  }

  const handleSelectConversation = (id) => {
    setActiveId(id)
  }

  const handleSendPrompt = async (textToSend) => {
    const prompt = (textToSend || inputPrompt).trim()
    if (!prompt || isLoading) return

    setInputPrompt('')
    setIsLoading(true)

    // Add user message
    const userMsg = {
      id: `msg-${Date.now()}`,
      role: 'user',
      content: prompt,
      timestamp: Date.now()
    }

    setConversations((prev) =>
      prev.map((c) => {
        if (c.id === activeId) {
          const updatedTitle = c.messages.length === 0 ? prompt.slice(0, 28) : c.title
          return {
            ...c,
            title: updatedTitle,
            messages: [...c.messages, userMsg]
          }
        }
        return c
      })
    )

    try {
      // Connect to backend task API
      const res = await fetch('http://127.0.0.1:8765/api/task/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          task_id: `task-${Date.now()}`,
          prompt: prompt,
          conversation_id: activeId
        })
      })

      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || `Server error: HTTP ${res.status}`)
      }

      const result = await res.json()

      const agentMsg = {
        id: `msg-${Date.now() + 1}`,
        role: 'agent',
        content: result.response || result.summary || 'Task completed.',
        plan: result.plan,
        actions: result.actions || [],
        status: result.status || 'success',
        timestamp: Date.now()
      }

      setConversations((prev) =>
        prev.map((c) =>
          c.id === activeId ? { ...c, messages: [...c.messages, agentMsg] } : c
        )
      )
    } catch (err) {
      const errorMsg = {
        id: `msg-${Date.now() + 1}`,
        role: 'agent',
        content: `Error executing task: ${err.message}`,
        status: 'failed',
        timestamp: Date.now()
      }
      setConversations((prev) =>
        prev.map((c) =>
          c.id === activeId ? { ...c, messages: [...c.messages, errorMsg] } : c
        )
      )
    } finally {
      setIsLoading(false)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSendPrompt()
    }
  }

  const handleSaveConfig = (newCfg) => {
    setConfig((prev) => ({ ...prev, ...newCfg }))
    refreshHealth()
  }

  const handleApprove = (approvalId) => {
    setPendingApproval(null)
  }

  const handleReject = (approvalId) => {
    setPendingApproval(null)
  }

  return (
    <div className="app-container">
      <Sidebar
        conversations={conversations}
        activeId={activeId}
        onSelectConversation={handleSelectConversation}
        onNewConversation={handleNewConversation}
        onOpenSettings={() => setIsSettingsOpen(true)}
        health={health}
      />

      <main className="main-chat-area">
        <header className="chat-header">
          <div className="chat-header-title">
            {activeConv?.title || 'Smart Manager'}
          </div>
          <div className="chat-header-model-pill">
            {health?.active_model ? `Model: ${health.active_model}` : 'Connecting...'}
          </div>
        </header>

        <div className="messages-stream-container">
          {activeConv?.messages.length === 0 ? (
            <div className="welcome-screen">
              <div className="welcome-hero-icon">
                <Sparkles size={32} />
              </div>
              <h2 className="welcome-title">What can I do for you today?</h2>
              <p className="welcome-subtitle">
                Describe your goal in plain English. Smart Manager will autonomously plan and execute
                approved Windows actions on your system.
              </p>

              <div className="suggestions-grid">
                <button
                  className="suggestion-chip"
                  onClick={() => handleSendPrompt('Find Cat.png in D drive and open it.')}
                >
                  <Search size={16} />
                  <span>"Find Cat.png in D drive and open it."</span>
                </button>
                <button
                  className="suggestion-chip"
                  onClick={() => handleSendPrompt('Find my ten most recent downloads.')}
                >
                  <FolderOpen size={16} />
                  <span>"Find my ten most recent downloads."</span>
                </button>
                <button
                  className="suggestion-chip"
                  onClick={() => handleSendPrompt('Find large files and help me free storage.')}
                >
                  <HardDrive size={16} />
                  <span>"Find large files to free storage."</span>
                </button>
                <button
                  className="suggestion-chip"
                  onClick={() => handleSendPrompt('Search for Python tutorials on Google.')}
                >
                  <Globe size={16} />
                  <span>"Search for Python tutorials on Google."</span>
                </button>
              </div>
            </div>
          ) : (
            activeConv.messages.map((m) => <MessageBubble key={m.id} message={m} />)
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
            <button
              className="chat-send-btn"
              onClick={() => handleSendPrompt()}
              disabled={isLoading || !inputPrompt.trim()}
              title="Send Prompt"
            >
              {isLoading ? <Loader2 size={18} className="spin" /> : <Send size={18} />}
            </button>
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
