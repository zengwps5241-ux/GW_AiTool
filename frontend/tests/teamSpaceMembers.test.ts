import { describe, expect, it } from "vitest";

function canAddMember(isOwner: boolean, selectedUserId: number | null) {
  return isOwner && selectedUserId !== null;
}

describe("team space member management", () => {
  it("only lets owners add selected users", () => {
    expect(canAddMember(true, 8)).toBe(true);
    expect(canAddMember(true, null)).toBe(false);
    expect(canAddMember(false, 8)).toBe(false);
  });
});
