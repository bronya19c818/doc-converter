import { ChangeEvent, FormEvent, useEffect, useMemo, useRef, useState } from 'react'
import {
  IconArrowsMaximize,
  IconArrowsMinimize,
  IconArrowsLeftRight,
  IconCircleCheck,
  IconDeviceFloppy,
  IconDownload,
  IconFilePlus,
  IconFileText,
  IconInfoCircle,
  IconPencil,
  IconSettings,
  IconUpload,
  IconX,
} from '@tabler/icons-react'

import {
  artifactUrl,
  createJob,
  createStylePack,
  fetchArtifactText,
  getJobDraft,
  Job,
  listStylePacks,
  normalizeAndRender,
  previewUrl,
  saveDraft,
  StylePack,
  Suggestion,
} from './api'
import { DocxPreview, preloadDocxPreview } from './DocxPreview'
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

function isMarkdownFile(filename: string): boolean {
  const normalizedName = filename.toLowerCase()
  return normalizedName.endsWith('.md') || normalizedName.endsWith('.markdown')
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
  const [isRendering, setIsRendering] = useState(false)
  const [previewFullscreen, setPreviewFullscreen] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const settingsTriggerRef = useRef<HTMLButtonElement>(null)
  const settingsCloseRef = useRef<HTMLButtonElement>(null)
  const settingsDialogRef = useRef<HTMLDivElement>(null)
  const previewPanelRef = useRef<HTMLElement>(null)
  const previewFullscreenButtonRef = useRef<HTMLButtonElement>(null)

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
      void preloadDocxPreview().catch(() => undefined)
      if (isMarkdownFile(file.name)) {
        const text = await file.text()
        setSourceMarkdown(text)
        setOriginalMarkdown(text)
      } else {
        setSourceMarkdown('')
        setOriginalMarkdown('')
      }
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
      const importedDraft = isMarkdownFile(sourceFile.name) ? null : await getJobDraft(created.id)
      const importedMarkdown = importedDraft?.source_markdown ?? sourceMarkdown
      const jobWithImportWarnings = importedDraft
        ? { ...created, import_warnings: importedDraft.warnings }
        : created
      const prepared = await persistHighConfidenceSuggestions(jobWithImportWarnings, importedMarkdown)
      setJob(prepared.job)
      setSourceMarkdown(prepared.markdown)
      setOriginalMarkdown(prepared.markdown)
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
      const saved = await saveDraft(job.id, sourceMarkdown)
      const prepared = await persistHighConfidenceSuggestions(saved, sourceMarkdown)
      setJob(prepared.job)
      setSourceMarkdown(prepared.markdown)
      setOriginalMarkdown(prepared.markdown)
    } catch (saveError) {
      setError(messageFor(saveError))
    } finally {
      setBusy(false)
    }
  }

  async function handleRender() {
    if (!job || !selectedPack) return
    setBusy(true)
    setIsRendering(true)
    setError(null)
    setDownloadsOpen(false)
    try {
      const renderedJob = await normalizeAndRender(job.id, sourceMarkdown, {}, selectedPack)
      setJob(renderedJob)
      if (renderedJob.artifacts.includes('document.normalized.md')) {
        try {
          const normalizedMarkdown = await fetchArtifactText(
            renderedJob.id,
            'document.normalized.md',
            renderedJob.render_revision,
          )
          setSourceMarkdown(normalizedMarkdown)
          setOriginalMarkdown(normalizedMarkdown)
        } catch (artifactError) {
          setOriginalMarkdown(sourceMarkdown)
          setError(`文档已生成，但规范化工作区未能载入：${messageFor(artifactError)}`)
        }
      } else {
        setOriginalMarkdown(sourceMarkdown)
      }
    } catch (renderError) {
      setError(messageFor(renderError))
    } finally {
      setIsRendering(false)
      setBusy(false)
    }
  }

  function applySuggestion(suggestion: Suggestion) {
    setSourceMarkdown((current) => applyRoleToMarkdown(current, suggestion))
  }

  async function persistHighConfidenceSuggestions(initialJob: Job, markdown: string): Promise<{ job: Job; markdown: string }> {
    let currentJob = initialJob
    let currentMarkdown = markdown
    for (let attempt = 0; attempt < 4; attempt += 1) {
      const nextMarkdown = applyHighConfidenceSuggestions(currentMarkdown, currentJob.suggestions)
      if (nextMarkdown === currentMarkdown) return { job: currentJob, markdown: currentMarkdown }
      currentMarkdown = nextMarkdown
      currentJob = await saveDraft(currentJob.id, currentMarkdown)
    }
    return { job: currentJob, markdown: currentMarkdown }
  }

  function openSettings() {
    setSettingsOpen(true)
  }

  function closeSettings() {
    setSettingsOpen(false)
    settingsTriggerRef.current?.focus()
  }

  useEffect(() => {
    if (!settingsOpen) return undefined

    settingsCloseRef.current?.focus()
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    function handleSettingsKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.preventDefault()
        closeSettings()
        return
      }
      if (event.key !== 'Tab') return

      const dialog = settingsDialogRef.current
      if (!dialog) return
      const focusable = Array.from(
        dialog.querySelectorAll<HTMLElement>(
          'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])',
        ),
      ).filter((element) => element.getAttribute('aria-hidden') !== 'true')
      if (!focusable.length) {
        event.preventDefault()
        return
      }

      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      const active = document.activeElement
      if (event.shiftKey && (active === first || !dialog.contains(active))) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && (active === last || !dialog.contains(active))) {
        event.preventDefault()
        first.focus()
      }
    }

    window.addEventListener('keydown', handleSettingsKeyDown)
    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', handleSettingsKeyDown)
    }
  }, [settingsOpen])

  useEffect(() => {
    if (!previewFullscreen) return undefined

    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    previewFullscreenButtonRef.current?.focus()

    function handlePreviewKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.preventDefault()
        setPreviewFullscreen(false)
        previewFullscreenButtonRef.current?.focus()
        return
      }
      if (event.key !== 'Tab') return

      const dialog = previewPanelRef.current
      if (!dialog) return
      const focusable = Array.from(
        dialog.querySelectorAll<HTMLElement>(
          'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href], iframe, [tabindex]:not([tabindex="-1"])',
        ),
      ).filter((element) => element.getAttribute('aria-hidden') !== 'true')
      if (!focusable.length) {
        event.preventDefault()
        return
      }

      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      const active = document.activeElement
      if (event.shiftKey && (active === first || !dialog.contains(active))) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && (active === last || !dialog.contains(active))) {
        event.preventDefault()
        first.focus()
      }
    }

    window.addEventListener('keydown', handlePreviewKeyDown)
    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', handlePreviewKeyDown)
    }
  }, [previewFullscreen])

  return (
    <main className="app-shell">
      <header className="app-header">
        <div className="brand-lockup">
          <span className="brand-mark-frame">
            <img alt="" className="brand-mark" src="/assets/doc-converter-mark.png" />
          </span>
          <div>
            <h1>Doc Converter</h1>
            <p>文档格式转换</p>
          </div>
        </div>
        <p className="brand-tagline">让内容自由流转</p>
      </header>

      <section className="workspace" aria-label="文档格式转换工作区">
        <section className="markdown-panel" aria-label="源文件工作区">
          <div className="panel-title">
            <span className="section-number">01</span>
            <div>
              <h2>源文件工作区</h2>
              <p>选择 Markdown、DOCX 或 DOC 文件。</p>
            </div>
          </div>
          <div className="file-picker">
            <IconFileText aria-hidden="true" size={30} stroke={1.8} />
            <label className="file-select-button" htmlFor="source-file">
              <IconUpload aria-hidden="true" size={18} stroke={1.8} />
              选择文件
            </label>
            <input
              accept=".md,.markdown,.docx,.doc,text/markdown,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/msword"
              aria-label="选择文件"
              className="file-input-hidden"
              id="source-file"
              onChange={handleFileChange}
              type="file"
            />
            <span className="file-name" title={sourceFile?.name ?? ''}>
              {sourceFile?.name ?? '尚未选择文件'}
            </span>
          </div>
          <p className="field-help source-help">源文件不会被改动。</p>
          <div className="editor-label-row">
            <label className="editor-label" htmlFor="markdown-draft">
              <IconPencil aria-hidden="true" size={22} stroke={1.8} />
              内容工作区
            </label>
            <span className="editor-support"><IconInfoCircle aria-hidden="true" size={17} />Markdown</span>
          </div>
          <textarea
            aria-label="内容工作区"
            className="markdown-editor"
            id="markdown-draft"
            onChange={(event) => setSourceMarkdown(event.target.value)}
            placeholder="选择文件后，可在这里编辑 Markdown 内容工作副本。"
            value={sourceMarkdown}
          />
          {job?.import_warnings?.length ? (
            <p className="field-help" role="status">
              导入提示：{job.import_warnings.join('；')}
            </p>
          ) : null}
          <div className="draft-status" role="status">
            <IconCircleCheck aria-hidden="true" size={18} />
            {markdownChanged ? '有未保存修改' : '工作区已保存'}
          </div>
          <div className="draft-actions">
            <button className="secondary-action primary-draft-action" disabled={busy || !sourceFile || !selectedPack} onClick={handlePrepare} type="button">
              <IconFilePlus aria-hidden="true" size={20} />
              {job ? '重新建立工作副本' : '建立本地工作副本'}
            </button>
            <button className="secondary-action" disabled={busy || !job || !markdownChanged} onClick={handleSaveDraft} type="button">
              <IconDeviceFloppy aria-hidden="true" size={20} />保存工作副本
            </button>
          </div>

          {job?.suggestions.length ? (
            <section className="suggestions" aria-label="结构建议">
              <h3>结构建议</h3>
              <p className="field-help">置信度超过90%的建议会自动应用，其余建议可手动应用。</p>
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

        <section
          aria-label="DOCX 预览"
          aria-modal={previewFullscreen ? true : undefined}
          className={previewFullscreen ? 'preview-panel is-fullscreen' : 'preview-panel'}
          ref={previewPanelRef}
          role={previewFullscreen ? 'dialog' : 'region'}
        >
          <div className="preview-heading">
            <div>
              <span className="section-number">02</span>
              <div>
                <h2>转换结果预览</h2>
                <p>转换完成后可在此查看结果。</p>
              </div>
            </div>
            <div className="preview-heading-actions">
              {completedJob || isRendering ? (
                <span className={isRendering ? 'processing-status' : 'completed-status'}>
                  {isRendering ? '正在转换' : '已生成'}
                </span>
              ) : null}
              <button
                aria-label={previewFullscreen ? '退出全屏预览' : '全屏预览'}
                className="preview-fullscreen-toggle"
                onClick={() => setPreviewFullscreen((current) => !current)}
                ref={previewFullscreenButtonRef}
                type="button"
              >
                {previewFullscreen ? <IconArrowsMinimize aria-hidden="true" size={18} /> : <IconArrowsMaximize aria-hidden="true" size={18} />}
                <span>{previewFullscreen ? '退出全屏' : '全屏预览'}</span>
              </button>
            </div>
          </div>
          {completedJob ? (
            <div aria-busy={isRendering} className="preview-frame">
              <DocxPreview
                documentUrl={artifactUrl(completedJob.id, completedJob.output_name ?? 'document.docx', completedJob.render_revision)}
                previewUrl={completedJob.preview_ready ? previewUrl(completedJob.id, completedJob.render_revision) : undefined}
              />
              {isRendering ? (
                <div aria-label="正在转换文档" className="preview-progress-overlay" role="status">
                  <span aria-hidden="true" className="conversion-spinner" />
                  <strong>正在转换文档…</strong>
                  <span>完成后会自动更新预览。</span>
                </div>
              ) : null}
            </div>
          ) : isRendering ? (
            <div aria-busy="true" aria-label="正在转换文档" className="preview-empty is-converting" role="status">
              <span aria-hidden="true" className="conversion-spinner" />
              <p>正在转换文档…</p>
              <span>页面预览完成后会显示在这里。</span>
            </div>
          ) : (
            <div className="preview-empty">
              <img alt="" aria-hidden="true" src="/assets/preview-empty-state.png" />
              <p>转换后可在此查看结果预览。</p>
              <span>文档生成后，页面内容会显示在这里。</span>
            </div>
          )}
        </section>
      </section>

      <button
        aria-hidden={!settingsOpen}
        aria-label="关闭设置"
        className={settingsOpen ? 'settings-backdrop is-open' : 'settings-backdrop'}
        onClick={closeSettings}
        tabIndex={-1}
        type="button"
      />

      <section
        aria-hidden={!settingsOpen}
        aria-label="设置面板"
        className={settingsOpen ? 'settings-panel is-open' : 'settings-panel'}
        id="settings-panel-root"
      >
        <div
          aria-labelledby="settings-dialog-title"
          aria-modal={settingsOpen}
          className="settings-shell"
          ref={settingsDialogRef}
          role="dialog"
        >
          <div className="settings-heading">
            <div>
              <span className="section-number">03</span>
              <h2 id="settings-dialog-title">样式设置</h2>
            </div>
            <div className="settings-heading-actions">
              <button aria-label="收起设置" className="settings-close" onClick={closeSettings} ref={settingsCloseRef} type="button">
                <IconX aria-hidden="true" size={18} />
                收起设置
              </button>
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
      </section>

      <div aria-label="快捷操作" className="floating-actions">
        <button
          aria-label={isRendering ? '正在转换' : '生成'}
          className="action-fab generate-fab"
          disabled={busy || !job || !selectedPack || !sourceMarkdown.trim()}
          onClick={handleRender}
          type="button"
        >
          <IconArrowsLeftRight aria-hidden="true" size={19} />
          <span>{isRendering ? '正在转换…' : '开始转换'}</span>
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
            <IconDownload aria-hidden="true" size={19} />
            <span>下载</span>
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
        <button
          aria-controls="settings-panel-root"
          aria-expanded={settingsOpen}
          aria-label="打开设置"
          className="settings-fab"
          onClick={openSettings}
          ref={settingsTriggerRef}
          type="button"
        >
          <IconSettings aria-hidden="true" size={20} />
          <span>设置</span>
        </button>
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

export function applyHighConfidenceSuggestions(markdown: string, suggestions: Suggestion[]): string {
  return suggestions
    .filter((suggestion) => suggestion.score > 0.9)
    .slice()
    .sort((left, right) => right.line - left.line)
    .reduce((current, suggestion) => applyRoleToMarkdown(current, suggestion), markdown)
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
