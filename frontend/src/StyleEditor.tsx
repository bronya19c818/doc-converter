import { FormEvent, useEffect, useState } from 'react'

import { reviseStylePack, StylePack } from './api'

type StyleEditorProps = {
  disabled: boolean
  onSaved: (pack: StylePack) => void
  pack: StylePack
}

type EditableStyles = {
  bodyFont: string
  bodyIndent: number
  bodySize: number
  headingFont: string
  headingSize: number
  titleFont: string
  titleSize: number
}

export function StyleEditor({ disabled, onSaved, pack }: StyleEditorProps) {
  const [values, setValues] = useState<EditableStyles>(() => editableStylesFor(pack))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setValues(editableStylesFor(pack))
    setError(null)
  }, [pack])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSaving(true)
    setError(null)
    try {
      const saved = await reviseStylePack(pack, {
        name: pack.name,
        roles: {
          ...pack.roles,
          'document-title': {
            ...pack.roles['document-title'],
            font_name: values.titleFont,
            font_size_pt: values.titleSize,
          },
          'heading-1': {
            ...pack.roles['heading-1'],
            font_name: values.headingFont,
            font_size_pt: values.headingSize,
          },
          body: {
            ...pack.roles.body,
            font_name: values.bodyFont,
            font_size_pt: values.bodySize,
            first_line_indent_pt: values.bodyIndent,
          },
        },
      })
      onSaved(saved)
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : '样式保存失败。')
    } finally {
      setSaving(false)
    }
  }

  const isDisabled = disabled || saving
  return (
    <form className="style-editor" onSubmit={handleSubmit}>
      <div className="style-editor-heading">
        <h3>编辑样式属性</h3>
        <span>下次保存为 v{pack.version + 1}</span>
      </div>
      <div className="style-grid">
        <label>文档标题字体
          <input aria-label="文档标题字体" disabled={isDisabled} onChange={(event) => setValues({ ...values, titleFont: event.target.value })} value={values.titleFont} />
        </label>
        <label>文档标题字号
          <input disabled={isDisabled} min="8" onChange={(event) => setValues({ ...values, titleSize: Number(event.target.value) })} type="number" value={values.titleSize} />
        </label>
        <label>一级标题字体
          <input disabled={isDisabled} onChange={(event) => setValues({ ...values, headingFont: event.target.value })} value={values.headingFont} />
        </label>
        <label>一级标题字号
          <input disabled={isDisabled} min="8" onChange={(event) => setValues({ ...values, headingSize: Number(event.target.value) })} type="number" value={values.headingSize} />
        </label>
        <label>正文字体
          <input disabled={isDisabled} onChange={(event) => setValues({ ...values, bodyFont: event.target.value })} value={values.bodyFont} />
        </label>
        <label>正文文字字号
          <input aria-label="正文文字字号" disabled={isDisabled} min="8" onChange={(event) => setValues({ ...values, bodySize: Number(event.target.value) })} type="number" value={values.bodySize} />
        </label>
        <label>正文首行缩进（磅）
          <input disabled={isDisabled} min="0" onChange={(event) => setValues({ ...values, bodyIndent: Number(event.target.value) })} type="number" value={values.bodyIndent} />
        </label>
      </div>
      <button className="secondary-action" disabled={isDisabled} type="submit">保存样式新版本</button>
      {error ? <p className="error-message" role="alert">{error}</p> : null}
    </form>
  )
}

function editableStylesFor(pack: StylePack): EditableStyles {
  return {
    titleFont: stringValue(pack.roles['document-title']?.font_name, '黑体'),
    titleSize: numberValue(pack.roles['document-title']?.font_size_pt, 22),
    headingFont: stringValue(pack.roles['heading-1']?.font_name, '黑体'),
    headingSize: numberValue(pack.roles['heading-1']?.font_size_pt, 16),
    bodyFont: stringValue(pack.roles.body?.font_name, '宋体'),
    bodySize: numberValue(pack.roles.body?.font_size_pt, 12),
    bodyIndent: numberValue(pack.roles.body?.first_line_indent_pt, 24),
  }
}

function stringValue(value: unknown, fallback: string): string {
  return typeof value === 'string' ? value : fallback
}

function numberValue(value: unknown, fallback: number): number {
  return typeof value === 'number' ? value : fallback
}
