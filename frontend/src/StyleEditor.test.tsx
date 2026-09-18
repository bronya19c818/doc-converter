import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { StyleEditor } from './StyleEditor'
import { StylePack } from './api'

const pack: StylePack = {
  id: 'formal',
  name: '正式报告',
  format_id: 'docx',
  version: 1,
  roles: {
    'document-title': { role_type: 'paragraph', font: { chinese_font: '黑体', western_font: 'Arial', size_pt: 22, bold: true, italic: false }, paragraph: { alignment: 'center' } },
    'body-paragraph': { role_type: 'paragraph', font: { chinese_font: '仿宋', western_font: 'Times New Roman', size_pt: 16, bold: false, italic: false }, paragraph: { first_line_indent_pt: 32 } },
    'body-table': { role_type: 'paragraph', font: { chinese_font: '仿宋', western_font: 'Times New Roman', size_pt: 14 }, paragraph: { first_line_indent_pt: 0 } },
  },
}

describe('StyleEditor', () => {
  it('renders independent Chinese and western font controls for body roles', () => {
    render(<StyleEditor disabled={false} onSaved={vi.fn()} pack={pack} />)

    expect(screen.getByLabelText('段落正文中文字体')).toHaveValue('仿宋')
    expect(screen.getByLabelText('段落正文西文字体')).toHaveValue('Times New Roman')
    expect(screen.getByLabelText('表格正文中文字体')).toHaveValue('仿宋')
    expect(screen.getByLabelText('段落正文首行缩进（磅）')).toHaveValue(32)
    expect(screen.getByText('页面设置')).toBeInTheDocument()
  })
})
