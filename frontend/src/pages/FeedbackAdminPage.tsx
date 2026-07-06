import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import { api } from "@/api/client";
import type { FeedbackIssueDetail, FeedbackIssueListItem } from "@/types";
import { I } from "@/icons";
import { Btn, Card, ConfirmDialog, Spinner, Tag, useToast } from "@/components/ui";

const PAGE_SIZE = 12;

export default function FeedbackAdminPage() {
  const { showToast } = useToast();
  const [items, setItems] = useState<FeedbackIssueListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const selectedIdRef = useRef<number | null>(null);
  const [detail, setDetail] = useState<FeedbackIssueDetail | null>(null);
  const [listLoading, setListLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [previewImage, setPreviewImage] = useState<{
    url: string;
    filename: string;
  } | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<FeedbackIssueDetail | null>(null);
  const [deleting, setDeleting] = useState(false);

  const pageCount = useMemo(
    () => Math.max(1, Math.ceil(total / PAGE_SIZE)),
    [total],
  );

  useEffect(() => {
    selectedIdRef.current = selectedId;
  }, [selectedId]);

  const loadList = useCallback(async () => {
    setListLoading(true);
    setListError(null);
    try {
      const result = await api.adminFeedbackIssues(page, PAGE_SIZE);
      const nextPageCount = Math.max(1, Math.ceil(result.total / PAGE_SIZE));
      if (page > nextPageCount) {
        setItems([]);
        setTotal(result.total);
        setSelectedId(null);
        setDetail(null);
        setPage(nextPageCount);
        return;
      }
      setItems(result.items);
      setTotal(result.total);
      const currentId = selectedIdRef.current;
      const nextSelectedId =
        currentId && result.items.some((item) => item.id === currentId)
          ? currentId
          : result.items[0]?.id ?? null;
      selectedIdRef.current = nextSelectedId;
      setSelectedId(nextSelectedId);
      if (nextSelectedId !== currentId) {
        setDetail(null);
      }
    } catch (error) {
      const message = formatError(error);
      setListError(message);
      showToast(`加载反馈列表失败：${message}`, "error");
    } finally {
      setListLoading(false);
    }
  }, [page, showToast]);

  useEffect(() => {
    void loadList();
  }, [loadList]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    let alive = true;
    setDetailLoading(true);
    setDetailError(null);
    api
      .adminFeedbackIssue(selectedId)
      .then((data) => {
        if (alive) setDetail(data);
      })
      .catch((error) => {
        if (!alive) return;
        const message = formatError(error);
        setDetailError(message);
        showToast(`加载反馈详情失败：${message}`, "error");
      })
      .finally(() => {
        if (alive) setDetailLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [selectedId, showToast]);

  const goPage = (nextPage: number) => {
    if (nextPage < 1 || nextPage > pageCount || nextPage === page) return;
    setPage(nextPage);
    setSelectedId(null);
    setDetail(null);
  };

  const deleteIssue = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await api.deleteFeedbackIssue(deleteTarget.id);
      showToast("反馈已删除", "success");
      setDeleteTarget(null);
      setPreviewImage(null);
      setSelectedId(null);
      selectedIdRef.current = null;
      setDetail(null);
      await loadList();
    } catch (error) {
      showToast(`删除反馈失败：${formatError(error)}`, "error");
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
      <div
        style={{
          flex: 1,
          overflow: "auto",
          padding: "24px 28px",
          minWidth: 0,
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "flex-end",
            justifyContent: "space-between",
            marginBottom: 18,
            gap: 12,
            flexWrap: "wrap",
          }}
        >
          <div style={{ minWidth: 0 }}>
            <h1
              style={{
                fontFamily: "var(--serif)",
                fontSize: 24,
                fontWeight: 500,
                marginBottom: 4,
                color: "var(--ink)",
                letterSpacing: -0.01,
              }}
            >
              反馈管理{" "}
              <span
                style={{
                  fontSize: 14,
                  color: "var(--ink-3)",
                  fontWeight: 400,
                  fontFamily: "var(--sans)",
                }}
              >
                · 共 {total} 条
              </span>
            </h1>
            <div style={{ fontSize: 13, color: "var(--ink-3)" }}>
              查看用户提交的问题标题、提出人、提出时间和截图附件。
            </div>
          </div>
          <Btn
            variant="secondary"
            icon={<I.Refresh size={14} />}
            onClick={() => void loadList()}
            disabled={listLoading}
          >
            刷新
          </Btn>
        </div>

        <main
          style={{
            minHeight: 0,
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 360px), 1fr))",
            gap: 16,
            alignItems: "stretch",
          }}
        >
        <Card style={{ display: "flex", flexDirection: "column", minHeight: 520 }}>
          <div
            style={{
              padding: "14px 14px 10px",
              borderBottom: "1px solid var(--line)",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              gap: 12,
            }}
          >
            <div style={{ fontSize: 13, color: "var(--ink-2)", fontWeight: 600 }}>
              反馈列表
            </div>
            <Tag tone="neutral">{total} 条</Tag>
          </div>

          <div style={{ flex: 1, minHeight: 0, overflow: "auto", padding: 8 }}>
            {listLoading ? (
              <StateBlock icon={<Spinner />} text="正在加载反馈列表" />
            ) : listError ? (
              <StateBlock icon={<I.CircleAlert size={18} />} text={listError} />
            ) : items.length === 0 ? (
              <StateBlock icon={<I.MessageSquare size={18} />} text="暂无反馈" />
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {items.map((item) => {
                  const active = selectedId === item.id;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => setSelectedId(item.id)}
                      className="focus-ring"
                      style={{
                        textAlign: "left",
                        border: "1px solid",
                        borderColor: active ? "var(--line)" : "transparent",
                        background: active ? "var(--bg)" : "transparent",
                        boxShadow: active ? "var(--shadow-sm)" : "none",
                        borderRadius: 8,
                        padding: "10px 12px",
                        cursor: "pointer",
                        display: "flex",
                        flexDirection: "column",
                        gap: 7,
                      }}
                    >
                      <span
                        style={{
                          color: "var(--ink)",
                          fontSize: 14,
                          fontWeight: 600,
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {item.title}
                      </span>
                      <span
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          gap: 10,
                          color: "var(--ink-3)",
                          fontSize: 12,
                        }}
                      >
                        <span>{item.reporter_username}</span>
                        <span>{formatDate(item.created_at)}</span>
                      </span>
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          <footer
            style={{
              borderTop: "1px solid var(--line)",
              padding: 10,
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 10,
              flexShrink: 0,
            }}
          >
            <Btn
              size="sm"
              variant="ghost"
              onClick={() => goPage(page - 1)}
              disabled={page <= 1 || listLoading}
            >
              上一页
            </Btn>
            <span style={{ fontSize: 12, color: "var(--ink-3)" }}>
              {page} / {pageCount}
            </span>
            <Btn
              size="sm"
              variant="ghost"
              onClick={() => goPage(page + 1)}
              disabled={page >= pageCount || listLoading}
            >
              下一页
            </Btn>
          </footer>
        </Card>

        <Card style={{ minHeight: 520, overflow: "auto" }}>
          {detailLoading ? (
            <StateBlock icon={<Spinner />} text="正在加载反馈详情" />
          ) : detailError ? (
            <StateBlock icon={<I.CircleAlert size={18} />} text={detailError} />
          ) : !detail ? (
            <StateBlock icon={<I.MessageSquare size={18} />} text="请选择一条反馈" />
          ) : (
            <FeedbackDetailView
              detail={detail}
              onDelete={() => setDeleteTarget(detail)}
              onPreviewImage={(url, filename) => setPreviewImage({ url, filename })}
            />
          )}
        </Card>
        </main>
      </div>
      <ImagePreviewDialog
        image={previewImage}
        onClose={() => setPreviewImage(null)}
      />
      <ConfirmDialog
        open={!!deleteTarget}
        title="删除反馈"
        message={
          deleteTarget
            ? `确认删除反馈 "${deleteTarget.title}"？此操作会同时删除图片附件。`
            : ""
        }
        confirmText={deleting ? "删除中" : "删除"}
        onConfirm={() => void deleteIssue()}
        onCancel={() => {
          if (!deleting) setDeleteTarget(null);
        }}
        variant="danger"
      />
    </div>
  );
}

function FeedbackDetailView({
  detail,
  onDelete,
  onPreviewImage,
}: {
  detail: FeedbackIssueDetail;
  onDelete: () => void;
  onPreviewImage: (url: string, filename: string) => void;
}) {
  return (
    <article style={{ padding: 20, display: "flex", flexDirection: "column", gap: 18 }}>
      <header style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <h2
              style={{
                margin: 0,
                fontFamily: "var(--serif)",
                fontSize: 20,
                fontWeight: 600,
                color: "var(--ink)",
              }}
            >
              {detail.title}
            </h2>
          </div>
          <Btn
            size="sm"
            variant="danger"
            icon={<I.Trash size={14} />}
            onClick={onDelete}
          >
            删除
          </Btn>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <Tag tone="info">提出人：{detail.reporter_username}</Tag>
          <Tag tone="neutral">提出时间：{formatDate(detail.created_at)}</Tag>
          <Tag tone={detail.attachments.length ? "accent" : "neutral"}>
            附件：{detail.attachments.length}
          </Tag>
        </div>
      </header>

      <section>
        <h3 style={sectionTitleStyle}>详细描述</h3>
        <div
          style={{
            marginTop: 8,
            background: "var(--bg-2)",
            border: "1px solid var(--line)",
            borderRadius: 8,
            padding: 14,
            minHeight: 120,
            color: detail.description ? "var(--ink-2)" : "var(--ink-3)",
            whiteSpace: "pre-wrap",
            lineHeight: 1.65,
            fontSize: 14,
          }}
        >
          {detail.description || "用户未填写详细描述。"}
        </div>
      </section>

      <section>
        <h3 style={sectionTitleStyle}>图片附件</h3>
        {detail.attachments.length === 0 ? (
          <p style={{ margin: "8px 0 0", color: "var(--ink-3)", fontSize: 13 }}>
            暂无图片附件。
          </p>
        ) : (
          <div
            style={{
              marginTop: 10,
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))",
              gap: 12,
            }}
          >
            {detail.attachments.map((attachment) => {
              const url = attachment.url || api.adminFeedbackAttachmentUrl(attachment.id);
              return (
                <button
                  key={attachment.id}
                  type="button"
                  onClick={() => onPreviewImage(url, attachment.filename)}
                  className="focus-ring"
                  style={{
                    color: "inherit",
                    border: "1px solid var(--line)",
                    borderRadius: 8,
                    overflow: "hidden",
                    background: "var(--surface)",
                    padding: 0,
                    cursor: "pointer",
                    textAlign: "left",
                  }}
                >
                  <div style={{ aspectRatio: "4 / 3", background: "var(--bg-3)" }}>
                    <img
                      src={url}
                      alt={attachment.filename}
                      style={{ width: "100%", height: "100%", objectFit: "cover" }}
                    />
                  </div>
                  <div style={{ padding: "8px 10px", display: "grid", gap: 4 }}>
                    <span
                      style={{
                        fontSize: 12,
                        color: "var(--ink-2)",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {attachment.filename}
                    </span>
                    <span style={{ fontSize: 11, color: "var(--ink-3)" }}>
                      {formatBytes(attachment.size)}
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </section>
    </article>
  );
}

function ImagePreviewDialog({
  image,
  onClose,
}: {
  image: { url: string; filename: string } | null;
  onClose: () => void;
}) {
  useEffect(() => {
    if (!image) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [image, onClose]);

  if (!image) return null;
  return (
    <>
      <div
        onClick={onClose}
        style={{
          position: "fixed",
          inset: 0,
          background: "rgba(0,0,0,0.58)",
          zIndex: 70,
        }}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label="图片预览"
        style={{
          position: "fixed",
          inset: 0,
          zIndex: 71,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: 24,
          pointerEvents: "none",
        }}
      >
        <section
          style={{
            pointerEvents: "auto",
            width: "min(960px, 100%)",
            maxHeight: "calc(100vh - 48px)",
            background: "var(--bg)",
            border: "1px solid var(--line)",
            borderRadius: 12,
            boxShadow: "var(--shadow-lg)",
            overflow: "hidden",
            display: "flex",
            flexDirection: "column",
          }}
        >
          <header
            style={{
              height: 46,
              padding: "0 14px",
              borderBottom: "1px solid var(--line)",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 12,
            }}
          >
            <div
              style={{
                fontSize: 13,
                fontWeight: 600,
                color: "var(--ink)",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {image.filename}
            </div>
            <button
              type="button"
              onClick={onClose}
              className="focus-ring"
              title="关闭预览"
              style={{
                border: "none",
                background: "transparent",
                color: "var(--ink-3)",
                cursor: "pointer",
                padding: 6,
                borderRadius: 8,
                display: "flex",
              }}
            >
              <I.X size={16} />
            </button>
          </header>
          <div
            style={{
              minHeight: 240,
              maxHeight: "calc(100vh - 96px)",
              overflow: "auto",
              background: "var(--bg-2)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              padding: 16,
            }}
          >
            <img
              src={image.url}
              alt={image.filename}
              style={{
                maxWidth: "100%",
                maxHeight: "calc(100vh - 128px)",
                objectFit: "contain",
                borderRadius: 8,
              }}
            />
          </div>
        </section>
      </div>
    </>
  );
}

function StateBlock({ icon, text }: { icon: ReactNode; text: string }) {
  return (
    <div
      style={{
        minHeight: 180,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: 8,
        color: "var(--ink-3)",
        fontSize: 13,
        padding: 24,
      }}
    >
      {icon}
      <span>{text}</span>
    </div>
  );
}

const sectionTitleStyle = {
  margin: 0,
  color: "var(--ink)",
  fontSize: 14,
  fontWeight: 600,
} satisfies CSSProperties;

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function formatError(error: unknown): string {
  return error instanceof Error ? error.message : "未知错误";
}
