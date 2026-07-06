import { api } from "@/api/client";
import type { UploadTask } from "@/types";
import { getUploadFailureMessage } from "./uploadQueuePolicy";

export interface UploadQueueItem {
  task: UploadTask;
  file: File;
}

interface ProgressReport {
  lastReportedPercent: number;
  lastReportedAt: number;
  chain: Promise<void>;
}

let queue: UploadQueueItem[] = [];
let active = false;
const pendingIds = new Set<number>();
const uploadProgress = new Map<number, number>();
const progressReports = new Map<number, ProgressReport>();
const waitingResponseTimers = new Map<number, number>();
const listeners = new Set<() => void>();

const CLIENT_UPLOAD_COMPLETE_PERCENT = 80;
const WAITING_RESPONSE_MAX_PERCENT = 99;

function notify() {
  listeners.forEach((fn) => {
    try {
      fn();
    } catch {
      // 忽略订阅者抛出的异常，避免中断其他订阅者
    }
  });
}

export function subscribeUploadQueue(callback: () => void): () => void {
  listeners.add(callback);
  return () => listeners.delete(callback);
}

export function getUploadQueueState() {
  return {
    queueLength: queue.length,
    active,
    pendingIds: new Set(pendingIds),
    uploadProgress: new Map(uploadProgress),
  };
}

export function isUploadPending(taskId: number): boolean {
  return pendingIds.has(taskId);
}

function syncProgressToBackend(taskId: number, percent: number) {
  const report =
    progressReports.get(taskId) ??
    { lastReportedPercent: -1, lastReportedAt: 0, chain: Promise.resolve() };
  if (!progressReports.has(taskId)) progressReports.set(taskId, report);

  // 先更新本地进度态,保证任务面板能即时看到变化,再异步同步到后端。
  uploadProgress.set(taskId, percent);

  const now = Date.now();
  const increasedBy = percent - report.lastReportedPercent;
  if (increasedBy <= 0) return;
  if (
    percent !== 100 &&
    report.lastReportedPercent >= 0 &&
    increasedBy < 5 &&
    now - report.lastReportedAt < 500
  ) {
    return;
  }

  report.lastReportedPercent = percent;
  report.lastReportedAt = now;
  report.chain = report.chain
    .catch(() => undefined)
    .then(() => api.updateUploadTaskProgress(taskId, percent))
    .then(() => undefined, () => undefined);
}

function toDisplayUploadProgress(rawPercent: number) {
  // 浏览器上传完成不代表服务端保存完成,因此把客户端传输阶段压缩到 80%。
  return Math.min(
    CLIENT_UPLOAD_COMPLETE_PERCENT,
    Math.round((Math.max(0, Math.min(100, rawPercent)) * CLIENT_UPLOAD_COMPLETE_PERCENT) / 100),
  );
}

function startWaitingResponseProgress(taskId: number) {
  if (waitingResponseTimers.has(taskId)) return;
  const timer = window.setInterval(() => {
    const current = uploadProgress.get(taskId) ?? CLIENT_UPLOAD_COMPLETE_PERCENT;
    if (current >= WAITING_RESPONSE_MAX_PERCENT) {
      window.clearInterval(timer);
      waitingResponseTimers.delete(taskId);
      return;
    }
    syncProgressToBackend(taskId, current + 1);
    notify();
  }, 1000);
  waitingResponseTimers.set(taskId, timer);
}

function stopWaitingResponseProgress(taskId: number) {
  const timer = waitingResponseTimers.get(taskId);
  if (!timer) return;
  window.clearInterval(timer);
  waitingResponseTimers.delete(taskId);
}

async function drainQueue() {
  if (active) return;
  active = true;
  notify();

  try {
    while (queue.length > 0) {
      const next = queue.shift();
      if (!next) continue;
      pendingIds.add(next.task.id);
      notify();

      try {
        await api.uploadTaskFile(next.task.id, next.file, {
          onProgress: (percent) => {
            const displayPercent = toDisplayUploadProgress(percent);
            syncProgressToBackend(next.task.id, displayPercent);
            if (percent >= 100) {
              startWaitingResponseProgress(next.task.id);
            }
            notify();
          },
        });
      } catch (error) {
        // 普通上传异常也要结束未完成任务，但不能写成页面刷新导致中断。
        await progressReports.get(next.task.id)?.chain;
        try {
          await api.abandonUploadTasks([next.task.id], getUploadFailureMessage(error));
        } catch {
          // 忽略失败状态回写异常
        }
      } finally {
        stopWaitingResponseProgress(next.task.id);
        progressReports.delete(next.task.id);
        pendingIds.delete(next.task.id);
        uploadProgress.delete(next.task.id);
        notify();
      }
    }
  } finally {
    active = false;
    notify();
  }
}

export async function uploadFiles(
  targetDir: string,
  files: File[],
  relativePaths: string[],
): Promise<UploadTask[]> {
  if (files.length === 0) return [];

  const created = await api.createUploadTasks(
    targetDir,
    files.map((file, index) => ({
      filename: file.name,
      relative_path: relativePaths[index] || file.name,
      size: file.size,
    })),
  );

  created.forEach((task, index) => {
    const file = files[index];
    if (!file) return;
    queue.push({ task, file });
    pendingIds.add(task.id);
    uploadProgress.set(task.id, 0);
  });

  notify();
  void drainQueue();
  return created;
}

function abandonPendingUploads() {
  const ids = Array.from(pendingIds);
  if (ids.length === 0) return;
  const body = JSON.stringify({ ids });
  if (navigator.sendBeacon) {
    navigator.sendBeacon(
      "/api/upload-tasks/abandon",
      new Blob([body], { type: "application/json" }),
    );
    return;
  }
  void fetch("/api/upload-tasks/abandon", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
    keepalive: true,
  });
}

window.addEventListener("beforeunload", (e: BeforeUnloadEvent) => {
  if (pendingIds.size === 0) return;
  e.preventDefault();
  e.returnValue = "";
  abandonPendingUploads();
});
