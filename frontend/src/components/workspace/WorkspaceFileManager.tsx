// 共享空间文件管理器:文件树 + 预览/编辑 + 任务列表
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import type { WorkspaceNode, WorkspaceTask } from "@/types";
import WorkspaceTree from "@/components/workspace/WorkspaceTree";
import WorkspacePreview from "@/components/workspace/WorkspacePreview";
import WorkspaceTaskDrawer from "@/components/workspace/WorkspaceTaskDrawer";
import { useWorkspacePreview } from "@/components/workspace/useWorkspacePreview";
import { Btn, Input, useToast } from "@/components/ui";
import { I } from "@/icons";
import type { WorkspaceApi } from "@/lib/workspaceApi";
import {
  isOfficeName,
  isPdfName,
  renameWorkspaceFileStem,
  splitWorkspaceFileName,
  uploadTargetForSelection,
} from "@/lib/workspace";
import { getUploadQueueState, subscribeUploadQueue, uploadFiles } from "@/lib/uploadQueue";

const TREE_MIN_WIDTH = 220;
const TREE_MAX_WIDTH = 520;
const TREE_DEFAULT_WIDTH = 300;

// 使用浏览器原生下载能力,避免把文件或目录压缩流读入前端内存。
function triggerWorkspaceDownload(url: string) {
  const a = document.createElement("a");
  a.href = url;
  a.rel = "noopener";
  a.download = "";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

function formatErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "操作失败，请稍后重试";
}

function isDuplicateConversionTaskError(error: unknown): boolean {
  const status = (error as { status?: number } | null)?.status;
  if (status !== 409) return false;
  const responseText = (error as { responseText?: string } | null)?.responseText;
  if (!responseText) return true;
  try {
    return JSON.parse(responseText).detail === "已存在转换任务";
  } catch {
    return true;
  }
}

function fileLockErrorMessage(error: unknown): string {
  const responseText = (error as { responseText?: string } | null)?.responseText;
  if (responseText) {
    try {
      const detail = JSON.parse(responseText).detail;
      if (detail?.code === "FILE_LOCK_EXPIRED") {
        return "编辑锁已失效，请重新进入编辑模式";
      }
      if (detail?.code === "FILE_LOCKED") {
        return "文件正在被其他用户或会话编辑";
      }
    } catch {
      // 保留原始错误格式化兜底。
    }
  }
  return formatErrorMessage(error);
}

function isFileLockError(error: unknown): boolean {
  const status = (error as { status?: number } | null)?.status;
  if (status !== 409) return false;
  const responseText = (error as { responseText?: string } | null)?.responseText;
  if (!responseText) return false;
  try {
    const code = JSON.parse(responseText).detail?.code;
    return code === "FILE_LOCK_EXPIRED" || code === "FILE_LOCKED";
  } catch {
    return false;
  }
}

function clampTreeWidth(width: number) {
  return Math.max(TREE_MIN_WIDTH, Math.min(TREE_MAX_WIDTH, Math.round(width)));
}

type WorkspaceDialogState =
  | {
      kind: "input";
      title: string;
      message?: string;
      label: string;
      initialValue: string;
      placeholder?: string;
      confirmText: string;
      onConfirm: (value: string) => void | Promise<void>;
    }
  | {
      kind: "confirm";
      title: string;
      message: string;
      confirmText: string;
      variant?: "primary" | "danger";
      onConfirm: () => void | Promise<void>;
    };

interface Props {
  title: string;
  api: WorkspaceApi;
  readonly?: boolean;
  readonlyReason?: string | null;
  onOpenDetail?: () => void;
  onOpenSessions?: () => void;
  headerActions?: ReactNode;
}

export default function WorkspaceFileManager({
  title,
  api,
  readonly = false,
  readonlyReason,
  onOpenDetail,
  onOpenSessions,
  headerActions,
}: Props) {
  const { showToast } = useToast();
  const [nodes, setNodes] = useState<WorkspaceNode[]>([]);
  const [tasks, setTasks] = useState<WorkspaceTask[]>([]);
  const [selected, setSelected] = useState<WorkspaceNode | null>(null);
  const [content, setContent] = useState("");
  const [dirty, setDirty] = useState(false);
  const [drawerCollapsed, setDrawerCollapsed] = useState(false);
  const [previewReloadKey, setPreviewReloadKey] = useState(0);
  const [previewMode, setPreviewMode] = useState<"preview" | "edit">("preview");
  const [fileLock, setFileLock] = useState<{ path: string; token: string } | null>(null);
  const [dialog, setDialog] = useState<WorkspaceDialogState | null>(null);
  const [hasMore, setHasMore] = useState(true);
  const [uploadQueueState, setUploadQueueState] = useState(getUploadQueueState());
  const [treeWidth, setTreeWidth] = useState(TREE_DEFAULT_WIDTH);
  const [resizingTree, setResizingTree] = useState(false);
  const workspaceLayoutRef = useRef<HTMLDivElement | null>(null);
  const lastAppliedPreviewRef = useRef<string | null>(null);
  const pendingUploadTargetRef = useRef<string | null>(null);
  const fileLockRef = useRef(fileLock);
  const tasksRef = useRef<WorkspaceTask[]>(tasks);
  tasksRef.current = tasks;
  fileLockRef.current = fileLock;

  const ensureWritable = useCallback(() => {
    if (!readonly) return true;
    showToast(readonlyReason || "当前空间只读，不能编辑文件", "info");
    return false;
  }, [readonly, readonlyReason, showToast]);

  const previewSource: "raw" | "markdown" =
    previewMode === "edit" && selected?.type === "file" && (isOfficeName(selected.name) || isPdfName(selected.name))
      ? "markdown"
      : "raw";

  const preview = useWorkspacePreview(
    selected?.type === "file" ? selected.path : null,
    selected?.type === "file" ? selected.name : null,
    previewReloadKey,
    previewSource,
    api,
  );

  const releaseCurrentLock = useCallback(async () => {
    const current = fileLockRef.current;
    if (!current || !api.unlockFile) return;
    setFileLock(null);
    try {
      await api.unlockFile(current.path, current.token);
    } catch {
      // 释放失败由 Redis TTL 兜底；前端不阻塞用户导航。
    }
  }, [api]);

  const loadTree = useCallback(async () => {
    try {
      setNodes(await api.tree());
    } catch (e) {
      // 忽略树加载错误,组件内部不显示全局错误
    }
  }, [api]);

  const loadTasks = useCallback(
    async (mode: "init" | "more" | "refresh") => {
      const currentLen = tasksRef.current.length;
      let limit: number;
      let offset: number;
      if (mode === "init") {
        limit = 10;
        offset = 0;
      } else if (mode === "more") {
        limit = 10;
        offset = currentLen;
      } else {
        limit = Math.max(10, currentLen);
        offset = 0;
      }
      try {
        const newTasks = await api.tasks(limit, offset);
        if (mode === "more") {
          setTasks((prev) => [...prev, ...newTasks]);
        } else {
          setTasks(newTasks);
        }
        setHasMore(newTasks.length === limit);
      } catch (e) {
        // 忽略任务加载错误
      }
    },
    [api],
  );

  useEffect(() => {
    loadTree();
    loadTasks("init");
  }, [loadTree, loadTasks]);

  const selectNode = useCallback((node: WorkspaceNode) => {
    setSelected(node);
    setDirty(false);
    setContent("");
    setPreviewMode("preview");
    lastAppliedPreviewRef.current = null;
  }, []);

  const confirmUnsaved = useCallback((onConfirm: () => void | Promise<void>) => {
    setDialog({
      kind: "confirm",
      title: "离开当前文件？",
      message: "当前文件尚未保存，离开后本次修改将丢失。",
      confirmText: "离开",
      variant: "danger",
      onConfirm,
    });
  }, []);

  const enterEditMode = useCallback(async () => {
    if (!selected || selected.type !== "file") return;
    if (!ensureWritable()) return;
    if (api.lockFile) {
      try {
        const current = fileLockRef.current;
        if (current && current.path !== selected.path) {
          await releaseCurrentLock();
        }
        if (fileLockRef.current?.path !== selected.path) {
          const locked = await api.lockFile(selected.path);
          setFileLock({ path: selected.path, token: locked.lock_token });
        }
      } catch (e) {
        showToast(`文件加锁失败：${fileLockErrorMessage(e)}`, "error");
        return;
      }
    }
    setPreviewMode("edit");
    setPreviewReloadKey((v) => v + 1);
  }, [api, ensureWritable, releaseCurrentLock, selected, showToast]);

  const switchMode = useCallback(
    async (mode: "preview" | "edit") => {
      const applyMode = async () => {
        if (mode === "edit") {
          await enterEditMode();
          return;
        }
        await releaseCurrentLock();
        setPreviewMode("preview");
        setPreviewReloadKey((v) => v + 1);
      };
      if (dirty) {
        confirmUnsaved(async () => {
          setDirty(false);
          setContent("");
          await applyMode();
        });
      } else {
        await applyMode();
      }
    },
    [dirty, confirmUnsaved, enterEditMode, releaseCurrentLock],
  );

  const openNode = useCallback(
    async (node: WorkspaceNode) => {
      if (selected?.path === node.path) {
        if (dirty) return;
        setSelected(node);
        lastAppliedPreviewRef.current = null;
        setPreviewReloadKey((v) => v + 1);
        return;
      }
      if (dirty) {
        confirmUnsaved(async () => {
          await releaseCurrentLock();
          selectNode(node);
        });
        return;
      }
      await releaseCurrentLock();
      selectNode(node);
    },
    [confirmUnsaved, dirty, releaseCurrentLock, selectNode, selected?.path],
  );

  const clearSelection = useCallback(() => {
    const clear = () => {
      void releaseCurrentLock();
      setSelected(null);
      setDirty(false);
      setContent("");
      lastAppliedPreviewRef.current = null;
    };
    if (dirty) {
      confirmUnsaved(clear);
      return false;
    }
    clear();
    return true;
  }, [confirmUnsaved, dirty, releaseCurrentLock]);

  useEffect(() => {
    if (dirty || preview.text === null || selected?.type !== "file") return;
    const previewKey = [
      selected.path,
      preview.resolvedPath || "",
      preview.text,
    ].join("\n");
    if (lastAppliedPreviewRef.current === previewKey) return;
    lastAppliedPreviewRef.current = previewKey;
    setContent(preview.text);
  }, [dirty, preview.resolvedPath, preview.text, selected?.path, selected?.type]);

  const upload = useCallback(
    async (targetDir: string, files: File[], relativePaths: string[]) => {
      if (!ensureWritable()) return;
      if (files.length === 0) return;
      try {
        const normalizedPaths = files.map((f, i) => relativePaths[i] || f.name);
        if (api.kind === "personal") {
          await uploadFiles(targetDir, files, normalizedPaths);
        } else {
          const tasks = await api.createUploadTasks(
            targetDir,
            files.map((file, index) => ({
              filename: file.name,
              relative_path: normalizedPaths[index] || file.name,
              size: file.size,
            })),
          );
          for (let index = 0; index < tasks.length; index += 1) {
            const task = tasks[index];
            const file = files[index];
            if (task && file) {
              await api.uploadTaskFile(task.id, file);
            }
          }
          await loadTree();
        }
        await loadTasks("refresh");
      } catch (e) {
        showToast(`创建上传任务失败：${formatErrorMessage(e)}`, "error");
      }
    },
    [api, ensureWritable, loadTasks, loadTree, showToast],
  );

  const openUploadPicker = useCallback((kind: "file" | "folder", targetDir: string) => {
    if (!ensureWritable()) return;
    pendingUploadTargetRef.current = targetDir;
    document
      .getElementById(kind === "file" ? "workspace-file-input" : "workspace-folder-input")
      ?.click();
  }, [ensureWritable]);

  const save = useCallback(async () => {
    if (!selected) return;
    if (!ensureWritable()) return;
    if (api.kind === "team" && !fileLock?.token) {
      showToast("编辑锁已失效，请重新进入编辑模式", "error");
      setPreviewMode("preview");
      return;
    }
    try {
      const saved = await api.saveContent(selected.path, content, fileLock?.token);
      setContent(saved.content);
      setDirty(false);
      setPreviewReloadKey((v) => v + 1);
      await loadTree();
    } catch (e) {
      if (isFileLockError(e)) {
        setFileLock(null);
        setPreviewMode("preview");
        showToast(fileLockErrorMessage(e), "error");
        return;
      }
      throw e;
    }
  }, [api, content, ensureWritable, fileLock?.token, loadTree, selected, showToast]);

  const retry = useCallback(
    async (path: string) => {
      if (!ensureWritable()) return;
      try {
        await api.retryConversion(path);
        await loadTasks("refresh");
        await loadTree();
      } catch (e) {
        if (isDuplicateConversionTaskError(e)) {
          showToast("已存在转换任务", "error");
          return;
        }
        showToast(`重试转换失败：${formatErrorMessage(e)}`, "error");
      }
    },
    [api, ensureWritable, loadTasks, loadTree, showToast],
  );

  const reconvertItem = useCallback(
    async (node: WorkspaceNode) => {
      if (!ensureWritable()) return;
      try {
        await api.retryConversion(node.path);
        await loadTasks("refresh");
        await loadTree();
        showToast("已进入转换任务", "success");
      } catch (e) {
        if (isDuplicateConversionTaskError(e)) {
          showToast("已存在转换任务", "error");
          return;
        }
        showToast(`重新转换失败：${formatErrorMessage(e)}`, "error");
      }
    },
    [api, ensureWritable, loadTasks, loadTree, showToast],
  );

  const convertedMarkdown = Boolean(
    previewMode === "edit" &&
      selected?.type === "file" &&
      preview.resolvedPath &&
      preview.resolvedPath !== selected.path,
  );

  // 未保存离开提示
  useEffect(() => {
    if (!dirty) return;
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [dirty]);

  useEffect(() => {
    return () => {
      const current = fileLockRef.current;
      if (current && api.unlockFile) {
        void api.unlockFile(current.path, current.token);
      }
    };
  }, [api]);

  // 订阅全局上传队列状态变化，上传完成时刷新文件树和任务列表。
  useEffect(() => {
    return subscribeUploadQueue(() => {
      setUploadQueueState(getUploadQueueState());
      void loadTree();
      void loadTasks("refresh");
    });
  }, [loadTree, loadTasks]);

  // 当任务列表中存在运行中任务时,定时轮询刷新状态,无需手动刷新即可看到转换失败/完成。
  useEffect(() => {
    const hasRunning = tasks.some((t) => t.status === "running");
    if (!hasRunning) return;
    const timer = setInterval(() => {
      void loadTasks("refresh");
    }, 3000);
    return () => clearInterval(timer);
  }, [tasks, loadTasks]);

  useEffect(() => {
    if (!resizingTree) return;
    const onMouseMove = (e: MouseEvent) => {
      const left = workspaceLayoutRef.current?.getBoundingClientRect().left ?? 0;
      setTreeWidth(clampTreeWidth(e.clientX - left));
    };
    const onMouseUp = () => setResizingTree(false);
    const previousCursor = document.body.style.cursor;
    const previousUserSelect = document.body.style.userSelect;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    return () => {
      document.body.style.cursor = previousCursor;
      document.body.style.userSelect = previousUserSelect;
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
  }, [resizingTree]);

  const createFile = async (parentDir: string) => {
    if (!ensureWritable()) return;
    setDialog({
      kind: "input",
      title: "新建文件",
      message: parentDir ? `位置: ${parentDir}` : "位置: 根目录",
      label: "文件名",
      initialValue: "",
      placeholder: "例如 notes.md",
      confirmText: "创建",
      onConfirm: async (name) => {
        const path = parentDir ? `${parentDir}/${name}` : name;
        await api.createItem(path, "file", "");
        await loadTree();
      },
    });
  };

  const createDir = async (parentDir: string) => {
    if (!ensureWritable()) return;
    setDialog({
      kind: "input",
      title: "新建文件夹",
      message: parentDir ? `位置: ${parentDir}` : "位置: 根目录",
      label: "文件夹名",
      initialValue: "",
      placeholder: "新建文件夹",
      confirmText: "创建",
      onConfirm: async (name) => {
        const path = parentDir ? `${parentDir}/${name}` : name;
        await api.createItem(path, "dir");
        await loadTree();
      },
    });
  };

  const renameItem = async (node: WorkspaceNode) => {
    if (!ensureWritable()) return;
    const fileNameParts =
      node.type === "file" ? splitWorkspaceFileName(node.name) : null;
    const defaultName = fileNameParts?.stem ?? node.name;
    setDialog({
      kind: "input",
      title: "重命名",
      message:
        node.type === "file" && fileNameParts?.suffix
          ? `后缀 ${fileNameParts.suffix} 将保持不变`
          : undefined,
      label: node.type === "file" ? "文件名" : "文件夹名",
      initialValue: defaultName,
      confirmText: "保存",
      onConfirm: async (name) => {
        if (name === defaultName) return;
        // 文件重命名只允许修改主体名称,保留原始后缀不变。
        const nextName =
          node.type === "file" ? renameWorkspaceFileStem(node.name, name) : name;
        if (nextName === node.name) return;
        await api.renameItem(node.path, nextName);
        if (selected?.path === node.path) {
          await releaseCurrentLock();
          setSelected(null);
        }
        await loadTree();
      },
    });
  };

  const moveItemTo = async (node: WorkspaceNode, targetDir: string) => {
    if (!ensureWritable()) return;
    await api.moveItem(node.path, targetDir);
    if (selected?.path === node.path) {
      await releaseCurrentLock();
      setSelected(null);
    }
    await loadTree();
  };

  const downloadItem = (node: WorkspaceNode) => {
    if (node.type !== "dir") {
      triggerWorkspaceDownload(api.downloadUrl(node.path));
      return;
    }
    setDialog({
      kind: "confirm",
      title: "下载文件夹",
      message: "即将压缩目录并下载，下载过程由浏览器接管。",
      confirmText: "下载",
      onConfirm: () => triggerWorkspaceDownload(api.downloadUrl(node.path)),
    });
  };

  const downloadMarkdownItem = (node: WorkspaceNode) => {
    if (!node.markdown_path && !node.agent_path) {
      showToast("尚未生成转换后的 Markdown，请等待转换完成或重新转换。", "error");
      return;
    }
    triggerWorkspaceDownload(api.markdownDownloadUrl(node.path));
  };

  return (
    <div
      ref={workspaceLayoutRef}
      style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column", background: "var(--bg)" }}
    >
      <div
        style={{
          height: 48,
          display: "flex",
          alignItems: "center",
          gap: 10,
          padding: "0 16px",
          borderBottom: "1px solid var(--line)",
          flexShrink: 0,
        }}
      >
        <div style={{ flex: 1, minWidth: 0, fontSize: 15, fontWeight: 700 }}>
          {title}
        </div>
        {readonly && (
          <span
            style={{
              color: "var(--ink-3)",
              fontSize: 12,
              border: "1px solid var(--line)",
              borderRadius: 999,
              padding: "3px 8px",
              background: "var(--bg-2)",
            }}
            title={readonlyReason || "当前空间只读"}
          >
            只读
          </span>
        )}
        {headerActions}
        {onOpenSessions && (
          <Btn
            size="sm"
            variant="secondary"
            icon={<I.MessagesSquare size={14} />}
            onClick={onOpenSessions}
          >
            会话列表
          </Btn>
        )}
        {onOpenDetail && (
          <Btn
            size="sm"
            variant="secondary"
            icon={<I.ExternalLink size={14} />}
            onClick={onOpenDetail}
          >
            空间详情
          </Btn>
        )}
      </div>
      <div style={{ flex: 1, minHeight: 0, display: "flex" }}>
        <div
          style={{
            width: treeWidth,
            flex: `0 0 ${treeWidth}px`,
            borderRight: "1px solid var(--line)",
            background: "var(--bg-2)",
            display: "flex",
            flexDirection: "column",
          }}
        >
        <input
          id="workspace-file-input"
          type="file"
          multiple
          style={{ display: "none" }}
          onChange={(e) => {
            const files = Array.from(e.target.files || []);
            const targetDir =
              pendingUploadTargetRef.current ?? uploadTargetForSelection(selected);
            pendingUploadTargetRef.current = null;
            upload(
              targetDir,
              files,
              files.map(
                (f) =>
                  (f as File & { webkitRelativePath?: string })
                    .webkitRelativePath || f.name,
              ),
            );
            e.currentTarget.value = "";
          }}
        />
        <input
          id="workspace-folder-input"
          type="file"
          multiple
          // @ts-expect-error webkitdirectory 是 Chromium 的目录选择能力
          webkitdirectory=""
          style={{ display: "none" }}
          onChange={(e) => {
            const files = Array.from(e.target.files || []);
            const targetDir =
              pendingUploadTargetRef.current ?? uploadTargetForSelection(selected);
            pendingUploadTargetRef.current = null;
            upload(
              targetDir,
              files,
              files.map(
                (f) =>
                  (f as File & { webkitRelativePath?: string })
                    .webkitRelativePath || f.name,
              ),
            );
            e.currentTarget.value = "";
          }}
        />
        <WorkspaceTree
          nodes={nodes}
          selectedPath={selected?.path ?? null}
          readonly={readonly}
          onSelect={openNode}
          onDropFiles={upload}
          onPreview={openNode}
          onDownload={downloadItem}
          onDownloadMarkdown={downloadMarkdownItem}
          onReconvert={reconvertItem}
          onDelete={async (node) => {
            if (!ensureWritable()) return;
            setDialog({
              kind: "confirm",
              title: "删除项目",
              message: `确认删除 "${node.name}"？此操作不可恢复。`,
              confirmText: "删除",
              variant: "danger",
              onConfirm: async () => {
                if (!ensureWritable()) return;
                await api.deleteItem(node.path);
                if (selected?.path === node.path) {
                  await releaseCurrentLock();
                  setSelected(null);
                }
                await loadTree();
              },
            });
          }}
          onCreateFile={createFile}
          onCreateDir={createDir}
          onRename={renameItem}
          onMoveTo={moveItemTo}
          onUploadFile={(targetDir) => openUploadPicker("file", targetDir)}
          onUploadFolder={(targetDir) => openUploadPicker("folder", targetDir)}
          onClearSelection={clearSelection}
        />
        </div>
        <div
          role="separator"
          aria-orientation="vertical"
          aria-label="调整文件树宽度"
          tabIndex={0}
          title="拖拽调整文件树宽度"
          onMouseDown={(e) => {
            e.preventDefault();
            setResizingTree(true);
          }}
          onKeyDown={(e) => {
            if (e.key === "ArrowLeft") {
              e.preventDefault();
              setTreeWidth((width) => clampTreeWidth(width - 16));
            }
            if (e.key === "ArrowRight") {
              e.preventDefault();
              setTreeWidth((width) => clampTreeWidth(width + 16));
            }
          }}
          style={{
            width: 6,
            flex: "0 0 6px",
            cursor: "col-resize",
            background: resizingTree ? "var(--accent-soft)" : "transparent",
            borderRight: resizingTree ? "1px solid var(--accent)" : "1px solid transparent",
          }}
        />
        <WorkspacePreview
          node={selected}
          preview={preview}
          content={content}
          dirty={dirty}
          convertedMarkdown={convertedMarkdown}
          mode={previewMode}
          readonly={readonly}
          workspaceApi={api}
          onChange={(v) => {
            if (readonly) return;
            setContent(v);
            setDirty(true);
          }}
          onSave={save}
          onReload={() => {
            if (!selected) return;
            setDirty(false);
            lastAppliedPreviewRef.current = null;
            setPreviewReloadKey((v) => v + 1);
          }}
          onSwitchMode={() => switchMode(previewMode === "preview" ? "edit" : "preview")}
          onRetryConversion={retry}
        />
        <WorkspaceTaskDrawer
          tasks={tasks}
          pendingUploadIds={uploadQueueState.pendingIds}
          uploadProgress={uploadQueueState.uploadProgress}
          collapsed={drawerCollapsed}
          hasMore={hasMore}
          onToggle={() => setDrawerCollapsed((v) => !v)}
          onRefresh={() => loadTasks("refresh")}
          onLoadMore={() => loadTasks("more")}
        />
      </div>
      <WorkspaceDialog state={dialog} onClose={() => setDialog(null)} />
    </div>
  );
}

function WorkspaceDialog({
  state,
  onClose,
}: {
  state: WorkspaceDialogState | null;
  onClose: () => void;
}) {
  const [value, setValue] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (state?.kind === "input") {
      setValue(state.initialValue);
    }
    setSubmitting(false);
  }, [state]);

  useEffect(() => {
    if (!state) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose, state]);

  if (!state) return null;

  const runConfirm = async () => {
    if (submitting) return;
    if (state.kind === "input" && !value.trim()) return;
    setSubmitting(true);
    try {
      if (state.kind === "input") {
        await state.onConfirm(value.trim());
      } else {
        await state.onConfirm();
      }
      onClose();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <div
        onClick={onClose}
        style={{
          position: "fixed",
          inset: 0,
          background: "rgba(0,0,0,0.32)",
          zIndex: 80,
        }}
      />
      <div
        role="dialog"
        aria-modal="true"
        style={{
          position: "fixed",
          inset: 0,
          zIndex: 81,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: 24,
          pointerEvents: "none",
        }}
      >
        <div
          style={{
            pointerEvents: "auto",
            width: "min(420px, 100%)",
            background: "var(--bg)",
            border: "1px solid var(--line)",
            borderRadius: 12,
            boxShadow: "var(--shadow-lg)",
            padding: "22px 20px 18px",
            display: "flex",
            flexDirection: "column",
            gap: 16,
          }}
        >
          <div style={{ display: "grid", gap: 6 }}>
            <h3
              style={{
                margin: 0,
                fontFamily: "var(--serif)",
                fontSize: 16,
                fontWeight: 500,
                color: "var(--ink)",
              }}
            >
              {state.title}
            </h3>
            {state.message && (
              <p style={{ margin: 0, fontSize: 13.5, color: "var(--ink-2)", lineHeight: 1.55 }}>
                {state.message}
              </p>
            )}
          </div>

          {state.kind === "input" && (
            <label style={{ display: "grid", gap: 6 }}>
              <span style={{ fontSize: 12.5, color: "var(--ink-3)" }}>
                {state.label}
              </span>
              <Input
                value={value}
                placeholder={state.placeholder}
                autoFocus
                onChange={(e) => setValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void runConfirm();
                }}
              />
            </label>
          )}

          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
            <Btn variant="ghost" onClick={onClose} disabled={submitting}>
              取消
            </Btn>
            <Btn
              variant={state.kind === "confirm" ? state.variant ?? "primary" : "primary"}
              onClick={() => void runConfirm()}
              disabled={submitting || (state.kind === "input" && !value.trim())}
            >
              {state.confirmText}
            </Btn>
          </div>
        </div>
      </div>
    </>
  );
}
