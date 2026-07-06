import { describe, expect, it } from "vitest";

function visibleActions(readonly: boolean) {
  return {
    upload: !readonly,
    create: !readonly,
    rename: !readonly,
    remove: !readonly,
    download: true,
    preview: true,
  };
}

describe("workspace file manager readonly actions", () => {
  it("hides write actions when readonly", () => {
    expect(visibleActions(true)).toEqual({
      upload: false,
      create: false,
      rename: false,
      remove: false,
      download: true,
      preview: true,
    });
  });
});
