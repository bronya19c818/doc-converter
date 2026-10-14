import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { App } from './App'

vi.mock('./DocxPreview', () => ({
  preloadDocxPreview: vi.fn().mockResolvedValue(undefined),
  DocxPreview: ({ documentUrl, previewUrl }: { documentUrl: string; previewUrl?: string }) => (
    <div data-preview-url={previewUrl ?? ''} data-testid="docx-preview">{documentUrl}</div>
  ),
}))
const pack = { id: 'formal', name: '正式报告', format_id: 'docx', version: 1, roles: {} }
const otherPack = { ...pack, id: 'business', name: '商务报告' }
const ready = {
  id: 'job-1', status: 'ready', conversion_mode: 'round-trip', source_name: '方案.md',
  source_format: 'markdown', source_original_name: '方案.md', import_warnings: [],
  style_pack_id: 'formal', style_pack_version: 1, suggestions: [], artifacts: [], error: null,
  output_name: null, source_hash: 'original', render_revision: 0, preview_ready: false,
}
const completed = {
  ...ready, status: 'completed', output_name: '方案.docx', render_revision: 1, preview_ready: true,
  artifacts: ['方案.docx', 'normalization-report.json', 'document.normalized.md'],
}
const response = (value: unknown) => ({ ok: true, json: async () => value })
async function selectFile(filename = '方案.md') {
  const file = new File(['# 方案\n\n正文。'], filename)
  const readText = vi.fn().mockRejectedValue(new Error('frontend must not read source text'))
  Object.defineProperty(file, 'text', { value: readText })
  fireEvent.change(await screen.findByLabelText('选择文件'), { target: { files: [file] } })
  return readText
}
async function clickConvert() {
  await waitFor(() => expect(screen.getByRole('button', { name: '开始转换' })).toBeEnabled())
  fireEvent.click(screen.getByRole('button', { name: '开始转换' }))
}
async function setupCompleted() {
  const fetchMock = vi.fn().mockResolvedValueOnce(response([pack, otherPack])).mockResolvedValueOnce(response(ready)).mockResolvedValueOnce(response(completed))
  vi.stubGlobal('fetch', fetchMock)
  render(<App />)
  await selectFile()
  await clickConvert()
  await screen.findByTestId('docx-preview')
  return fetchMock
}
describe('one-click converter', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response([pack, otherPack])))
  })
  it('has conversion and preview without an editor or confirmation controls', async () => {
    render(<App />)
    expect(await screen.findByRole('heading', { name: 'Doc Converter' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '开始转换' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '下载' })).toBeDisabled()
    expect(screen.queryByLabelText('内容工作区')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('结构建议')).not.toBeInTheDocument()
    expect(screen.queryByText(/工作副本|应用建议|未保存修改/)).not.toBeInTheDocument()
  })
  it.each([
    ['方案.md', 'round-trip', 'normalize-and-render'],
    ['方案.markdown', 'round-trip', 'normalize-and-render'],
    ['合同.doc', 'round-trip', 'normalize-and-render'],
    ['合同.DOCX', 'docx-direct', 'normalize-docx-direct'],
  ])('converts %s in one click without source editing calls', async (filename, mode, endpoint) => {
    const fetchMock = vi.fn().mockResolvedValueOnce(response([pack])).mockResolvedValueOnce(response(ready)).mockResolvedValueOnce(response(completed))
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)
    const readText = await selectFile(filename)
    await clickConvert()
    await screen.findByTestId('docx-preview')
    expect(readText).not.toHaveBeenCalled()
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect((fetchMock.mock.calls[1][1].body as FormData).get('conversion_mode')).toBe(mode)
    expect(fetchMock.mock.calls[2][0]).toBe(`/api/jobs/job-1/${endpoint}`)
    expect(JSON.parse(fetchMock.mock.calls[2][1].body)).toEqual({ style_pack_id: pack.id, style_pack_version: 1 })
    fireEvent.click(screen.getByRole('button', { name: '下载' }))
    expect(screen.getByRole('link', { name: '下载 DOCX' })).toHaveAttribute('href', '/api/jobs/job-1/artifacts/%E6%96%B9%E6%A1%88.docx?revision=1')
    expect(screen.getByRole('link', { name: '下载处理报告' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /normalized.md/ })).not.toBeInTheDocument()
  })
  it('regenerates the same immutable job using the current style selection', async () => {
    const fetchMock = await setupCompleted()
    fireEvent.click(screen.getByRole('button', { name: '打开设置' }))
    fireEvent.change(screen.getByLabelText('DOCX 样式组合'), { target: { value: 'business' } })
    fireEvent.click(screen.getByRole('button', { name: '收起设置' }))
    fetchMock.mockResolvedValueOnce(response({ ...completed, render_revision: 2 }))
    await clickConvert()
    await waitFor(() => expect(screen.getByTestId('docx-preview')).toHaveTextContent('revision=2'))
    expect(fetchMock).toHaveBeenCalledTimes(4)
    expect(JSON.parse(fetchMock.mock.calls[3][1].body)).toEqual({ style_pack_id: 'business', style_pack_version: 1 })
  })
  it('locks source selection during upload and shows conversion progress', async () => {
    let resolveUpload!: (value: unknown) => void
    const fetchMock = vi.fn().mockResolvedValueOnce(response([pack])).mockReturnValueOnce(new Promise((resolve) => { resolveUpload = resolve })).mockResolvedValueOnce(response(completed))
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)
    await selectFile()
    await clickConvert()
    expect(screen.getByLabelText('选择文件')).toBeDisabled()
    expect(screen.getByRole('button', { name: '正在转换' })).toBeDisabled()
    expect(screen.getByRole('status', { name: '正在转换文档' })).toBeInTheDocument()
    resolveUpload(response(ready))
    await screen.findByTestId('docx-preview')
  })
  it.each(['upload', 'render'])('reports %s failure and supports retry', async (phase) => {
    const failure = { ok: false, json: async () => ({ detail: '处理失败' }) }
    const fetchMock = vi.fn().mockResolvedValueOnce(response([pack]))
    if (phase === 'upload') fetchMock.mockResolvedValueOnce(failure).mockResolvedValueOnce(response(ready))
    else fetchMock.mockResolvedValueOnce(response(ready)).mockResolvedValueOnce(failure)
    fetchMock.mockResolvedValueOnce(response(completed))
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)
    await selectFile()
    await clickConvert()
    expect(await screen.findByRole('alert')).toHaveTextContent('处理失败')
    await clickConvert()
    await screen.findByTestId('docx-preview')
    expect(fetchMock.mock.calls.filter(([url]) => url === '/api/jobs')).toHaveLength(phase === 'upload' ? 2 : 1)
  })
  it('clears previous results when selecting a new file', async () => {
    const fetchMock = await setupCompleted()
    await selectFile('新方案.md')
    expect(screen.queryByTestId('docx-preview')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '下载' })).toBeDisabled()
    fetchMock.mockResolvedValueOnce(response({ ...ready, id: 'job-2' })).mockResolvedValueOnce(response({ ...completed, id: 'job-2' }))
    await clickConvert()
    await waitFor(() => expect(screen.getByTestId('docx-preview')).toHaveTextContent('job-2'))
  })
  it('keeps previous preview visible during regeneration and disables downloads', async () => {
    const fetchMock = await setupCompleted()
    let resolveRender!: (value: unknown) => void
    fetchMock.mockReturnValueOnce(new Promise((resolve) => { resolveRender = resolve }))
    await clickConvert()
    expect(screen.getByTestId('docx-preview')).toBeInTheDocument()
    expect(screen.getByRole('status', { name: '正在转换文档' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '下载' })).toBeDisabled()
    resolveRender(response({ ...completed, render_revision: 2 }))
    await waitFor(() => expect(screen.getByTestId('docx-preview')).toHaveTextContent('revision=2'))
  })
  it('preserves preview fullscreen and restores focus and scrolling on Escape', async () => {
    await setupCompleted()
    fireEvent.click(screen.getByRole('button', { name: '全屏预览' }))
    expect(screen.getByRole('dialog', { name: 'DOCX 预览' })).toBeInTheDocument()
    expect(document.body.style.overflow).toBe('hidden')
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(document.body.style.overflow).toBe('')
    expect(screen.getByRole('button', { name: '全屏预览' })).toHaveFocus()
  })
  it('preserves settings dismissal and supported page settings', async () => {
    render(<App />)
    const trigger = screen.getByRole('button', { name: '打开设置' })
    fireEvent.click(trigger)
    expect(screen.getByRole('tab', { name: '页面设置' })).toBeInTheDocument()
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(trigger).toHaveFocus()
    await selectFile('合同.docx')
    fireEvent.click(trigger)
    expect(screen.queryByRole('tab', { name: '页面设置' })).not.toBeInTheDocument()
  })
})
