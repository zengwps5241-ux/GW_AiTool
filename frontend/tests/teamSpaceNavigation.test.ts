import { describe, expect, it } from "vitest";

type ViewName =
  | "personalSpace"
  | "personalSpaceDetail"
  | "teamSpaces"
  | "teamSpaceChat"
  | "teamSpaceDetail";

function breadcrumb(view: ViewName, teamName?: string) {
  if (view === "personalSpace") return ["个人空间", "会话列表"];
  if (view === "personalSpaceDetail") return ["个人空间", "文件管理"];
  if (view === "teamSpaces") return ["团队空间", "空间列表"];
  if (view === "teamSpaceChat") return ["团队空间", teamName || "团队会话"];
  return ["团队空间", teamName || "空间详情"];
}

describe("space navigation labels", () => {
  it("uses space entries instead of standalone chat workspace", () => {
    expect(breadcrumb("personalSpace")).toEqual(["个人空间", "会话列表"]);
    expect(breadcrumb("teamSpaceChat", "客户试点资料")).toEqual([
      "团队空间",
      "客户试点资料",
    ]);
  });
});
