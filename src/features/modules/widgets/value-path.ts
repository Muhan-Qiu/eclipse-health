/**
 * 受限路径读取：只接受 `a.b.c` 与 `a[0].b`，不执行任何表达式。
 *
 * 与 `schemas/module.schema.json` 的 `valuePath` 规则一致；这里是第二道闸，
 * 防止库被外部改坏或旧版本模块带回带副作用的路径。读取时只走自有属性，
 * 既挡原型链（`constructor`/`__proto__`）也不触发 getter 之外的求值。
 */
const PATH_PATTERN = /^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+|\[\d+\])*$/;
const TOKEN_PATTERN = /[A-Za-z_][A-Za-z0-9_]*|\[\d+\]|[A-Za-z0-9_]+/g;
const MAX_PATH_LENGTH = 128;
const FORBIDDEN_KEYS = new Set(["__proto__", "constructor", "prototype"]);

export function isSafeValuePath(path: string): boolean {
  return path.length > 0 && path.length <= MAX_PATH_LENGTH && PATH_PATTERN.test(path);
}

export function readValuePath(source: unknown, path: string): unknown {
  if (!isSafeValuePath(path)) return undefined;
  const tokens = path.match(TOKEN_PATTERN);
  if (!tokens) return undefined;

  let current: unknown = source;
  for (const token of tokens) {
    if (current === null || typeof current !== "object") return undefined;

    if (token.startsWith("[")) {
      if (!Array.isArray(current)) return undefined;
      const index = Number(token.slice(1, -1));
      if (!Number.isInteger(index) || index < 0) return undefined;
      current = current[index];
      continue;
    }

    if (Array.isArray(current) || FORBIDDEN_KEYS.has(token)) return undefined;
    if (!Object.prototype.hasOwnProperty.call(current, token)) return undefined;
    current = (current as Record<string, unknown>)[token];
  }
  return current;
}
