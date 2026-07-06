import { useEffect, useMemo, useState } from "react";
import { api, fetchPreviewText } from "@/api/client";
import {
  isConvertibleName,
  workspacePreviewCategory,
  type WorkspacePreviewCategory,
} from "@/lib/workspace";

export interface WorkspacePreviewState {
  category: WorkspacePreviewCategory;
  shouldFetchText: boolean;
  loading: boolean;
  error: string | null;
  text: string | null;
  mime: string;
  resolvedPath: string | null;
}

interface WorkspacePreviewUrls {
  previewUrl(path: string): string;
  markdownPreviewUrl(path: string): string;
}

export function useWorkspacePreview(
  path: string | null,
  name: string | null,
  reloadKey = 0,
  source: "raw" | "markdown" = "raw",
  urls?: WorkspacePreviewUrls,
): WorkspacePreviewState {
  const category = useMemo(
    () => (name ? workspacePreviewCategory(name) : "unsupported"),
    [name],
  );
  const shouldFetchText = Boolean(
    name && (category === "text" || (source === "markdown" && isConvertibleName(name))),
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [text, setText] = useState<string | null>(null);
  const [mime, setMime] = useState("");
  const [resolvedPath, setResolvedPath] = useState<string | null>(null);
  const [loadedPath, setLoadedPath] = useState<string | null>(null);
  const [loadedName, setLoadedName] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    if (!path || !name) {
      setLoading(false);
      setError(null);
      setText(null);
      setMime("");
      setResolvedPath(null);
      setLoadedPath(null);
      setLoadedName(null);
      return;
    }

    const abort = new AbortController();
    setLoadedPath(path);
    setLoadedName(name);
    setError(null);
    setText(null);
    setMime("");
    setResolvedPath(null);

    if (!shouldFetchText) {
      setLoading(false);
      return () => {
        active = false;
        abort.abort();
      };
    }

    setLoading(true);
    (async () => {
      try {
        const url =
          source === "markdown"
            ? (urls?.markdownPreviewUrl ?? api.workspaceMarkdownPreviewUrl)(path)
            : (urls?.previewUrl ?? api.workspacePreviewUrl)(path);
        const result = await fetchPreviewText(url, abort.signal);
        if (!active) return;
        setMime(result.mime);
        setResolvedPath(result.resolvedPath);
        setText(result.text);
      } catch (e) {
        if (active && (e as Error).name !== "AbortError") {
          setError((e as Error).message);
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    })();

    return () => {
      active = false;
      abort.abort();
    };
  }, [path, name, shouldFetchText, reloadKey, source, urls]);

  // React 会先用新 path/name 渲染一帧，再执行 effect 清空旧内容。
  // 这里同步屏蔽不属于当前文件的预览数据，避免切换文件时短暂渲染上一个 Markdown 里的图片。
  const isCurrentPreview = loadedPath === path && loadedName === name;

  return {
    category,
    shouldFetchText,
    loading: shouldFetchText ? loading || !isCurrentPreview : loading,
    error: isCurrentPreview ? error : null,
    text: isCurrentPreview ? text : null,
    mime: isCurrentPreview ? mime : "",
    resolvedPath: isCurrentPreview ? resolvedPath : null,
  };
}
