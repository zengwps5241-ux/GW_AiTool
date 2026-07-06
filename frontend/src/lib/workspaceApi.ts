import { api, request } from "@/api/client";
import type {
  ConversionTask,
  UploadTask,
  UploadTaskCreateItem,
  WorkspaceKind,
  WorkspaceNode,
  WorkspaceTask,
} from "@/types";

const q = (path: string) => encodeURIComponent(path);

export interface WorkspaceApi {
  kind: WorkspaceKind;
  tree(): Promise<WorkspaceNode[]>;
  tasks(limit?: number, offset?: number): Promise<WorkspaceTask[]>;
  previewUrl(path: string): string;
  markdownPreviewUrl(path: string): string;
  officePreviewUrl(path: string): string;
  downloadUrl(path: string): string;
  markdownDownloadUrl(path: string): string;
  lockFile?(path: string): Promise<{ ok: boolean; path: string; lock_token: string; expires_at_ms: number }>;
  unlockFile?(path: string, lockToken: string): Promise<{ released: boolean }>;
  saveContent(path: string, content: string, lockToken?: string): Promise<{
    path: string;
    content: string;
    size: number;
    mtime?: number;
  }>;
  createItem(path: string, kind: "file" | "dir", content?: string): Promise<{ path: string }>;
  renameItem(path: string, newName: string): Promise<{ path: string }>;
  moveItem(path: string, targetDir: string): Promise<{ path: string }>;
  deleteItem(path: string): Promise<void>;
  retryConversion(sourcePath: string): Promise<ConversionTask>;
  createUploadTasks(targetDir: string, items: UploadTaskCreateItem[]): Promise<UploadTask[]>;
  uploadTaskFile(
    taskId: number,
    file: File,
    opts?: { onProgress?: (percent: number) => void },
  ): Promise<UploadTask>;
}

export function personalWorkspaceApi(): WorkspaceApi {
  return {
    kind: "personal",
    tree: api.workspaceTree,
    tasks: api.workspaceTasks,
    previewUrl: api.workspacePreviewUrl,
    markdownPreviewUrl: api.workspaceMarkdownPreviewUrl,
    officePreviewUrl: api.workspaceOfficePreviewUrl,
    downloadUrl: api.workspaceDownloadUrl,
    markdownDownloadUrl: api.workspaceMarkdownDownloadUrl,
    saveContent: (path, content) => api.workspaceSaveContent(path, content),
    createItem: api.workspaceCreateItem,
    renameItem: api.workspaceRenameItem,
    moveItem: api.workspaceMoveItem,
    deleteItem: api.deleteWorkspaceItem,
    retryConversion: api.retryConversion,
    createUploadTasks: api.createUploadTasks,
    uploadTaskFile: api.uploadTaskFile,
  };
}

export function teamWorkspaceApi(spaceId: number): WorkspaceApi {
  const prefix = `/api/team-spaces/${spaceId}`;
  const workspaceBase = `${prefix}/workspace`;
  const previewUrl = (path: string) => `${workspaceBase}/preview?path=${q(path)}`;
  const markdownPreviewUrl = (path: string) => `${workspaceBase}/markdown-preview?path=${q(path)}`;
  const officePreviewUrl = (path: string) => `${workspaceBase}/office-preview?path=${q(path)}`;
  const downloadUrl = (path: string) => `${workspaceBase}/download?path=${q(path)}`;

  return {
    kind: "team",
    tree: () => request<WorkspaceNode[]>(`${workspaceBase}/tree`),
    tasks: (limit?: number, offset?: number) => {
      const qs = new URLSearchParams();
      if (limit !== undefined) qs.set("limit", String(limit));
      if (offset !== undefined) qs.set("offset", String(offset));
      const query = qs.toString();
      return request<WorkspaceTask[]>(
        `${prefix}/workspace-tasks${query ? "?" + query : ""}`,
      );
    },
    previewUrl,
    markdownPreviewUrl,
    officePreviewUrl,
    downloadUrl,
    markdownDownloadUrl: downloadUrl,
    lockFile: (path: string) =>
      request<{ ok: boolean; path: string; lock_token: string; expires_at_ms: number }>(`${workspaceBase}/locks`, {
        method: "POST",
        body: JSON.stringify({ path }),
      }),
    unlockFile: (path: string, lockToken: string) =>
      request<{ released: boolean }>(`${workspaceBase}/locks`, {
        method: "DELETE",
        body: JSON.stringify({ path, lock_token: lockToken }),
      }),
    saveContent: (path: string, content: string, lockToken?: string) =>
      request(`${workspaceBase}/content`, {
        method: "PUT",
        body: JSON.stringify({ path, content, lock_token: lockToken }),
      }),
    createItem: (path: string, kind: "file" | "dir", content = "") =>
      request<{ path: string }>(`${workspaceBase}/file`, {
        method: "POST",
        body: JSON.stringify({ path, kind, content }),
      }),
    renameItem: (path: string, newName: string) =>
      request<{ path: string }>(`${workspaceBase}/file/rename`, {
        method: "PATCH",
        body: JSON.stringify({ path, new_name: newName }),
      }),
    moveItem: (path: string, targetDir: string) =>
      request<{ path: string }>(`${workspaceBase}/file/move`, {
        method: "PATCH",
        body: JSON.stringify({ path, target_dir: targetDir }),
      }),
    deleteItem: (path: string) =>
      request<void>(`${workspaceBase}/file?path=${q(path)}`, { method: "DELETE" }),
    retryConversion: (sourcePath: string) =>
      request<ConversionTask>(`${prefix}/conversion-tasks/retry`, {
        method: "POST",
        body: JSON.stringify({ source_path: sourcePath }),
      }),
    createUploadTasks: (targetDir: string, items: UploadTaskCreateItem[]) =>
      request<UploadTask[]>(`${prefix}/upload-tasks`, {
        method: "POST",
        body: JSON.stringify({ target_dir: targetDir, items }),
      }),
    uploadTaskFile: (taskId: number, file: File, opts = {}) =>
      api.uploadTaskFile(taskId, file, {
        ...opts,
        url: `${prefix}/upload-tasks/${taskId}/file`,
      }),
  };
}
