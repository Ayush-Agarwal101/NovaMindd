import axios from 'axios'

const BASE = '/api/v1'

export const api = axios.create({
  baseURL: BASE,
  headers: { 'Content-Type': 'application/json' },
  timeout: 120_000,
})

// ── Types ────────────────────────────────────────────────────────────────────

export interface ModelStatus {
  model_id: string
  model_name: string
  status: string
  capabilities: string[]
  vram_limit_mb: number
  is_loaded: boolean
}

export interface RouteResult {
  model_id: string
  model_name: string
  already_loaded: boolean
  reason: string
}

export interface SearchResult {
  text: string
  document_id: string
  source_path: string
  page: number
  score: number
}

export interface IngestResult {
  document_id: string
  chunks_created: number
  ocr_needed_pages: number[]
}

export interface SubStepInfo {
  step_index: number
  capability: string
  model_id: string
  model_name: string
}

export interface AgentRunResult {
  request_id: string | null
  status: string
  answer: string | null
  tool_calls: ToolCall[]
  evidence_count: number
  files_ingested: number
  sub_steps: SubStepInfo[]
  output_files: Record<string, string>
  download_urls: Record<string, string>
  error: string | null
}

export interface ToolCall {
  tool_id: string
  success: boolean
  output: Record<string, unknown> | null
  error: string | null
}

export interface Tool {
  tool_id: string
  name: string
  description: string
  status: string
  required_permissions: string[]
  requires_network: boolean
  requires_human_approval: boolean
}

export interface PlatformConfig {
  app: Record<string, unknown>
  api: Record<string, unknown>
  retrieval: Record<string, unknown>
  document_ai: Record<string, unknown>
  residency: Record<string, unknown>
  sandbox: Record<string, unknown>
}

export interface DocumentIR {
  title: string
  author?: string
  blocks: IRBlock[]
  metadata?: Record<string, unknown>
  evidence_refs?: EvidenceRef[]
}

export interface IRBlock {
  block_type: string
  text?: string
  items?: string[]
  rows?: IRTableCell[][]
  metadata?: Record<string, unknown>
}

export interface IRTableCell {
  text: string
  bold?: boolean
  align?: string
}

export interface EvidenceRef {
  document_id: string
  page: number
  score: number
}

// ── Health ───────────────────────────────────────────────────────────────────

export async function getHealth(): Promise<{ status: string; service: string }> {
  const r = await axios.get('/health')
  return r.data
}

// ── Models ───────────────────────────────────────────────────────────────────

export async function listModels(): Promise<ModelStatus[]> {
  const r = await api.get('/models/')
  return r.data
}

export async function loadModel(modelId: string): Promise<void> {
  await api.post(`/models/${modelId}/load`)
}

export async function unloadModel(modelId: string): Promise<void> {
  await api.post(`/models/${modelId}/unload`)
}

export async function routeModel(capability: string, requiresVision = false): Promise<RouteResult> {
  const r = await api.post('/models/route', { capability, requires_vision: requiresVision })
  return r.data
}

// ── Knowledge ────────────────────────────────────────────────────────────────

export async function ingestDocument(
  file: File,
  scope: 'global' | 'session' = 'global',
  sessionId?: string,
): Promise<IngestResult> {
  const form = new FormData()
  form.append('file', file)
  const params = new URLSearchParams({ scope })
  if (sessionId) params.set('session_id', sessionId)
  const r = await api.post(`/knowledge/ingest?${params}`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return r.data
}

export async function searchKnowledge(
  query: string,
  topK = 5,
  scope: 'global' | 'session' | 'combined' = 'global',
  sessionId?: string,
): Promise<SearchResult[]> {
  const r = await api.post('/knowledge/search', {
    query, top_k: topK, scope, session_id: sessionId ?? null,
  })
  return r.data
}

// ── Global Documents ──────────────────────────────────────────────────────────

export interface DocumentMeta {
  document_id: string
  filename: string
  doc_type: string
  scope: string
  session_id: string | null
  page_count: number
  chunk_count: number
  created_at: number
}

export interface IngestDocumentResult {
  document_id: string
  filename: string
  chunks_created: number
  ocr_needed_pages: number[]
}

export async function ingestGlobalDocument(file: File): Promise<IngestDocumentResult> {
  const form = new FormData()
  form.append('file', file)
  const r = await api.post('/documents/ingest', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return r.data
}

export async function listGlobalDocuments(): Promise<DocumentMeta[]> {
  const r = await api.get('/documents/')
  return r.data
}

export async function deleteGlobalDocument(documentId: string): Promise<void> {
  await api.delete(`/documents/${documentId}`)
}

// ── Chat ─────────────────────────────────────────────────────────────────────

export interface ChatTurn {
  role: 'user' | 'assistant' | 'system'
  content: string
}

export interface ChatCompleteResult {
  content: string
  model: string
  prompt_tokens: number
  completion_tokens: number
}

export async function chatComplete(params: {
  model: string
  messages: ChatTurn[]
  temperature?: number
  max_tokens?: number
  session_id?: string
}): Promise<ChatCompleteResult> {
  const r = await api.post('/chat/complete', {
    model: params.model,
    messages: params.messages,
    temperature: params.temperature ?? 0.7,
    max_tokens: params.max_tokens ?? 2048,
    session_id: params.session_id ?? null,
  })
  return r.data
}

// ── Agents ───────────────────────────────────────────────────────────────────

export async function runAgent(params: {
  task: string
  capability?: string
  requires_vision?: boolean
  user_id?: string
  user_roles?: string[]
  max_tool_calls?: number
  files?: File[]
}): Promise<AgentRunResult> {
  // The backend now accepts multipart/form-data so we can attach files
  const form = new FormData()
  form.append('task', params.task)
  form.append('capability', params.capability ?? 'reasoning')
  form.append('requires_vision', String(params.requires_vision ?? false))
  form.append('user_id', params.user_id ?? 'web-user')
  form.append('user_roles', (params.user_roles ?? ['operator']).join(','))
  form.append('max_tool_calls', String(params.max_tool_calls ?? 5))
  for (const file of params.files ?? []) {
    form.append('files', file)
  }
  const r = await api.post('/agents/run', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return r.data
}

// ── Artifacts ────────────────────────────────────────────────────────────────

export async function generateArtifact(format: string, documentIR: DocumentIR): Promise<Blob> {
  const r = await api.post(
    '/artifacts/generate',
    { format, document_ir: documentIR },
    { responseType: 'blob' },
  )
  return r.data
}

// ── Admin ────────────────────────────────────────────────────────────────────

export async function listTools(): Promise<Tool[]> {
  const r = await api.get('/admin/tools')
  return r.data
}

export async function getPlatformConfig(): Promise<PlatformConfig> {
  const r = await api.get('/admin/config')
  return r.data
}
