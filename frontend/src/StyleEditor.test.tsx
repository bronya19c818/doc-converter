import { fireEvent, render, screen } from '@testing-library/react'
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
  it('renders Chinese font-size labels and character-based indent controls', () => {
    render(<StyleEditor disabled={false} onSaved={vi.fn()} pack={pack} />)

    expect(screen.getByLabelText('摘要标签中文字体')).toHaveValue('黑体')
    expect(screen.getByLabelText('摘要内容中文字体')).toHaveValue('楷体')
    expect(screen.getByLabelText('关键词标签中文字体')).toHaveValue('黑体')
    expect(screen.getByLabelText('关键词内容中文字体')).toHaveValue('楷体')
    expect(screen.getByLabelText('关键词内容字号').tagName).toBe('SELECT')
    fireEvent.click(screen.getByRole('tab', { name: '正文部分' }))
    expect(screen.getByLabelText('段落正文中文字体')).toHaveValue('仿宋')
    expect(screen.getByLabelText('段落正文西文字体')).toHaveValue('Times New Roman')
    expect(screen.getByLabelText('表格正文中文字体')).toHaveValue('仿宋')
    expect(screen.getByLabelText('段落正文字号').tagName).toBe('SELECT')
    expect(screen.getByLabelText('段落正文字号')).toHaveValue('16')
    expect(screen.getAllByRole('option', { name: '三号（16 磅）' }).length).toBeGreaterThan(0)
    expect(screen.getByLabelText('段落正文首行缩进单位')).toHaveValue('character')
    expect(screen.getByLabelText('段落正文首行缩进')).toHaveValue(2)
    expect(screen.getByLabelText('段落正文行距类型')).toHaveValue('exact')
    expect(screen.getByLabelText('段落正文行距（磅）')).toHaveValue(29)
    expect(screen.getAllByRole('option', { name: '多倍' }).length).toBeGreaterThan(0)
    expect(screen.getByRole('tab', { name: '正文部分' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: '正文部分' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: '文后部分' })).toBeInTheDocument()
    expect(screen.queryByLabelText('摘要中文字体')).not.toBeInTheDocument()
    expect(screen.queryByText('页面设置')).not.toBeInTheDocument()
  })

  it('switches to independent multi-level heading roles', () => {
    render(<StyleEditor disabled={false} onSaved={vi.fn()} pack={pack} />)

    fireEvent.click(screen.getByRole('tab', { name: '正文部分' }))

    expect(screen.getByLabelText('一级标题中文字体')).toBeInTheDocument()
    expect(screen.getByLabelText('二级标题中文字体')).toBeInTheDocument()
    expect(screen.getByLabelText('三级标题中文字体')).toBeInTheDocument()
    expect(screen.getByLabelText('六级标题中文字体')).toBeInTheDocument()
    expect(screen.queryByLabelText('作者中文字体')).not.toBeInTheDocument()
  })

  it('can isolate the page settings tab content', () => {
    render(<StyleEditor disabled={false} onSaved={vi.fn()} pack={pack} section="page" />)

    expect(screen.getByText('页面设置')).toBeInTheDocument()
    expect(screen.queryByLabelText('段落正文中文字体')).not.toBeInTheDocument()
    expect(screen.getByLabelText('页面宽度（厘米）')).toHaveValue(21)
    expect(screen.getByLabelText('页面高度（厘米）')).toHaveValue(29.7)
  })

  it('keeps character indentation stable when the font size changes', () => {
    render(<StyleEditor disabled={false} onSaved={vi.fn()} pack={pack} />)

    fireEvent.click(screen.getByRole('tab', { name: '正文部分' }))

    fireEvent.change(screen.getByLabelText('段落正文字号'), { target: { value: '22' } })

    expect(screen.getByLabelText('段落正文首行缩进单位')).toHaveValue('character')
    expect(screen.getByLabelText('段落正文首行缩进')).toHaveValue(2)
  })

  it('converts indentation units and labels multiple line spacing explicitly', () => {
    render(<StyleEditor disabled={false} onSaved={vi.fn()} pack={pack} />)

    fireEvent.click(screen.getByRole('tab', { name: '正文部分' }))

    fireEvent.change(screen.getByLabelText('段落正文首行缩进单位'), { target: { value: 'cm' } })
    expect(screen.getByLabelText('段落正文首行缩进')).toHaveValue(1.13)

    fireEvent.change(screen.getByLabelText('段落正文行距类型'), { target: { value: 'multiple' } })
    expect(screen.getByLabelText('段落正文行距（倍数）')).toHaveValue(1.5)
  })
})
