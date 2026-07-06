import React from "react";
import type { WorkspaceTask } from "@/types";
import { I } from "@/icons";
import {
  getTaskStatusColor,
  getTaskStatusText,
  shouldShowUploadProgress,
} from "./taskStatus";

interface Props {
  tasks: WorkspaceTask[];
  pendingUploadIds: Set<number>;
  uploadProgress: Map<number, number>;
  collapsed: boolean;
  hasMore: boolean;
  onToggle: () => void;
  onRefresh: () => void;
  onLoadMore: () => void;
}

function clampProgress(progress: number | null) {
  return Math.max(0, Math.min(100, Math.round(progress ?? 0)));
}

export default function WorkspaceTaskDrawer(props: Props) {
  const { tasks, collapsed, pendingUploadIds, uploadProgress } = props;

  if (collapsed) {
    return (
      <div
        style={{
          width: 40,
          borderLeft: "1px solid var(--line)",
          background: "var(--bg-2)",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          paddingTop: 12,
        }}
      >
        <button
          onClick={props.onToggle}
          title="展开任务"
          style={{
            background: "transparent",
            border: "none",
            color: "var(--ink-3)",
            cursor: "pointer",
            padding: 4,
            display: "flex",
          }}
        >
          <I.ChevronLeft size={16} />
        </button>
      </div>
    );
  }

  return (
    <div
      style={{
        width: 280,
        borderLeft: "1px solid var(--line)",
        background: "var(--bg-2)",
        display: "flex",
        flexDirection: "column",
      }}
    >
      {/* 任务列表头部保留刷新和收起入口 */}
      <div
        style={{
          height: 48,
          padding: "0 12px 0 16px",
          borderBottom: "1px solid var(--line)",
          display: "flex",
          alignItems: "center",
          gap: 8,
          flexShrink: 0,
        }}
      >
        <I.Server size={14} />
        <div
          style={{
            flex: 1,
            fontSize: 13,
            fontWeight: 600,
            color: "var(--ink)",
          }}
        >
          任务
        </div>
        <button onClick={props.onRefresh} title="刷新" style={iconBtnStyle}>
          <I.Refresh size={13} />
        </button>
        <button onClick={props.onToggle} title="收起" style={iconBtnStyle}>
          <I.ChevronRight size={16} />
        </button>
      </div>

      <div style={{ flex: 1, overflow: "auto" }}>
        {tasks.length === 0 && (
          <div
            style={{
              padding: 20,
              color: "var(--ink-3)",
              fontSize: 12.5,
              textAlign: "center",
            }}
          >
            暂无任务
          </div>
        )}
        {tasks.map((task) => {
          const pendingUpload = task.type === "upload" && pendingUploadIds.has(task.id);
          const status = getTaskStatusText(task, pendingUpload);
          const color = getTaskStatusColor(task, pendingUpload);
          const progress = clampProgress(
            task.type === "upload" && uploadProgress.has(task.id)
              ? uploadProgress.get(task.id) ?? task.progress
              : task.progress,
          );
          const showProgress = shouldShowUploadProgress(task, pendingUpload);

          return (
            <div
              key={task.task_key}
              style={{
                padding: "10px 12px",
                borderBottom: "1px solid var(--line)",
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  minWidth: 0,
                }}
              >
                <span
                  style={{
                    flexShrink: 0,
                    fontSize: 11,
                    lineHeight: "18px",
                    padding: "0 6px",
                    borderRadius: 4,
                    color: "var(--ink-3)",
                    background: "var(--bg)",
                    border: "1px solid var(--line)",
                  }}
                >
                  {task.type === "upload" ? "上传" : "转换"}
                </span>
                <div
                  style={{
                    minWidth: 0,
                    flex: 1,
                    fontSize: 12.5,
                    fontWeight: 500,
                    color: "var(--ink)",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                  title={task.name}
                >
                  {task.name}
                </div>
                <span
                  style={{
                    flexShrink: 0,
                    fontSize: 11,
                    color,
                    fontWeight: 600,
                  }}
                >
                  {showProgress ? `${status} ${progress}%` : status}
                </span>
              </div>
              <div
                style={{
                  fontSize: 11,
                  color: "var(--ink-4)",
                  marginTop: 5,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
                title={task.path}
              >
                {task.path}
              </div>
              {showProgress && (
                <div
                  style={{
                    height: 4,
                    borderRadius: 999,
                    background: "var(--line)",
                    overflow: "hidden",
                    marginTop: 8,
                  }}
                >
                  <div
                    style={{
                      width: `${progress}%`,
                      height: "100%",
                      background: "var(--accent)",
                    }}
                  />
                </div>
              )}
              {task.status === "failed" && task.error_message && (
                <div
                  style={{
                    fontSize: 11,
                    color: "var(--danger)",
                    marginTop: 5,
                    wordBreak: "break-word",
                  }}
                >
                  {task.error_message}
                </div>
              )}
            </div>
          );
        })}
        {props.tasks.length > 0 && (
          <div style={{ padding: "10px 12px", textAlign: "center" }}>
            {props.hasMore ? (
              <button
                onClick={props.onLoadMore}
                style={{
                  fontSize: 12.5,
                  color: "var(--accent-2)",
                  background: "transparent",
                  border: "none",
                  cursor: "pointer",
                  fontFamily: "inherit",
                  padding: "4px 8px",
                }}
              >
                显示更多
              </button>
            ) : (
              <span
                style={{
                  fontSize: 12,
                  color: "var(--ink-4)",
                }}
              >
                已显示全部
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

const iconBtnStyle: React.CSSProperties = {
  background: "transparent",
  border: "none",
  color: "var(--ink-3)",
  cursor: "pointer",
  padding: 4,
  display: "flex",
};
