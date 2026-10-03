import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { App, applyHighConfidenceSuggestions, applyRoleToMarkdown } from './App'

vi.mock('./DocxPreview', () => ({
  preloadDocxPreview: vi.fn().mockResolvedValue(undefined),
  DocxPreview: ({ documentUrl, previewUrl }: { documentUrl: string; previewUrl?: string }) => (
    <div data-preview-url={previewUrl ?? ''} data-testid="docx-preview">{documentUrl}</div>
  ),
}))

import { preloadDocxPreview } from './DocxPreview'

describe('App', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [],
      }),
    )
  })

  it('keeps the workspace focused on conversion controls', async () => {
    render(<App />)

    expect(screen.getByRole('heading', { name: 'Doc Converter' })).toBeInTheDocument()
    expect(screen.queryByText('本地转换，不调用 AI，也不上传文档。')).not.toBeInTheDocument()
    expect(screen.queryByText('仅本机运行')).not.toBeInTheDocument()
    expect(await screen.findByLabelText('选择文件')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '转换结果预览' })).toBeInTheDocument()
    expect(screen.queryByText('预览按独立 A4 纸张显示，在浏览器内完成；不依赖 LibreOffice 自动转换。')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '生成' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '下载' })).toBeDisabled()
  })

  it('preloads the DOCX renderer as soon as a source file is selected', async () => {
    render(<App />)

    const file = new File(['# 项目方案\n'], 'demo.md', { type: 'text/markdown' })
    fireEvent.change(await screen.findByLabelText('选择文件'), { target: { files: [file] } })

    await waitFor(() => expect(preloadDocxPreview).toHaveBeenCalledTimes(1))
  })

  it('runs DOCX direct normalization without a Markdown draft and shows its output', async () => {
    const pack = { id: 'formal-report', name: '正式报告', format_id: 'docx', version: 1, roles: {} }
    const readyJob = {
      id: 'direct-job', status: 'ready', conversion_mode: 'docx-direct', source_name: '合同.docx',
      source_original_name: '合同.docx', source_format: 'docx', import_warnings: [],
      style_pack_id: pack.id, style_pack_version: 1, suggestions: [], artifacts: [], error: null,
      output_name: null, draft_updated_at: null, source_hash: '', render_revision: 0, preview_ready: false,
    }
    const completedJob = {
      ...readyJob, status: 'completed', output_name: '合同_规范化.docx', render_revision: 1,
      artifacts: ['合同_规范化.docx', 'docx-normalization-report.json'],
    }
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => [pack] })
      .mockResolvedValueOnce({ ok: true, json: async () => readyJob })
      .mockResolvedValueOnce({ ok: true, json: async () => completedJob })
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)

    const file = new File([new Uint8Array([0, 1, 2, 3])], '合同.docx')
    fireEvent.change(await screen.findByLabelText('选择文件'), { target: { files: [file] } })
    expect(screen.queryByLabelText('内容工作区')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '打开设置' }))
    expect(screen.queryByRole('tab', { name: '页面设置' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '收起设置' }))
    await waitFor(() => expect(screen.getByRole('button', { name: '生成' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: '生成' }))
    await waitFor(() => expect(fetchMock.mock.calls).toHaveLength(3))
    expect(fetchMock.mock.calls[1][1].body).toBeInstanceOf(FormData)
    expect((fetchMock.mock.calls[1][1].body as FormData).get('conversion_mode')).toBe('docx-direct')
    await waitFor(() => expect(screen.getByTestId('docx-preview')).toHaveTextContent('%E5%90%88%E5%90%8C_%E8%A7%84%E8%8C%83%E5%8C%96.docx'))
    expect(String(fetchMock.mock.calls[2][0])).toBe('/api/jobs/direct-job/normalize-docx-direct')
    fireEvent.click(screen.getByRole('button', { name: '下载' }))
    expect(screen.getByRole('link', { name: '下载 DOCX' })).toHaveAttribute('href', '/api/jobs/direct-job/artifacts/%E5%90%88%E5%90%8C_%E8%A7%84%E8%8C%83%E5%8C%96.docx')
  })

  it.each([
    { format: 'DOC', filename: '合同.doc', sourceFormat: 'doc' },
  ])('loads $format content from the backend without reading the binary file as text', async ({ filename, sourceFormat }) => {
    const pack = { id: 'formal-report', name: '正式报告', format_id: 'docx', version: 1, roles: {} }
    const readyJob = {
      id: 'job-1', status: 'ready', source_name: filename, source_original_name: filename,
      source_format: sourceFormat, import_warnings: [], style_pack_id: pack.id, style_pack_version: 1,
      suggestions: [], artifacts: [], error: null, output_name: null, draft_updated_at: null,
      source_hash: 'source', render_revision: 0, preview_ready: false,
    }
    const importedMarkdown = '# 合同标题\n\n从 DOCX 导入的正文。\n'
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => [pack] })
      .mockResolvedValueOnce({ ok: true, json: async () => readyJob })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          source_format: sourceFormat,
          source_markdown: importedMarkdown,
          warnings: ['Pandoc 导入提示。'],
        }),
      })
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)

    const file = new File([new Uint8Array([0, 1, 2, 3])], filename)
    const readText = vi.fn().mockResolvedValue('not the imported Markdown')
    Object.defineProperty(file, 'text', { value: readText })
    fireEvent.change(await screen.findByLabelText('选择文件'), { target: { files: [file] } })

    expect(readText).not.toHaveBeenCalled()
    expect(screen.getByLabelText('内容工作区')).toHaveValue('')
    fireEvent.click(await screen.findByRole('button', { name: '建立本地工作副本' }))

    await waitFor(() => expect(screen.getByLabelText('内容工作区')).toHaveValue(importedMarkdown))
    expect(screen.getByText('导入提示：Pandoc 导入提示。')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(String(fetchMock.mock.calls[2][0])).toBe('/api/jobs/job-1/draft')
  })

  it('auto-applies only suggestions with confidence above 90 percent', () => {
    const source = `---
title: 项目方案
---

摘要：这是摘要。

关键词：项目；实施
`

    const result = applyHighConfidenceSuggestions(source, [
      { line: 5, role: 'abstract', score: 0.91, reason: '摘要标签', value: '摘要：这是摘要。' },
      { line: 7, role: 'keywords', score: 0.9, reason: '关键词标签', value: '关键词：项目；实施' },
    ])

    expect(result).toContain('abstract: 这是摘要。')
    expect(result).toContain('关键词：项目；实施')
    expect(result).not.toContain('摘要：这是摘要。')
  })

  it('persists high-confidence structure suggestions after creating a working copy', async () => {
    const pack = { id: 'formal-report', name: '正式报告', format_id: 'docx', version: 1, roles: {} }
    const readyJob = {
      id: 'job-1', status: 'ready', source_name: 'demo.md', style_pack_id: pack.id, style_pack_version: 1,
      suggestions: [{ line: 5, role: 'abstract', score: 0.98, reason: '检测到摘要标签', value: '摘要：这是摘要。' }],
      artifacts: [], error: null, output_name: null, draft_updated_at: null, source_hash: 'source', render_revision: 0,
    }
    const savedJob = { ...readyJob, suggestions: [], source_hash: 'saved' }
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => [pack] })
      .mockResolvedValueOnce({ ok: true, json: async () => readyJob })
      .mockResolvedValueOnce({ ok: true, json: async () => savedJob })
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)

    const file = new File(['---\ntitle: 项目方案\n---\n\n摘要：这是摘要。\n'], 'demo.md', { type: 'text/markdown' })
    fireEvent.change(await screen.findByLabelText('选择文件'), { target: { files: [file] } })
    fireEvent.click(await screen.findByRole('button', { name: '建立本地工作副本' }))

    const editor = await screen.findByLabelText('内容工作区')
    await waitFor(() => expect(editor).toHaveValue('---\ntitle: 项目方案\nabstract: 这是摘要。\n---\n'))
    expect(screen.queryByRole('button', { name: '应用为摘要' })).not.toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(3)
    const savedBody = JSON.parse(fetchMock.mock.calls[2][1].body as string) as { source_markdown: string }
    expect(savedBody.source_markdown).toContain('abstract: 这是摘要。')
  })

  it('returns the normalized document to the workspace and uses it for later generations', async () => {
    const pack = { id: 'formal-report', name: '正式报告', format_id: 'docx', version: 3, roles: {} }
    const readyJob = {
      id: 'job-1', status: 'ready', source_name: 'demo.md', style_pack_id: pack.id, style_pack_version: 1,
      suggestions: [], artifacts: [], error: null, output_name: null, draft_updated_at: null, source_hash: 'source', render_revision: 0,
    }
    const normalizedMarkdown = '---\nschema: normalized-md/v1\ntitle: 项目方案\n---\n\n# 一、背景\n'
    const normalizedMarkdownAgain = '---\nschema: normalized-md/v1\ntitle: 项目方案\n---\n\n# 一、背景\n\n正文。\n'
    const completedJob = {
      ...readyJob, status: 'completed', style_pack_version: 3, artifacts: ['demo.docx', 'document.normalized.md'], output_name: 'demo.docx', render_revision: 1,
      preview_ready: true,
    }
    const regeneratedJob = { ...completedJob, render_revision: 2 }
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => [pack] })
      .mockResolvedValueOnce({ ok: true, json: async () => readyJob })
      .mockResolvedValueOnce({ ok: true, json: async () => completedJob })
      .mockResolvedValueOnce({ ok: true, text: async () => normalizedMarkdown })
      .mockResolvedValueOnce({ ok: true, json: async () => regeneratedJob })
      .mockResolvedValueOnce({ ok: true, text: async () => normalizedMarkdownAgain })
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)

    const file = new File(['# 项目方案\n'], 'demo.md', { type: 'text/markdown' })
    fireEvent.change(await screen.findByLabelText('选择文件'), { target: { files: [file] } })
    fireEvent.click(await screen.findByRole('button', { name: '建立本地工作副本' }))
    const generateButton = await screen.findByRole('button', { name: '生成' })
    const editor = screen.getByLabelText('内容工作区')

    fireEvent.click(generateButton)
    await waitFor(() => expect(screen.getByTestId('docx-preview')).toHaveTextContent('revision=1'))
    expect(screen.getByTestId('docx-preview')).toHaveAttribute('data-preview-url', '/api/jobs/job-1/preview?revision=1')
    await waitFor(() => expect(editor).toHaveValue(normalizedMarkdown))

    fireEvent.click(screen.getByRole('button', { name: '生成' }))
    await waitFor(() => expect(screen.getByTestId('docx-preview')).toHaveTextContent('revision=2'))
    await waitFor(() => expect(editor).toHaveValue(normalizedMarkdownAgain))

    const renderCalls = fetchMock.mock.calls.filter(([input]) => String(input).includes('/normalize-and-render'))
    expect(renderCalls).toHaveLength(2)
    const firstRenderBody = JSON.parse(renderCalls[0][1].body as string) as Record<string, unknown>
    const secondRenderBody = JSON.parse(renderCalls[1][1].body as string) as Record<string, unknown>
    expect(firstRenderBody.style_pack_id).toBe(pack.id)
    expect(firstRenderBody.style_pack_version).toBe(pack.version)
    expect(firstRenderBody.source_markdown).toBe('# 项目方案\n')
    expect(secondRenderBody.source_markdown).toBe(normalizedMarkdown)
  })

  it('shows a live progress state while the first conversion is still running', async () => {
    const pack = { id: 'formal-report', name: '正式报告', format_id: 'docx', version: 1, roles: {} }
    const readyJob = {
      id: 'job-1', status: 'ready', source_name: 'demo.md', style_pack_id: pack.id, style_pack_version: 1,
      suggestions: [], artifacts: [], error: null, output_name: null, draft_updated_at: null, source_hash: 'source', render_revision: 0,
    }
    const completedJob = {
      ...readyJob, status: 'completed', artifacts: ['demo.docx'], output_name: 'demo.docx', render_revision: 1, preview_ready: true,
    }
    let resolveRender!: (response: { ok: boolean; json: () => Promise<typeof completedJob> }) => void
    const pendingRender = new Promise<{ ok: boolean; json: () => Promise<typeof completedJob> }>((resolve) => {
      resolveRender = resolve
    })
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => [pack] })
      .mockResolvedValueOnce({ ok: true, json: async () => readyJob })
      .mockReturnValueOnce(pendingRender)
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)

    const file = new File(['# 项目方案\n'], 'demo.md', { type: 'text/markdown' })
    fireEvent.change(await screen.findByLabelText('选择文件'), { target: { files: [file] } })
    fireEvent.click(await screen.findByRole('button', { name: '建立本地工作副本' }))
    fireEvent.click(await screen.findByRole('button', { name: '生成' }))

    try {
      expect(screen.getByRole('status', { name: '正在转换文档' })).toHaveTextContent('正在转换')
      expect(screen.getByRole('button', { name: '正在转换' })).toBeDisabled()
    } finally {
      resolveRender({ ok: true, json: async () => completedJob })
    }

    expect(await screen.findByTestId('docx-preview')).toHaveAttribute('data-preview-url', '/api/jobs/job-1/preview?revision=1')
    await waitFor(() => expect(screen.queryByRole('status', { name: '正在转换文档' })).not.toBeInTheDocument())
  })

  it('keeps the previous preview visible under a progress veil during regeneration', async () => {
    const pack = { id: 'formal-report', name: '正式报告', format_id: 'docx', version: 1, roles: {} }
    const readyJob = {
      id: 'job-1', status: 'ready', source_name: 'demo.md', style_pack_id: pack.id, style_pack_version: 1,
      suggestions: [], artifacts: [], error: null, output_name: null, draft_updated_at: null, source_hash: 'source', render_revision: 0,
    }
    const completedJob = {
      ...readyJob, status: 'completed', artifacts: ['demo.docx'], output_name: 'demo.docx', render_revision: 1, preview_ready: true,
    }
    const regeneratedJob = { ...completedJob, render_revision: 2 }
    let resolveRender!: (response: { ok: boolean; json: () => Promise<typeof regeneratedJob> }) => void
    const pendingRender = new Promise<{ ok: boolean; json: () => Promise<typeof regeneratedJob> }>((resolve) => {
      resolveRender = resolve
    })
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => [pack] })
      .mockResolvedValueOnce({ ok: true, json: async () => readyJob })
      .mockResolvedValueOnce({ ok: true, json: async () => completedJob })
      .mockReturnValueOnce(pendingRender)
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)

    const file = new File(['# 项目方案\n'], 'demo.md', { type: 'text/markdown' })
    fireEvent.change(await screen.findByLabelText('选择文件'), { target: { files: [file] } })
    fireEvent.click(await screen.findByRole('button', { name: '建立本地工作副本' }))
    fireEvent.click(await screen.findByRole('button', { name: '生成' }))
    await waitFor(() => expect(screen.getByTestId('docx-preview')).toHaveAttribute('data-preview-url', '/api/jobs/job-1/preview?revision=1'))

    fireEvent.click(screen.getByRole('button', { name: '生成' }))
    try {
      expect(screen.getByRole('status', { name: '正在转换文档' })).toBeInTheDocument()
      expect(screen.getByTestId('docx-preview')).toHaveAttribute('data-preview-url', '/api/jobs/job-1/preview?revision=1')
    } finally {
      resolveRender({ ok: true, json: async () => regeneratedJob })
    }
    await waitFor(() => expect(screen.getByTestId('docx-preview')).toHaveAttribute('data-preview-url', '/api/jobs/job-1/preview?revision=2'))
  })

  it('expands the generated preview and exits with Escape while restoring page scrolling', async () => {
    const pack = { id: 'formal-report', name: '正式报告', format_id: 'docx', version: 1, roles: {} }
    const readyJob = {
      id: 'job-1', status: 'ready', source_name: 'demo.md', style_pack_id: pack.id, style_pack_version: 1,
      suggestions: [], artifacts: [], error: null, output_name: null, draft_updated_at: null, source_hash: 'source', render_revision: 0,
    }
    const completedJob = {
      ...readyJob, status: 'completed', artifacts: ['demo.docx'], output_name: 'demo.docx', render_revision: 1, preview_ready: true,
    }
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => [pack] })
      .mockResolvedValueOnce({ ok: true, json: async () => readyJob })
      .mockResolvedValueOnce({ ok: true, json: async () => completedJob }))
    render(<App />)

    const file = new File(['# 项目方案\n'], 'demo.md', { type: 'text/markdown' })
    fireEvent.change(await screen.findByLabelText('选择文件'), { target: { files: [file] } })
    fireEvent.click(await screen.findByRole('button', { name: '建立本地工作副本' }))
    fireEvent.click(await screen.findByRole('button', { name: '生成' }))
    const fullscreenButton = await screen.findByRole('button', { name: '全屏预览' })

    fireEvent.click(fullscreenButton)
    expect(screen.getByRole('dialog', { name: 'DOCX 预览' })).toHaveAttribute('aria-modal', 'true')
    expect(document.body.style.overflow).toBe('hidden')

    fireEvent.keyDown(window, { key: 'Escape' })

    expect(screen.getByRole('region', { name: 'DOCX 预览' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '全屏预览' })).toHaveFocus()
    expect(document.body.style.overflow).toBe('')
  })

  it('uses the DOCX fallback when the render engine could not prepare a PDF', async () => {
    const pack = { id: 'formal-report', name: '正式报告', format_id: 'docx', version: 1, roles: {} }
    const readyJob = {
      id: 'job-1', status: 'ready', source_name: 'demo.md', style_pack_id: pack.id, style_pack_version: 1,
      suggestions: [], artifacts: [], error: null, output_name: null, draft_updated_at: null, source_hash: 'source', render_revision: 0,
    }
    const completedJob = {
      ...readyJob, status: 'completed', artifacts: ['demo.docx'], output_name: 'demo.docx', render_revision: 1, preview_ready: false,
    }
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => [pack] })
      .mockResolvedValueOnce({ ok: true, json: async () => readyJob })
      .mockResolvedValueOnce({ ok: true, json: async () => completedJob })
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)

    const file = new File(['# 项目方案\n'], 'demo.md', { type: 'text/markdown' })
    fireEvent.change(await screen.findByLabelText('选择文件'), { target: { files: [file] } })
    fireEvent.click(await screen.findByRole('button', { name: '建立本地工作副本' }))
    fireEvent.click(await screen.findByRole('button', { name: '生成' }))

    await waitFor(() => expect(screen.getByTestId('docx-preview')).toBeInTheDocument())
    expect(screen.getByTestId('docx-preview')).toHaveAttribute('data-preview-url', '')
  })

  it('exposes the A-layout workspace and collapsible settings', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [
          {
            id: 'formal-report',
            name: '正式报告',
            format_id: 'docx',
            version: 1,
            roles: {
              'document-title': { role_type: 'paragraph', font: { chinese_font: '黑体', western_font: 'Times New Roman', size_pt: 22, bold: true }, paragraph: { alignment: 'center' } },
              'heading-1': { role_type: 'paragraph', font: { chinese_font: '黑体', western_font: 'Arial', size_pt: 16, bold: true }, paragraph: { first_line_indent_pt: 32 } },
              'body-paragraph': { role_type: 'paragraph', font: { chinese_font: '宋体', western_font: 'Times New Roman', size_pt: 16 }, paragraph: { first_line_indent_pt: 32 } },
            },
          },
        ],
      }),
    )
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: '打开设置' }))
    fireEvent.click(screen.getByRole('tab', { name: '正文部分' }))
    expect(await screen.findByLabelText('段落正文中文字体')).toHaveValue('宋体')
    fireEvent.click(screen.getByRole('tab', { name: '文前部分' }))
    expect(screen.getByLabelText('文档标题中文字体')).toHaveValue('黑体')
    expect(screen.getByLabelText('文档标题字号').tagName).toBe('SELECT')
    expect(screen.getByLabelText('文档标题字号')).toHaveValue('22')
    fireEvent.click(screen.getByRole('tab', { name: '正文部分' }))
    expect(screen.getByLabelText('段落正文首行缩进单位')).toHaveValue('character')
    expect(screen.getByRole('button', { name: '保存样式新版本' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '收起设置' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '生成' })).toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: '下载产物' })).not.toBeInTheDocument()
    expect(screen.getByLabelText('内容工作区')).toBeInTheDocument()
    expect(screen.queryByText('请确认结构建议')).not.toBeInTheDocument()
  })

  it('keeps generation and downloads as floating actions beside settings', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [
          {
            id: 'formal-report',
            name: '正式报告',
            format_id: 'docx',
            version: 1,
            roles: {},
          },
        ],
      }),
    )
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: '打开设置' }))
    expect(screen.getByRole('tab', { name: '样式角色' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: '页面设置' })).toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: '下载产物' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '生成' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '下载' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '收起设置' })).toBeInTheDocument()
  })

  it('opens settings as a modal drawer and restores focus after Escape', async () => {
    render(<App />)

    const trigger = await screen.findByRole('button', { name: '打开设置' })
    fireEvent.click(trigger)

    const dialog = await screen.findByRole('dialog', { name: '样式设置' })
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(screen.getByRole('button', { name: '收起设置' })).toHaveFocus()

    fireEvent.keyDown(window, { key: 'Escape' })

    await waitFor(() => expect(screen.queryByRole('dialog', { name: '样式设置' })).not.toBeInTheDocument())
    expect(screen.getByRole('button', { name: '打开设置' })).toHaveFocus()
  })

  it('closes the settings drawer from its backdrop', async () => {
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: '打开设置' }))
    await screen.findByRole('dialog', { name: '样式设置' })
    fireEvent.click(screen.getByRole('button', { name: '关闭设置' }))

    await waitFor(() => expect(screen.queryByRole('dialog', { name: '样式设置' })).not.toBeInTheDocument())
    expect(screen.getByRole('button', { name: '打开设置' })).toHaveFocus()
  })

  it('writes applied structure roles into Markdown front matter', () => {
    const source = `---
title: 项目方案
---

摘要：这里是摘要内容。

关键词：项目；实施

# 华软钢

重庆市公共资源交易中心

采购管理部

2026年9月18日
`

    const withAuthor = applyRoleToMarkdown(source, { line: 9, role: 'author', value: '# 华软钢', score: 0.9, reason: '常见姓名' })
    const withAbstract = applyRoleToMarkdown(withAuthor, { line: 5, role: 'abstract', value: '摘要：这里是摘要内容。', score: 0.9, reason: '摘要标签' })
    const withKeywords = applyRoleToMarkdown(withAbstract, { line: 7, role: 'keywords', value: '关键词：项目；实施', score: 0.9, reason: '关键词标签' })
    const withOrganization = applyRoleToMarkdown(withKeywords, { line: 11, role: 'organization', value: '重庆市公共资源交易中心', score: 0.9, reason: '单位关键词' })
    const withDepartment = applyRoleToMarkdown(withOrganization, { line: 13, role: 'department', value: '采购管理部', score: 0.9, reason: '部门关键词' })
    const result = applyRoleToMarkdown(withDepartment, { line: 15, role: 'date', value: '2026年9月18日', score: 0.9, reason: '日期' })

    expect(result).toContain('authors:\n  - 华软钢')
    expect(result).toContain('abstract: 这里是摘要内容。')
    expect(result).toContain('keywords:\n  - 项目\n  - 实施')
    expect(result).toContain('organization: 重庆市公共资源交易中心')
    expect(result).toContain('department: 采购管理部')
    expect(result).toContain('date: 2026年9月18日')
    expect(result).not.toContain('摘要：这里是摘要内容。')
    expect(result).not.toContain('# 华软钢')
  })
})
