import assert from "node:assert/strict";
import type { ModelSettings } from "../src/types";
import { resolveStoredModelSelection } from "../src/lib/chatModelSelection";

const settings: ModelSettings = {
  models: ["deepseek-v4-pro", "deepseek-v4-flash"],
  default_model: "deepseek-v4-pro",
  default_thinking_level: "low",
  thinking_levels: [
    { value: "disabled", label: "关闭" },
    { value: "low", label: "低" },
    { value: "medium", label: "中" },
    { value: "high", label: "高" },
  ],
};

assert.deepEqual(
  resolveStoredModelSelection(settings, {
    model: "deepseek-v4-flash",
    thinkingLevel: "medium",
  }),
  {
    model: "deepseek-v4-flash",
    thinkingLevel: "medium",
  },
);

assert.deepEqual(
  resolveStoredModelSelection(settings, {
    model: "removed-model",
    thinkingLevel: "max",
  }),
  {
    model: "deepseek-v4-pro",
    thinkingLevel: "low",
  },
);
