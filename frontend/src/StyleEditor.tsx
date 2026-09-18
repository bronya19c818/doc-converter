import { FormEvent, useEffect, useState } from 'react'

import { reviseStylePack, StylePack } from './api'

type StyleEditorProps = {
  disabled: boolean
  onSaved: (pack: StylePack) => void
  pack: StylePack
}

type RoleValue = {
  role_type: 'paragraph' | 'character' | 'page'
  font?: Record<string, unknown>
  paragraph?: Record<string, unknown>
  page?: Record<string, unknown>
}

type RoleMap = Record<string, RoleValue>

const ROLE_LABELS: Record<string, string> = {
  'document-title': '文档标题',
  'document-subtitle': '副标题',
  'organization-department': '单位/部门',
  author: '作者',
  date: '日期',
  'heading-1': '一级标题',
  'body-paragraph': '段落正文',
  'body-table': '表格正文',
  point: '要点',
  'table-caption': '表格题',
  'figure-caption': '图表题',
  footer: '页脚',
}

const GROUPS: Array<{ title: string; roles: string[] }> = [
  { title: '标题区角色', roles: ['document-title', 'document-subtitle', 'organization-department', 'author', 'date'] },
  { title: '一级标题', roles: ['heading-1'] },
  { title: '段落正文', roles: ['body-paragraph'] },
  { title: '表格正文', roles: ['body-table'] },
  { title: '要点', roles: ['point'] },
  { title: '图表题', roles: ['table-caption', 'figure-caption'] },
  { title: '页脚', roles: ['footer'] },
]

export function StyleEditor({ disabled, onSaved, pack }: StyleEditorProps) {
  const [roles, setRoles] = useState<RoleMap>(() => editableRolesFor(pack))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setRoles(editableRolesFor(pack))
    setError(null)
  }, [pack])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSaving(true)
    setError(null)
    try {
      const saved = await reviseStylePack(pack, { name: pack.name, roles })
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
      {GROUPS.map((group) => (
        <fieldset className="style-group" key={group.title}>
          <legend>{group.title}</legend>
          <div className="role-grid">
            {group.roles.map((roleKey) => (
              <RoleEditor
                disabled={isDisabled}
                key={roleKey}
                onChange={(field, value) => updateRole(setRoles, roleKey, field, value)}
                roleKey={roleKey}
                role={roles[roleKey]}
              />
            ))}
          </div>
        </fieldset>
      ))}
      <fieldset className="style-group page-settings">
        <legend>页面设置</legend>
        <div className="style-grid">
          {(['margin_top_cm', 'margin_bottom_cm', 'margin_left_cm', 'margin_right_cm'] as const).map((key) => (
            <label key={key}>
              {pageLabel(key)}
              <input
                aria-label={pageLabel(key)}
                disabled={isDisabled}
                min="0"
                onChange={(event) => updateRole(setRoles, 'page', ['page', key], Number(event.target.value))}
                step="0.1"
                type="number"
                value={numberValue(roles.page?.page?.[key], 2.8)}
              />
            </label>
          ))}
        </div>
      </fieldset>
      <button className="secondary-action" disabled={isDisabled} type="submit">保存样式新版本</button>
      {error ? <p className="error-message" role="alert">{error}</p> : null}
    </form>
  )
}

function RoleEditor({
  disabled,
  onChange,
  roleKey,
  role,
}: {
  disabled: boolean
  onChange: (field: string | string[], value: unknown) => void
  roleKey: string
  role: RoleValue
}) {
  const label = ROLE_LABELS[roleKey] ?? roleKey
  const font = role.font ?? {}
  const paragraph = role.paragraph ?? {}
  const characterOnly = role.role_type === 'character'
  return (
    <article className="role-card">
      <h4>{label}</h4>
      <div className="style-grid">
        <label>
          {label}中文字体
          <input aria-label={`${label}中文字体`} disabled={disabled} onChange={(event) => onChange(['font', 'chinese_font'], event.target.value)} value={stringValue(font.chinese_font, '仿宋')} />
        </label>
        <label>
          {label}西文字体
          <input aria-label={`${label}西文字体`} disabled={disabled} onChange={(event) => onChange(['font', 'western_font'], event.target.value)} value={stringValue(font.western_font, 'Times New Roman')} />
        </label>
        <label>
          {label}字号
          <input aria-label={`${label}字号`} disabled={disabled} min="1" onChange={(event) => onChange(['font', 'size_pt'], Number(event.target.value))} type="number" value={numberValue(font.size_pt, 16)} />
        </label>
        <label className="checkbox-label">
          <input aria-label={`${label}粗体`} checked={booleanValue(font.bold)} disabled={disabled} onChange={(event) => onChange(['font', 'bold'], event.target.checked)} type="checkbox" />
          粗体
        </label>
        <label className="checkbox-label">
          <input aria-label={`${label}斜体`} checked={booleanValue(font.italic)} disabled={disabled} onChange={(event) => onChange(['font', 'italic'], event.target.checked)} type="checkbox" />
          斜体
        </label>
        {!characterOnly ? (
          <>
            <label>
              {label}对齐
              <select aria-label={`${label}对齐`} disabled={disabled} onChange={(event) => onChange(['paragraph', 'alignment'], event.target.value)} value={stringValue(paragraph.alignment, 'left')}>
                <option value="left">左对齐</option>
                <option value="center">居中</option>
                <option value="right">右对齐</option>
                <option value="justify">两端对齐</option>
              </select>
            </label>
            {(['first_line_indent_pt', 'left_indent_pt', 'right_indent_pt', 'line_spacing_pt', 'space_before_pt', 'space_after_pt'] as const).map((key) => (
              <label key={key}>
                {paragraphLabel(label, key)}
                <input
                  aria-label={paragraphLabel(label, key)}
                  disabled={disabled}
                  min="0"
                  onChange={(event) => onChange(['paragraph', key], Number(event.target.value))}
                  step="0.5"
                  type="number"
                  value={numberValue(paragraph[key], key === 'line_spacing_pt' ? 29 : 0)}
                />
              </label>
            ))}
          </>
        ) : null}
      </div>
    </article>
  )
}

function editableRolesFor(pack: StylePack): RoleMap {
  const roles: RoleMap = {}
  Object.entries(pack.roles).forEach(([key, value]) => {
    roles[key] = {
      role_type: roleType(value.role_type),
      font: { ...(value.font as Record<string, unknown> | undefined) },
      paragraph: { ...(value.paragraph as Record<string, unknown> | undefined) },
      page: { ...(value.page as Record<string, unknown> | undefined) },
    }
  })
  const defaults = defaultRoleMap()
  if (roles.body && !roles['body-paragraph']) roles['body-paragraph'] = roles.body
  Object.entries(defaults).forEach(([key, value]) => {
    roles[key] = {
      ...value,
      ...roles[key],
      font: { ...value.font, ...roles[key]?.font },
      paragraph: { ...value.paragraph, ...roles[key]?.paragraph },
      page: { ...value.page, ...roles[key]?.page },
    }
  })
  return roles
}

function defaultRoleMap(): RoleMap {
  const paragraph = { alignment: 'left', first_line_indent_pt: 0, left_indent_pt: 0, right_indent_pt: 0, line_spacing_pt: 29, space_before_pt: 0, space_after_pt: 0 }
  const font = { chinese_font: '仿宋', western_font: 'Times New Roman', size_pt: 16, bold: false, italic: false }
  const roles: RoleMap = {}
  Object.keys(ROLE_LABELS).forEach((key) => {
    roles[key] = { role_type: key === 'point' ? 'character' : 'paragraph', font: { ...font }, paragraph: { ...paragraph } }
  })
  roles['document-title'] = { role_type: 'paragraph', font: { ...font, chinese_font: '宋体', size_pt: 22, bold: true }, paragraph: { ...paragraph, alignment: 'center' } }
  roles['document-subtitle'] = { role_type: 'paragraph', font: { ...font, chinese_font: '楷体', bold: true }, paragraph: { ...paragraph, alignment: 'center' } }
  roles['organization-department'] = { ...roles['document-subtitle'] }
  roles.author = { ...roles['document-subtitle'] }
  roles.date = { ...roles['document-subtitle'] }
  roles['heading-1'] = { role_type: 'paragraph', font: { ...font, chinese_font: '黑体', bold: true }, paragraph: { ...paragraph, first_line_indent_pt: 32 } }
  roles['body-table'] = { role_type: 'paragraph', font: { ...font, size_pt: 14 }, paragraph: { ...paragraph, first_line_indent_pt: 0 } }
  roles.footer = { role_type: 'paragraph', font: { ...font, chinese_font: '宋体', size_pt: 14 }, paragraph: { ...paragraph, alignment: 'center' } }
  roles.page = { role_type: 'page', page: { margin_top_cm: 3.5, margin_bottom_cm: 3.5, margin_left_cm: 2.8, margin_right_cm: 2.8 } }
  return roles
}

function updateRole(setRoles: React.Dispatch<React.SetStateAction<RoleMap>>, roleKey: string, field: string | string[], value: unknown) {
  const path = Array.isArray(field) ? field : [field]
  setRoles((current) => {
    const next: RoleMap = { ...current, [roleKey]: { ...current[roleKey] } }
    let cursor: Record<string, unknown> = next[roleKey] as unknown as Record<string, unknown>
    path.slice(0, -1).forEach((part) => {
      cursor[part] = { ...(cursor[part] as Record<string, unknown> | undefined) }
      cursor = cursor[part] as Record<string, unknown>
    })
    cursor[path[path.length - 1]] = value
    return next
  })
}

function roleType(value: unknown): RoleValue['role_type'] {
  return value === 'character' || value === 'page' ? value : 'paragraph'
}

function stringValue(value: unknown, fallback: string): string {
  return typeof value === 'string' ? value : fallback
}

function numberValue(value: unknown, fallback: number): number {
  return typeof value === 'number' ? value : fallback
}

function booleanValue(value: unknown): boolean {
  return value === true
}

function paragraphLabel(label: string, key: string): string {
  const names: Record<string, string> = {
    first_line_indent_pt: '首行缩进（磅）',
    left_indent_pt: '左缩进（磅）',
    right_indent_pt: '右缩进（磅）',
    line_spacing_pt: '行距（磅）',
    space_before_pt: '段前（磅）',
    space_after_pt: '段后（磅）',
  }
  return `${label}${names[key] ?? key}`
}

function pageLabel(key: string): string {
  const names: Record<string, string> = {
    margin_top_cm: '上边距（厘米）',
    margin_bottom_cm: '下边距（厘米）',
    margin_left_cm: '左边距（厘米）',
    margin_right_cm: '右边距（厘米）',
  }
  return names[key]
}
