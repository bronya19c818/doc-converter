import { ChangeEvent, FormEvent, useEffect, useMemo, useRef, useState } from 'react'

import {
  artifactUrl,
  createJob,
  createStylePack,
  Job,
  listStylePacks,
  normalizeAndRender,
  saveDraft,
  StylePack,
  Suggestion,
} from './api'
import { DocxPreview } from './DocxPreview'
import { StyleEditor } from './StyleEditor'
import './styles.css'

type SettingsTab = 'styles' | 'page'

const SUGGESTION_ROLE_LABELS: Record<string, string> = {
  'document-title': '文档标题',
  'document-subtitle': '副标题',
  author: '作者',
  organization: '单位',
  department: '部门',
  date: '日期',
  abstract: '摘要',
  keywords: '关键词',
}

export function App() {
  const [stylePacks, setStylePacks] = useState<StylePack[]>([])
  const [selectedPackId, setSelectedPackId] = useState('')
  const [sourceFile, setSourceFile] = useState<File | null>(null)
  const [sourceMarkdown, setSourceMarkdown] = useState('')
  const [originalMarkdown, setOriginalMarkdown] = useState('')
  const [job, setJob] = useState<Job | null>(null)
  const [newPackName, setNewPackName] = useState('')
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [settingsTab, setSettingsTab] = useState<SettingsTab>('styles')
  const [downloadsOpen, setDownloadsOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const settingsTriggerRef = useRef<HTMLButtonElement>(null)
  const settingsCloseRef = useRef<HTMLButtonElement>(null)

  const selectedPack = useMemo(
    () => stylePacks.find((pack) => pack.id === selectedPackId) ?? null,
    [selectedPackId, stylePacks],
  )
  const markdownChanged = sourceMarkdown !== originalMarkdown
  const completedJob = job?.status === 'completed' ? job : null

  useEffect(() => {
    void loadStylePacks()
  }, [])

  async function loadStylePacks() {
    try {
      const packs = await listStylePacks()
      setStylePacks(packs)
      setSelectedPackId((current) => current || packs[0]?.id || '')
    } catch (loadError) {
      setError(messageFor(loadError))
    }
  }

  async function handleCreateStylePack(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!newPackName.trim()) return
    setBusy(true)
    setError(null)
    try {
      const pack = await createStylePack({ name: newPackName.trim(), format_id: 'docx' })
      setStylePacks((packs) => [...packs, pack].sort((left, right) => left.name.localeCompare(right.name)))
      setSelectedPackId(pack.id)
      setNewPackName('')
    } catch (createError) {
      setError(messageFor(createError))
    } finally {
      setBusy(false)
    }
  }

  async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null
    setSourceFile(file)
    setJob(null)
    setDownloadsOpen(false)
    setError(null)
    if (file) {
      const text = await file.text()
      setSourceMarkdown(text)
      setOriginalMarkdown(text)
    } else {
      setSourceMarkdown('')
      setOriginalMarkdown('')
    }
  }

  async function handlePrepare() {
    if (!sourceFile || !selectedPack) return
    setBusy(true)
    setError(null)
    setDownloadsOpen(false)
    try {
      const created = await createJob(sourceFile, selectedPack)
      setJob(created)
      setOriginalMarkdown(sourceMarkdown)
    } catch (prepareError) {
      setError(messageFor(prepareError))
    } finally {
      setBusy(false)
    }
  }

  async function handleSaveDraft() {
    if (!job) return
    setBusy(true)
    setError(null)
    try {
      setJob(await saveDraft(job.id, sourceMarkdown))
      setOriginalMarkdown(sourceMarkdown)
    } catch (saveError) {
      setError(messageFor(saveError))
    } finally {
      setBusy(false)
    }
  }

  async function handleRender() {
    if (!job || !selectedPack) return
    setBusy(true)
    setError(null)
    setDownloadsOpen(false)
    try {
      setJob(await normalizeAndRender(job.id, sourceMarkdown, {}))
      setOriginalMarkdown(sourceMarkdown)
    } catch (renderError) {
      setError(messageFor(renderError))
    } finally {
      setBusy(false)
    }
  }

  function applySuggestion(suggestion: Suggestion) {
    setSourceMarkdown((current) => applyRoleToMarkdown(current, suggestion))
  }

  function openSettings() {
    setSettingsOpen(true)
    window.requestAnimationFrame(() => settingsCloseRef.current?.focus())
  }

  function closeSettings() {
    setSettingsOpen(false)
    window.requestAnimationFrame(() => settingsTriggerRef.current?.focus())
  }

  return (
    <main className="app-shell">
      <header className="app-header">
        <div>
          <h1>Doc Converter</h1>
          <p>本地转换，不调用 AI，也不上传文档。</p>
        </div>
        <span className="local-status">仅本机运行</span>
      </header>

      <section className="workspace" aria-label="Markdown 转 DOCX 工作区">
        <section className="markdown-panel" aria-label="Markdown 工作区">
          <div className="section-heading">
            <span>01</span>
            <h2>Markdown 工作副本</h2>
          </div>
          <label className="field-label" htmlFor="source-file">选择 Markdown 文件</label>
          <input accept=".md,.markdown,text/markdown" id="source-file" onChange={handleFileChange} type="file" />
          <p className="field-help">只编辑本机工作副本，源文件不会被改动。</p>
          <label className="field-label" htmlFor="markdown-draft">Markdown 工作副本</label>
          <textarea
            aria-label="Markdown 工作副本"
            className="markdown-editor"
            id="markdown-draft"
            onChange={(event) => setSourceMarkdown(event.target.value)}
            placeholder="选择 Markdown 文件后，可在这里编辑工作副本。"
            value={sourceMarkdown}
          />
          <div className="draft-status" role="status">
            {markdownChanged ? '有未保存修改' : '工作副本已保存'}
          </div>
          <div className="draft-actions">
            <button className="secondary-action" disabled={busy || !sourceFile || !selectedPack} onClick={handlePrepare} type="button">
              {job ? '重新建立工作副本' : '建立本地工作副本'}
            </button>
            <button className="secondary-action" disabled={busy || !job || !markdownChanged} onClick={handleSaveDraft} type="button">保存工作副本</button>
          </div>

          {job?.suggestions.length ? (
            <section className="suggestions" aria-label="结构建议">
              <h3>结构建议</h3>
              <p className="field-help">建议只是提示，不会阻止生成；应用后会把 role 写入 Markdown Front Matter，并移除原标题区行。</p>
              {job.suggestions.map((suggestion) => (
                <article key={`${suggestion.line}-${suggestion.role}`}>
                  <strong>第 {suggestion.line} 行：{SUGGESTION_ROLE_LABELS[suggestion.role] ?? suggestion.role}</strong>
                  <p>{suggestion.reason}，置信度 {Math.round(suggestion.score * 100)}%。</p>
                  <button className="text-action" onClick={() => applySuggestion(suggestion)} type="button">
                    应用为{SUGGESTION_ROLE_LABELS[suggestion.role] ?? suggestion.role}
                  </button>
                </article>
              ))}
            </section>
          ) : null}
          {error ? <p className="error-message" role="alert">{error}</p> : null}
        </section>

        <section className="preview-panel" aria-label="DOCX 预览">
          <div className="preview-heading">
            <div>
              <span>02</span>
              <h2>DOCX 预览</h2>
            </div>
            {completedJob ? <span className="completed-status">已生成</span> : null}
          </div>
          {completedJob ? (
            <div className="preview-frame"><DocxPreview documentUrl={artifactUrl(completedJob.id, completedJob.output_name ?? 'document.docx')} /></div>
          ) : (
            <div className="preview-empty">
              <p>生成后可在此查看 A4 分页 DOCX 预览。</p>
              <small>预览按独立 A4 纸张显示，在浏览器内完成；不依赖 LibreOffice 自动转换。</small>
            </div>
          )}
        </section>
      </section>

      <section className={`settings-panel ${settingsOpen ? 'is-open' : 'is-collapsed'}`} aria-label="设置面板" id="settings-panel-root">
        {!settingsOpen ? (
          <button
            aria-expanded={false}
            aria-controls="settings-panel-root"
            aria-label="打开设置"
            className="settings-fab"
            onClick={openSettings}
            ref={settingsTriggerRef}
            type="button"
          >
            ⚙ 设置
          </button>
        ) : (
          <div className="settings-shell">
            <div className="settings-heading">
              <div>
                <span>03</span>
                <h2>样式设置</h2>
              </div>
              <div className="settings-heading-actions">
                <button aria-label="收起设置" className="settings-close" onClick={closeSettings} ref={settingsCloseRef} type="button">收起设置</button>
              </div>
            </div>
            <div aria-label="设置分类" className="settings-tabs" role="tablist">
              {([
                ['styles', '样式角色'],
                ['page', '页面设置'],
              ] as const).map(([tab, label]) => (
                <button
                  aria-controls={`settings-panel-${tab}`}
                  aria-selected={settingsTab === tab}
                  className="settings-tab"
                  id={`settings-tab-${tab}`}
                  key={tab}
                  onClick={() => setSettingsTab(tab)}
                  role="tab"
                  type="button"
                >
                  {label}
                </button>
              ))}
            </div>
            <div className="settings-content">
              {settingsTab === 'styles' ? (
                <div aria-labelledby="settings-tab-styles" id="settings-panel-styles" role="tabpanel">
                  <label className="field-label" htmlFor="style-pack">DOCX 样式组合</label>
                  <select id="style-pack" onChange={(event) => setSelectedPackId(event.target.value)} value={selectedPackId}>
                    {stylePacks.map((pack) => <option key={pack.id} value={pack.id}>{pack.name} · v{pack.version}</option>)}
                  </select>
                  <form className="new-pack-form" onSubmit={handleCreateStylePack}>
                    <label className="field-label" htmlFor="new-style-pack">新建样式组合</label>
                    <div>
                      <input id="new-style-pack" onChange={(event) => setNewPackName(event.target.value)} placeholder="例如：公司报告" value={newPackName} />
                      <button disabled={busy || !newPackName.trim()} type="submit">保存</button>
                    </div>
                  </form>
                  {selectedPack ? (
                    <StyleEditor
                      disabled={busy}
                      key={`${selectedPack.id}-${selectedPack.version}-roles`}
                      onSaved={(savedPack) => {
                        setStylePacks((packs) => packs.map((pack) => (pack.id === savedPack.id ? savedPack : pack)))
                        setSelectedPackId(savedPack.id)
                      }}
                      pack={selectedPack}
                      section="roles"
                    />
                  ) : <p className="field-help">正在加载本机样式组合。</p>}
                </div>
              ) : null}
              {settingsTab === 'page' ? (
                <div aria-labelledby="settings-tab-page" id="settings-panel-page" role="tabpanel">
                  {selectedPack ? (
                    <StyleEditor
                      disabled={busy}
                      key={`${selectedPack.id}-${selectedPack.version}-page`}
                      onSaved={(savedPack) => {
                        setStylePacks((packs) => packs.map((pack) => (pack.id === savedPack.id ? savedPack : pack)))
                        setSelectedPackId(savedPack.id)
                      }}
                      pack={selectedPack}
                      section="page"
                    />
                  ) : <p className="field-help">正在加载本机样式组合。</p>}
                </div>
              ) : null}
            </div>
          </div>
        )}
      </section>

      <div aria-label="快捷操作" className={`floating-actions ${settingsOpen ? 'is-settings-open' : ''}`}>
        <button
          aria-label="生成"
          className="action-fab generate-fab"
          disabled={busy || !job || !selectedPack || !sourceMarkdown.trim()}
          onClick={handleRender}
          type="button"
        >
          生成
        </button>
        <div className="download-action">
          <button
            aria-expanded={downloadsOpen}
            aria-label="下载"
            className="action-fab download-fab"
            disabled={!completedJob}
            onClick={() => setDownloadsOpen((open) => !open)}
            type="button"
          >
            下载
          </button>
          {downloadsOpen && completedJob ? (
            <div aria-label="任务产物下载" className="download-popover">
              {completedJob.artifacts.map((artifact) => (
                <a href={artifactUrl(completedJob.id, artifact)} key={artifact}>
                  {artifact === completedJob.output_name ? '下载 DOCX' : `下载 ${artifact}`}
                </a>
              ))}
            </div>
          ) : null}
        </div>
      </div>
    </main>
  )
}

export function applyRoleToMarkdown(markdown: string, suggestion: Suggestion): string {
  const key = metadataKeyForRole(suggestion.role)
  if (!key) return markdown

  const lines = markdown.split(/\r?\n/)
  const selectedIndex = findSuggestionLine(lines, suggestion)
  if (selectedIndex < 0) return markdown
  const rawValue = extractSuggestionValue(lines[selectedIndex], suggestion.role)
  if (!rawValue) return markdown

  const removeEnd = Math.min(
    lines.length - 1,
    selectedIndex + Math.max(0, (suggestion.end_line ?? suggestion.line) - suggestion.line),
  )
  const bodyLines = lines.filter((_, index) => index < selectedIndex || index > removeEnd)
  const entry = formatMetadataEntry(key, rawValue)
  const frontMatterStart = lines[0]?.trim() === '---' ? 0 : -1
  if (frontMatterStart >= 0) {
    const closingIndex = lines.findIndex((line, index) => index > 0 && line.trim() === '---')
    if (closingIndex > 0) {
      const metadataLines = lines.slice(1, closingIndex)
      const updatedMetadata = replaceMetadataEntry(metadataLines, key, entry)
      const updatedLines = ['---', ...updatedMetadata, '---', ...bodyLines.slice(closingIndex + 1)]
      return trimMarkdownLines(updatedLines)
    }
  }
  return trimMarkdownLines(['---', ...entry, '---', '', ...bodyLines])
}

function metadataKeyForRole(role: string): string | null {
  const keys: Record<string, string> = {
    'document-title': 'title',
    'document-subtitle': 'subtitle',
    author: 'authors',
    authors: 'authors',
    organization: 'organization',
    department: 'department',
    date: 'date',
    abstract: 'abstract',
    keywords: 'keywords',
  }
  return keys[role] ?? null
}

function findSuggestionLine(lines: string[], suggestion: Suggestion): number {
  const expectedIndex = Math.min(lines.length - 1, Math.max(0, suggestion.line - 1))
  if (suggestion.value && lineMatchesSuggestion(lines[expectedIndex] ?? '', suggestion.value)) {
    return expectedIndex
  }
  if (!suggestion.value) return expectedIndex
  const normalizedValue = suggestion.value.trim()
  const fallback = lines.findIndex((line) => line.trim() === normalizedValue)
  if (fallback >= 0) return fallback
  return lines.findIndex((line) => line.includes(normalizedValue))
}

function lineMatchesSuggestion(line: string, value: string): boolean {
  const normalizedLine = line.trim()
  const normalizedValue = value.trim()
  return normalizedLine === normalizedValue || normalizedLine.includes(normalizedValue)
}

function extractSuggestionValue(line: string, role: string): string {
  const withoutHeading = line.trim().replace(/^#{1,6}\s+/, '')
  const withoutLabel = withoutHeading.replace(
    /^(摘要|关键词|作者单位|作者|单位|机构|组织|部门|所属部门|日期|时间|发布时间)\s*[:：]\s*/,
    '',
  )
  if (role === 'keywords') {
    return withoutLabel
      .split(/[；;，,\n]+/)
      .map((item) => item.trim())
      .filter(Boolean)
      .join('\n')
  }
  return withoutLabel.trim()
}

function formatMetadataEntry(key: string, value: string): string[] {
  if (key === 'authors' || key === 'keywords') {
    const values = value.split(/[、，,;；\n]+/).map((item) => item.trim()).filter(Boolean)
    return [
      `${key}:`,
      ...values.map((item) => `  - ${item}`),
    ]
  }
  return [`${key}: ${value}`]
}

function replaceMetadataEntry(metadataLines: string[], key: string, entry: string[]): string[] {
  const result: string[] = []
  let index = 0
  let replaced = false
  while (index < metadataLines.length) {
    const line = metadataLines[index]
    if (new RegExp(`^${key}:\\s*`).test(line)) {
      if (!replaced) {
        result.push(...entry)
        replaced = true
      }
      index += 1
      while (index < metadataLines.length && /^\s+-\s+/.test(metadataLines[index])) index += 1
      continue
    }
    result.push(line)
    index += 1
  }
  if (!replaced) result.push(...entry)
  return result
}

function trimMarkdownLines(lines: string[]): string {
  return `${lines.join('\n').replace(/^\n+/, '').replace(/\n+$/, '')}\n`
}

function messageFor(error: unknown): string {
  return error instanceof Error ? error.message : '发生未预期的本地处理错误。'
}
