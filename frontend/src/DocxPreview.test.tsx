import { render, waitFor } from '@testing-library/react'
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
})
