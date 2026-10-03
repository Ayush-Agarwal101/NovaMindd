import { useCallback, useEffect, useRef, useState } from 'react'
import { chatComplete, ingestDocument, listModels } from '../api/client'
import type { ChatTurn, IngestResult, ModelStatus } from '../api/client'
import { S, Spinner } from '../components/ui'
import {
  ChevronDown,
  Edit3,
  MessageSquare,
  Paperclip,
  Plus,
  Send,
  Trash2,
  Upload,
  X,
} from 'lucide-react'

// ─────────────────────────────────────────────────────────────────────────────
// Domain types
// ─────────────────────────────────────────────────────────────────────────────

export interface StoredMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  attachedDocs?: string[]   // filenames shown in user bubble
  error?: boolean
  ts: number
}

export interface ChatSession {
  id: string
  title: string
  model: string
  createdAt: number
  updatedAt: number
  messages: StoredMessage[]
}

interface AttachedDoc {
  file: File
  result: IngestResult
}

// ─────────────────────────────────────────────────────────────────────────────
// localStorage persistence
// ─────────────────────────────────────────────────────────────────────────────

const LS_KEY = 'novamindd_chat_sessions'

function loadSessions(): ChatSession[] {
  try {
    const raw = localStorage.getItem(LS_KEY)
    return raw ? (JSON.parse(raw) as ChatSession[]) : []
  } catch {
    return []
  }
}

function saveSessions(sessions: ChatSession[]) {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify(sessions))
  } catch { /* quota exceeded — silently ignore */ }
}

function newSessionId() {
  return `s_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`
}

function newMsgId() {
  return `m_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`
}

function titleFrom(text: string): string {
  return text.length > 42 ? text.slice(0, 42).trimEnd() + '…' : text
}

// ─────────────────────────────────────────────────────────────────────────────
// useChatSessions hook
// ─────────────────────────────────────────────────────────────────────────────

function useChatSessions() {
  const [sessions, setSessions] = useState<ChatSession[]>(loadSessions)
  const [activeId, setActiveId] = useState<string | null>(
    () => loadSessions()[0]?.id ?? null,
  )

  // Persist on every change
  useEffect(() => { saveSessions(sessions) }, [sessions])

  const active = sessions.find(s => s.id === activeId) ?? null

  const createSession = useCallback((model: string): ChatSession => {
    const s: ChatSession = {
      id: newSessionId(),
      title: 'New chat',
      model,
      createdAt: Date.now(),
      updatedAt: Date.now(),
      messages: [],
    }
    setSessions(prev => [s, ...prev])
    setActiveId(s.id)
    return s
  }, [])

  const deleteSession = useCallback((id: string) => {
    setSessions(prev => {
      const next = prev.filter(s => s.id !== id)
      return next
    })
    setActiveId(prev => {
      if (prev !== id) return prev
      const remaining = loadSessions().filter(s => s.id !== id)
      return remaining[0]?.id ?? null
    })
  }, [])

  const renameSession = useCallback((id: string, title: string) => {
    setSessions(prev => prev.map(s => s.id === id ? { ...s, title, updatedAt: Date.now() } : s))
  }, [])

  const appendMessage = useCallback((sessionId: string, msg: StoredMessage) => {
    setSessions(prev => prev.map(s => {
      if (s.id !== sessionId) return s
      const messages = [...s.messages, msg]
      const title = s.messages.length === 0 && msg.role === 'user'
        ? titleFrom(msg.content)
        : s.title
      return { ...s, messages, title, updatedAt: Date.now() }
    }))
  }, [])

  const updateLastAssistant = useCallback((sessionId: string, patch: Partial<StoredMessage>) => {
    setSessions(prev => prev.map(s => {
      if (s.id !== sessionId) return s
      const messages = [...s.messages]
      for (let i = messages.length - 1; i >= 0; i--) {
        if (messages[i].role === 'assistant') {
          messages[i] = { ...messages[i], ...patch }
          break
        }
      }
      return { ...s, messages }
    }))
  }, [])

  const updateModel = useCallback((sessionId: string, model: string) => {
    setSessions(prev => prev.map(s => s.id === sessionId ? { ...s, model } : s))
  }, [])

  return {
    sessions,
    active,
    activeId,
    setActiveId,
    createSession,
    deleteSession,
    renameSession,
    appendMessage,
    updateLastAssistant,
    updateModel,
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// AttachPopover  (multi-file)
// ─────────────────────────────────────────────────────────────────────────────

type FilePhase = 'idle' | 'ingesting' | 'done' | 'error'
interface FileEntry {
  key: string          // stable key = name+size
  file: File
  phase: FilePhase
  result?: IngestResult
  error?: string
}

function AttachPopover({
  onClose,
  onAttached,
  sessionId,
}: {
  onClose: () => void
  onAttached: (docs: AttachedDoc[]) => void
  sessionId?: string
}) {
  const [entries, setEntries] = useState<FileEntry[]>([])
  const fileRef = useRef<HTMLInputElement>(null)

  const fileKey = (f: File) => `${f.name}_${f.size}`

  const addFiles = (files: FileList | File[]) => {
    const arr = Array.from(files)
    setEntries(prev => {
      const existingKeys = new Set(prev.map(e => e.key))
      const fresh = arr
        .filter(f => !existingKeys.has(fileKey(f)))
        .map(f => ({ key: fileKey(f), file: f, phase: 'idle' as FilePhase }))
      return [...prev, ...fresh]
    })
  }

  const removeEntry = (key: string) =>
    setEntries(prev => prev.filter(e => e.key !== key))

  const ingestOne = async (key: string) => {
    setEntries(prev => prev.map(e => e.key === key ? { ...e, phase: 'ingesting' } : e))
    const entry = entries.find(e => e.key === key)!
    try {
      // Scope to session when sessionId provided, otherwise global
      const scope = sessionId ? 'session' : 'global'
      const result = await ingestDocument(entry.file, scope, sessionId)
      setEntries(prev => prev.map(e => e.key === key ? { ...e, phase: 'done', result } : e))
    } catch (err: any) {
      const msg = err?.response?.data?.detail ?? 'Ingestion failed'
      setEntries(prev => prev.map(e => e.key === key ? { ...e, phase: 'error', error: msg } : e))
    }
  }

  const ingestAll = async () => {
    const pending = entries.filter(e => e.phase === 'idle' || e.phase === 'error')
    await Promise.all(pending.map(e => ingestOne(e.key)))
  }

  // After all done, call onAttached with finished docs
  const handleDone = () => {
    const done = entries.filter(e => e.phase === 'done' && e.result)
    if (done.length > 0) onAttached(done.map(e => ({ file: e.file, result: e.result! })))
    onClose()
  }

  const allDone = entries.length > 0 && entries.every(e => e.phase === 'done')
  const anyIngesting = entries.some(e => e.phase === 'ingesting')
  const hasPending = entries.some(e => e.phase === 'idle' || e.phase === 'error')

  return (
    <>
      <div onClick={onClose} style={{ position: 'fixed', inset: 0, zIndex: 40 }} />
      <div style={{
        position: 'absolute',
        bottom: 'calc(100% + 10px)',
        left: 0,
        zIndex: 50,
        width: 320,
        background: 'var(--color-surface)',
        border: '1px solid var(--color-border)',
        borderRadius: 10,
        boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
        overflow: 'hidden',
      }}>
        {/* Header */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '10px 14px', borderBottom: '1px solid var(--color-border)',
          background: 'var(--color-surface2)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
            <Paperclip size={13} color="var(--color-accent)" />
            <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-text)' }}>
              Attach Documents
            </span>
            {entries.length > 0 && (
              <span style={{
                background: 'var(--color-accent)', color: '#fff',
                borderRadius: 10, fontSize: 10, fontWeight: 700,
                padding: '1px 7px',
              }}>{entries.length}</span>
            )}
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-muted)', display: 'flex' }}>
            <X size={14} />
          </button>
        </div>

        <div style={{ padding: 12 }}>
          {/* Drop zone */}
          <div
            onClick={() => fileRef.current?.click()}
            onDragOver={e => e.preventDefault()}
            onDrop={e => { e.preventDefault(); addFiles(e.dataTransfer.files) }}
            style={{
              border: `2px dashed ${entries.length ? 'var(--color-accent)' : 'var(--color-border)'}`,
              borderRadius: 8, padding: '14px 12px', textAlign: 'center',
              cursor: 'pointer', marginBottom: 10, transition: 'border-color 0.15s',
            }}
          >
            <Upload size={20} color={entries.length ? 'var(--color-accent)' : 'var(--color-muted)'} style={{ marginBottom: 5 }} />
            <div style={{ fontSize: 12, color: 'var(--color-muted)' }}>
              Click or drag files here<br />
              <span style={{ fontSize: 11 }}>PDF · TXT · MD · multiple allowed</span>
            </div>
          </div>
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.txt,.md"
            multiple
            style={{ display: 'none' }}
            onChange={e => { if (e.target.files) addFiles(e.target.files); e.target.value = '' }}
          />

          {/* File list */}
          {entries.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 10, maxHeight: 200, overflowY: 'auto' }}>
              {entries.map(entry => (
                <div key={entry.key} style={{
                  display: 'flex', alignItems: 'center', gap: 8,
                  background: 'var(--color-surface2)',
                  border: `1px solid ${
                    entry.phase === 'done'  ? 'rgba(16,185,129,0.3)' :
                    entry.phase === 'error' ? 'rgba(239,68,68,0.3)'  :
                    'var(--color-border)'
                  }`,
                  borderRadius: 7, padding: '7px 10px',
                }}>
                  {/* Status icon */}
                  <div style={{ flexShrink: 0, width: 18, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    {entry.phase === 'ingesting' && <Spinner size={13} />}
                    {entry.phase === 'done'  && <span style={{ color: 'var(--color-success)', fontSize: 13 }}>✓</span>}
                    {entry.phase === 'error' && <span style={{ color: 'var(--color-danger)',  fontSize: 13 }}>✕</span>}
                    {entry.phase === 'idle'  && <Paperclip size={13} color="var(--color-muted)" />}
                  </div>

                  {/* Name + meta */}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{
                      fontSize: 12, fontWeight: 500, color: 'var(--color-text)',
                      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    }}>{entry.file.name}</div>
                    <div style={{ fontSize: 10.5, color: 'var(--color-muted)', marginTop: 1 }}>
                      {entry.phase === 'done'  && entry.result
                        ? `${entry.result.chunks_created} chunks`
                        : entry.phase === 'error'
                          ? entry.error
                          : `${(entry.file.size / 1024).toFixed(1)} KB`
                      }
                    </div>
                  </div>

                  {/* Retry / remove */}
                  <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
                    {(entry.phase === 'idle' || entry.phase === 'error') && (
                      <button
                        onClick={() => ingestOne(entry.key)}
                        title="Ingest"
                        style={{
                          background: 'var(--color-accent)', border: 'none', borderRadius: 5,
                          padding: '3px 8px', fontSize: 11, color: '#fff', cursor: 'pointer',
                          display: 'flex', alignItems: 'center', gap: 4,
                        }}
                      >
                        <Upload size={10} /> {entry.phase === 'error' ? 'Retry' : 'Ingest'}
                      </button>
                    )}
                    {entry.phase !== 'ingesting' && (
                      <button
                        onClick={() => removeEntry(entry.key)}
                        title="Remove"
                        style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-muted)', display: 'flex', alignItems: 'center', padding: 2, borderRadius: 4 }}
                      >
                        <X size={12} />
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Action buttons */}
          <div style={{ display: 'flex', gap: 8 }}>
            {hasPending && (
              <button
                style={{ ...S.btn, flex: 1, justifyContent: 'center', fontSize: 13 }}
                disabled={anyIngesting}
                onClick={ingestAll}
              >
                {anyIngesting ? <Spinner size={13} /> : <Upload size={13} />}
                {anyIngesting ? 'Ingesting…' : 'Ingest All'}
              </button>
            )}
            <button
              style={{
                ...S.btnGhost,
                flex: allDone ? 1 : 0,
                justifyContent: 'center',
                fontSize: 13,
                ...(allDone ? { borderColor: 'var(--color-success)', color: 'var(--color-success)' } : {}),
              }}
              onClick={handleDone}
            >
              {allDone ? '✓ Attach & Close' : 'Close'}
            </button>
          </div>
        </div>
      </div>
    </>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Session sidebar
// ─────────────────────────────────────────────────────────────────────────────

function SessionSidebar({
  sessions,
  activeId,
  onSelect,
  onNew,
  onDelete,
  onRename,
}: {
  sessions: ChatSession[]
  activeId: string | null
  onSelect: (id: string) => void
  onNew: () => void
  onDelete: (id: string) => void
  onRename: (id: string, title: string) => void
}) {
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editVal, setEditVal] = useState('')

  const startEdit = (s: ChatSession) => {
    setEditingId(s.id)
    setEditVal(s.title)
  }

  const commitEdit = (id: string) => {
    const t = editVal.trim()
    if (t) onRename(id, t)
    setEditingId(null)
  }

  // Group sessions by day
  const today = new Date()
  const yesterday = new Date(today); yesterday.setDate(today.getDate() - 1)
  const fmt = (ts: number) => {
    const d = new Date(ts)
    if (d.toDateString() === today.toDateString()) return 'Today'
    if (d.toDateString() === yesterday.toDateString()) return 'Yesterday'
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  }

  const groups: { label: string; items: ChatSession[] }[] = []
  for (const s of sessions) {
    const label = fmt(s.updatedAt)
    const last = groups[groups.length - 1]
    if (last && last.label === label) last.items.push(s)
    else groups.push({ label, items: [s] })
  }

  return (
    <aside style={{
      width: 240,
      minWidth: 240,
      display: 'flex',
      flexDirection: 'column',
      borderRight: '1px solid var(--color-border)',
      background: 'var(--color-surface)',
      overflow: 'hidden',
    }}>
      {/* Header */}
      <div style={{
        padding: '12px 14px',
        borderBottom: '1px solid var(--color-border)',
        display: 'flex',
        alignItems: 'center',
        gap: 8,
      }}>
        <span style={{ flex: 1, fontSize: 13, fontWeight: 600, color: 'var(--color-text)' }}>
          Chats
        </span>
        <button
          onClick={onNew}
          title="New chat"
          style={{
            background: 'var(--color-accent)',
            border: 'none',
            borderRadius: 7,
            width: 28, height: 28,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            cursor: 'pointer',
          }}
        >
          <Plus size={14} color="#fff" />
        </button>
      </div>

      {/* List */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '8px 6px' }}>
        {sessions.length === 0 && (
          <div style={{ textAlign: 'center', padding: '32px 12px', fontSize: 12, color: 'var(--color-muted)' }}>
            No chats yet.<br />Click + to start.
          </div>
        )}

        {groups.map(group => (
          <div key={group.label}>
            <div style={{
              fontSize: 10.5, fontWeight: 700, color: 'var(--color-muted)',
              textTransform: 'uppercase', letterSpacing: '0.07em',
              padding: '8px 8px 4px',
            }}>
              {group.label}
            </div>
            {group.items.map(s => (
              <div
                key={s.id}
                onClick={() => onSelect(s.id)}
                style={{
                  display: 'flex', alignItems: 'center',
                  padding: '7px 8px',
                  borderRadius: 7,
                  cursor: 'pointer',
                  background: s.id === activeId ? 'var(--color-surface2)' : 'transparent',
                  border: `1px solid ${s.id === activeId ? 'var(--color-border)' : 'transparent'}`,
                  marginBottom: 2,
                  gap: 7,
                  transition: 'background 0.1s',
                }}
              >
                <MessageSquare size={13} color={s.id === activeId ? 'var(--color-accent)' : 'var(--color-muted)'} style={{ flexShrink: 0 }} />

                {editingId === s.id ? (
                  <input
                    autoFocus
                    value={editVal}
                    onChange={e => setEditVal(e.target.value)}
                    onBlur={() => commitEdit(s.id)}
                    onKeyDown={e => { if (e.key === 'Enter') commitEdit(s.id); if (e.key === 'Escape') setEditingId(null) }}
                    onClick={e => e.stopPropagation()}
                    style={{
                      flex: 1, background: 'var(--color-bg)',
                      border: '1px solid var(--color-accent)',
                      borderRadius: 4, padding: '2px 6px',
                      fontSize: 12.5, color: 'var(--color-text)', outline: 'none',
                    }}
                  />
                ) : (
                  <span style={{
                    flex: 1,
                    fontSize: 12.5,
                    color: 'var(--color-text)',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}>
                    {s.title}
                  </span>
                )}

                {s.id === activeId && editingId !== s.id && (
                  <div style={{ display: 'flex', gap: 2, flexShrink: 0 }} onClick={e => e.stopPropagation()}>
                    <button
                      onClick={() => startEdit(s)}
                      title="Rename"
                      style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 3, color: 'var(--color-muted)', display: 'flex', alignItems: 'center', borderRadius: 4 }}
                    >
                      <Edit3 size={12} />
                    </button>
                    <button
                      onClick={() => onDelete(s.id)}
                      title="Delete"
                      style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 3, color: 'var(--color-muted)', display: 'flex', alignItems: 'center', borderRadius: 4 }}
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        ))}
      </div>
    </aside>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Message bubble
// ─────────────────────────────────────────────────────────────────────────────

function Bubble({ msg }: { msg: StoredMessage }) {
  const isUser = msg.role === 'user'
  return (
    <div style={{
      display: 'flex',
      flexDirection: isUser ? 'row-reverse' : 'row',
      gap: 10,
      marginBottom: 18,
      alignItems: 'flex-start',
    }}>
      <div style={{
        flexShrink: 0, width: 30, height: 30, borderRadius: '50%',
        background: isUser ? 'var(--color-accent)' : 'var(--color-surface2)',
        border: '1px solid var(--color-border)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 11, fontWeight: 700,
        color: isUser ? '#fff' : 'var(--color-muted)',
      }}>
        {isUser ? 'U' : 'AI'}
      </div>

      <div style={{ maxWidth: '76%', display: 'flex', flexDirection: 'column', gap: 4, alignItems: isUser ? 'flex-end' : 'flex-start' }}>
        {msg.attachedDocs && msg.attachedDocs.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, justifyContent: isUser ? 'flex-end' : 'flex-start' }}>
            {msg.attachedDocs.map(name => (
              <div key={name} style={{
                display: 'inline-flex', alignItems: 'center', gap: 5,
                background: 'rgba(99,102,241,0.12)', border: '1px solid rgba(99,102,241,0.3)',
                borderRadius: 20, padding: '3px 10px',
                fontSize: 11, color: 'var(--color-accent-hover)',
              }}>
                <Paperclip size={10} />
                {name}
              </div>
            ))}
          </div>
        )}

        <div style={{
          background: isUser ? 'var(--color-accent)' : 'var(--color-surface2)',
          border: `1px solid ${msg.error ? 'rgba(239,68,68,0.4)' : 'var(--color-border)'}`,
          borderRadius: isUser ? '14px 4px 14px 14px' : '4px 14px 14px 14px',
          padding: '10px 14px',
        }}>
          <p style={{
            margin: 0,
            fontSize: 13.5, lineHeight: 1.75,
            color: msg.error ? 'var(--color-danger)' : isUser ? '#fff' : 'var(--color-text)',
            whiteSpace: 'pre-wrap', wordBreak: 'break-word',
          }}>
            {msg.content}
          </p>
        </div>

        <div style={{ fontSize: 10.5, color: 'var(--color-muted)', marginTop: 1 }}>
          {new Date(msg.ts).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}
        </div>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Thinking indicator
// ─────────────────────────────────────────────────────────────────────────────

function Thinking() {
  return (
    <div style={{ display: 'flex', gap: 10, marginBottom: 18, alignItems: 'flex-start' }}>
      <div style={{
        flexShrink: 0, width: 30, height: 30, borderRadius: '50%',
        background: 'var(--color-surface2)', border: '1px solid var(--color-border)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 11, fontWeight: 700, color: 'var(--color-muted)',
      }}>AI</div>
      <div style={{
        background: 'var(--color-surface2)', border: '1px solid var(--color-border)',
        borderRadius: '4px 14px 14px 14px', padding: '12px 16px',
        display: 'flex', gap: 5, alignItems: 'center',
      }}>
        {[0, 1, 2].map(i => (
          <span key={i} style={{
            width: 6, height: 6, borderRadius: '50%',
            background: 'var(--color-muted)',
            display: 'inline-block',
            animation: `chat-pulse 1.2s ease-in-out ${i * 0.2}s infinite`,
          }} />
        ))}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// ModelSelect
// ─────────────────────────────────────────────────────────────────────────────

function ModelSelect({ models, value, onChange }: {
  models: ModelStatus[]
  value: string
  onChange: (v: string) => void
}) {
  return (
    <div style={{ position: 'relative', display: 'inline-flex', alignItems: 'center' }}>
      <select
        value={value}
        onChange={e => onChange(e.target.value)}
        style={{
          background: 'var(--color-surface2)',
          border: '1px solid var(--color-border)',
          borderRadius: 7,
          color: 'var(--color-text)',
          fontSize: 12.5,
          fontWeight: 500,
          padding: '5px 28px 5px 10px',
          appearance: 'none',
          cursor: 'pointer',
          outline: 'none',
          maxWidth: 220,
        }}
      >
        {models.length === 0 && <option value={value}>{value || 'No models'}</option>}
        {models.map(m => (
          <option key={m.model_id} value={m.model_name}>
            {m.model_name}{m.is_loaded ? ' ●' : ''}
          </option>
        ))}
      </select>
      <ChevronDown size={11} color="var(--color-muted)" style={{ position: 'absolute', right: 8, pointerEvents: 'none' }} />
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// ChatPane
// ─────────────────────────────────────────────────────────────────────────────

function ChatPane({
  session,
  models,
  thinking,
  onSend,
  onModelChange,
}: {
  session: ChatSession | null
  models: ModelStatus[]
  thinking: boolean
  onSend: (text: string, attachedDocs: AttachedDoc[]) => void
  onModelChange: (model: string) => void
}) {
  const [draft, setDraft] = useState('')
  const [attachedDocs, setAttachedDocs] = useState<AttachedDoc[]>([])
  const [showAttach, setShowAttach] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Clear draft + attachments when switching sessions
  useEffect(() => { setDraft(''); setAttachedDocs([]); setShowAttach(false) }, [session?.id])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [session?.messages, thinking])

  const submit = () => {
    const text = draft.trim()
    if (!text || thinking) return
    setDraft('')
    const docs = attachedDocs
    setAttachedDocs([])
    onSend(text, docs)
    setTimeout(() => textareaRef.current?.focus(), 50)
  }

  const messages = session?.messages ?? []

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minWidth: 0 }}>

      {/* ── Toolbar ── */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 12,
        padding: '10px 20px',
        borderBottom: '1px solid var(--color-border)',
        background: 'var(--color-surface)',
        flexShrink: 0,
      }}>
        <span style={{ fontSize: 13, color: 'var(--color-muted)' }}>Model</span>
        <ModelSelect
          models={models}
          value={session?.model ?? ''}
          onChange={onModelChange}
        />
        {session && (
          <>
            <div style={{ width: 1, height: 16, background: 'var(--color-border)' }} />
            <span style={{
              fontSize: 12, color: 'var(--color-muted)',
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 300,
            }}>
              {session.title}
            </span>
          </>
        )}
      </div>

      {/* ── Messages ── */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '28px 24px 16px' }}>
        {!session && (
          <EmptyHint />
        )}

        {session && messages.length === 0 && (
          <EmptyHint />
        )}

        {messages.map(msg => <Bubble key={msg.id} msg={msg} />)}
        {thinking && <Thinking />}
        <div ref={bottomRef} />
      </div>

      {/* ── Input area ── */}
      <div style={{
        borderTop: '1px solid var(--color-border)',
        background: 'var(--color-surface)',
        padding: '12px 20px 16px',
        flexShrink: 0,
      }}>
        {/* Attached doc pills */}
        {attachedDocs.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 10 }}>
            {attachedDocs.map(doc => (
              <div key={doc.file.name} style={{
                display: 'inline-flex', alignItems: 'center', gap: 6,
                background: 'rgba(99,102,241,0.1)', border: '1px solid rgba(99,102,241,0.3)',
                borderRadius: 20, padding: '4px 10px 4px 8px',
                fontSize: 12, color: 'var(--color-accent-hover)',
              }}>
                <Paperclip size={11} />
                <span style={{ fontWeight: 500, maxWidth: 140, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {doc.file.name}
                </span>
                <span style={{ color: 'var(--color-muted)', fontSize: 11 }}>· {doc.result.chunks_created} chunks</span>
                <button
                  onClick={() => setAttachedDocs(prev => prev.filter(d => d.file.name !== doc.file.name))}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', color: 'var(--color-muted)', padding: 0, marginLeft: 2 }}
                >
                  <X size={12} />
                </button>
              </div>
            ))}
          </div>
        )}

        <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
          {/* + attach */}
          <div style={{ position: 'relative', flexShrink: 0 }}>
            <button
              onClick={() => setShowAttach(v => !v)}
              title="Attach document"
              style={{
                width: 36, height: 36,
                background: showAttach ? 'var(--color-accent)' : 'var(--color-surface2)',
                border: `1px solid ${showAttach ? 'var(--color-accent)' : 'var(--color-border)'}`,
                borderRadius: 8,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                cursor: 'pointer', transition: 'all 0.15s',
              }}
            >
              <Plus size={16} color={showAttach ? '#fff' : 'var(--color-muted)'} />
            </button>

            {showAttach && (
              <AttachPopover
                sessionId={session?.id}
                onClose={() => setShowAttach(false)}
                onAttached={docs => {
                  setAttachedDocs(prev => {
                    const existingNames = new Set(prev.map(d => d.file.name))
                    const fresh = docs.filter(d => !existingNames.has(d.file.name))
                    return [...prev, ...fresh]
                  })
                  setShowAttach(false)
                  setTimeout(() => textareaRef.current?.focus(), 80)
                }}
              />
            )}
          </div>

          {/* Textarea */}
          <textarea
            ref={textareaRef}
            value={draft}
            onChange={e => setDraft(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit() }
            }}
            placeholder={session ? 'Message…' : 'Start a new chat or select one from the sidebar…'}
            disabled={!session || thinking}
            rows={1}
            style={{
              ...S.input,
              flex: 1,
              resize: 'none',
              fontFamily: 'inherit',
              lineHeight: 1.6,
              maxHeight: 140,
              overflowY: 'auto',
              opacity: !session ? 0.5 : 1,
            }}
            onInput={e => {
              const el = e.currentTarget
              el.style.height = 'auto'
              el.style.height = Math.min(el.scrollHeight, 140) + 'px'
            }}
          />

          {/* Send */}
          <button
            onClick={submit}
            disabled={!draft.trim() || thinking || !session}
            style={{
              ...S.btn,
              flexShrink: 0,
              width: 36, height: 36,
              padding: 0,
              justifyContent: 'center',
              opacity: (!draft.trim() || thinking || !session) ? 0.4 : 1,
              transition: 'opacity 0.15s',
            }}
          >
            {thinking ? <Spinner size={14} /> : <Send size={15} />}
          </button>
        </div>

        <div style={{ fontSize: 11, color: 'var(--color-muted)', marginTop: 7, paddingLeft: 44 }}>
          Enter to send · Shift+Enter for newline · + to attach a document
        </div>
      </div>
    </div>
  )
}

function EmptyHint() {
  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      height: '100%', gap: 14, color: 'var(--color-muted)', paddingBottom: 40,
    }}>
      <div style={{
        width: 52, height: 52, borderRadius: 14,
        background: 'var(--color-surface2)', border: '1px solid var(--color-border)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        <MessageSquare size={22} color="var(--color-muted)" />
      </div>
      <div style={{ textAlign: 'center' }}>
        <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--color-text)', marginBottom: 6 }}>
          How can I help you today?
        </div>
        <div style={{ fontSize: 13, lineHeight: 1.6, maxWidth: 340 }}>
          Select a model above, then type a message.<br />
          Use{' '}
          <span style={{
            display: 'inline-flex', alignItems: 'center', gap: 3,
            background: 'var(--color-surface2)', border: '1px solid var(--color-border)',
            borderRadius: 5, padding: '0px 6px', fontSize: 12, color: 'var(--color-text)',
          }}>
            <Plus size={10} />
          </span>{' '}
          to attach a document for grounded Q&amp;A.
        </div>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Root page
// ─────────────────────────────────────────────────────────────────────────────

export default function Chat() {
  const store = useChatSessions()
  const [models, setModels] = useState<ModelStatus[]>([])
  const [thinking, setThinking] = useState(false)

  // Inject CSS keyframes once
  useEffect(() => {
    if (document.getElementById('chat-kf')) return
    const s = document.createElement('style')
    s.id = 'chat-kf'
    s.textContent = `
      @keyframes chat-pulse {
        0%,80%,100% { opacity:0.25; transform:scale(0.75); }
        40%          { opacity:1;    transform:scale(1); }
      }
    `
    document.head.appendChild(s)
  }, [])

  useEffect(() => {
    listModels().then(ms => {
      setModels(ms)
      // If no active session and we have models, default model is first loaded or first
      if (!store.active && ms.length > 0) {
        const defaultModel = ms.find(m => m.is_loaded)?.model_name ?? ms[0].model_name
        store.createSession(defaultModel)
      }
    }).catch(() => {})
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const defaultModel = models.find(m => m.is_loaded)?.model_name ?? models[0]?.model_name ?? 'llama3'

  const handleNew = () => {
    store.createSession(defaultModel)
  }

  const handleSend = async (text: string, attachedDocs: AttachedDoc[]) => {
    let session = store.active
    if (!session) {
      session = store.createSession(defaultModel)
    }

    const sessionId = session.id
    const model = session.model

    // Append user message
    const userMsg: StoredMessage = {
      id: newMsgId(),
      role: 'user',
      content: text,
      attachedDocs: attachedDocs.length > 0 ? attachedDocs.map(d => d.file.name) : undefined,
      ts: Date.now(),
    }
    store.appendMessage(sessionId, userMsg)
    setThinking(true)

    // Build message history for the API
    const history: ChatTurn[] = session.messages.map(m => ({
      role: m.role,
      content: m.content,
    }))
    history.push({ role: 'user', content: text })

    // Placeholder assistant message
    const asstMsg: StoredMessage = {
      id: newMsgId(),
      role: 'assistant',
      content: '',
      ts: Date.now(),
    }
    store.appendMessage(sessionId, asstMsg)

    try {
      const result = await chatComplete({ model, messages: history, session_id: sessionId })
      store.updateLastAssistant(sessionId, { content: result.content, ts: Date.now() })
    } catch (e: any) {
      const errText = e?.response?.data?.detail ?? 'Request failed. Is the backend running?'
      store.updateLastAssistant(sessionId, { content: errText, error: true, ts: Date.now() })
    } finally {
      setThinking(false)
    }
  }

  const handleModelChange = (model: string) => {
    if (store.active) store.updateModel(store.active.id, model)
  }

  return (
    <div style={{ display: 'flex', height: 'calc(100vh - 56px)', overflow: 'hidden' }}>
      <SessionSidebar
        sessions={store.sessions}
        activeId={store.activeId}
        onSelect={store.setActiveId}
        onNew={handleNew}
        onDelete={store.deleteSession}
        onRename={store.renameSession}
      />
      <ChatPane
        session={store.active}
        models={models}
        thinking={thinking}
        onSend={handleSend}
        onModelChange={handleModelChange}
      />
    </div>
  )
}
