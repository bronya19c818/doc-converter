import { useEffect, useRef, useState } from 'react'

type DocxPreviewProps = {
  documentUrl: string
  previewUrl?: string
}

type DocxPreviewModule = typeof import('docx-preview')

let docxPreviewModule: Promise<DocxPreviewModule> | null = null

export function preloadDocxPreview(): Promise<DocxPreviewModule> {
  if (!docxPreviewModule) {
    docxPreviewModule = import('docx-preview').catch((error: unknown) => {
      docxPreviewModule = null
      throw error
    })
  }
  return docxPreviewModule
}

export function DocxPreview({ documentUrl, previewUrl }: DocxPreviewProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [error, setError] = useState<string | null>(null)
  const [failedPreviewUrl, setFailedPreviewUrl] = useState<string | null>(null)
  const [loadedPreviewUrl, setLoadedPreviewUrl] = useState<string | null>(null)
  const [docxLoading, setDocxLoading] = useState(true)
  const useDocxFallback = !previewUrl || failedPreviewUrl === previewUrl
  const loading = useDocxFallback ? docxLoading : loadedPreviewUrl !== previewUrl

  useEffect(() => {
    let cancelled = false
    const container = containerRef.current
    if (!container || !useDocxFallback) return undefined
    const previewContainer = container

    previewContainer.replaceChildren()
    setError(null)
    setDocxLoading(true)

    async function renderDocxFallback() {
      const [response, { renderAsync }] = await Promise.all([
        fetch(documentUrl, { cache: 'no-store' }),
        preloadDocxPreview(),
      ])
      if (!response.ok) throw new Error('无法读取生成的 DOCX。')
      const documentBlob = await response.blob()
      if (!cancelled) {
        await renderAsync(documentBlob, previewContainer, undefined, {
          breakPages: true,
          ignoreLastRenderedPageBreak: false,
          inWrapper: true,
          renderHeaders: true,
          renderFooters: true,
        })
        setDocxLoading(false)
      }
    }

    void renderDocxFallback().catch((previewError: unknown) => {
      if (!cancelled) {
        setDocxLoading(false)
        setError(previewError instanceof Error ? previewError.message : '内置预览失败。')
      }
    })

    return () => {
      cancelled = true
    }
  }, [documentUrl, useDocxFallback])

  useEffect(() => {
    setError(null)
    setLoadedPreviewUrl(null)
  }, [documentUrl, previewUrl])

  return (
    <div className="docx-preview-host">
      {error ? <p className="preview-error">{error} 可下载 DOCX 后使用 Word 或 WPS 打开。</p> : null}
      {loading ? (
        <p className="preview-loading" role="status">
          正在载入{useDocxFallback ? ' DOCX' : ' PDF'} 预览…
        </p>
      ) : null}
      {previewUrl && !useDocxFallback ? (
        <iframe
          className="pdf-preview"
          loading="eager"
          onError={() => setFailedPreviewUrl(previewUrl)}
          onLoad={() => setLoadedPreviewUrl(previewUrl)}
          src={previewUrl}
          title="DOCX PDF 预览"
        />
      ) : null}
      <div
        aria-label="内置 DOCX 预览内容"
        className="docx-preview"
        ref={containerRef}
        style={{ display: useDocxFallback ? undefined : 'none' }}
      />
    </div>
  )
}
