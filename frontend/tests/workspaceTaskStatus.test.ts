import assert from "node:assert/strict";
import type { WorkspaceTask } from "../src/types";
import {
  getTaskStatusColor,
  getTaskStatusText,
  shouldShowUploadProgress,
} from "../src/components/workspace/taskStatus";

const queuedUploadTask: WorkspaceTask = {
  task_key: "upload:1",
  type: "upload",
  id: 1,
  name: "a.txt",
  path: "docs/a.txt",
  status: "queued",
  progress: 0,
  error_message: null,
  created_at: "2026-05-27T00:00:00Z",
  started_at: null,
  finished_at: null,
};

assert.equal(getTaskStatusText(queuedUploadTask, false), "等待中");
assert.equal(getTaskStatusText(queuedUploadTask, true), "上传中");
assert.equal(getTaskStatusColor(queuedUploadTask, true), "var(--accent)");
assert.equal(shouldShowUploadProgress(queuedUploadTask, true), true);

// 上传任务的本地进度应优先于后端旧值,避免面板一直停在 0%。
const localProgress = new Map<number, number>([[1, 37]]);
assert.equal(localProgress.get(queuedUploadTask.id), 37);
