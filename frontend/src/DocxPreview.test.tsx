import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { DocxPreview } from './DocxPreview'

const renderAsync = vi.fn().mockResolvedValue(undefined)

vi.mock('docx-preview', () => ({ renderAsync }))

describe('DocxPreview', () => {
  beforeEach(() => {
    renderAsync.mockClear()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, blob: async () => new Blob(['docx']) }))
  })

  it('renders with a wrapped A4-friendly paged document', async () => {
    render(<DocxPreview documentUrl="/api/jobs/demo/artifacts/demo.docx" />)

    await waitFor(() => expect(renderAsync).toHaveBeenCalled())
    expect(renderAsync.mock.calls[0][3]).toMatchObject({
      breakPages: true,
      inWrapper: true,
      renderHeaders: true,
      renderFooters: true,
      ignoreLastRenderedPageBreak: false,
    })
  })

  it('loads a pre-rendered PDF directly and eagerly without buffering a blob', () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    const preview = '/api/jobs/demo/preview?revision=1'

    render(
      <DocxPreview
        documentUrl="/api/jobs/demo/artifacts/demo.docx"
        previewUrl={preview}
      />,
    )

    const iframe = screen.getByTitle('DOCX PDF 预览')
    expect(iframe).toHaveAttribute('src', preview)
    expect(iframe).toHaveAttribute('loading', 'eager')
    expect(screen.getByRole('status')).toHaveTextContent('正在载入 PDF 预览')
    expect(fetchMock).not.toHaveBeenCalled()

    fireEvent.load(iframe)
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    expect(renderAsync).not.toHaveBeenCalled()
  })

  it('reloads the PDF when the render revision changes', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    const { rerender } = render(
      <DocxPreview
        documentUrl="/api/jobs/demo/artifacts/demo.docx?revision=1"
        previewUrl="/api/jobs/demo/preview?revision=1"
      />,
    )
    expect(screen.getByTitle('DOCX PDF 预览')).toHaveAttribute('src', '/api/jobs/demo/preview?revision=1')

    rerender(
      <DocxPreview
        documentUrl="/api/jobs/demo/artifacts/demo.docx?revision=2"
        previewUrl="/api/jobs/demo/preview?revision=2"
      />,
    )
    expect(screen.getByTitle('DOCX PDF 预览')).toHaveAttribute('src', '/api/jobs/demo/preview?revision=2')
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
