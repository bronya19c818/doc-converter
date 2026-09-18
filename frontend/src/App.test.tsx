import { fireEvent, render, screen } from '@testing-library/react'
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
    expect(screen.getByRole('heading', { name: 'DOCX 预览' })).toBeInTheDocument()
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
    expect(await screen.findByLabelText('段落正文中文字体')).toHaveValue('宋体')
    expect(screen.getByLabelText('文档标题中文字体')).toHaveValue('黑体')
    expect(screen.getByLabelText('文档标题字号').tagName).toBe('SELECT')
    expect(screen.getByLabelText('文档标题字号')).toHaveValue('22')
    expect(screen.getByLabelText('段落正文首行缩进单位')).toHaveValue('character')
    expect(screen.getByRole('button', { name: '保存样式新版本' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '收起设置' })).toBeInTheDocument()
    expect(screen.getByLabelText('Markdown 工作副本')).toBeInTheDocument()
    expect(screen.queryByText('请确认结构建议')).not.toBeInTheDocument()
  })

  it('opens floating settings and switches between tabs', async () => {
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
    fireEvent.click(screen.getByRole('tab', { name: '下载产物' }))
    expect(screen.getByRole('heading', { name: '下载产物' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '收起设置' })).toBeInTheDocument()
  })
})
