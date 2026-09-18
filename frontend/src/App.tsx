import { ChangeEvent, FormEvent, useEffect, useMemo, useState } from 'react'

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

type SettingsTab = 'styles' | 'page' | 'artifacts'

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
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [appliedRoles, setAppliedRoles] = useState<Record<string, string>>({})

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
    setAppliedRoles({})
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
    try {
      setJob(await normalizeAndRender(job.id, sourceMarkdown, appliedRoles))
      setOriginalMarkdown(sourceMarkdown)
    } catch (renderError) {
      setError(messageFor(renderError))
    } finally {
      setBusy(false)
    }
  }

  function applySuggestion(suggestion: Suggestion) {
    setSourceMarkdown((current) => applyRoleToMarkdown(current, suggestion))
    setAppliedRoles((roles) => ({ ...roles, [suggestion.line]: suggestion.role }))
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
              <p className="field-help">建议只是提示，不会阻止生成；应用后会直接更新工作副本。</p>
              {job.suggestions.map((suggestion) => (
                <article key={`${suggestion.line}-${suggestion.role}`}>
                  <strong>第 {suggestion.line} 行：{suggestion.role === 'document-subtitle' ? '副标题' : '文档标题'}</strong>
                  <p>{suggestion.reason}，置信度 {Math.round(suggestion.score * 100)}%。</p>
                  <button className="text-action" onClick={() => applySuggestion(suggestion)} type="button">
                    应用为{suggestion.role === 'document-subtitle' ? '副标题' : '标题'}
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

      <section className={`settings-panel ${settingsOpen ? 'is-open' : 'is-collapsed'}`} aria-label="设置面板">
        {!settingsOpen ? (
          <button
            aria-expanded={false}
            aria-label="打开设置"
            className="settings-fab"
            onClick={() => setSettingsOpen(true)}
            type="button"
          >
            ⚙ 设置
          </button>
        ) : (
          <div className="settings-shell">
            <div className="settings-heading">
              <div>
                <span>03</span>
                <h2>样式与产物</h2>
              </div>
              <div className="settings-heading-actions">
                <button className="primary-action compact" disabled={busy || !job || !selectedPack || !sourceMarkdown.trim()} onClick={handleRender} type="button">生成 DOCX</button>
                <button aria-label="收起设置" className="settings-close" onClick={() => setSettingsOpen(false)} type="button">收起设置</button>
              </div>
            </div>
            <div aria-label="设置分类" className="settings-tabs" role="tablist">
              {([
                ['styles', '样式角色'],
                ['page', '页面设置'],
                ['artifacts', '下载产物'],
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
              {settingsTab === 'artifacts' ? (
                <div aria-labelledby="settings-tab-artifacts" id="settings-panel-artifacts" role="tabpanel">
                  <h3>下载产物</h3>
                  {completedJob ? (
                    <div className="artifact-links" aria-label="任务产物下载">
                      {completedJob.artifacts.map((artifact) => <a href={artifactUrl(completedJob.id, artifact)} key={artifact}>{artifact === completedJob.output_name ? '下载 DOCX' : `下载 ${artifact}`}</a>)}
                    </div>
                  ) : <p className="field-help">生成 DOCX 后，规范化 Markdown、审计报告、样式快照和 DOCX 会出现在这里。</p>}
                </div>
              ) : null}
            </div>
          </div>
        )}
      </section>
    </main>
  )
}

function applyRoleToMarkdown(markdown: string, suggestion: Suggestion): string {
  const lines = markdown.split(/\r?\n/)
  const index = suggestion.line - 1
  const selected = lines[index] ?? ''
  const match = selected.match(/^#{1,6}\s+(.+?)\s*$/)
  if (!match) return markdown
  const key = suggestion.role === 'document-subtitle' ? 'subtitle' : 'title'
  const metadata = `---\n${key}: ${match[1]}\n---`
  const withoutLine = [...lines.slice(0, index), ...lines.slice(index + 1)].join('\n').replace(/^\n+/, '')
  if (/^---\r?\n[\s\S]*?\r?\n---/.test(markdown)) {
    return markdown.replace(/^---\r?\n/, `---\n${key}: ${match[1]}\n`).replace(/^(---\r?\n[\s\S]*?)\r?\n---/, '$1\n---').replace(selected, '')
  }
  return `${metadata}\n\n${withoutLine}`
}

function messageFor(error: unknown): string {
  return error instanceof Error ? error.message : '发生未预期的本地处理错误。'
}
