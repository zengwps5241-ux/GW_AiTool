import type { WorkspaceNode } from "@/types";

const TEXT_EXTS = new Set([
  "txt",
  "md",
  "markdown",
  "rst",
  "xml",
  "py",
  "js",
  "jsx",
  "mjs",
  "cjs",
  "ts",
  "tsx",
  "json",
  "yaml",
  "yml",
  "toml",
  "ini",
  "conf",
  "cfg",
  "css",
  "scss",
  "less",
  "vue",
  "html",
  "sh",
  "bash",
  "zsh",
  "fish",
  "sql",
  "log",
  "env",
  "go",
  "rs",
  "java",
  "kt",
  "swift",
  "c",
  "cc",
  "cpp",
  "h",
  "hh",
  "hpp",
]);

const OFFICE_EXTS = new Set([
  "doc",
  "docx",
  "ppt",
  "pptx",
  "xls",
  "xlsx",
  "csv",
]);
const CONVERTIBLE_EXTS = new Set([...OFFICE_EXTS, "pdf"]);

export function fileExt(name: string): string {
  return name.toLowerCase().split(".").pop() || "";
}

export function isTextEditableName(name: string): boolean {
  return TEXT_EXTS.has(fileExt(name));
}

export function isOfficeName(name: string): boolean {
  return OFFICE_EXTS.has(fileExt(name));
}

export function isPdfName(name: string): boolean {
  return fileExt(name) === "pdf";
}

export function isConvertibleName(name: string): boolean {
  return CONVERTIBLE_EXTS.has(fileExt(name));
}

export type WorkspacePreviewCategory =
  | "text"
  | "office"
  | "pdf"
  | "image"
  | "video"
  | "audio"
  | "unsupported";

export function workspacePreviewCategory(name: string): WorkspacePreviewCategory {
  const ext = fileExt(name);
  if (TEXT_EXTS.has(ext)) return "text";
  if (OFFICE_EXTS.has(ext)) return "office";
  if (ext === "pdf") return "pdf";
  if (["png", "jpg", "jpeg", "gif", "webp", "svg", "bmp", "ico"].includes(ext)) return "image";
  if (["mp4", "webm", "mov", "mkv", "avi"].includes(ext)) return "video";
  if (["mp3", "wav", "ogg", "m4a", "flac"].includes(ext)) return "audio";
  return "unsupported";
}

export function isTextualMime(mime: string): boolean {
  const base = mime.split(";", 1)[0].trim().toLowerCase();
  return base.startsWith("text/") || base === "application/json" || base === "application/xml";
}

export function isMarkdownName(name: string): boolean {
  const ext = fileExt(name);
  return ext === "md" || ext === "markdown";
}

export function isHtmlName(name: string): boolean {
  const ext = fileExt(name);
  return ext === "html" || ext === "htm";
}

export function isMarkdownPreview(name: string, mime: string, resolvedPath?: string | null): boolean {
  return isMarkdownName(name) || isMarkdownName(resolvedPath || "") || (isConvertibleName(name) && isTextualMime(mime));
}

export function uploadTargetForSelection(node: WorkspaceNode | null): string {
  return node?.type === "dir" ? node.path : "";
}

export function splitWorkspaceFileName(name: string): { stem: string; suffix: string } {
  const dotIndex = name.lastIndexOf(".");
  if (dotIndex <= 0) return { stem: name, suffix: "" };
  return {
    stem: name.slice(0, dotIndex),
    suffix: name.slice(dotIndex),
  };
}

export function renameWorkspaceFileStem(name: string, nextStem: string): string {
  return `${nextStem}${splitWorkspaceFileName(name).suffix}`;
}

export function canMoveWorkspaceNode(node: WorkspaceNode, targetDir: string): boolean {
  if (node.path === targetDir) return false;
  // 目录不能移动到自身的子目录里,否则后端会形成无效路径关系。
  return !(node.type === "dir" && targetDir.startsWith(`${node.path}/`));
}

export function flattenTree(nodes: WorkspaceNode[]): WorkspaceNode[] {
  const out: WorkspaceNode[] = [];
  const walk = (items: WorkspaceNode[]) => {
    for (const item of items) {
      out.push(item);
      if (item.children) walk(item.children);
    }
  };
  walk(nodes);
  return out;
}
