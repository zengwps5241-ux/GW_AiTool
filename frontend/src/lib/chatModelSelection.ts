import type { ModelSettings, ThinkingLevelValue } from "../types";

export const CHAT_MODEL_STORAGE_KEYS = {
  model: "agent.chat.selectedModel",
  thinkingLevel: "agent.chat.thinkingLevel",
} as const;

interface StoredModelSelection {
  model: string | null;
  thinkingLevel: string | null;
}

export function resolveStoredModelSelection(
  settings: ModelSettings,
  stored: StoredModelSelection,
): { model: string | null; thinkingLevel: ThinkingLevelValue } {
  const model =
    stored.model && settings.models.includes(stored.model)
      ? stored.model
      : settings.default_model;
  const thinkingValues = new Set(settings.thinking_levels.map((level) => level.value));
  const thinkingLevel =
    stored.thinkingLevel &&
    thinkingValues.has(stored.thinkingLevel as ThinkingLevelValue)
      ? (stored.thinkingLevel as ThinkingLevelValue)
      : settings.default_thinking_level;
  return { model, thinkingLevel };
}

export function readStoredModelSelection(): StoredModelSelection {
  if (typeof window === "undefined") {
    return { model: null, thinkingLevel: null };
  }
  return {
    model: window.localStorage.getItem(CHAT_MODEL_STORAGE_KEYS.model),
    thinkingLevel: window.localStorage.getItem(CHAT_MODEL_STORAGE_KEYS.thinkingLevel),
  };
}

export function writeStoredModelSelection(
  model: string | null,
  thinkingLevel: ThinkingLevelValue,
): void {
  if (typeof window === "undefined") return;
  if (model) {
    window.localStorage.setItem(CHAT_MODEL_STORAGE_KEYS.model, model);
  } else {
    window.localStorage.removeItem(CHAT_MODEL_STORAGE_KEYS.model);
  }
  window.localStorage.setItem(CHAT_MODEL_STORAGE_KEYS.thinkingLevel, thinkingLevel);
}
