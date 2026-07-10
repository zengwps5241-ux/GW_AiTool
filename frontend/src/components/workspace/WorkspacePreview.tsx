import React from "react";
import type { WorkspaceNode } from "@/types";
import { isMarkdownPreview, isTextualMime, isOfficeName, isPdfName } from "@/lib/workspace";
import MarkdownView from "@/components/workspace/MarkdownView";
import type { WorkspacePreviewState } from "@/components/workspace/useWorkspacePreview";
import type { WorkspaceApi } from "@/lib/workspaceApi";

interface WorkspacePreviewProps {
  node: WorkspaceNode | null;
  preview: WorkspacePreviewState;
  content: string;
  dirty: boolean;
  convertedMarkdown: boolean;
  mode: "preview" | "edit";
  readonly?: boolean;
  workspaceApi: WorkspaceApi;
  onChange: (value: string) => void;
  onSave: () => void | Promise<void>;
  onReload: () => void;
  onSwitchMode: () => void | Promise<void>;
  onRetryConversion: (path: string) => void;
}

export default function WorkspacePreview(props: WorkspacePreviewProps) {
  const { node, preview, content, dirty, convertedMarkdown, mode } = props;
  const isOfficeOrPdf = node?.type === "file" && (isOfficeName(node.name) || isPdfName(node.name));
  const documentPreviewUrl = node && isOfficeOrPdf ? props.workspaceApi.officePreviewUrl(node.path) : "";
  const documentPreviewActive = Boolean(documentPreviewUrl && mode === "preview");
  const [documentLoading, setDocumentLoading] = React.useState(false);

  React.useEffect(() => {
    setDocumentLoading(documentPreviewActive);
  }, [documentPreviewActive, documentPreviewUrl]);

  if (!node) {
    return (
      <div
        style={{
          flex: 1,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "var(--ink-3)",
          fontSize: 13,
        }}
      >
        选择左侧文件以预览或编辑
      </div>
    );
  }

  if (node.type === "dir") {
    return (
      <div
        style={{
          flex: 1,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "var(--ink-3)",
          fontSize: 13,
        }}
      >
        目录: {node.name}
      </div>
    );
  }

  const editable = preview.text !== null && isTextualMime(preview.mime);

  return (
    <div
      style={{
        flex: 1,
        display: "flex",
        flexDirection: "column",
        minWidth: 0,
        background: "var(--bg)",
      }}
    >
      {/* 工具栏 */}
      <div
        style={{
          height: 48,
          padding: "0 16px",
          borderBottom: "1px solid var(--line)",
          display: "flex",
          alignItems: "center",
          gap: 12,
          flexShrink: 0,
        }}
      >
        <div
          style={{
            flex: 1,
            fontSize: 13,
            fontWeight: 600,
            color: "var(--ink)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {node.name}
        </div>
        {editable && (
          <>
            <button
              onClick={props.onReload}
              disabled={preview.loading}
              style={toolbarBtnStyle}
            >
              重新加载
            </button>
            {!props.readonly && mode === "edit" && (
              <button
                onClick={props.onSave}
                disabled={preview.loading || !dirty}
                style={{
                  ...toolbarBtnStyle,
                  background: dirty ? "var(--accent)" : "transparent",
                  color: dirty ? "var(--on-accent)" : "var(--ink-3)",
                  borderColor: dirty ? "var(--accent)" : "var(--line)",
                }}
              >
                保存
              </button>
            )}
          </>
        )}
        {!props.readonly && (editable || isOfficeOrPdf) && (
          <button onClick={props.onSwitchMode} style={toolbarBtnStyle}>
            {mode === "preview" ? "编辑" : "返回预览"}
          </button>
        )}
      </div>

      {/* 转换后 Markdown 警告 */}
      {convertedMarkdown && (
        <div
          style={{
            padding: "8px 12px",
            background: "var(--accent-soft)",
            color: "var(--accent-2)",
            borderBottom: "1px solid var(--line)",
            fontSize: 12.5,
          }}
        >
          当前编辑的是转换后的 Markdown，不是原始文件。
        </div>
      )}

      {/* 内容区 */}
      <div style={{ flex: 1, overflow: "auto", minHeight: 0 }}>
        {preview.loading && !documentPreviewActive && (
          <div
            style={{
              padding: 40,
              textAlign: "center",
              color: "var(--ink-3)",
              fontSize: 13,
            }}
          >
            加载中…
          </div>
        )}

        {preview.error && !preview.loading && (
          <div
            style={{
              padding: 40,
              textAlign: "center",
              color: "var(--danger)",
              fontSize: 13,
            }}
          >
            <div>{preview.error}</div>
            {!props.readonly && node.conversion_status === "failed" && (
              <button
                onClick={() => props.onRetryConversion(node.path)}
                style={{
                  marginTop: 12,
                  padding: "6px 14px",
                  background: "var(--accent)",
                  color: "var(--on-accent)",
                  border: "none",
                  borderRadius: 6,
                  cursor: "pointer",
                  fontSize: 12.5,
                  fontFamily: "inherit",
                }}
              >
                重试转换
              </button>
            )}
          </div>
        )}

        {/* Office / PDF 预览模式：iframe 渲染 */}
        {!preview.error && mode === "preview" && isOfficeOrPdf && (
          <div style={{ position: "relative", width: "100%", height: "100%", minHeight: 400 }}>
            {documentLoading && (
              <div
                style={{
                  position: "absolute",
                  inset: 0,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  color: "var(--ink-3)",
                  fontSize: 13,
                  background: "var(--bg)",
                  zIndex: 1,
                }}
              >
                文档加载中，请稍后。大文件首次加载耗时较长，请耐心等待。
              </div>
            )}
            <iframe
              key={documentPreviewUrl}
              src={documentPreviewUrl}
              title={node.name}
              onLoad={() => setDocumentLoading(false)}
              style={{
                width: "100%",
                height: "100%",
                border: "none",
                minHeight: 400,
                visibility: documentLoading ? "hidden" : "visible",
              }}
            />
          </div>
        )}

        {!preview.loading && !preview.error && mode === "preview" && editable && !isOfficeOrPdf && (
          isMarkdownPreview(node.name, preview.mime, preview.resolvedPath) ? (
            <div style={{ padding: 16 }}>
              <MarkdownView text={content} basePath={preview.resolvedPath || node.path} />
            </div>
          ) : (
            <pre style={textPreviewStyle}>{content}</pre>
          )
        )}

        {/* 编辑模式：文本编辑器 */}
        {!preview.loading && !preview.error && mode === "edit" && editable && (
          isMarkdownPreview(node.name, preview.mime, preview.resolvedPath) ? (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", minHeight: "100%" }}>
              <textarea
                value={content}
                readOnly={props.readonly}
                onChange={(e) => !props.readonly && props.onChange(e.target.value)}
                style={editorStyle}
              />
              <div style={{ padding: 16, borderLeft: "1px solid var(--line)", background: "var(--surface)", overflow: "auto" }}>
                <MarkdownView text={content} basePath={preview.resolvedPath || node.path} />
              </div>
            </div>
          ) : (
            <textarea
              value={content}
              readOnly={props.readonly}
              onChange={(e) => !props.readonly && props.onChange(e.target.value)}
              style={editorStyle}
            />
          )
        )}

        {!preview.loading && !preview.error && preview.category === "image" && (
          <div style={mediaWrapStyle}>
            <img
              src={props.workspaceApi.previewUrl(node.path)}
              alt={node.name}
              style={{ maxWidth: "100%", maxHeight: "100%", objectFit: "contain" }}
            />
          </div>
        )}

        {!preview.loading && !preview.error && preview.category === "video" && (
          <div style={mediaWrapStyle}>
            <video
              src={props.workspaceApi.previewUrl(node.path)}
              controls
              style={{ maxWidth: "100%", maxHeight: "70vh" }}
            />
          </div>
        )}

        {!preview.loading && !preview.error && preview.category === "audio" && (
          <div style={mediaWrapStyle}>
            <audio src={props.workspaceApi.previewUrl(node.path)} controls style={{ width: "80%" }} />
          </div>
        )}

        {/* 编辑模式下，Office/PDF 文本获取失败时的兜底提示 */}
        {!preview.loading && !preview.error && mode === "edit" && isOfficeOrPdf && !editable && preview.shouldFetchText && (
          <div
            style={{
              padding: 40,
              textAlign: "center",
              color: "var(--ink-3)",
              fontSize: 13,
            }}
          >
            尚未生成转换后的 Markdown，请等待转换完成或重新转换。
            <div style={{ marginTop: 8, fontSize: 12, color: "var(--ink-4)" }}>
              状态: {node.conversion_status || "排队中"}
            </div>
          </div>
        )}

        {!preview.loading && !preview.error && preview.category === "unsupported" && !preview.shouldFetchText && (
          <div
            style={{
              padding: 40,
              textAlign: "center",
              color: "var(--ink-3)",
              fontSize: 13,
            }}
          >
            该文件类型不支持在线预览，请下载后查看。
          </div>
        )}
      </div>
    </div>
  );
}

const toolbarBtnStyle: React.CSSProperties = {
  padding: "4px 10px",
  fontSize: 12,
  background: "transparent",
  border: "1px solid var(--line)",
  borderRadius: 6,
  color: "var(--ink-2)",
  cursor: "pointer",
  fontFamily: "inherit",
};

const editorStyle: React.CSSProperties = {
  width: "100%",
  height: "100%",
  minHeight: 300,
  border: "none",
  outline: "none",
  resize: "none",
  background: "var(--bg)",
  fontSize: 13.5,
  lineHeight: 1.6,
  color: "var(--ink)",
  fontFamily: "var(--font-mono, ui-monospace, monospace)",
  padding: 16,
};

const textPreviewStyle: React.CSSProperties = {
  margin: 0,
  padding: 16,
  whiteSpace: "pre-wrap",
  wordBreak: "break-word",
  fontSize: 13.5,
  lineHeight: 1.6,
  color: "var(--ink)",
  fontFamily: "var(--font-mono, ui-monospace, monospace)",
};

const mediaWrapStyle: React.CSSProperties = {
  height: "100%",
  minHeight: 300,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  padding: 16,
};
