import { useEffect, useRef, useState } from 'react'
import {
  deleteGlobalDocument,
  ingestGlobalDocument,
  listGlobalDocuments,
} from '../api/client'
import type { DocumentMeta, IngestDocumentResult } from '../api/client'
import { S, Spinner, ErrorBanner } from '../components/ui'
import { FileText, Trash2, Upload, X, RefreshCw } from 'lucide-react'

// ── helpers ───────────────────────────────────────────────────────────────────

function fmtDate(ts: number) {
  return new Date(ts * 1000).toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

const TYPE_COLOR: Record<string, string> = {
  pdf:     'rgba(239,68,68,0.15)',
  text:    'rgba(99,102,241,0.15)',
  image:   'rgba(16,185,129,0.15)',
  unknown: 'rgba(124,133,168,0.15)',
}
const TYPE_TEXT: Record<string, string> = {
  pdf: '#ef4444', text: '#818cf8', image: '#10b981', unknown: '#7c85a8',
}

function DocTypeBadge({ t }: { t: string }) {
  return (
    <span style={{
      background: TYPE_COLOR[t] ?? TYPE_COLOR.unknown,
      color: TYPE_TEXT[t] ?? TYPE_TEXT.unknown,
      borderRadius: 5, padding: '2px 8px',
      fontSize: 10.5, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em',
    }}>
      {t}
    </span>
  )
}

// ── Upload panel ──────────────────────────────────────────────────────────────

type UploadEntry = {
  key: string
  file: File
  phase: 'idle' | 'uploading' | 'done' | 'error'
  result?: IngestDocumentResult
  error?: string
}

function fileKey(f: File) { return `${f.name}_${f.size}` }

function UploadPanel({ onDone }: { onDone: () => void }) {
  const [entries, setEntries] = useState<UploadEntry[]>([])
  const [dragOver, setDragOver] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const addFiles = (files: FileList | File[]) => {
    const arr = Array.from(files)
    setEntries(prev => {
      const keys = new Set(prev.map(e => e.key))
      const fresh = arr
        .filter(f => !keys.has(fileKey(f)))
        .map(f => ({ key: fileKey(f), file: f, phase: 'idle' as const }))
      return [...prev, ...fresh]
    })
  }

  const remove = (key: string) =>
    setEntries(prev => prev.filter(e => e.key !== key))

  const uploadOne = async (key: string) => {
    setEntries(prev => prev.map(e => e.key === key ? { ...e, phase: 'uploading' } : e))
    const entry = entries.find(e => e.key === key)!
    try {
      const result = await ingestGlobalDocument(entry.file)
      setEntries(prev => prev.map(e => e.key === key ? { ...e, phase: 'done', result } : e))
      onDone()
    } catch (err: any) {
      const msg = err?.response?.data?.detail ?? 'Upload failed'
      setEntries(prev => prev.map(e => e.key === key ? { ...e, phase: 'error', error: msg } : e))
    }
  }

  const uploadAll = () => {
    entries.filter(e => e.phase === 'idle' || e.phase === 'error').forEach(e => uploadOne(e.key))
  }

  const anyPending = entries.some(e => e.phase === 'idle' || e.phase === 'error')
  const anyUploading = entries.some(e => e.phase === 'uploading')

  return (
    <div style={S.card}>
      <h3 style={{ fontSize: 14, fontWeight: 600, color: 'var(--color-text)', marginBottom: 14 }}>
        Upload Documents
      </h3>

      {/* Drop zone */}
      <div
        onClick={() => fileRef.current?.click()}
        onDragOver={e => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={e => { e.preventDefault(); setDragOver(false); addFiles(e.dataTransfer.files) }}
        style={{
          border: `2px dashed ${dragOver ? 'var(--color-accent)' : entries.length ? 'var(--color-accent)' : 'var(--color-border)'}`,
          borderRadius: 9, padding: '28px 20px', textAlign: 'center',
          cursor: 'pointer', marginBottom: 14, transition: 'border-color 0.15s',
          background: dragOver ? 'rgba(99,102,241,0.05)' : 'transparent',
        }}
      >
        <Upload size={28} color={entries.length ? 'var(--color-accent)' : 'var(--color-muted)'} style={{ marginBottom: 8 }} />
        <div style={{ fontSize: 13, color: 'var(--color-muted)' }}>
          Click or drag files here<br />
          <span style={{ fontSize: 11 }}>PDF · TXT · MD · PNG · JPG — multiple allowed</span>
        </div>
      </div>
      <input
        ref={fileRef}
        type="file"
        multiple
        accept=".pdf,.txt,.md,.png,.jpg,.jpeg,.webp,.tiff"
        style={{ display: 'none' }}
        onChange={e => { if (e.target.files) addFiles(e.target.files); e.target.value = '' }}
      />

      {/* File list */}
      {entries.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 14 }}>
          {entries.map(entry => (
            <div key={entry.key} style={{
              display: 'flex', alignItems: 'center', gap: 10,
              background: 'var(--color-surface2)',
              border: `1px solid ${
                entry.phase === 'done'  ? 'rgba(16,185,129,0.3)' :
                entry.phase === 'error' ? 'rgba(239,68,68,0.3)'  :
                'var(--color-border)'
              }`,
              borderRadius: 8, padding: '8px 12px',
            }}>
              <div style={{ width: 20, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                {entry.phase === 'uploading' && <Spinner size={14} />}
                {entry.phase === 'done'      && <span style={{ color: 'var(--color-success)', fontWeight: 700 }}>✓</span>}
                {entry.phase === 'error'     && <span style={{ color: 'var(--color-danger)',  fontWeight: 700 }}>✕</span>}
                {entry.phase === 'idle'      && <FileText size={14} color="var(--color-muted)" />}
              </div>

              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--color-text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {entry.file.name}
                </div>
                <div style={{ fontSize: 11, color: 'var(--color-muted)', marginTop: 2 }}>
                  {entry.phase === 'done' && entry.result
                    ? `${entry.result.chunks_created} chunks · ${entry.result.ocr_needed_pages.length > 0 ? `OCR needed: ${entry.result.ocr_needed_pages.join(', ')}` : 'no OCR needed'}`
                    : entry.phase === 'error'
                      ? entry.error
                      : `${(entry.file.size / 1024).toFixed(1)} KB`
                  }
                </div>
              </div>

              <div style={{ display: 'flex', gap: 6, flexShrink: 0, alignItems: 'center' }}>
                {(entry.phase === 'idle' || entry.phase === 'error') && (
                  <button
                    onClick={() => uploadOne(entry.key)}
                    style={{ ...S.btn, fontSize: 12, padding: '4px 10px' }}
                  >
                    <Upload size={11} />
                    {entry.phase === 'error' ? 'Retry' : 'Upload'}
                  </button>
                )}
                {entry.phase !== 'uploading' && (
                  <button onClick={() => remove(entry.key)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-muted)', display: 'flex', alignItems: 'center', padding: 4 }}>
                    <X size={13} />
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {anyPending && (
        <button
          style={{ ...S.btn, width: '100%', justifyContent: 'center' }}
          disabled={anyUploading}
          onClick={uploadAll}
        >
          {anyUploading ? <Spinner size={14} /> : <Upload size={14} />}
          {anyUploading ? 'Uploading…' : `Upload All (${entries.filter(e => e.phase === 'idle' || e.phase === 'error').length})`}
        </button>
      )}
    </div>
  )
}

// ── Document library ──────────────────────────────────────────────────────────

function DocLibrary({ docs, loading, onDelete, onRefresh }: {
  docs: DocumentMeta[]
  loading: boolean
  onDelete: (id: string) => void
  onRefresh: () => void
}) {
  const [deleting, setDeleting] = useState<string | null>(null)
  const [deleteError, setDeleteError] = useState('')

  const handleDelete = async (id: string) => {
    setDeleting(id)
    setDeleteError('')
    try {
      await deleteGlobalDocument(id)
      onDelete(id)
    } catch (e: any) {
      setDeleteError(e?.response?.data?.detail ?? 'Delete failed')
    } finally {
      setDeleting(null)
    }
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
        <h3 style={{ fontSize: 14, fontWeight: 600, color: 'var(--color-text)' }}>
          Global Library
          {docs.length > 0 && (
            <span style={{ marginLeft: 8, fontSize: 12, color: 'var(--color-muted)', fontWeight: 400 }}>
              {docs.length} document{docs.length !== 1 ? 's' : ''}
            </span>
          )}
        </h3>
        <button
          onClick={onRefresh}
          disabled={loading}
          style={{ ...S.btnGhost, padding: '5px 10px', fontSize: 12 }}
        >
          {loading ? <Spinner size={12} /> : <RefreshCw size={12} />}
          Refresh
        </button>
      </div>

      {deleteError && <div style={{ marginBottom: 12 }}><ErrorBanner message={deleteError} /></div>}

      {loading && docs.length === 0 && (
        <div style={{ textAlign: 'center', padding: '40px 0', color: 'var(--color-muted)', fontSize: 13 }}>
          <Spinner size={20} />
        </div>
      )}

      {!loading && docs.length === 0 && (
        <div style={{
          textAlign: 'center', padding: '48px 20px',
          color: 'var(--color-muted)', fontSize: 13,
          background: 'var(--color-surface2)', border: '1px solid var(--color-border)', borderRadius: 10,
        }}>
          <FileText size={32} color="var(--color-muted)" style={{ margin: '0 auto 12px' }} />
          No documents yet. Upload files above.
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {docs.map(doc => (
          <div key={doc.document_id} style={{
            ...S.card,
            padding: '12px 16px',
            display: 'flex', alignItems: 'center', gap: 12,
          }}>
            <FileText size={18} color="var(--color-muted)" style={{ flexShrink: 0 }} />

            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 3 }}>
                <span style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--color-text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {doc.filename}
                </span>
                <DocTypeBadge t={doc.doc_type} />
              </div>
              <div style={{ display: 'flex', gap: 16, fontSize: 11.5, color: 'var(--color-muted)' }}>
                <span>{doc.chunk_count} chunks</span>
                <span>{doc.page_count} page{doc.page_count !== 1 ? 's' : ''}</span>
                <span>{fmtDate(doc.created_at)}</span>
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
              <code style={{ fontSize: 10.5, color: 'var(--color-muted)', fontFamily: 'monospace', maxWidth: 100, overflow: 'hidden', textOverflow: 'ellipsis', display: 'block' }}>
                {doc.document_id}
              </code>
              <button
                onClick={() => handleDelete(doc.document_id)}
                disabled={deleting === doc.document_id}
                title="Delete"
                style={{ ...S.btnGhost, padding: '5px 8px', border: '1px solid rgba(239,68,68,0.3)', color: 'var(--color-danger)' }}
              >
                {deleting === doc.document_id ? <Spinner size={12} /> : <Trash2 size={13} />}
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function Documents() {
  const [docs, setDocs] = useState<DocumentMeta[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')

  const fetchDocs = async () => {
    setLoading(true)
    setLoadError('')
    try {
      setDocs(await listGlobalDocuments())
    } catch (e: any) {
      setLoadError(e?.response?.data?.detail ?? 'Failed to load documents')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchDocs() }, [])

  return (
    <div>
      <div style={{ marginBottom: 20 }}>
        <h2 style={{ fontSize: 18, fontWeight: 700, color: 'var(--color-text)', marginBottom: 2 }}>
          Global Documents
        </h2>
        <p style={{ fontSize: 13, color: 'var(--color-muted)' }}>
          Documents uploaded here are available to every chat session and persist across restarts.
        </p>
      </div>

      {loadError && <ErrorBanner message={loadError} />}

      <div style={{ display: 'grid', gridTemplateColumns: '380px 1fr', gap: 24, alignItems: 'start' }}>
        <UploadPanel onDone={fetchDocs} />
        <DocLibrary
          docs={docs}
          loading={loading}
          onDelete={id => setDocs(prev => prev.filter(d => d.document_id !== id))}
          onRefresh={fetchDocs}
        />
      </div>
    </div>
  )
}
