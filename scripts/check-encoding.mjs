#!/usr/bin/env node
/**
 * 扫描源码与文档的 UTF-8 编码问题：BOM、非法字节、U+FFFD。
 *
 * 用法：
 *   node scripts/check-encoding.mjs
 *   node scripts/check-encoding.mjs --fix-bom
 *
 * 默认只报告，不修改文件。--fix-bom 只删除文件开头的 UTF-8 BOM，
 * 不改变其余任何字节。只用 Node 内置模块；从项目根目录运行。
 */

import fs from "node:fs";
import path from "node:path";
import process from "node:process";

const ROOT = process.cwd();
const FIX_BOM = process.argv.slice(2).includes("--fix-bom");

const TARGET_DIRS = [
  "src",
  "backend/src",
  "backend/tests",
  "modules",
  "schemas",
  "docs",
  "scripts",
];
const EXCLUDED_DIRS = new Set([
  "node_modules",
  ".venv",
  "__pycache__",
  "dist",
  "build",
  "releases",
  "packaging",
  ".git",
  "target",
]);
const TEXT_EXTENSIONS = new Set([
  ".ts",
  ".tsx",
  ".js",
  ".mjs",
  ".py",
  ".json",
  ".md",
  ".css",
  ".html",
  ".toml",
  ".yaml",
  ".yml",
]);

function rel(file) {
  return path.relative(ROOT, file).split(path.sep).join("/");
}

function walk(dir, output) {
  let entries;
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch {
    return;
  }
  entries.sort((a, b) => a.name.localeCompare(b.name));
  for (const entry of entries) {
    if (EXCLUDED_DIRS.has(entry.name)) continue;
    const full = path.join(dir, entry.name);
    if (entry.isSymbolicLink()) continue;
    if (entry.isDirectory()) {
      walk(full, output);
    } else if (entry.isFile() && TEXT_EXTENSIONS.has(path.extname(entry.name).toLowerCase())) {
      output.push(full);
    }
  }
}

/** 返回第一个非法 UTF-8 字节的偏移；全部合法时返回 -1。 */
function firstInvalidUtf8(buffer) {
  let index = 0;
  while (index < buffer.length) {
    const byte = buffer[index];
    if (byte <= 0x7f) {
      index += 1;
      continue;
    }
    let needed;
    if (byte >= 0xc2 && byte <= 0xdf) {
      needed = 1;
    } else if (byte >= 0xe0 && byte <= 0xef) {
      needed = 2;
    } else if (byte >= 0xf0 && byte <= 0xf4) {
      needed = 3;
    } else {
      return index;
    }
    if (index + needed >= buffer.length) return index;
    for (let offset = 1; offset <= needed; offset += 1) {
      const continuation = buffer[index + offset];
      if (continuation < 0x80 || continuation > 0xbf) return index;
    }
    if (byte === 0xe0 && buffer[index + 1] < 0xa0) return index;
    if (byte === 0xed && buffer[index + 1] >= 0xa0) return index;
    if (byte === 0xf0 && buffer[index + 1] < 0x90) return index;
    if (byte === 0xf4 && buffer[index + 1] > 0x8f) return index;
    index += needed + 1;
  }
  return -1;
}

function lineAtByte(buffer, offset) {
  let line = 1;
  const end = Math.min(Math.max(offset, 0), buffer.length);
  for (let index = 0; index < end; index += 1) {
    if (buffer[index] === 0x0a) line += 1;
  }
  return line;
}

function lineAtChar(text, offset) {
  let line = 1;
  const end = Math.min(Math.max(offset, 0), text.length);
  for (let index = 0; index < end; index += 1) {
    if (text.charCodeAt(index) === 10) line += 1;
  }
  return line;
}

const files = [];
for (const directory of TARGET_DIRS) {
  const absolute = path.join(ROOT, directory);
  if (fs.existsSync(absolute)) walk(absolute, files);
}
files.sort((a, b) => rel(a).localeCompare(rel(b)));

let errorCount = 0;
let fixedCount = 0;

for (const file of files) {
  const relative = rel(file);
  let buffer;
  try {
    buffer = fs.readFileSync(file);
  } catch (cause) {
    process.stdout.write(`[ERROR] ${relative}:1: cannot read file: ${cause.message}\n`);
    errorCount += 1;
    continue;
  }

  const hasUtf8Bom =
    buffer.length >= 3 && buffer[0] === 0xef && buffer[1] === 0xbb && buffer[2] === 0xbf;
  const hasUtf16Bom =
    buffer.length >= 2 &&
    ((buffer[0] === 0xff && buffer[1] === 0xfe) ||
      (buffer[0] === 0xfe && buffer[1] === 0xff));

  if (hasUtf8Bom) {
    if (FIX_BOM) {
      try {
        fs.writeFileSync(file, buffer.subarray(3));
        buffer = buffer.subarray(3);
        fixedCount += 1;
        process.stdout.write(`[FIXED] ${relative}: removed UTF-8 BOM\n`);
      } catch (cause) {
        process.stdout.write(
          `[ERROR] ${relative}:1: cannot remove BOM: ${cause.message}\n`,
        );
        errorCount += 1;
      }
    } else {
      process.stdout.write(
        `[ERROR] ${relative}:1: UTF-8 BOM (EF BB BF); use --fix-bom to remove it\n`,
      );
      errorCount += 1;
    }
  }

  if (hasUtf16Bom) {
    process.stdout.write(
      `[ERROR] ${relative}:1: UTF-16 BOM detected; save the file as UTF-8 without BOM\n`,
    );
    errorCount += 1;
  }

  const invalidOffset = firstInvalidUtf8(buffer);
  if (invalidOffset >= 0) {
    process.stdout.write(
      `[ERROR] ${relative}:${lineAtByte(buffer, invalidOffset)}: invalid UTF-8 byte sequence (offset ${invalidOffset})\n`,
    );
    errorCount += 1;
  }

  const text = new TextDecoder("utf-8", { fatal: false }).decode(buffer);
  const replacementLines = [];
  let searchFrom = 0;
  while (replacementLines.length < 3) {
    const index = text.indexOf("\uFFFD", searchFrom);
    if (index < 0) break;
    replacementLines.push(lineAtChar(text, index));
    searchFrom = index + 1;
  }
  if (replacementLines.length > 0) {
    const more = text.indexOf("\uFFFD", searchFrom) >= 0 ? " (+more)" : "";
    process.stdout.write(
      `[ERROR] ${relative}:${replacementLines[0]}: U+FFFD replacement character at lines ${replacementLines.join(", ")}${more}\n`,
    );
    errorCount += 1;
  }
}

const fixedSuffix = fixedCount > 0 ? `, ${fixedCount} BOMs fixed` : "";
process.stdout.write(`scanned ${files.length} files, ${errorCount} errors${fixedSuffix}\n`);

if (errorCount > 0) {
  process.exitCode = 1;
}
