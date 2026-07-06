export interface CommandTrigger {
  start: number;
  end: number;
  query: string;
}

export function isCommandSelectionKey(key: string): boolean {
  return key === "Enter" || key === "Tab";
}

export function getCommandTrigger(value: string, cursorPosition: number): CommandTrigger | null {
  const cursor = Math.max(0, Math.min(cursorPosition, value.length));
  const beforeCursor = value.slice(0, cursor);
  // 只根据光标前的当前非空白片段触发,支持在一段文本中间输入 slash command。
  const tokenStart = beforeCursor.search(/\S+$/);
  if (tokenStart < 0) return null;

  const tokenPrefix = beforeCursor.slice(tokenStart);
  if (!tokenPrefix.startsWith("/")) return null;

  return {
    start: tokenStart,
    end: cursor,
    query: tokenPrefix.slice(1),
  };
}

export function replaceCommandTrigger(
  value: string,
  trigger: CommandTrigger,
  commandName: string,
): string {
  const suffix = value.slice(trigger.end);
  // 如果命令后面原本已经有空格,避免替换后出现双空格。
  const separator = suffix.startsWith(" ") ? "" : " ";
  return `${value.slice(0, trigger.start)}/${commandName}${separator}${suffix}`;
}
