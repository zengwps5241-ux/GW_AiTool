import { useEffect, useMemo, useRef, useState } from "react";
import type { ClipboardEvent, KeyboardEvent } from "react";
import { api } from "@/api/client";
import { I } from "@/icons";
import { Btn, Field, Input, TextArea, useToast } from "@/components/ui";

interface FeedbackDialogProps {
  open: boolean;
  onClose: () => void;
}

interface PastedImage {
  id: number;
  file: File;
  url: string;
}

const MAX_IMAGE_SIZE = 10 * 1024 * 1024;
const MAX_TOTAL_IMAGE_SIZE = 30 * 1024 * 1024;

export default function FeedbackDialog({ open, onClose }: FeedbackDialogProps) {
  const { showToast } = useToast();
  const panelRef = useRef<HTMLElement | null>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [images, setImages] = useState<PastedImage[]>([]);
  const [submitting, setSubmitting] = useState(false);

  const totalSize = useMemo(
    () => images.reduce((sum, item) => sum + item.file.size, 0),
    [images],
  );

  useEffect(() => {
    if (!open) return;
    previousFocusRef.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    window.setTimeout(() => {
      panelRef.current?.querySelector<HTMLInputElement>("input")?.focus();
    }, 0);
    return () => {
      previousFocusRef.current?.focus();
      setImages((prev) => {
        prev.forEach((item) => URL.revokeObjectURL(item.url));
        return [];
      });
    };
  }, [open]);

  if (!open) return null;

  const resetAndClose = (force = false) => {
    if (submitting && !force) return;
    images.forEach((item) => URL.revokeObjectURL(item.url));
    setTitle("");
    setDescription("");
    setImages([]);
    setSubmitting(false);
    onClose();
  };

  const requestClose = () => resetAndClose();

  const handleDialogKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key === "Escape") {
      event.stopPropagation();
      requestClose();
      return;
    }
    if (event.key !== "Tab" || !panelRef.current) return;

    const focusable = Array.from(
      panelRef.current.querySelectorAll<HTMLElement>(
        'button:not([disabled]), input:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      ),
    );
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  const addImagesFromClipboard = (event: ClipboardEvent) => {
    const files = Array.from(event.clipboardData.files).filter((file) =>
      file.type.startsWith("image/"),
    );
    if (!files.length) return;
    event.preventDefault();

    const accepted: PastedImage[] = [];
    let nextTotal = totalSize;
    for (const file of files) {
      if (file.size > MAX_IMAGE_SIZE) {
        showToast(`图片 ${file.name || "截图"} 超过 10MB，已跳过`, "error");
        continue;
      }
      if (nextTotal + file.size > MAX_TOTAL_IMAGE_SIZE) {
        showToast("图片总大小不能超过 30MB，后续图片已跳过", "error");
        break;
      }
      nextTotal += file.size;
      accepted.push({
        id: Date.now() + Math.random(),
        file,
        url: URL.createObjectURL(file),
      });
    }
    if (accepted.length) {
      setImages((prev) => [...prev, ...accepted]);
      showToast(`已添加 ${accepted.length} 张图片`, "success");
    }
  };

  const removeImage = (id: number) => {
    setImages((prev) => {
      const removed = prev.find((item) => item.id === id);
      if (removed) URL.revokeObjectURL(removed.url);
      return prev.filter((item) => item.id !== id);
    });
  };

  const submit = async () => {
    const nextTitle = title.trim();
    const nextDescription = description.trim();
    if (!nextTitle) {
      showToast("请输入问题标题", "error");
      return;
    }
    setSubmitting(true);
    try {
      await api.createFeedbackIssue({
        title: nextTitle,
        description: nextDescription,
        images: images.map((item) => item.file),
      });
      showToast("反馈已提交", "success");
      resetAndClose(true);
    } catch (error) {
      showToast(`提交反馈失败：${formatError(error)}`, "error");
      setSubmitting(false);
    }
  };

  return (
    <>
      <div
        onClick={requestClose}
        style={{
          position: "fixed",
          inset: 0,
          background: "rgba(0,0,0,0.32)",
          zIndex: 60,
        }}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label="问题反馈"
        style={{
          position: "fixed",
          inset: 0,
          zIndex: 61,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: 24,
          pointerEvents: "none",
        }}
      >
        <section
          ref={panelRef}
          onKeyDown={handleDialogKeyDown}
          style={{
            pointerEvents: "auto",
            width: "min(560px, 100%)",
            maxHeight: "min(720px, calc(100vh - 48px))",
            overflow: "auto",
            background: "var(--bg)",
            border: "1px solid var(--line)",
            borderRadius: 12,
            boxShadow: "var(--shadow-lg)",
            padding: 20,
            display: "flex",
            flexDirection: "column",
            gap: 16,
          }}
        >
          <header style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <div
              style={{
                width: 34,
                height: 34,
                borderRadius: 8,
                background: "var(--accent-soft)",
                color: "var(--accent-2)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
              }}
            >
              <I.MessageSquare size={17} />
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <h2
                style={{
                  margin: 0,
                  fontFamily: "var(--serif)",
                  fontSize: 18,
                  color: "var(--ink)",
                  fontWeight: 600,
                }}
              >
                问题反馈
              </h2>
              <p style={{ margin: "4px 0 0", fontSize: 12, color: "var(--ink-3)" }}>
                详细描述问题，并可在描述框中粘贴截图。
              </p>
            </div>
            <button
              type="button"
              onClick={requestClose}
              className="focus-ring"
              title="关闭"
              disabled={submitting}
              style={{
                border: "none",
                background: "transparent",
                color: "var(--ink-3)",
                cursor: submitting ? "not-allowed" : "pointer",
                opacity: submitting ? 0.5 : 1,
                padding: 6,
                borderRadius: 8,
                display: "flex",
              }}
            >
              <I.X size={16} />
            </button>
          </header>

          <Field label="问题标题">
            <Input
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              maxLength={120}
              placeholder="用一句话描述问题"
              autoFocus
            />
          </Field>

          <Field label="详细描述" hint="支持直接粘贴截图，单张不超过 10MB，总大小不超过 30MB。">
            <TextArea
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              onPaste={addImagesFromClipboard}
              placeholder="描述复现步骤、期望结果和实际结果"
              rows={8}
              style={{ minHeight: 160 }}
            />
          </Field>

          {images.length > 0 && (
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(96px, 1fr))",
                gap: 10,
              }}
            >
              {images.map((item) => (
                <div
                  key={item.id}
                  style={{
                    position: "relative",
                    border: "1px solid var(--line)",
                    borderRadius: 8,
                    overflow: "hidden",
                    background: "var(--surface)",
                    aspectRatio: "4 / 3",
                  }}
                >
                  <img
                    src={item.url}
                    alt={item.file.name || "反馈截图"}
                    style={{ width: "100%", height: "100%", objectFit: "cover" }}
                  />
                  <button
                    type="button"
                    onClick={() => removeImage(item.id)}
                    title="移除图片"
                    className="focus-ring"
                    style={{
                      position: "absolute",
                      top: 6,
                      right: 6,
                      width: 24,
                      height: 24,
                      borderRadius: 999,
                      border: "1px solid var(--line)",
                      background: "var(--surface)",
                      color: "var(--ink-2)",
                      cursor: "pointer",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      padding: 0,
                    }}
                  >
                    <I.X size={13} />
                  </button>
                </div>
              ))}
            </div>
          )}

          <footer style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
            <Btn variant="ghost" onClick={requestClose} disabled={submitting}>
              取消
            </Btn>
            <Btn onClick={submit} disabled={submitting} icon={submitting ? <I.Loader size={14} /> : undefined}>
              {submitting ? "提交中" : "提交反馈"}
            </Btn>
          </footer>
        </section>
      </div>
    </>
  );
}

function formatError(error: unknown): string {
  return error instanceof Error ? error.message : "未知错误";
}
