export type StylePack = {
  id: string
  name: string
  format_id: string
  version: number
  roles: Record<string, Record<string, unknown>>
}

export type Suggestion = {
  line: number
  role: string
  score: number
  reason: string
  value?: string
  end_line?: number
}

export type Job = {
  id: string
  status: string
  source_name: string
  source_format: string
  conversion_mode?: 'round-trip' | 'docx-direct'
  source_original_name: string
  import_warnings: string[]
  style_pack_id: string
  style_pack_version: number
  suggestions: Suggestion[]
  artifacts: string[]
  error: string | null
  output_name: string | null
  draft_updated_at: string | null
  source_hash: string
  render_revision: number
  preview_ready: boolean
}

export type JobDraft = {
  source_format: string
  source_markdown: string
  warnings: string[]
}

const apiBase = import.meta.env.VITE_API_BASE ?? ''

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, init)
  if (!response.ok) {
    const data = (await response.json().catch(() => null)) as { detail?: string } | null
    throw new Error(data?.detail ?? '本地服务未能完成请求。')
  }
  return (await response.json()) as T
}

export function listStylePacks(): Promise<StylePack[]> {
  return request<StylePack[]>('/api/style-packs')
}

export function createStylePack(payload: {
  name: string
  format_id: string
  roles?: Record<string, Record<string, unknown>>
}): Promise<StylePack> {
  return request<StylePack>('/api/style-packs', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function reviseStylePack(
  stylePack: StylePack,
  payload: { name: string; roles: Record<string, Record<string, unknown>> },
): Promise<StylePack> {
  return request<StylePack>(`/api/style-packs/${stylePack.id}`, {
    method: 'PUT',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      base_version: stylePack.version,
      format_id: stylePack.format_id,
      ...payload,
    }),
  })
}

export function createJob(file: File, stylePack: StylePack, conversionMode: 'round-trip' | 'docx-direct' = 'round-trip'): Promise<Job> {
  const formData = new FormData()
  formData.append('source', file)
  formData.append('style_pack_id', stylePack.id)
  formData.append('style_pack_version', String(stylePack.version))
  formData.append('conversion_mode', conversionMode)
  return request<Job>('/api/jobs', { method: 'POST', body: formData })
}

export function normalizeDocxDirect(jobId: string, stylePack: Pick<StylePack, 'id' | 'version'>): Promise<Job> {
  return request<Job>(`/api/jobs/${jobId}/normalize-docx-direct`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ style_pack_id: stylePack.id, style_pack_version: stylePack.version }),
  })
}

export function getJobDraft(jobId: string): Promise<JobDraft> {
  return request<JobDraft>(`/api/jobs/${jobId}/draft`)
}

export function saveDraft(jobId: string, sourceMarkdown: string): Promise<Job> {
  return request<Job>(`/api/jobs/${jobId}/draft`, {
    method: 'PUT',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ source_markdown: sourceMarkdown }),
  })
}

export function normalizeAndRender(
  jobId: string,
  sourceMarkdown: string,
  confirmedRoles: Record<string, string>,
  stylePack?: Pick<StylePack, 'id' | 'version'>,
): Promise<Job> {
  return request<Job>(`/api/jobs/${jobId}/normalize-and-render`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      source_markdown: sourceMarkdown,
      confirmed_roles: confirmedRoles,
      ...(stylePack ? { style_pack_id: stylePack.id, style_pack_version: stylePack.version } : {}),
    }),
  })
}

export function artifactUrl(jobId: string, artifactName: string, revision?: number): string {
  const url = `${apiBase}/api/jobs/${jobId}/artifacts/${encodeURIComponent(artifactName)}`
  return revision ? `${url}?revision=${revision}` : url
}

export async function fetchArtifactText(jobId: string, artifactName: string, revision?: number): Promise<string> {
  const response = await fetch(artifactUrl(jobId, artifactName, revision), { cache: 'no-store' })
  if (!response.ok) {
    throw new Error('无法读取规范化后的工作文档。')
  }
  return response.text()
}

export function previewUrl(jobId: string, revision: number): string {
  return `${apiBase}/api/jobs/${jobId}/preview?revision=${revision}`
}
