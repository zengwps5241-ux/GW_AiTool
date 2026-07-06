import React, { useEffect, useRef, useState } from "react";
import type { WorkspaceNode } from "@/types";
import { I } from "@/icons";
import { formatBytes } from "./format";
import { canMoveWorkspaceNode, isConvertibleName } from "@/lib/workspace";
import FileNameTooltip from "@/components/workspace/FileNameTooltip";

interface Props {
  nodes: WorkspaceNode[];
  selectedPath: string | null;
  readonly?: boolean;
  onSelect: (node: WorkspaceNode) => void;
  onDropFiles: (targetDir: string, files: File[], relativePaths: string[]) => void;
  onPreview: (node: WorkspaceNode) => void;
  onDownload: (node: WorkspaceNode) => void;
  onDownloadMarkdown?: (node: WorkspaceNode) => void;
  onReconvert?: (node: WorkspaceNode) => void;
  onDelete: (node: WorkspaceNode) => void;
  onCreateFile?: (parentDir: string) => void;
  onCreateDir?: (parentDir: string) => void;
  onRename?: (node: WorkspaceNode) => void;
  onMoveTo?: (node: WorkspaceNode, targetDir: string) => void;
  onUploadFile?: (targetDir: string) => void;
  onUploadFolder?: (targetDir: string) => void;
  onClearSelection?: () => boolean;
}

interface ContextMenuState {
  x: number;
  y: number;
  node: WorkspaceNode | null;
}

const WORKSPACE_DRAG_TYPE = "application/x-workspace-node";

export default function WorkspaceTree(props: Props) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null);
  const [activeDropPath, setActiveDropPath] = useState<string | null>(null);
  const closeContextMenu = () => setContextMenu(null);

  useEffect(() => {
    setExpanded((prev) => {
      const next = new Set(prev);
      props.nodes.forEach((n) => n.type === "dir" && next.add(n.path));
      return next;
    });
  }, [props.nodes]);

  useEffect(() => {
    if (!contextMenu) return;
    const onKeyDown = (e: KeyboardEvent) => e.key === "Escape" && closeContextMenu();
    window.addEventListener("click", closeContextMenu);
    window.addEventListener("scroll", closeContextMenu, true);
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("click", closeContextMenu);
      window.removeEventListener("scroll", closeContextMenu, true);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [contextMenu]);

  const toggle = (path: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(path) ? next.delete(path) : next.add(path);
      return next;
    });

  return (
    <div
      style={{ flex: 1, overflow: "auto", padding: 8 }}
      onDragOver={(e) => {
        if (props.readonly) return;
        e.preventDefault();
        setActiveDropPath(null);
        e.dataTransfer.dropEffect = e.dataTransfer.types.includes(WORKSPACE_DRAG_TYPE)
          ? "move"
          : "copy";
      }}
      onDragLeave={(e) => {
        if (e.currentTarget.contains(e.relatedTarget as Node | null)) return;
        setActiveDropPath(null);
      }}
      onDrop={(e) => {
        if (props.readonly) return;
        e.preventDefault();
        setActiveDropPath(null);
        const draggedNode = readDraggedWorkspaceNode(e.dataTransfer);
        if (draggedNode) {
          if (canMoveWorkspaceNode(draggedNode, "")) {
            props.onMoveTo?.(draggedNode, "");
          }
          return;
        }
        const files = Array.from(e.dataTransfer.files);
        if (!files.length) return;
        props.onDropFiles(
          "",
          files,
          files.map(
            (f) =>
              (f as File & { webkitRelativePath?: string }).webkitRelativePath ||
              f.name,
          ),
        );
      }}
      onContextMenu={(e) => {
        e.preventDefault();
        if (props.readonly) return;
        const cleared = props.onClearSelection?.() ?? true;
        if (!cleared) return;
        setContextMenu({ x: e.clientX, y: e.clientY, node: null });
      }}
    >
      {props.nodes.map((node) => (
        <TreeRow
          key={node.path}
          node={node}
          depth={0}
          expanded={expanded}
          activeDropPath={activeDropPath}
          setActiveDropPath={setActiveDropPath}
          onToggle={toggle}
          onOpenContextMenu={(node, e) => {
            e.preventDefault();
            e.stopPropagation();
            props.onSelect(node);
            setContextMenu({ x: e.clientX, y: e.clientY, node });
          }}
          {...props}
        />
      ))}
      {contextMenu && (
        <WorkspaceContextMenu
          menu={contextMenu}
          onClose={closeContextMenu}
          readonly={props.readonly}
          onUploadFile={props.onUploadFile}
          onUploadFolder={props.onUploadFolder}
          onDownload={props.onDownload}
          onDownloadMarkdown={props.onDownloadMarkdown}
          onReconvert={props.onReconvert}
          onCreateFile={props.onCreateFile}
          onCreateDir={props.onCreateDir}
          onRename={props.onRename}
          onDelete={props.onDelete}
        />
      )}
    </div>
  );
}

function TreeRow(
  props: Omit<Props, "selectedPath"> & {
    node: WorkspaceNode;
    depth: number;
    expanded: Set<string>;
    activeDropPath: string | null;
    selectedPath: string | null;
    setActiveDropPath: (path: string | null) => void;
    onToggle: (path: string) => void;
    onOpenContextMenu: (node: WorkspaceNode, e: React.MouseEvent) => void;
  },
) {
  const { node } = props;
  const pressTimerRef = useRef<number | null>(null);
  const [dragEnabled, setDragEnabled] = useState(false);
  const open = node.type === "dir" && props.expanded.has(node.path);
  const selected = props.selectedPath === node.path;
  const dropActive = props.activeDropPath === node.path;
  const clearPressTimer = () => {
    if (pressTimerRef.current !== null) {
      window.clearTimeout(pressTimerRef.current);
      pressTimerRef.current = null;
    }
  };
  const isWorkspaceDrag = (e: React.DragEvent) =>
    e.dataTransfer.types.includes(WORKSPACE_DRAG_TYPE);

  return (
    <>
      <div
        onClick={() => props.onSelect(node)}
        onContextMenu={(e) => props.onOpenContextMenu(node, e)}
        onDoubleClick={() => node.type === "dir" && props.onToggle(node.path)}
        draggable={dragEnabled}
        onMouseDown={(e) => {
          if (props.readonly) return;
          if (e.button !== 0) return;
          clearPressTimer();
          pressTimerRef.current = window.setTimeout(() => {
            setDragEnabled(true);
          }, 50);
        }}
        onMouseUp={() => {
          clearPressTimer();
          setDragEnabled(false);
        }}
        onMouseLeave={clearPressTimer}
        onDragStart={(e) => {
          clearPressTimer();
          if (!dragEnabled) {
            e.preventDefault();
            return;
          }
          e.dataTransfer.effectAllowed = "move";
          e.dataTransfer.setData(
            WORKSPACE_DRAG_TYPE,
            JSON.stringify({ path: node.path, name: node.name, type: node.type }),
          );
        }}
        onDragEnd={() => {
          clearPressTimer();
          setDragEnabled(false);
          props.setActiveDropPath(null);
        }}
        onDragEnter={(e) => {
          if (props.readonly) return;
          if (node.type !== "dir") return;
          e.preventDefault();
          e.stopPropagation();
          props.setActiveDropPath(node.path);
        }}
        onDragOver={(e) => {
          if (props.readonly) return;
          if (node.type !== "dir") {
            e.preventDefault();
            e.stopPropagation();
            props.setActiveDropPath(null);
            e.dataTransfer.dropEffect = "none";
            return;
          }
          e.preventDefault();
          e.stopPropagation();
          e.dataTransfer.dropEffect = isWorkspaceDrag(e) ? "move" : "copy";
          props.setActiveDropPath(node.path);
        }}
        onDrop={(e) => {
          if (props.readonly) return;
          e.preventDefault();
          e.stopPropagation();
          if (node.type !== "dir") return;
          props.setActiveDropPath(null);
          const draggedNode = readDraggedWorkspaceNode(e.dataTransfer);
          if (draggedNode) {
            if (canMoveWorkspaceNode(draggedNode, node.path)) {
              props.onMoveTo?.(draggedNode, node.path);
            }
            return;
          }
          const files = Array.from(e.dataTransfer.files);
          props.onDropFiles(
            node.path,
            files,
            files.map(
              (f) =>
                (f as File & { webkitRelativePath?: string }).webkitRelativePath ||
                f.name,
            ),
          );
        }}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          minHeight: node.type === "dir" ? 36 : 30,
          padding: node.type === "dir" ? "8px 8px" : "5px 8px",
          paddingLeft: 8 + props.depth * 14,
          background: dropActive
            ? "var(--accent-soft)"
            : selected
              ? "var(--surface)"
              : "transparent",
          border: "1px solid",
          borderColor: dropActive ? "var(--accent)" : selected ? "var(--line)" : "transparent",
          borderRadius: 6,
          boxShadow: dropActive ? "inset 0 0 0 1px var(--accent)" : "none",
          cursor: dragEnabled ? "grab" : "pointer",
        }}
      >
        <button
          onClick={(e) => {
            e.stopPropagation();
            node.type === "dir" && props.onToggle(node.path);
          }}
          style={{ border: 0, background: "transparent", display: "flex" }}
        >
          {node.type === "dir" ? (
            open ? (
              <I.ChevronDown size={12} />
            ) : (
              <I.ChevronRight size={12} />
            )
          ) : (
            <span style={{ width: 12 }} />
          )}
        </button>
        {node.type === "dir" ? <I.Folder size={14} /> : <I.File size={14} />}
        <FileNameTooltip
          label={node.name}
          style={{
            flex: 1,
            minWidth: 0,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            display: "block",
          }}
        >
          {node.name}
        </FileNameTooltip>
        {node.type === "file" && typeof node.size === "number" && (
          <span style={{ fontSize: 11, color: "var(--ink-4)" }}>
            {formatBytes(node.size)}
          </span>
        )}
      </div>
      {open &&
        node.children?.map((child) => (
          <TreeRow
            key={child.path}
            {...props}
            node={child}
            depth={props.depth + 1}
          />
        ))}
    </>
  );
}

function readDraggedWorkspaceNode(dataTransfer: DataTransfer): WorkspaceNode | null {
  const raw = dataTransfer.getData(WORKSPACE_DRAG_TYPE);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as WorkspaceNode;
  } catch {
    return null;
  }
}

function WorkspaceContextMenu(props: {
  menu: ContextMenuState;
  onClose: () => void;
  readonly?: boolean;
  onUploadFile?: (targetDir: string) => void;
  onUploadFolder?: (targetDir: string) => void;
  onDownload: (node: WorkspaceNode) => void;
  onDownloadMarkdown?: (node: WorkspaceNode) => void;
  onReconvert?: (node: WorkspaceNode) => void;
  onCreateFile?: (parentDir: string) => void;
  onCreateDir?: (parentDir: string) => void;
  onRename?: (node: WorkspaceNode) => void;
  onDelete?: (node: WorkspaceNode) => void;
}) {
  const { node } = props.menu;
  const canWrite = !props.readonly;
  const targetDir = node?.type === "dir" ? node.path : "";
  const canDownloadMarkdown = Boolean(
    node?.type === "file" &&
      isConvertibleName(node.name) &&
      props.onDownloadMarkdown,
  );
  const canReconvert = Boolean(
    node?.type === "file" &&
      isConvertibleName(node.name) &&
      props.onReconvert,
  );
  const run = (action?: () => void) => {
    props.onClose();
    action?.();
  };
  return (
    <div
      onClick={(e) => e.stopPropagation()}
      onContextMenu={(e) => e.stopPropagation()}
      style={{
        position: "fixed",
        left: props.menu.x,
        top: props.menu.y,
        zIndex: 1000,
        minWidth: 156,
        padding: 4,
        background: "var(--surface)",
        border: "1px solid var(--line)",
        borderRadius: 8,
        boxShadow: "0 12px 28px rgba(15, 23, 42, 0.16)",
      }}
    >
      {(!node || node.type === "dir") && (
        <>
          {canWrite && (
            <>
              <ContextMenuItem icon={<I.Upload size={13} />} onClick={() => run(() => props.onUploadFile?.(targetDir))}>
                上传文件
              </ContextMenuItem>
              <ContextMenuItem icon={<I.FolderOpen size={13} />} onClick={() => run(() => props.onUploadFolder?.(targetDir))}>
                上传文件夹
              </ContextMenuItem>
            </>
          )}
          {node && (
            <ContextMenuItem icon={<I.Download size={13} />} onClick={() => run(() => props.onDownload(node))}>
              下载文件夹
            </ContextMenuItem>
          )}
          {canWrite && (
            <>
              <MenuDivider />
              <ContextMenuItem icon={<I.File size={13} />} onClick={() => run(() => props.onCreateFile?.(targetDir))}>
                创建文件
              </ContextMenuItem>
              <ContextMenuItem icon={<I.Folder size={13} />} onClick={() => run(() => props.onCreateDir?.(targetDir))}>
                创建文件夹
              </ContextMenuItem>
            </>
          )}
          {node && (canWrite || node.type === "file") && <MenuDivider />}
        </>
      )}
      {node && (
        <>
          {node.type === "file" && (
            <>
              <ContextMenuItem icon={<I.Download size={13} />} onClick={() => run(() => props.onDownload(node))}>
                下载源文件
              </ContextMenuItem>
              {canDownloadMarkdown && (
                <ContextMenuItem icon={<I.File size={13} />} onClick={() => run(() => props.onDownloadMarkdown?.(node))}>
                  下载Markdown
                </ContextMenuItem>
              )}
              {canWrite && canReconvert && (
                <ContextMenuItem icon={<I.Refresh size={13} />} onClick={() => run(() => props.onReconvert?.(node))}>
                  重新转换格式
                </ContextMenuItem>
              )}
              {canWrite && <MenuDivider />}
            </>
          )}
          {canWrite && (
            <>
              <ContextMenuItem icon={<I.Edit size={13} />} onClick={() => run(() => props.onRename?.(node))}>
                重命名
              </ContextMenuItem>
              <ContextMenuItem icon={<I.Trash size={13} />} danger onClick={() => run(() => props.onDelete?.(node))}>
                删除
              </ContextMenuItem>
            </>
          )}
        </>
      )}
    </div>
  );
}

function ContextMenuItem(props: {
  children: React.ReactNode;
  icon: React.ReactNode;
  danger?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={props.onClick}
      style={{
        width: "100%",
        height: 30,
        padding: "0 8px",
        display: "flex",
        alignItems: "center",
        gap: 8,
        border: 0,
        borderRadius: 6,
        background: "transparent",
        color: props.danger ? "var(--danger)" : "var(--ink-2)",
        cursor: "pointer",
        fontSize: 12.5,
        fontFamily: "inherit",
        textAlign: "left",
      }}
    >
      {props.icon}
      <span>{props.children}</span>
    </button>
  );
}

function MenuDivider() {
  return <div style={{ height: 1, margin: "4px 2px", background: "var(--line)" }} />;
}
