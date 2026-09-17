import { ChangeEvent, FormEvent, useEffect, useMemo, useState } from 'react'

import {
  artifactUrl,
  createJob,
  createStylePack,
  Job,
  listStylePacks,
  normalizeAndRender,
  StylePack,
} from './api'
import { DocxPreview } from './DocxPreview'
import { StyleEditor } from './StyleEditor'
import './styles.css'

const defaultStyleRoles = {
  'document-title': { font_name: '黑体', font_size_pt: 22, alignment: 'center', bold: true },
  'heading-1': { font_name: '黑体', font_size_pt: 16, bold: true },
  body: { font_name: '宋体', font_size_pt: 12, first_line_indent_pt: 24 },
}

export function App() {
  const [stylePacks, setStylePacks] = useState<StylePack[]>([])
  const [selectedPackId, setSelectedPackId] = useState('')
  const [sourceFile, setSourceFile] = useState<File | null>(null)
  const [job, setJob] = useState<Job | null>(null)
  const [newPackName, setNewPackName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const selectedPack = useMemo(
    () => stylePacks.find((pack) => pack.id === selectedPackId) ?? null,
    [selectedPackId, stylePacks],
  )

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
      const pack = await createStylePack({
        name: newPackName.trim(),
        format_id: 'docx',
        roles: defaultStyleRoles,
      })
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
    const file = event.target.files?.[0] ?? null
    setSourceFile(file)
    setJob(null)
    setError(null)
  }

  async function handlePrepare() {
    if (!sourceFile || !selectedPack) return
    setBusy(true)
    setError(null)
    try {
      setJob(await createJob(sourceFile, selectedPack))
    } catch (prepareError) {
      setError(messageFor(prepareError))
    } finally {
      setBusy(false)
    }
  }

  async function handleRender() {
    if (!job) return
    setBusy(true)
    setError(null)
    try {
      const confirmedRoles = Object.fromEntries(job.suggestions.map((suggestion) => [suggestion.line, suggestion.role]))
      setJob(await normalizeAndRender(job.id, confirmedRoles))
    } catch (renderError) {
      setError(messageFor(renderError))
    } finally {
      setBusy(false)
    }
  }

  const completedJob = job?.status === 'completed' ? job : null

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
        <section className="control-panel">
          <div className="section-heading">
            <span>01</span>
            <h2>选择内容与样式</h2>
          </div>

          <label className="field-label" htmlFor="source-file">选择 Markdown 文件</label>
          <input accept=".md,.markdown,text/markdown" id="source-file" onChange={handleFileChange} type="file" />
          <p className="field-help">源文件只复制到本机任务目录，原文件不会被改动。</p>

          <label className="field-label" htmlFor="style-pack">DOCX 样式组合</label>
          <select
            id="style-pack"
            onChange={(event) => setSelectedPackId(event.target.value)}
            value={selectedPackId}
          >
            {stylePacks.map((pack) => (
              <option key={pack.id} value={pack.id}>
                {pack.name} · v{pack.version}
              </option>
            ))}
          </select>

          <form className="new-pack-form" onSubmit={handleCreateStylePack}>
            <label className="field-label" htmlFor="new-style-pack">新建样式组合</label>
            <div>
              <input
                id="new-style-pack"
                onChange={(event) => setNewPackName(event.target.value)}
                placeholder="例如：公司报告"
                value={newPackName}
              />
              <button disabled={busy || !newPackName.trim()} type="submit">保存</button>
            </div>
            <p className="field-help">新组合使用可编辑的标题、一级标题和正文默认样式。</p>
          </form>

          {selectedPack ? (
            <StyleEditor
              disabled={busy}
              key={`${selectedPack.id}-${selectedPack.version}`}
              onSaved={(savedPack) => {
                setStylePacks((packs) => packs.map((pack) => (pack.id === savedPack.id ? savedPack : pack)))
                setSelectedPackId(savedPack.id)
              }}
              pack={selectedPack}
            />
          ) : null}

          <button className="primary-action" disabled={busy || !sourceFile || !selectedPack} onClick={handlePrepare} type="button">
            {busy ? '处理中…' : '检查文档结构'}
          </button>

          {job?.suggestions.length ? (
            <section className="suggestions" aria-label="待确认的结构建议">
              <h3>请确认结构建议</h3>
              {job.suggestions.map((suggestion) => (
                <article key={suggestion.line}>
                  <strong>第 {suggestion.line} 行：文档标题</strong>
                  <p>{suggestion.reason}，置信度 {Math.round(suggestion.score * 100)}%。</p>
                </article>
              ))}
              <button className="primary-action" disabled={busy} onClick={handleRender} type="button">
                确认并生成 DOCX
              </button>
            </section>
          ) : null}

          {job?.status === 'ready' ? (
            <button className="primary-action" disabled={busy} onClick={handleRender} type="button">
              生成 DOCX
            </button>
          ) : null}
          {error ? <p className="error-message" role="alert">{error}</p> : null}
        </section>

        <section className="preview-panel">
          <div className="preview-heading">
            <div>
              <span>02</span>
              <h2>文档预览</h2>
            </div>
            {job?.status === 'completed' ? <span className="completed-status">已生成</span> : null}
          </div>

          {completedJob ? (
            <>
              <div className="preview-frame"><DocxPreview documentUrl={artifactUrl(completedJob.id, 'result.docx')} /></div>
              <div className="artifact-links">
                <a href={artifactUrl(completedJob.id, 'result.docx')}>下载 DOCX</a>
                {completedJob.artifacts.filter((artifact) => artifact !== 'result.docx').map((artifact) => (
                  <a href={artifactUrl(completedJob.id, artifact)} key={artifact}>{artifact}</a>
                ))}
              </div>
            </>
          ) : (
            <div className="preview-empty">
              <p>生成后可在此查看内置 DOCX 预览。</p>
              <small>预览在浏览器内完成；需要版式复核时可另用本机 Word 打开导出的 DOCX。</small>
            </div>
          )}
        </section>
      </section>
    </main>
  )
}

function messageFor(error: unknown): string {
  return error instanceof Error ? error.message : '发生未预期的本地处理错误。'
}
