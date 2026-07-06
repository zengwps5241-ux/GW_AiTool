import assert from "node:assert/strict";
import {
  getUploadFailureMessage,
} from "../src/lib/uploadQueuePolicy";

assert.equal(
  getUploadFailureMessage(new Error("HTTP 500: internal error")),
  "上传失败，请重新上传",
);

assert.equal(
  getUploadFailureMessage(new Error("上传失败")),
  "上传失败，请重新上传",
);
