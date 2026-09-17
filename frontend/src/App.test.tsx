import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { App } from './App'

describe('App', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [],
      }),
    )
  })

  it('explains the local no-AI conversion workflow', async () => {
    render(<App />)

    expect(screen.getByRole('heading', { name: 'Doc Converter' })).toBeInTheDocument()
    expect(screen.getByText('本地转换，不调用 AI，也不上传文档。')).toBeInTheDocument()
    expect(await screen.findByLabelText('选择 Markdown 文件')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '文档预览' })).toBeInTheDocument()
  })

  it('exposes editable semantic DOCX style fields for the selected pack', async () => {
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
              'document-title': { font_name: '黑体', font_size_pt: 22 },
              'heading-1': { font_name: '黑体', font_size_pt: 16 },
              body: { font_name: '宋体', font_size_pt: 12, first_line_indent_pt: 24 },
            },
          },
        ],
      }),
    )
    render(<App />)

    expect(await screen.findByLabelText('正文文字字号')).toHaveValue(12)
    expect(screen.getByLabelText('文档标题字体')).toHaveValue('黑体')
    expect(screen.getByRole('button', { name: '保存样式新版本' })).toBeInTheDocument()
  })
})
