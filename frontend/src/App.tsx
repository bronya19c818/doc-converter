import { ChangeEvent, FormEvent, useEffect, useMemo, useRef, useState } from 'react'
import {
  IconArrowsMaximize,
  IconArrowsMinimize,
  IconArrowsLeftRight,
  IconDownload,
  IconFileText,
  IconSettings,
  IconUpload,
  IconX,
} from '@tabler/icons-react'

import {
  artifactUrl,
  createJob,
  createStylePack,
  Job,
  listStylePacks,
  normalizeAndRender,
  normalizeDocxDirect,
  previewUrl,
  StylePack,
} from './api'
import { DocxPreview, preloadDocxPreview } from './DocxPreview'
import { StyleEditor } from './StyleEditor'
import './styles.css'

type SettingsTab = 'styles' | 'page'

export function App() {
  const [stylePacks, setStylePacks] = useState<StylePack[]>([])
  const [selectedPackId, setSelectedPackId] = useState('')
  const [sourceFile, setSourceFile] = useState<File | null>(null)
  const [job, setJob] = useState<Job | null>(null)
  const [newPackName, setNewPackName] = useState('')
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [settingsTab, setSettingsTab] = useState<SettingsTab>('styles')
  const [downloadsOpen, setDownloadsOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [isRendering, setIsRendering] = useState(false)
  const [previewFullscreen, setPreviewFullscreen] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const settingsDirtyRef = useRef(false)
  const settingsTriggerRef = useRef<HTMLButtonElement>(null)
  const settingsCloseRef = useRef<HTMLButtonElement>(null)
  const settingsDialogRef = useRef<HTMLDivElement>(null)
  const previewPanelRef = useRef<HTMLElement>(null)
  const previewFullscreenButtonRef = useRef<HTMLButtonElement>(null)

  const selectedPack = useMemo(
    () => stylePacks.find((pack) => pack.id === selectedPackId) ?? null,
    [selectedPackId, stylePacks],
  )
  const completedJob = job?.status === 'completed' ? job : null
  const directMode = sourceFile?.name.toLowerCase().endsWith('.docx') ?? false

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

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    if (busy) return
    const file = event.target.files?.[0] ?? null
    setSourceFile(file)
    setJob(null)
    setSettingsTab('styles')
    setDownloadsOpen(false)
    setError(null)
    if (file) void preloadDocxPreview().catch(() => undefined)
  }

  async function handleRender() {
    if (busy || !selectedPack || !sourceFile) return
    setBusy(true)
    setIsRendering(true)
    setError(null)
    setDownloadsOpen(false)
    try {
      const currentJob = job ?? await createJob(sourceFile, selectedPack, directMode ? 'docx-direct' : 'round-trip')
      if (!job) setJob(currentJob)
      const renderedJob = directMode
        ? await normalizeDocxDirect(currentJob.id, selectedPack)
        : await normalizeAndRender(currentJob.id, selectedPack)
      setJob(renderedJob)
    } catch (renderError) {
      setError(messageFor(renderError))
    } finally {
      setIsRendering(false)
      setBusy(false)
    }
  }

  function openSettings() {
    setSettingsOpen(true)
  }

  function closeSettings() {
    if (settingsDirtyRef.current && !window.confirm('有未保存的样式修改，仍要关闭设置吗？')) return
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
      ).filter((element) => element.getAttribute('aria-hidden') !== 'true' && !element.closest('[hidden]') && !element.closest('details:not([open])'))
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
      ).filter((element) => element.getAttribute('aria-hidden') !== 'true' && !element.closest('[hidden]') && !element.closest('details:not([open])'))
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

      <div className="workspace-toolbar">
        <label htmlFor="active-style-pack">样式预设</label>
        <select aria-label="样式预设" id="active-style-pack" disabled={busy || !stylePacks.length} onChange={(event) => {
          if (settingsDirtyRef.current && !window.confirm('切换预设会放弃未保存的修改，继续吗？')) return
          settingsDirtyRef.current = false
          setSelectedPackId(event.target.value)
        }} value={selectedPackId}>
          {stylePacks.map((pack) => <option key={pack.id} value={pack.id}>{pack.name} · v{pack.version}</option>)}
        </select>
        <button aria-label="打开设置" aria-expanded={settingsOpen} aria-controls="settings-panel-root" className="secondary-action" onClick={openSettings} ref={settingsTriggerRef} type="button">
          <IconSettings aria-hidden="true" size={18} />编辑样式
        </button>
      </div>
      <section className="workspace" aria-label="文档格式转换工作区">
        <section className={sourceFile ? "source-panel" : "source-panel is-empty"} aria-label="源文件工作区">
          <div className="panel-title">
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
              disabled={busy}
              onChange={handleFileChange}
              type="file"
            />
            <span className="file-name" title={sourceFile?.name ?? ''}>
              {sourceFile?.name ?? '尚未选择文件'}
            </span>
          </div>
          <p className="field-help source-help">源文件不会被改动。</p>
          {sourceFile ? <p className="conversion-help">
            {directMode ? '自动识别段落并应用样式，保留表格、图片和页面布局。' : '自动识别标题层级和文前信息，统一格式并生成 DOCX。'}
          </p> : null}
          {job?.import_warnings?.length ? (
            <p className="field-help" role="status">导入提示：{job.import_warnings.join('；')}</p>
          ) : null}
          {job?.processing_warnings?.length ? (
            <p className="field-help" role="status">{job.processing_warnings.join('；')}</p>
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
              <div>
                <h2>转换结果预览</h2>
                <p>{completedJob ? (sourceFile?.name ?? completedJob.source_original_name) : ""}</p>
              </div>
            </div>
            <div className="preview-heading-actions">
              {completedJob || isRendering ? (
                <span className={isRendering ? 'processing-status' : 'completed-status'}>
                  {isRendering ? '正在转换' : completedJob && selectedPack && (completedJob.style_pack_id !== selectedPack.id || completedJob.style_pack_version !== selectedPack.version) ? '样式已更新，待重新转换' : '已生成'}
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
              <IconFileText aria-hidden="true" size={44} stroke={1.3} />
              <p>{sourceFile ? "点击开始转换，结果将在这里显示。" : "选择源文件后，在这里预览转换结果。"}</p>
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
            ] as const).filter(([tab]) => !directMode || tab !== 'page').map(([tab, label]) => (
              <button
                aria-controls={`settings-panel-${tab}`}
                aria-selected={settingsTab === tab}
                className="settings-tab"
                id={`settings-tab-${tab}`}
                key={tab}
                onClick={() => {
                  if (settingsDirtyRef.current && !window.confirm('切换设置会放弃未保存的修改，继续吗？')) return
                  settingsDirtyRef.current = false
                  setSettingsTab(tab)
                }}
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
                <div className="preset-context"><strong>{selectedPack?.name}</strong><span>v{selectedPack?.version}</span></div>
                <details className="new-preset-disclosure"><summary>新建样式组合</summary>
                <form className="new-pack-form" onSubmit={handleCreateStylePack}>
                  <label className="field-label" htmlFor="new-style-pack">新建样式组合</label>
                  <div>
                    <input id="new-style-pack" onChange={(event) => setNewPackName(event.target.value)} placeholder="例如：公司报告" value={newPackName} />
                    <button disabled={busy || !newPackName.trim()} type="submit">保存</button>
                  </div>
                </form>
                </details>
                {selectedPack ? (
                  <StyleEditor
                    disabled={busy}
                    key={`${selectedPack.id}-roles`}
                    onDirtyChange={(dirty) => { settingsDirtyRef.current = dirty }}
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
            {settingsTab === 'page' && !directMode ? (
              <div aria-labelledby="settings-tab-page" id="settings-panel-page" role="tabpanel">
                {selectedPack ? (
                  <StyleEditor
                    disabled={busy}
                    key={`${selectedPack.id}-page`}
                    onDirtyChange={(dirty) => { settingsDirtyRef.current = dirty }}
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
        <span className="action-context" title={sourceFile?.name}>{sourceFile?.name ?? "选择源文件后开始转换"}</span>
        <button
          aria-label={isRendering ? '正在转换' : '开始转换'}
          className="action-fab generate-fab"
          disabled={busy || !selectedPack || !sourceFile}
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
            disabled={busy || !completedJob}
            onClick={() => setDownloadsOpen((open) => !open)}
            type="button"
          >
            <IconDownload aria-hidden="true" size={19} />
            <span>下载</span>
          </button>
          {downloadsOpen && completedJob ? (
            <div aria-label="任务产物下载" className="download-popover">
              {completedJob.artifacts.filter((artifact) => artifact === completedJob.output_name || artifact === 'normalization-report.json' || artifact === 'docx-normalization-report.json').map((artifact) => (
                <a href={artifactUrl(completedJob.id, artifact, completedJob.render_revision)} key={artifact}>
                  {artifact === completedJob.output_name ? '下载 DOCX' : '下载处理报告'}
                </a>
              ))}
            </div>
          ) : null}
        </div>

      </div>
    </main>
  )
}

function messageFor(error: unknown): string {
  return error instanceof Error ? error.message : '发生未预期的本地处理错误。'
}

