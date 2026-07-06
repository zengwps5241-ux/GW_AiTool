import { describe, expect, it } from "vitest";
import { teamWorkspaceApi } from "../src/lib/workspaceApi";

describe("teamWorkspaceApi", () => {
  it("builds team workspace URLs", () => {
    const api = teamWorkspaceApi(12);
    expect(api.previewUrl("README.md")).toBe(
      "/api/team-spaces/12/workspace/preview?path=README.md",
    );
    expect(api.downloadUrl("docs/a.md")).toBe(
      "/api/team-spaces/12/workspace/download?path=docs%2Fa.md",
    );
  });
});
