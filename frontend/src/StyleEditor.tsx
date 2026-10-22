import { FormEvent, useEffect, useRef, useState } from 'react'

import { reviseStylePack, StylePack } from './api'

type StyleEditorProps = {
  disabled: boolean
  onSaved: (pack: StylePack) => void
  onDirtyChange?: (dirty: boolean) => void
  pack: StylePack
  section?: 'roles' | 'page'
}

type RoleSection = 'pre' | 'body' | 'post'

type RoleValue = {
  role_type: 'paragraph' | 'character' | 'page' | 'image'
  font?: Record<string, unknown>
  paragraph?: Record<string, unknown>
  page?: Record<string, unknown>
  image?: Record<string, unknown>
}

type RoleMap = Record<string, RoleValue>

const ROLE_LABELS: Record<string, string> = {
  'document-title': '文档标题',
  'document-subtitle': '副标题',
  'organization-department': '单位/部门',
  author: '作者',
  date: '日期',
  'abstract-label': '摘要标签',
  'abstract-content': '摘要内容',
  'keywords-label': '关键词标签',
  'keywords-content': '关键词内容',
  'heading-1': '一级标题',
  'heading-2': '二级标题',
  'heading-3': '三级标题',
  'heading-4': '四级标题',
  'heading-5': '五级标题',
  'heading-6': '六级标题',
  'body-paragraph': '段落正文',
  'body-table': '表格正文',
  point: '要点',
  'table-caption': '表格标题',
  'table-credit': '制表人',
  'table-row-header': '行标题',
  'table-column-header': '列标题',
  'figure-caption': '图片标题',
  'figure-credit': '制图人',
  image: '图片样式',
  'reference-heading': '参考文献标题',
  'reference-entry': '参考文献条目',
  footer: '页脚',
}

const ROLE_SECTIONS: Array<{ key: RoleSection; label: string }> = [
  { key: 'pre', label: '文前部分' },
  { key: 'body', label: '正文部分' },
  { key: 'post', label: '文后部分' },
]

const GROUPS: Record<RoleSection, Array<{ title: string; roles: string[] }>> = {
  pre: [
    { title: '标题与元数据', roles: ['document-title', 'document-subtitle', 'organization-department', 'author', 'date'] },
    { title: '摘要', roles: ['abstract-label', 'abstract-content'] },
    { title: '关键词', roles: ['keywords-label', 'keywords-content'] },
  ],
  body: [
    { title: '标题层级', roles: ['heading-1', 'heading-2', 'heading-3', 'heading-4', 'heading-5', 'heading-6'] },
    { title: '正文', roles: ['body-paragraph', 'point'] },
    { title: '表格', roles: ['table-caption', 'table-credit', 'table-row-header', 'table-column-header', 'body-table'] },
    { title: '图片', roles: ['figure-caption', 'figure-credit', 'image'] },
  ],
  post: [
    { title: '参考文献（检测到“参考文献”标题后生效）', roles: ['reference-heading', 'reference-entry'] },
    { title: '页脚', roles: ['footer'] },
  ],
}

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

export function StyleEditor({ disabled, onSaved, onDirtyChange, pack, section = 'roles' }: StyleEditorProps) {
  const [roles, setRoles] = useState<RoleMap>(() => editableRolesFor(pack))
  const [savedRoles, setSavedRoles] = useState<RoleMap>(() => editableRolesFor(pack))
  const [saveNotice, setSaveNotice] = useState('')
  const inspectorRef = useRef<HTMLDivElement>(null)
  const reportedDirty = useRef<boolean | undefined>(undefined)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [roleSection, setRoleSection] = useState<RoleSection>('pre')
  const [activeRole, setActiveRole] = useState('document-title')
  const visibleGroups = GROUPS[roleSection]
  const visibleKeys = visibleGroups.flatMap((group) => group.roles)
  const selectedRole = visibleKeys.includes(activeRole) ? activeRole : visibleKeys[0]

  useEffect(() => {
    const nextRoles = editableRolesFor(pack)
    setRoles(nextRoles)
    setSavedRoles(nextRoles)
    setError(null)
  }, [pack])

  useEffect(() => {
    if (inspectorRef.current) inspectorRef.current.scrollTop = 0
  }, [selectedRole, section])

  useEffect(() => {
    if (!saveNotice) return
    const timer = window.setTimeout(() => setSaveNotice(''), 4000)
    return () => window.clearTimeout(timer)
  }, [saveNotice])

  const hasChanges = JSON.stringify(roles) !== JSON.stringify(savedRoles)

  useEffect(() => {
    if (reportedDirty.current === hasChanges) return
    reportedDirty.current = hasChanges
    onDirtyChange?.(hasChanges)
  }, [hasChanges, onDirtyChange])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (disabled || saving || !hasChanges) return
    setSaving(true)
    setError(null)
    setSaveNotice('')
    try {
      const saved = await reviseStylePack(pack, { name: pack.name, roles })
      const nextRoles = editableRolesFor(saved)
      setRoles(nextRoles)
      setSavedRoles(nextRoles)
      setSaveNotice(`已保存 · 版本 ${saved.version}`)
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
      {section === 'roles' ? (
        <>
          <div className="style-navigation">
          <div aria-label="样式角色分区" className="role-section-tabs" role="tablist">
            {ROLE_SECTIONS.map((item) => (
              <button
                aria-selected={roleSection === item.key}
                className="role-section-tab"
                key={item.key}
                onClick={() => { setRoleSection(item.key); setActiveRole(item.key === 'pre' ? 'document-title' : item.key === 'body' ? 'body-paragraph' : 'reference-heading') }}
                role="tab"
                type="button"
              >
                {item.label}
              </button>
            ))}
          </div>
          </div>
          <div className="role-workspace">
            <nav aria-label="样式目录" className="role-directory">
              {visibleGroups.map((group) => (
                <div key={group.title}>
                  <p>{group.title}</p>
                  {group.roles.map((key) => (
                    <button aria-pressed={key === selectedRole} key={key} onClick={() => { setActiveRole(key); if (inspectorRef.current) inspectorRef.current.scrollTop = 0 }} type="button">{ROLE_LABELS[key]}</button>
                  ))}
                </div>
              ))}
            </nav>
            <div className="role-inspector" ref={inspectorRef}>
              <h3 className="role-inspector-heading">{ROLE_LABELS[selectedRole]}</h3>
          {visibleGroups.map((group) => (
            <fieldset className="style-group inspector-group" key={group.title}>
              <legend>{group.title}</legend>
              <div className="role-grid">
                {group.roles.map((roleKey) => (
                  <div hidden={roleKey !== selectedRole} key={roleKey}>
                  <RoleEditor
                    disabled={isDisabled}
                    key={roleKey}
                    onChange={(field, value) => updateRole(setRoles, roleKey, field, value)}
                    roleKey={roleKey}
                    role={roles[roleKey]}
                  />
                  </div>
                ))}
              </div>
            </fieldset>
          ))}
            </div>
          </div>
        </>
      ) : null}
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
      <div className="style-savebar">
        {error ? <p className="error-message" role="alert">{error}</p> : null}
        <span className="style-save-status" role="status">{hasChanges ? '有未保存修改' : !error ? saveNotice : ''}</span>
        <button className="secondary-action primary-draft-action" disabled={isDisabled || !hasChanges} type="submit">{saving ? '正在保存…' : '保存样式新版本'}</button>
      </div>
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
  const image = role.image ?? {}
  const characterOnly = role.role_type === 'character'
  const fontSize = numberValue(font.size_pt, 16)
  const lineSpacingRule = lineSpacingRuleValue(paragraph.line_spacing_rule)
  const lineSpacingValue = lineSpacingRule === 'multiple'
    ? numberValue(paragraph.line_spacing_multiple, 1.5)
    : numberValue(paragraph.line_spacing_pt, 29)
  const previewSize = previewPositive(font.size_pt, 16)
  const previewSpacing = previewPositive(lineSpacingValue, lineSpacingRule === 'multiple' ? 1.5 : 29)
  const previewLineHeight = characterOnly ? 'normal' : lineSpacingRule === 'multiple'
    ? previewSpacing
    : `${lineSpacingRule === 'minimum' ? Math.max(previewSize * 1.2, previewSpacing) : lineSpacingRule === 'maximum' ? Math.min(previewSize * 1.2, previewSpacing) : previewSpacing}pt`
  if (role.role_type === 'image') {
    return (
      <article className="role-card">
        <div className="style-grid">
          <label>
            对齐
            <select aria-label={`${label}对齐`} disabled={disabled} onChange={(event) => onChange(['image', 'alignment'], event.target.value)} value={stringValue(image.alignment, 'center')}>
              <option value="left">左对齐</option>
              <option value="center">居中</option>
              <option value="right">右对齐</option>
            </select>
          </label>
          <label>
            最大宽度（厘米）
            <input
              aria-label={`${label}最大宽度（厘米）`}
              disabled={disabled}
              min="0.1"
              onChange={(event) => onChange(['image', 'max_width_cm'], event.target.value === '' ? null : Number(event.target.value))}
              placeholder="按正文宽度适配"
              step="0.1"
              type="number"
              value={typeof image.max_width_cm === 'number' ? image.max_width_cm : ''}
            />
          </label>
          {(['space_before_pt', 'space_after_pt'] as const).map((key) => (
            <label key={key}>
              {paragraphLabel('', key)}
              <input
                aria-label={paragraphLabel(label, key)}
                disabled={disabled}
                min="0"
                onChange={(event) => onChange(['image', key], Number(event.target.value))}
                step="0.5"
                type="number"
                value={numberValue(image[key], 0)}
              />
            </label>
          ))}
        </div>
        <p className="field-help">留空时按正文宽度适配，较小图片不会放大。</p>
      </article>
    )
  }
  return (
    <article className="role-card">
      <div className="style-grid">
        <label>
          中文字体
          <input aria-label={`${label}中文字体`} disabled={disabled} onChange={(event) => onChange(['font', 'chinese_font'], event.target.value)} value={stringValue(font.chinese_font, '仿宋')} />
        </label>
        <label>
          西文字体
          <input aria-label={`${label}西文字体`} disabled={disabled} onChange={(event) => onChange(['font', 'western_font'], event.target.value)} value={stringValue(font.western_font, 'Times New Roman')} />
        </label>
        <label>
          字号
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
        <div className="font-options">
        <label className="checkbox-label">
          <input aria-label={`${label}粗体`} checked={booleanValue(font.bold)} disabled={disabled} onChange={(event) => onChange(['font', 'bold'], event.target.checked)} type="checkbox" />
          粗体
        </label>
        <label className="checkbox-label">
          <input aria-label={`${label}斜体`} checked={booleanValue(font.italic)} disabled={disabled} onChange={(event) => onChange(['font', 'italic'], event.target.checked)} type="checkbox" />
          斜体
        </label>
        </div>
        {!characterOnly ? (
          <>
            <label>
              对齐
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
                    {paragraphLabel('', key)}
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
              行距类型
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
              {lineSpacingLabel('', lineSpacingRule)}
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
                {paragraphLabel('', key)}
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
      <div className="role-typesetting-preview" aria-label={`${label}文字试排示例`}>
        <p className="role-typesetting-label">文字试排示例</p>
        <p className="role-typesetting-sample" style={{
          fontFamily: `${JSON.stringify(stringValue(font.western_font, 'Times New Roman'))}, ${JSON.stringify(stringValue(font.chinese_font, '仿宋'))}, serif`,
          fontSize: `${previewSize}pt`,
          fontWeight: booleanValue(font.bold) ? 'bold' : 'normal',
          fontStyle: booleanValue(font.italic) ? 'italic' : 'normal',
          textAlign: characterOnly ? 'left' : stringValue(paragraph.alignment, 'left') as 'left' | 'center' | 'right' | 'justify',
          lineHeight: previewLineHeight,
        }}>
          {roleKey === 'figure-credit' || roleKey === 'table-credit'
            ? `${label}：张三　2026年10月22日 14:30（示例）`
            : `${label}示例：春风拂过山野，文字呈现清晰的层次。Sample 2026。`}
          <br />
          {roleKey === 'figure-credit' || roleKey === 'table-credit'
            ? `${label}：李四　2026年10月23日 09:00（示例）`
            : '第二行示例，用于查看行距与对齐效果。'}
        </p>
      </div>
    </article>
  )
}

function previewPositive(value: unknown, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : fallback
}

function editableRolesFor(pack: StylePack): RoleMap {
  const roles: RoleMap = {}
  Object.entries(pack.roles).forEach(([key, value]) => {
    roles[key] = {
      role_type: roleType(value.role_type),
      font: { ...(value.font as Record<string, unknown> | undefined) },
      paragraph: { ...(value.paragraph as Record<string, unknown> | undefined) },
      page: { ...(value.page as Record<string, unknown> | undefined) },
      image: { ...(value.image as Record<string, unknown> | undefined) },
    }
  })
  const defaults = defaultRoleMap()
  if (roles.body && !roles['body-paragraph']) roles['body-paragraph'] = roles.body
  const metadataRolePairs = [
    ['abstract', 'abstract-label', 'abstract-content'],
    ['keywords', 'keywords-label', 'keywords-content'],
  ] as const
  metadataRolePairs.forEach(([legacyKey, labelKey, contentKey]) => {
    const labelRole = roles[labelKey]
    const contentRole = roles[contentKey]
    const legacyRole = roles[legacyKey]
    const paragraphRole = labelRole?.role_type === 'paragraph'
      ? labelRole
      : contentRole?.role_type === 'paragraph' ? contentRole : legacyRole
    const contentFontRole = contentRole?.font ? contentRole : legacyRole
    roles[labelKey] = {
      ...defaults[labelKey],
      ...labelRole,
      role_type: 'paragraph',
      font: { ...defaults[labelKey].font, ...labelRole?.font },
      paragraph: { ...defaults[labelKey].paragraph, ...paragraphRole?.paragraph },
    }
    roles[contentKey] = {
      ...defaults[contentKey],
      ...contentRole,
      role_type: 'character',
      font: { ...defaults[contentKey].font, ...contentFontRole?.font },
      paragraph: {},
    }
    delete roles[legacyKey]
  })
  Object.entries(defaults).forEach(([key, value]) => {
    const role = roles[key]
    roles[key] = {
      ...value,
      ...role,
      font: { ...value.font, ...role?.font },
      paragraph: role?.role_type === 'character' ? {} : { ...value.paragraph, ...role?.paragraph },
      page: { ...value.page, ...role?.page },
      image: { ...value.image, ...role?.image },
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
    roles[key] = key === 'image'
      ? { role_type: 'image', image: { alignment: 'center', space_before_pt: 0, space_after_pt: 0 } }
      : { role_type: key === 'point' ? 'character' : 'paragraph', font: { ...font }, paragraph: { ...paragraph } }
  })
  roles['document-title'] = { role_type: 'paragraph', font: { ...font, chinese_font: '宋体', size_pt: 22, bold: true }, paragraph: { ...paragraph, alignment: 'center' } }
  roles['document-subtitle'] = { role_type: 'paragraph', font: { ...font, chinese_font: '楷体', bold: true }, paragraph: { ...paragraph, alignment: 'center' } }
  roles['organization-department'] = { ...roles['document-subtitle'] }
  roles.author = { ...roles['document-subtitle'] }
  roles.date = { ...roles['document-subtitle'] }
  roles['abstract-label'] = {
    role_type: 'paragraph',
    font: { ...font, chinese_font: '黑体', size_pt: 9, bold: true },
    paragraph: { ...paragraph, alignment: 'justify', first_line_indent_pt: 0, left_indent_pt: 18, right_indent_pt: 18, line_spacing_pt: 12, line_spacing_rule: 'minimum', space_before_pt: 12 },
  }
  roles['abstract-content'] = { role_type: 'character', font: { ...font, chinese_font: '楷体', size_pt: 9 }, paragraph: {} }
  roles['keywords-label'] = {
    role_type: 'paragraph',
    font: { ...font, chinese_font: '黑体', size_pt: 9, bold: true },
    paragraph: { ...paragraph, alignment: 'justify', first_line_indent_pt: 0, left_indent_pt: 18, right_indent_pt: 18, line_spacing_pt: 12, line_spacing_rule: 'minimum', space_after_pt: 5 },
  }
  roles['keywords-content'] = { role_type: 'character', font: { ...font, chinese_font: '楷体', size_pt: 9 }, paragraph: {} }
  roles['heading-1'] = { role_type: 'paragraph', font: { ...font, chinese_font: '黑体', western_font: 'Times New Roman', size_pt: 14, bold: true }, paragraph: { ...paragraph, first_line_indent_pt: 0, space_before_pt: 5, line_spacing_pt: 18, line_spacing_rule: 'minimum' } }
  roles['heading-2'] = { role_type: 'paragraph', font: { ...font, chinese_font: '黑体', western_font: 'Times New Roman', size_pt: 12, bold: true }, paragraph: { ...paragraph, first_line_indent_pt: 0, space_before_pt: 5, line_spacing_pt: 12, line_spacing_rule: 'minimum' } }
  roles['heading-3'] = { role_type: 'paragraph', font: { ...font, chinese_font: '黑体', western_font: 'Times New Roman', size_pt: 10.5, bold: true }, paragraph: { ...paragraph, first_line_indent_pt: 0, space_before_pt: 5, line_spacing_pt: 12, line_spacing_rule: 'minimum' } }
  roles['heading-4'] = { role_type: 'paragraph', font: { ...font, chinese_font: '黑体', western_font: 'Times New Roman', size_pt: 9, bold: true }, paragraph: { ...paragraph, first_line_indent_pt: 0, space_before_pt: 5, line_spacing_pt: 12, line_spacing_rule: 'minimum' } }
  roles['heading-5'] = { role_type: 'paragraph', font: { ...font, chinese_font: '黑体', western_font: 'Times New Roman', size_pt: 7.5, bold: true }, paragraph: { ...paragraph, first_line_indent_pt: 0, space_before_pt: 5, line_spacing_pt: 12, line_spacing_rule: 'minimum' } }
  roles['heading-6'] = { role_type: 'paragraph', font: { ...font, chinese_font: '黑体', western_font: 'Times New Roman', size_pt: 6.5, bold: true }, paragraph: { ...paragraph, first_line_indent_pt: 0, space_before_pt: 5, line_spacing_pt: 12, line_spacing_rule: 'minimum' } }
  roles['table-credit'] = { role_type: 'paragraph', font: { ...font, chinese_font: '黑体', western_font: 'Arial', size_pt: 14 }, paragraph: { ...paragraph, alignment: 'right' } }
  roles['figure-credit'] = { role_type: 'paragraph', font: { ...font, chinese_font: '黑体', western_font: 'Arial', size_pt: 14 }, paragraph: { ...paragraph, alignment: 'right' } }
  roles['body-table'] = { role_type: 'paragraph', font: { ...font, size_pt: 14 }, paragraph: { ...paragraph, first_line_indent_pt: 0 } }
  roles['table-row-header'] = { ...roles['body-table'], font: { ...font, size_pt: 14, bold: true }, paragraph: { ...paragraph, first_line_indent_pt: 0, alignment: 'left' } }
  roles['table-column-header'] = { ...roles['body-table'], font: { ...font, size_pt: 14, bold: true }, paragraph: { ...paragraph, first_line_indent_pt: 0, alignment: 'center' } }
  roles['reference-heading'] = { role_type: 'paragraph', font: { ...font, chinese_font: '黑体', western_font: 'Times New Roman', size_pt: 14, bold: true }, paragraph: { ...paragraph, first_line_indent_pt: 0, space_before_pt: 5, line_spacing_pt: 18, line_spacing_rule: 'minimum' } }
  roles['reference-entry'] = { role_type: 'paragraph', font: { ...font, chinese_font: '宋体', western_font: 'Times New Roman', size_pt: 7.5 }, paragraph: { ...paragraph, alignment: 'justify', first_line_indent_pt: 0, line_spacing_pt: 12, line_spacing_rule: 'minimum' } }
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
  return value === 'character' || value === 'page' || value === 'image' ? value : 'paragraph'
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
