import { useMemo, useRef, useEffect } from "react";
import { marked } from "marked";
import { api } from "@/api/client";

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function dirname(path: string): string {
  const idx = path.lastIndexOf("/");
  return idx >= 0 ? path.slice(0, idx) : "";
}

function normalizeWorkspacePath(path: string): string | null {
  const parts: string[] = [];
  for (const part of path.split("/")) {
    if (!part || part === ".") continue;
    if (part === "..") {
      if (parts.length === 0) return null;
      parts.pop();
      continue;
    }
    parts.push(part);
  }
  return parts.join("/");
}

function isExternalSrc(src: string): boolean {
  return /^(https?:|data:|blob:|\/)/i.test(src);
}

function imagePreviewUrl(basePath: string, src: string): string {
  if (isExternalSrc(src)) return src;
  const rel = normalizeWorkspacePath(`${dirname(basePath)}/${src}`);
  return rel ? api.workspacePreviewUrl(rel) : src;
}

function rewriteMarkdownImageSources(html: string, basePath?: string): string {
  if (!basePath || typeof document === "undefined") return html;
  const container = document.createElement("template");
  container.innerHTML = html;
  container.content.querySelectorAll("img[src]").forEach((img) => {
    const src = img.getAttribute("src") || "";
    img.setAttribute("src", imagePreviewUrl(basePath, src));
  });
  return container.innerHTML;
}

function escapeAttr(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

export default function MarkdownView({ text, basePath }: { text: string; basePath?: string }) {
  const containerRef = useRef<HTMLDivElement>(null);

  const html = useMemo(() => {
    try {
      const renderer = new marked.Renderer();
      renderer.image = (href, title, text) => {
        const rawHref = String(href || "");
        const src = basePath ? imagePreviewUrl(basePath, rawHref) : rawHref;
        const safeTitle = title ? ` title="${escapeAttr(String(title))}"` : "";
        const safeAlt = escapeAttr(String(text || ""));
        return `<img src="${escapeAttr(src)}" alt="${safeAlt}"${safeTitle}>`;
      };
      // 为 html 代码块添加预览按钮和 iframe 容器
      renderer.code = (codeText, lang) => {
        const language = (lang || "").toLowerCase();
        const isHtml = language === "html" || language === "htm";
        if (isHtml) {
          const safeSrcdoc = escapeAttr(codeText);
          return `<div class="md-code-block">
            <div class="md-code-header">
              <span class="md-code-lang">${escapeHtml(lang || "")}</span>
              <button type="button" class="md-html-preview-toggle">预览</button>
            </div>
            <pre><code class="language-${escapeAttr(lang || "")}">${escapeHtml(codeText)}</code></pre>
            <div class="md-html-preview" style="display:none;">
              <iframe sandbox="allow-scripts" srcdoc="${safeSrcdoc}"></iframe>
            </div>
          </div>`;
        }
        return `<pre><code class="language-${escapeAttr(lang || "")}">${escapeHtml(codeText)}</code></pre>`;
      };
      const html = marked.parse(text, { async: false, breaks: true, renderer }) as string;
      return rewriteMarkdownImageSources(html, basePath);
    } catch {
      return text;
    }
  }, [text, basePath]);

  // 处理预览按钮点击：切换 iframe 显示/隐藏
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const handler = (e: MouseEvent) => {
      const btn = (e.target as HTMLElement).closest(".md-html-preview-toggle");
      if (!btn) return;
      const block = btn.closest(".md-code-block");
      if (!block) return;
      const preview = block.querySelector(".md-html-preview") as HTMLElement | null;
      if (!preview) return;
      const isVisible = preview.style.display !== "none";
      preview.style.display = isVisible ? "none" : "block";
      (btn as HTMLElement).textContent = isVisible ? "预览" : "关闭预览";
    };
    el.addEventListener("click", handler);
    return () => el.removeEventListener("click", handler);
  }, []);

  return (
    <div
      ref={containerRef}
      className="md-content"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
