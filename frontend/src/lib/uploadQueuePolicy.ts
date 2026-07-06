const DEFAULT_UPLOAD_FAILURE_MESSAGE = "上传失败，请重新上传";

export function getUploadFailureMessage(_error: unknown): string {
  // 页面关闭或刷新由 beforeunload 的 sendBeacon 使用默认刷新文案；普通上传异常使用独立文案。
  return DEFAULT_UPLOAD_FAILURE_MESSAGE;
}
