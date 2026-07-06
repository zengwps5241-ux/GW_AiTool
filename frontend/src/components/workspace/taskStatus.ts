import type { WorkspaceTask } from "@/types";

const statusText: Record<WorkspaceTask["status"], string> = {
  queued: "等待中",
  running: "转换中",
  succeeded: "已完成",
  failed: "失败",
};

const statusColor: Record<WorkspaceTask["status"], string> = {
  queued: "var(--ink-3)",
  running: "var(--accent)",
  succeeded: "var(--success)",
  failed: "var(--danger)",
};

export function isTaskUploading(task: WorkspaceTask, pendingUpload: boolean) {
  // 本地队列已接收但后端状态仍停留在 queued 时,前端也应显示上传中。
  return task.type === "upload" && (task.status === "running" || (pendingUpload && task.status === "queued"));
}

export function getTaskStatusText(task: WorkspaceTask, pendingUpload: boolean) {
  if (isTaskUploading(task, pendingUpload)) {
    return "上传中";
  }
  return statusText[task.status];
}

export function getTaskStatusColor(task: WorkspaceTask, pendingUpload: boolean) {
  if (isTaskUploading(task, pendingUpload)) {
    return "var(--accent)";
  }
  return statusColor[task.status];
}

export function shouldShowUploadProgress(task: WorkspaceTask, pendingUpload: boolean) {
  return isTaskUploading(task, pendingUpload);
}
