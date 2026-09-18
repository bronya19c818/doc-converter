import { FormEvent, useEffect, useState } from 'react'

import { reviseStylePack, StylePack } from './api'

type StyleEditorProps = {
  disabled: boolean
  onSaved: (pack: StylePack) => void
  pack: StylePack
  section?: 'roles' | 'page'
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
  abstract: '摘要',
  'abstract-label': '摘要标签',
  keywords: '关键词',
  'keywords-label': '关键词标签',
  'heading-1': '一级标题',
  'body-paragraph': '段落正文',
  'body-table': '表格正文',
  point: '要点',
  'table-caption': '表格题',
  'figure-caption': '图表题',
  footer: '页脚',
}

const GROUPS: Array<{ title: string; roles: string[] }> = [
  { title: '标题区角色', roles: ['document-title', 'document-subtitle', 'organization-department', 'author', 'date', 'abstract-label', 'abstract', 'keywords-label', 'keywords'] },
  { title: '一级标题', roles: ['heading-1'] },
  { title: '段落正文', roles: ['body-paragraph'] },
  { title: '表格正文', roles: ['body-table'] },
  { title: '要点', roles: ['point'] },
  { title: '图表题', roles: ['table-caption', 'figure-caption'] },
  { title: '页脚', roles: ['footer'] },
]

type IndentUnit = 'character' | 'pt' | 'cm'
type LineSpacingRule = 'maximum' | 'minimum' | 'exact' | 'multiple'

const FONT_SIZE_PRESETS = [
  { label: '初号', pt: 42 },
  { label: '小初', pt: 36 },
  { label: '一号', pt: 26 },
  { label: '小一', pt: 24 },
  { label: '二号', pt: 22 },
  { label: '小二', pt: 18 },
  { label: '三号', pt: 16 },
  { label: '小三', pt: 15 },
  { label: '四号', pt: 14 },
  { label: '小四', pt: 12 },
  { label: '五号', pt: 10.5 },
  { label: '小五', pt: 9 },
  { label: '六号', pt: 7.5 },
  { label: '小六', pt: 6.5 },
  { label: '七号', pt: 5.5 },
  { label: '八号', pt: 5 },
]

const INDENT_UNITS: Array<{ value: IndentUnit; label: string }> = [
  { value: 'character', label: '字符' },
  { value: 'pt', label: '磅' },
  { value: 'cm', label: '厘米' },
]

const LINE_SPACING_RULES: Array<{ value: LineSpacingRule; label: string }> = [
  { value: 'maximum', label: '最大值' },
  { value: 'minimum', label: '最小值' },
  { value: 'exact', label: '固定值' },
  { value: 'multiple', label: '多倍' },
]

const INDENT_KEYS = ['first_line_indent_pt', 'left_indent_pt', 'right_indent_pt'] as const

export function StyleEditor({ disabled, onSaved, pack, section = 'roles' }: StyleEditorProps) {
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
      {section === 'roles' ? GROUPS.map((group) => (
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
      )) : null}
      {section === 'page' ? <fieldset className="style-group page-settings">
        <legend>页面设置</legend>
        <div className="style-grid">
          {(['page_width_cm', 'page_height_cm', 'margin_top_cm', 'margin_bottom_cm', 'margin_left_cm', 'margin_right_cm'] as const).map((key) => (
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
      </fieldset> : null}
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
  const fontSize = numberValue(font.size_pt, 16)
  const lineSpacingRule = lineSpacingRuleValue(paragraph.line_spacing_rule)
  const lineSpacingValue = lineSpacingRule === 'multiple'
    ? numberValue(paragraph.line_spacing_multiple, 1.5)
    : numberValue(paragraph.line_spacing_pt, 29)
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
          <select
            aria-label={`${label}字号`}
            disabled={disabled}
            onChange={(event) => {
              const nextSize = Number(event.target.value)
              onChange(['font', 'size_pt'], nextSize)
              INDENT_KEYS.forEach((key) => {
                const unitKey = indentUnitKey(key)
                if (indentUnitValue(paragraph[unitKey]) === 'character') {
                  const characters = indentDisplayValue(paragraph[key], 'character', fontSize)
                  onChange(['paragraph', key], pointsFromIndent(characters, 'character', nextSize))
                }
              })
            }}
            value={String(fontSize)}
          >
            {fontSizeOptions(fontSize).map((option) => (
              <option key={option.pt} value={String(option.pt)}>{option.label}（{formatNumber(option.pt)} 磅）</option>
            ))}
          </select>
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
            {INDENT_KEYS.map((key) => {
              const unitKey = indentUnitKey(key)
              const unit = indentUnitValue(paragraph[unitKey])
              return (
                <div className="measurement-control" key={key}>
                  <label>
                    {paragraphLabel(label, key)}
                    <input
                      aria-label={paragraphLabel(label, key)}
                      disabled={disabled}
                      min="0"
                      onChange={(event) => onChange(['paragraph', key], pointsFromIndent(Number(event.target.value), unit, fontSize))}
                      step={indentStep(unit)}
                      type="number"
                      value={indentDisplayValue(paragraph[key], unit, fontSize)}
                    />
                  </label>
                  <label>
                    单位
                    <select
                      aria-label={indentUnitLabel(label, key)}
                      className="unit-select"
                      disabled={disabled}
                      onChange={(event) => onChange(['paragraph', unitKey], event.target.value)}
                      value={unit}
                    >
                      {INDENT_UNITS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                    </select>
                  </label>
                </div>
              )
            })}
            <label>
              {label}行距类型
              <select
                aria-label={`${label}行距类型`}
                disabled={disabled}
                onChange={(event) => {
                  const nextRule = event.target.value as LineSpacingRule
                  onChange(['paragraph', 'line_spacing_rule'], nextRule)
                  if (nextRule === 'multiple' && typeof paragraph.line_spacing_multiple !== 'number') {
                    onChange(['paragraph', 'line_spacing_multiple'], 1.5)
                  }
                  if (nextRule !== 'multiple' && typeof paragraph.line_spacing_pt !== 'number') {
                    onChange(['paragraph', 'line_spacing_pt'], 29)
                  }
                }}
                value={lineSpacingRule}
              >
                {LINE_SPACING_RULES.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
            </label>
            <label>
              {lineSpacingLabel(label, lineSpacingRule)}
              <input
                aria-label={lineSpacingLabel(label, lineSpacingRule)}
                disabled={disabled}
                min="0"
                onChange={(event) => onChange(['paragraph', lineSpacingRule === 'multiple' ? 'line_spacing_multiple' : 'line_spacing_pt'], Number(event.target.value))}
                step={lineSpacingRule === 'multiple' ? '0.1' : '0.5'}
                type="number"
                value={lineSpacingValue}
              />
            </label>
            {(['space_before_pt', 'space_after_pt'] as const).map((key) => (
              <label key={key}>
                {paragraphLabel(label, key)}
                <input
                  aria-label={paragraphLabel(label, key)}
                  disabled={disabled}
                  min="0"
                  onChange={(event) => onChange(['paragraph', key], Number(event.target.value))}
                  step="0.5"
                  type="number"
                  value={numberValue(paragraph[key], 0)}
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
  const paragraph = {
    alignment: 'left',
    first_line_indent_pt: 0,
    first_line_indent_unit: 'character',
    left_indent_pt: 0,
    left_indent_unit: 'character',
    right_indent_pt: 0,
    right_indent_unit: 'character',
    line_spacing_pt: 29,
    line_spacing_rule: 'exact',
    line_spacing_multiple: 1.5,
    space_before_pt: 0,
    space_after_pt: 0,
  }
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
  roles.abstract = { role_type: 'paragraph', font: { ...font }, paragraph: { ...paragraph, first_line_indent_pt: 32 } }
  roles['abstract-label'] = { role_type: 'character', font: { ...font, chinese_font: '黑体', western_font: 'Arial', bold: true } }
  roles.keywords = { role_type: 'paragraph', font: { ...font }, paragraph: { ...paragraph, first_line_indent_pt: 0 } }
  roles['keywords-label'] = { role_type: 'character', font: { ...font, chinese_font: '黑体', western_font: 'Arial', bold: true } }
  roles['heading-1'] = { role_type: 'paragraph', font: { ...font, chinese_font: '黑体', bold: true }, paragraph: { ...paragraph, first_line_indent_pt: 32 } }
  roles['body-table'] = { role_type: 'paragraph', font: { ...font, size_pt: 14 }, paragraph: { ...paragraph, first_line_indent_pt: 0 } }
  roles.footer = { role_type: 'paragraph', font: { ...font, chinese_font: '宋体', size_pt: 14 }, paragraph: { ...paragraph, alignment: 'center' } }
  roles.page = { role_type: 'page', page: { margin_top_cm: 3.5, margin_bottom_cm: 3.5, margin_left_cm: 2.8, margin_right_cm: 2.8, page_width_cm: 21, page_height_cm: 29.7 } }
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
    first_line_indent_pt: '首行缩进',
    left_indent_pt: '左缩进',
    right_indent_pt: '右缩进',
    line_spacing_pt: '行距',
    space_before_pt: '段前（磅）',
    space_after_pt: '段后（磅）',
  }
  return `${label}${names[key] ?? key}`
}

function fontSizeOptions(sizePt: number): Array<{ label: string; pt: number }> {
  if (FONT_SIZE_PRESETS.some((option) => option.pt === sizePt)) return FONT_SIZE_PRESETS
  return [{ label: '自定义', pt: sizePt }, ...FONT_SIZE_PRESETS]
}

function formatNumber(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1).replace(/\.0$/, '')
}

function indentUnitKey(key: string): string {
  return key.replace(/_pt$/, '_unit')
}

function indentUnitValue(value: unknown): IndentUnit {
  return value === 'pt' || value === 'cm' || value === 'character' ? value : 'character'
}

function indentUnitLabel(label: string, key: string): string {
  return `${paragraphLabel(label, key)}单位`
}

function indentDisplayValue(value: unknown, unit: IndentUnit, fontSize: number): number {
  const points = numberValue(value, 0)
  if (unit === 'character') return round(points / Math.max(fontSize, 1))
  if (unit === 'cm') return round(points / 28.3464567)
  return round(points)
}

function pointsFromIndent(value: number, unit: IndentUnit, fontSize: number): number {
  if (unit === 'character') return round(value * Math.max(fontSize, 1))
  if (unit === 'cm') return round(value * 28.3464567)
  return round(value)
}

function indentStep(unit: IndentUnit): string {
  if (unit === 'character') return '0.1'
  if (unit === 'cm') return '0.01'
  return '0.5'
}

function round(value: number): number {
  return Math.round(value * 100) / 100
}

function lineSpacingRuleValue(value: unknown): LineSpacingRule {
  return value === 'maximum' || value === 'minimum' || value === 'multiple' || value === 'exact' ? value : 'exact'
}

function lineSpacingLabel(label: string, rule: LineSpacingRule): string {
  return `${label}行距（${rule === 'multiple' ? '倍数' : '磅'}）`
}

function pageLabel(key: string): string {
  const names: Record<string, string> = {
    margin_top_cm: '上边距（厘米）',
    margin_bottom_cm: '下边距（厘米）',
    margin_left_cm: '左边距（厘米）',
    margin_right_cm: '右边距（厘米）',
    page_width_cm: '页面宽度（厘米）',
    page_height_cm: '页面高度（厘米）',
  }
  return names[key]
}
