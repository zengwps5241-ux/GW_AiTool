import assert from "node:assert/strict";
import {
  isOfficeName,
  isPdfName,
  workspacePreviewCategory,
} from "../src/lib/workspace";
import { api } from "../src/api/client";

assert.equal(isOfficeName("a.doc"), true);
assert.equal(isOfficeName("a.docx"), true);
assert.equal(isOfficeName("a.pptx"), true);
assert.equal(isOfficeName("a.xlsx"), true);
assert.equal(isOfficeName("a.csv"), true);
assert.equal(isOfficeName("a.pdf"), false);
assert.equal(isPdfName("a.pdf"), true);
assert.equal(isPdfName("a.docx"), false);

assert.equal(workspacePreviewCategory("a.docx"), "office");
assert.equal(workspacePreviewCategory("a.csv"), "office");
assert.equal(workspacePreviewCategory("a.pdf"), "pdf");
assert.equal(workspacePreviewCategory("a.md"), "text");
assert.equal(workspacePreviewCategory("a.png"), "image");

assert.equal(
  api.workspaceOfficePreviewUrl("dir/a.docx"),
  "/api/workspace/office-preview?path=dir%2Fa.docx",
);
assert.equal(
  api.workspaceOfficePreviewUrl("dir/a.pdf"),
  "/api/workspace/office-preview?path=dir%2Fa.pdf",
);
assert.equal(
  api.workspaceOfficePreviewUrl("dir/a.csv"),
  "/api/workspace/office-preview?path=dir%2Fa.csv",
);
assert.equal(
  api.workspaceMarkdownPreviewUrl("dir/a.docx"),
  "/api/workspace/markdown-preview?path=dir%2Fa.docx",
);
