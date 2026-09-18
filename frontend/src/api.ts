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
  style_pack_id: string
  style_pack_version: number
  suggestions: Suggestion[]
  artifacts: string[]
  error: string | null
  output_name: string | null
  draft_updated_at: string | null
  source_hash: string
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

export function createJob(file: File, stylePack: StylePack): Promise<Job> {
  const formData = new FormData()
  formData.append('source', file)
  formData.append('style_pack_id', stylePack.id)
  formData.append('style_pack_version', String(stylePack.version))
  return request<Job>('/api/jobs', { method: 'POST', body: formData })
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
): Promise<Job> {
  return request<Job>(`/api/jobs/${jobId}/normalize-and-render`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ source_markdown: sourceMarkdown, confirmed_roles: confirmedRoles }),
  })
}

export function artifactUrl(jobId: string, artifactName: string): string {
  return `${apiBase}/api/jobs/${jobId}/artifacts/${encodeURIComponent(artifactName)}`
}
