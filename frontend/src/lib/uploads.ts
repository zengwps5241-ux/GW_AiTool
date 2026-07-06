import type { UploadBatch, UploadedFile } from "@/types";

export function uploadedFilesFromBatch(batch: UploadBatch): UploadedFile[] {
  return batch.items
    .filter((item) => item.status === "success" && item.path)
    .map((item) => ({
      name: item.name,
      path: item.path!,
      size: item.size,
      preview_path: item.preview_path || item.path!,
      agent_path: item.agent_path || item.path!,
      converted: item.converted,
    }));
}

export function uploadFailureMessage(batch: UploadBatch): string | null {
  const failed = batch.items.filter((item) => item.status === "failed");
  if (failed.length === 0) return null;
  const detail = failed
    .slice(0, 3)
    .map((item) => `${item.name}: ${item.error || "上传失败"}`)
    .join("；");
  const more = failed.length > 3 ? `；另有 ${failed.length - 3} 个文件失败` : "";
  return `上传失败 ${failed.length} 个文件：${detail}${more}`;
}
