import { useEffect, useRef, useState } from 'react'

type DocxPreviewProps = {
  documentUrl: string
}

export function DocxPreview({ documentUrl }: DocxPreviewProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    const container = containerRef.current
    if (!container) return undefined

    container.replaceChildren()
    setError(null)
    void (async () => {
      try {
        const response = await fetch(documentUrl)
        if (!response.ok) throw new Error('无法读取生成的 DOCX。')
        const documentBlob = await response.blob()
        const { renderAsync } = await import('docx-preview')
        if (!cancelled) {
          await renderAsync(documentBlob, container, undefined, {
            breakPages: true,
            ignoreLastRenderedPageBreak: false,
            inWrapper: true,
            renderHeaders: true,
            renderFooters: true,
          })
        }
      } catch (previewError) {
        if (!cancelled) {
          setError(previewError instanceof Error ? previewError.message : '内置预览失败。')
        }
      }
    })()

    return () => {
      cancelled = true
    }
  }, [documentUrl])

  if (error) {
    return <p className="preview-error">{error} 可下载 DOCX 后使用 Word 或 WPS 打开。</p>
  }

  return <div aria-label="内置 DOCX 预览内容" className="docx-preview" ref={containerRef} />
}
