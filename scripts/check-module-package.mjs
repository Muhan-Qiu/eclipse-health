#!/usr/bin/env node
/**
 * 校验 .ehmod（ZIP）包：ZIP 结构、module.json 编码/JSON、checksums.json 的 sha256。
 *
 * 用法：
 *   node scripts/check-module-package.mjs path/to/module.ehmod
 *   node scripts/check-module-package.mjs dist/modules
 *   node scripts/check-module-package.mjs            # 扫描 dist/modules 与 releases
 *
 * 只用 Node 内置模块（fs/path/zlib/crypto）；支持 stored 与 deflate，
 * 不处理加密 ZIP。从项目根目录运行。
 */

import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import zlib from "node:zlib";

const ROOT = process.cwd();
const MAX_ENTRIES = 20000;
const MAX_UNCOMPRESSED = 512 * 1024 * 1024;

const EOCD_SIGNATURE = 0x06054b50;
const ZIP64_EOCD_SIGNATURE = 0x06064b50;
const ZIP64_LOCATOR_SIGNATURE = 0x07064b50;
const CENTRAL_SIGNATURE = 0x02014b50;
const LOCAL_SIGNATURE = 0x04034b50;

function rel(file) {
  return path.relative(ROOT, file).split(path.sep).join("/");
}

function displayPath(file) {
  const relative = rel(file);
  return relative.startsWith("../") || relative === ".." ? file.split(path.sep).join("/") : relative;
}

function isPlainObject(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function readUInt64(buffer, offset) {
  return Number(buffer.readBigUInt64LE(offset));
}

function lineAtChar(text, offset) {
  let line = 1;
  const end = Math.min(Math.max(offset, 0), text.length);
  for (let index = 0; index < end; index += 1) {
    if (text.charCodeAt(index) === 10) line += 1;
  }
  return line;
}

function firstReplacementLines(text, limit) {
  const lines = [];
  let from = 0;
  while (lines.length < limit) {
    const index = text.indexOf("\uFFFD", from);
    if (index < 0) break;
    lines.push(lineAtChar(text, index));
    from = index + 1;
  }
  return lines;
}

function jsonLocation(text, message) {
  const position = /position\s+(\d+)/i.exec(message);
  let offset = position ? Number(position[1]) : -1;
  if (offset < 0) {
    const contextStart = message.indexOf("...");
    const contextEnd = message.lastIndexOf('" is not valid JSON');
    if (contextStart >= 0 && contextEnd > contextStart) {
      let context = message.slice(contextStart + 3, contextEnd);
      if (context.startsWith('"')) context = context.slice(1);
      if (context.endsWith('"')) context = context.slice(0, -1);
      offset = context ? text.indexOf(context) : -1;
    }
  }
  if (offset < 0) return { line: 1, column: 1 };
  const before = text.slice(0, offset);
  return {
    line: before.split("\n").length,
    column: offset - before.lastIndexOf("\n"),
  };
}

function findEndOfCentralDirectory(buffer) {
  const minimum = Math.max(0, buffer.length - 22 - 0xffff);
  for (let offset = buffer.length - 22; offset >= minimum; offset -= 1) {
    if (buffer.readUInt32LE(offset) === EOCD_SIGNATURE) return offset;
  }
  return -1;
}

function readCentralDirectory(buffer) {
  const eocd = findEndOfCentralDirectory(buffer);
  if (eocd < 0) throw new Error("ZIP end-of-central-directory record not found");

  let total = buffer.readUInt16LE(eocd + 10);
  let cdOffset = buffer.readUInt32LE(eocd + 16);
  const notes = [];

  if (total === 0xffff || cdOffset === 0xffffffff) {
    const locator = eocd - 20;
    if (locator >= 0 && buffer.readUInt32LE(locator) === ZIP64_LOCATOR_SIGNATURE) {
      const zip64Offset = readUInt64(buffer, locator + 8);
      if (
        zip64Offset >= 0 &&
        zip64Offset + 56 <= buffer.length &&
        buffer.readUInt32LE(zip64Offset) === ZIP64_EOCD_SIGNATURE
      ) {
        total = readUInt64(buffer, zip64Offset + 32);
        cdOffset = readUInt64(buffer, zip64Offset + 48);
        notes.push("ZIP64");
      }
    }
  }

  if (total > MAX_ENTRIES) {
    throw new Error(`too many ZIP entries (${total} > ${MAX_ENTRIES})`);
  }
  if (cdOffset < 0 || cdOffset > buffer.length) {
    throw new Error(`central directory offset out of range (${cdOffset})`);
  }

  const entries = [];
  let offset = cdOffset;
  for (let index = 0; index < total; index += 1) {
    if (offset + 46 > buffer.length || buffer.readUInt32LE(offset) !== CENTRAL_SIGNATURE) {
      throw new Error(`bad central directory entry #${index + 1}`);
    }
    const flags = buffer.readUInt16LE(offset + 8);
    const method = buffer.readUInt16LE(offset + 10);
    let compressedSize = buffer.readUInt32LE(offset + 20);
    let uncompressedSize = buffer.readUInt32LE(offset + 24);
    const nameLength = buffer.readUInt16LE(offset + 28);
    const extraLength = buffer.readUInt16LE(offset + 30);
    const commentLength = buffer.readUInt16LE(offset + 32);
    let localOffset = buffer.readUInt32LE(offset + 42);
    const name = buffer.toString("utf8", offset + 46, offset + 46 + nameLength);

    if (
      compressedSize === 0xffffffff ||
      uncompressedSize === 0xffffffff ||
      localOffset === 0xffffffff
    ) {
      let extra = offset + 46 + nameLength;
      const extraEnd = extra + extraLength;
      while (extra + 4 <= extraEnd) {
        const headerId = buffer.readUInt16LE(extra);
        const headerSize = buffer.readUInt16LE(extra + 2);
        if (headerId === 0x0001) {
          let cursor = extra + 4;
          if (uncompressedSize === 0xffffffff && cursor + 8 <= extra + 4 + headerSize) {
            uncompressedSize = readUInt64(buffer, cursor);
            cursor += 8;
          }
          if (compressedSize === 0xffffffff && cursor + 8 <= extra + 4 + headerSize) {
            compressedSize = readUInt64(buffer, cursor);
            cursor += 8;
          }
          if (localOffset === 0xffffffff && cursor + 8 <= extra + 4 + headerSize) {
            localOffset = readUInt64(buffer, cursor);
          }
        }
        extra += 4 + headerSize;
      }
    }

    entries.push({
      name,
      flags,
      method,
      compressedSize,
      uncompressedSize,
      localOffset,
    });
    offset += 46 + nameLength + extraLength + commentLength;
  }
  return { entries, notes };
}

function extractEntry(buffer, entry) {
  const local = entry.localOffset;
  if (local + 30 > buffer.length || buffer.readUInt32LE(local) !== LOCAL_SIGNATURE) {
    throw new Error(`bad local header for "${entry.name}"`);
  }
  if ((entry.flags & 0x1) !== 0) {
    throw new Error(`encrypted entry is not supported: "${entry.name}"`);
  }
  const nameLength = buffer.readUInt16LE(local + 26);
  const extraLength = buffer.readUInt16LE(local + 28);
  const dataStart = local + 30 + nameLength + extraLength;
  const dataEnd = dataStart + entry.compressedSize;
  if (dataEnd > buffer.length) {
    throw new Error(`truncated data for "${entry.name}"`);
  }
  const raw = buffer.subarray(dataStart, dataEnd);
  if (entry.method === 0) return raw;
  if (entry.method === 8) {
    const inflated = zlib.inflateRawSync(raw);
    if (inflated.length > MAX_UNCOMPRESSED) {
      throw new Error(`entry too large after inflate: "${entry.name}"`);
    }
    return inflated;
  }
  throw new Error(`unsupported compression method ${entry.method} for "${entry.name}"`);
}

function findEntry(entries, name) {
  const normalized = name.replace(/\\/g, "/").replace(/^\.\//, "");
  return (
    entries.find((entry) => entry.name === normalized) ??
    entries.find((entry) => entry.name.endsWith(`/${normalized}`))
  );
}

function validateJsonBuffer(buffer, label, result) {
  if (buffer.length >= 3 && buffer[0] === 0xef && buffer[1] === 0xbb && buffer[2] === 0xbf) {
    result.errors.push(`${label} contains a UTF-8 BOM`);
  }
  let text;
  try {
    text = new TextDecoder("utf-8", { fatal: true }).decode(buffer);
  } catch {
    text = buffer.toString("utf8");
    result.errors.push(`${label} is not valid UTF-8`);
  }
  const replacementLines = firstReplacementLines(text, 3);
  if (replacementLines.length > 0) {
    result.errors.push(
      `${label} contains U+FFFD replacement characters (lines ${replacementLines.join(", ")})`,
    );
  }
  try {
    return JSON.parse(text);
  } catch (cause) {
    const location = jsonLocation(text, cause.message);
    result.errors.push(
      `${label} JSON parse failed at line ${location.line}, column ${location.column}: ${cause.message}`,
    );
    return null;
  }
}

function validatePackage(file) {
  const result = {
    path: displayPath(file),
    errors: [],
    warnings: [],
    entries: 0,
    moduleId: null,
    moduleVersion: null,
    verified: 0,
  };

  let buffer;
  try {
    buffer = fs.readFileSync(file);
  } catch (cause) {
    result.errors.push(`cannot read file: ${cause.message}`);
    return result;
  }
  if (
    buffer.length < 4 ||
    (buffer.readUInt32LE(0) !== LOCAL_SIGNATURE && buffer.readUInt32LE(0) !== EOCD_SIGNATURE)
  ) {
    result.errors.push("not a ZIP archive (missing PK signature)");
    return result;
  }

  let zip;
  try {
    zip = readCentralDirectory(buffer);
  } catch (cause) {
    result.errors.push(cause.message);
    return result;
  }
  result.entries = zip.entries.length;
  for (const note of zip.notes) result.warnings.push(note);

  const cache = new Map();
  function dataFor(entry) {
    if (!cache.has(entry.name)) cache.set(entry.name, extractEntry(buffer, entry));
    return cache.get(entry.name);
  }

  const moduleEntry = findEntry(zip.entries, "module.json");
  if (!moduleEntry) {
    result.errors.push("module.json not found in package");
  } else {
    try {
      const manifest = validateJsonBuffer(dataFor(moduleEntry), "module.json", result);
      if (isPlainObject(manifest)) {
        result.moduleId = typeof manifest.id === "string" ? manifest.id : null;
        result.moduleVersion = typeof manifest.version === "string" ? manifest.version : null;
      }
    } catch (cause) {
      result.errors.push(`cannot read module.json: ${cause.message}`);
    }
  }

  const checksumsEntry = findEntry(zip.entries, "checksums.json");
  if (checksumsEntry) {
    let checksums;
    try {
      checksums = validateJsonBuffer(dataFor(checksumsEntry), "checksums.json", result);
    } catch (cause) {
      result.errors.push(`cannot read checksums.json: ${cause.message}`);
      checksums = null;
    }
    if (isPlainObject(checksums)) {
      if (checksums.algorithm !== "sha256") {
        result.warnings.push(
          `checksums.json algorithm is ${JSON.stringify(checksums.algorithm)}, expected "sha256"`,
        );
      }
      if (!isPlainObject(checksums.files)) {
        result.errors.push('checksums.json is missing an object field "files"');
      } else {
        const listed = new Set();
        for (const [name, expected] of Object.entries(checksums.files)) {
          const normalized = name.replace(/\\/g, "/").replace(/^\.\//, "");
          listed.add(normalized);
          const entry = findEntry(zip.entries, normalized);
          if (!entry) {
            result.errors.push(`checksums.json references missing file "${normalized}"`);
            continue;
          }
          if (typeof expected !== "string" || !/^[a-f0-9]{64}$/i.test(expected)) {
            result.errors.push(`checksums.json has an invalid sha256 for "${normalized}"`);
            continue;
          }
          let actual;
          try {
            actual = crypto
              .createHash("sha256")
              .update(dataFor(entry))
              .digest("hex");
          } catch (cause) {
            result.errors.push(`cannot hash "${normalized}": ${cause.message}`);
            continue;
          }
          if (actual.toLowerCase() !== expected.toLowerCase()) {
            result.errors.push(
              `sha256 mismatch for "${normalized}": expected ${expected.toLowerCase()}, actual ${actual}`,
            );
          } else {
            result.verified += 1;
          }
        }
        for (const entry of zip.entries) {
          if (entry.name.endsWith("/")) continue;
          if (entry.name === checksumsEntry.name) continue;
          if (!listed.has(entry.name)) {
            result.warnings.push(`file "${entry.name}" is not listed in checksums.json`);
          }
        }
      }
    }
  } else {
    result.warnings.push("checksums.json not found in package");
  }

  return result;
}

function walkPackages(directory, output) {
  let entries;
  try {
    entries = fs.readdirSync(directory, { withFileTypes: true });
  } catch {
    return;
  }
  entries.sort((a, b) => a.name.localeCompare(b.name));
  for (const entry of entries) {
    const full = path.join(directory, entry.name);
    if (entry.isSymbolicLink()) continue;
    if (entry.isDirectory()) {
      walkPackages(full, output);
    } else if (entry.isFile() && entry.name.toLowerCase().endsWith(".ehmod")) {
      output.push(full);
    }
  }
}

const args = process.argv.slice(2).filter((item) => !item.startsWith("--"));
const packages = [];
if (args.length > 0) {
  for (const item of args) {
    const absolute = path.resolve(ROOT, item);
    if (fs.existsSync(absolute) && fs.statSync(absolute).isDirectory()) {
      walkPackages(absolute, packages);
    } else if (fs.existsSync(absolute)) {
      packages.push(absolute);
    } else {
      process.stdout.write(`[ERROR] ${item}: file or directory not found\n`);
      process.exitCode = 1;
    }
  }
} else {
  for (const directory of ["dist/modules", "releases"]) {
    const absolute = path.join(ROOT, directory);
    if (fs.existsSync(absolute)) walkPackages(absolute, packages);
  }
}

packages.sort((a, b) => rel(a).localeCompare(rel(b)));
const results = packages.map(validatePackage);
const errorCount = results.reduce((total, item) => total + item.errors.length, 0);
const warningCount = results.reduce((total, item) => total + item.warnings.length, 0);

for (const result of results) {
  const status = result.errors.length === 0 ? "OK" : "FAIL";
  const identity =
    result.moduleId !== null
      ? ` module.json: ${result.moduleId}@${result.moduleVersion ?? "?"}`
      : "";
  process.stdout.write(`[${status}] ${result.path} (${result.entries} entries)${identity}\n`);
  if (result.verified > 0) {
    process.stdout.write(`  checksums: ${result.verified} files verified\n`);
  }
  for (const message of result.errors) {
    process.stdout.write(`[ERROR] ${result.path}: ${message}\n`);
  }
  for (const message of result.warnings) {
    process.stdout.write(`[WARN] ${result.path}: ${message}\n`);
  }
}

process.stdout.write(
  `checked ${results.length} packages, ${errorCount} errors, ${warningCount} warnings\n`,
);

if (errorCount > 0) {
  process.exitCode = 1;
}
