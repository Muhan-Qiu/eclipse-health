#!/usr/bin/env node
/**
 * 校验 modules 目录下所有 module.json 的结构、编码与声明式 UI 贡献点。
 *
 * 用法：
 *   node scripts/validate-modules.mjs
 *   node scripts/validate-modules.mjs --json
 *
 * 只用 Node 内置模块；从项目根目录运行。
 */

import fs from "node:fs";
import path from "node:path";
import process from "node:process";

const ROOT = process.cwd();
const EXCLUDED_DIRS = new Set([
  "node_modules",
  ".venv",
  "dist",
  "releases",
  "packaging",
  "__pycache__",
  ".git",
  "build",
  "target",
]);
const ALLOWED_COMPONENTS = new Set(["text", "list", "table", "detail", "form"]);
const ALLOWED_FIELD_TYPES = new Set([
  "text",
  "textarea",
  "number",
  "date",
  "select",
  "checkbox",
]);
const ALLOWED_WIDGET_SIZES = new Set(["sm", "md", "lg"]);
const ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;

const jsonMode = process.argv.slice(2).includes("--json");

function rel(file) {
  return path.relative(ROOT, file).split(path.sep).join("/");
}

function isPlainObject(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function nonEmptyString(value) {
  return typeof value === "string" && value.trim().length > 0;
}

function getPath(object, dotted) {
  let current = object;
  for (const key of dotted.split(".")) {
    if (!isPlainObject(current) || !(key in current)) return undefined;
    current = current[key];
  }
  return current;
}

function lineAt(text, offset) {
  let line = 1;
  const end = Math.min(Math.max(offset, 0), text.length);
  for (let index = 0; index < end; index += 1) {
    if (text.charCodeAt(index) === 10) line += 1;
  }
  return line;
}

function lineNumbersOf(text, needle, limit) {
  const lines = [];
  let from = 0;
  while (lines.length < limit) {
    const index = text.indexOf(needle, from);
    if (index < 0) break;
    lines.push(lineAt(text, index));
    from = index + needle.length;
  }
  return lines;
}

function jsonErrorLocation(text, message) {
  let offset = -1;
  const position = /position\s+(\d+)/i.exec(message);
  const lineColumn = /line\s+(\d+)\s+column\s+(\d+)/i.exec(message);
  if (position) {
    offset = Number(position[1]);
  } else if (lineColumn) {
    const wantedLine = Number(lineColumn[1]);
    const wantedColumn = Number(lineColumn[2]);
    let line = 1;
    let index = 0;
    while (index < text.length && line < wantedLine) {
      if (text.charCodeAt(index) === 10) line += 1;
      index += 1;
    }
    offset = Math.min(index + Math.max(wantedColumn - 1, 0), text.length);
  } else {
    const contextStart = message.indexOf("...");
    const contextEnd = message.lastIndexOf('" is not valid JSON');
    if (contextStart >= 0 && contextEnd > contextStart) {
      let context = message.slice(contextStart + 3, contextEnd);
      if (context.startsWith('"')) context = context.slice(1);
      if (context.endsWith('"')) context = context.slice(0, -1);
      const found = context ? text.indexOf(context) : -1;
      if (found >= 0) {
        const token = /Unexpected token '([\s\S]*?)'/.exec(message);
        const tokenIndex = token ? context.lastIndexOf(token[1]) : -1;
        offset = found + (tokenIndex >= 0 ? tokenIndex : 0);
      }
    }
  }
  if (offset < 0) return { line: 1, column: 1, snippet: "" };
  const before = text.slice(0, offset);
  const line = before.split("\n").length;
  const column = offset - before.lastIndexOf("\n");
  const from = Math.max(0, offset - 40);
  const to = Math.min(text.length, offset + 40);
  const snippet = text
    .slice(from, to)
    .replace(/\r/g, "\\r")
    .replace(/\n/g, "\\n")
    .replace(/\t/g, "\\t");
  return { line, column, snippet };
}

function walkModuleManifests(dir, output) {
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
      walkModuleManifests(full, output);
    } else if (entry.isFile() && entry.name === "module.json") {
      output.push(full);
    }
  }
}

function makeResult(file) {
  return { path: rel(file), errors: [], warnings: [] };
}

function error(result, message) {
  result.errors.push(message);
}

function warn(result, message) {
  result.warnings.push(message);
}

function validateSource(result, source, where) {
  if (!isPlainObject(source)) {
    error(result, `${where}.source must be an object`);
    return;
  }
  if (source.type !== "module-rpc") {
    error(result, `${where}.source.type must be "module-rpc"`);
  }
  if (!nonEmptyString(source.method)) {
    error(result, `${where}.source.method must be a non-empty string`);
  }
}

function validatePages(result, pages) {
  if (!Array.isArray(pages)) {
    error(result, 'contributes.ui.pages must be an array');
    return;
  }
  const seen = new Set();
  pages.forEach((page, pageIndex) => {
    const where = `contributes.ui.pages[${pageIndex}]`;
    if (!isPlainObject(page)) {
      error(result, `${where} must be an object`);
      return;
    }
    if (!nonEmptyString(page.id)) {
      error(result, `${where}.id must be a non-empty string`);
    } else if (seen.has(page.id)) {
      warn(result, `${where}.id "${page.id}" is duplicated`);
    } else {
      seen.add(page.id);
    }
    if (!nonEmptyString(page.title)) {
      error(result, `${where}.title must be a non-empty string`);
    }
    if (!Array.isArray(page.layout)) {
      error(result, `${where}.layout must be an array`);
      return;
    }
    if (page.layout.length === 0) {
      warn(result, `${where}.layout is empty`);
    }
    page.layout.forEach((block, blockIndex) => {
      const blockWhere = `${where}.layout[${blockIndex}]`;
      if (!isPlainObject(block)) {
        error(result, `${blockWhere} must be an object`);
        return;
      }
      if (!ALLOWED_COMPONENTS.has(block.component)) {
        error(
          result,
          `${blockWhere}.component must be one of ${[...ALLOWED_COMPONENTS].join("|")} (got ${JSON.stringify(block.component)})`,
        );
        return;
      }
      if (block.component === "table") {
        if (!("source" in block)) {
          error(result, `${blockWhere} (table) is missing "source"`);
        }
        if (!Array.isArray(block.columns) || block.columns.length === 0) {
          error(result, `${blockWhere} (table) must have a non-empty "columns" array`);
        } else {
          block.columns.forEach((column, columnIndex) => {
            if (!isPlainObject(column)) {
              error(result, `${blockWhere}.columns[${columnIndex}] must be an object`);
              return;
            }
            if (!nonEmptyString(column.key)) {
              error(result, `${blockWhere}.columns[${columnIndex}].key must be a non-empty string`);
            }
            if (!nonEmptyString(column.label)) {
              error(result, `${blockWhere}.columns[${columnIndex}].label must be a non-empty string`);
            }
          });
        }
      }
      if (block.component === "form") {
        if (!("source" in block)) {
          error(result, `${blockWhere} (form) is missing "source"`);
        }
        if (!Array.isArray(block.fields) || block.fields.length === 0) {
          error(result, `${blockWhere} (form) must have a non-empty "fields" array`);
        } else {
          block.fields.forEach((field, fieldIndex) => {
            if (!isPlainObject(field)) {
              error(result, `${blockWhere}.fields[${fieldIndex}] must be an object`);
              return;
            }
            if (!nonEmptyString(field.key)) {
              error(result, `${blockWhere}.fields[${fieldIndex}].key must be a non-empty string`);
            }
            if (!nonEmptyString(field.label)) {
              error(result, `${blockWhere}.fields[${fieldIndex}].label must be a non-empty string`);
            }
            if (!nonEmptyString(field.type)) {
              error(result, `${blockWhere}.fields[${fieldIndex}].type must be a non-empty string`);
            } else if (!ALLOWED_FIELD_TYPES.has(field.type)) {
              warn(
                result,
                `${blockWhere}.fields[${fieldIndex}].type "${field.type}" is not one of ${[...ALLOWED_FIELD_TYPES].join("|")}`,
              );
            }
          });
        }
      }
      if ("source" in block) {
        validateSource(result, block.source, blockWhere);
      } else if (block.component === "list" || block.component === "detail") {
        warn(result, `${blockWhere} (${block.component}) has no "source"; the block will stay empty`);
      }
    });
  });
}

function validateTools(result, tools) {
  if (!Array.isArray(tools)) {
    error(result, "contributes.tools must be an array");
    return;
  }
  const seen = new Set();
  tools.forEach((tool, index) => {
    const where = `contributes.tools[${index}]`;
    if (!isPlainObject(tool)) {
      error(result, `${where} must be an object`);
      return;
    }
    if (!nonEmptyString(tool.id)) {
      error(result, `${where}.id must be a non-empty string`);
    } else if (seen.has(tool.id)) {
      warn(result, `${where}.id "${tool.id}" is duplicated`);
    } else {
      seen.add(tool.id);
    }
    if (!nonEmptyString(tool.name)) {
      error(result, `${where}.name must be a non-empty string`);
    }
    if (!nonEmptyString(tool.description)) {
      error(result, `${where}.description must be a non-empty string`);
    }
    const hasInput = isPlainObject(tool.inputSchema);
    const hasParameters = isPlainObject(tool.parameters);
    if (!hasInput && !hasParameters) {
      error(result, `${where} must declare "inputSchema" or "parameters"`);
    }
  });
}

function validateWidgets(result, widgets) {
  if (!Array.isArray(widgets)) {
    error(result, "contributes.ui.widgets must be an array");
    return;
  }
  const seen = new Set();
  widgets.forEach((widget, index) => {
    const where = `contributes.ui.widgets[${index}]`;
    if (!isPlainObject(widget)) {
      error(result, `${where} must be an object`);
      return;
    }
    if (!nonEmptyString(widget.id)) {
      error(result, `${where}.id must be a non-empty string`);
    } else if (seen.has(widget.id)) {
      warn(result, `${where}.id "${widget.id}" is duplicated`);
    } else {
      seen.add(widget.id);
    }
    if (!nonEmptyString(widget.title)) {
      error(result, `${where}.title must be a non-empty string`);
    }
    if (!ALLOWED_WIDGET_SIZES.has(widget.size)) {
      error(result, `${where}.size must be one of sm|md|lg (got ${JSON.stringify(widget.size)})`);
    }
    if (!isPlainObject(widget.dataSource)) {
      error(result, `${where}.dataSource must be an object`);
    } else {
      if (widget.dataSource.type !== "module-rpc") {
        error(result, `${where}.dataSource.type must be "module-rpc"`);
      }
      if (!nonEmptyString(widget.dataSource.method)) {
        warn(result, `${where}.dataSource.method is missing; the widget cannot call RPC`);
      }
    }
    if (!isPlainObject(widget.view) || !nonEmptyString(widget.view.type)) {
      error(result, `${where}.view.type must be a non-empty string`);
    }
  });
}

function validateManifest(file) {
  const result = makeResult(file);
  let buffer;
  try {
    buffer = fs.readFileSync(file);
  } catch (cause) {
    error(result, `cannot read file: ${cause.message}`);
    return result;
  }

  if (buffer.length >= 3 && buffer[0] === 0xef && buffer[1] === 0xbb && buffer[2] === 0xbf) {
    error(result, "contains a UTF-8 BOM (EF BB BF); module.json must be UTF-8 without BOM");
  }

  let text;
  try {
    text = new TextDecoder("utf-8", { fatal: true }).decode(buffer);
  } catch {
    text = buffer.toString("utf8");
    error(result, "is not valid UTF-8");
  }

  const replacementLines = lineNumbersOf(text, "\uFFFD", 3);
  if (replacementLines.length > 0) {
    error(
      result,
      `contains U+FFFD replacement characters (lines ${replacementLines.join(", ")}); the file is not clean UTF-8`,
    );
  }

  const controlMatch = /[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/.exec(text);
  if (controlMatch) {
    error(
      result,
      `contains illegal control character U+${controlMatch[0].charCodeAt(0).toString(16).padStart(4, "0")} at line ${lineAt(text, controlMatch.index)}`,
    );
  }

  let manifest;
  try {
    manifest = JSON.parse(text);
  } catch (cause) {
    const location = jsonErrorLocation(text, cause.message);
    error(
      result,
      `JSON parse failed at line ${location.line}, column ${location.column}: ${cause.message}` +
        (location.snippet ? ` | near: ${location.snippet}` : ""),
    );
    return result;
  }

  if (!isPlainObject(manifest)) {
    error(result, "top-level JSON value must be an object");
    return result;
  }

  const requiredStrings = [
    "schemaVersion",
    "id",
    "name",
    "description",
    "version",
    "apiVersion",
    "type",
    "license",
    "engines.eclipse",
    "author.name",
    "entry.python",
    "entry.factory",
  ];
  for (const dotted of requiredStrings) {
    const value = getPath(manifest, dotted);
    if (value === undefined) {
      error(result, `missing required field "${dotted}"`);
    } else if (!nonEmptyString(value)) {
      error(result, `field "${dotted}" must be a non-empty string`);
    }
  }
  for (const dotted of ["contributes", "resources"]) {
    const value = getPath(manifest, dotted);
    if (value === undefined) {
      error(result, `missing required field "${dotted}"`);
    } else if (!isPlainObject(value)) {
      error(result, `field "${dotted}" must be an object`);
    }
  }

  if (typeof manifest.id === "string" && manifest.id.length > 0) {
    if (manifest.id.length > 64) {
      error(result, `id must be at most 64 characters (got ${manifest.id.length})`);
    }
    if (!ID_PATTERN.test(manifest.id)) {
      error(result, `id must match ${ID_PATTERN} (got ${JSON.stringify(manifest.id)})`);
    }
  }

  if (isPlainObject(manifest.contributes) && isPlainObject(manifest.contributes.ui)) {
    const ui = manifest.contributes.ui;
    if (ui.pages !== undefined) validatePages(result, ui.pages);
    if (ui.widgets !== undefined) validateWidgets(result, ui.widgets);
  }
  if (isPlainObject(manifest.contributes) && manifest.contributes.tools !== undefined) {
    validateTools(result, manifest.contributes.tools);
  }

  return result;
}

const files = [];
const modulesRoot = path.join(ROOT, "modules");
if (fs.existsSync(modulesRoot)) {
  walkModuleManifests(modulesRoot, files);
}
files.sort((a, b) => rel(a).localeCompare(rel(b)));

const results = files.map(validateManifest);
const errorCount = results.reduce((total, item) => total + item.errors.length, 0);
const warningCount = results.reduce((total, item) => total + item.warnings.length, 0);

if (jsonMode) {
  process.stdout.write(
    `${JSON.stringify(
      {
        checked: results.length,
        errors: errorCount,
        warnings: warningCount,
        manifests: results,
      },
      null,
      2,
    )}\n`,
  );
} else {
  for (const result of results) {
    for (const message of result.errors) {
      process.stdout.write(`[ERROR] ${result.path}: ${message}\n`);
    }
    for (const message of result.warnings) {
      process.stdout.write(`[WARN] ${result.path}: ${message}\n`);
    }
  }
  process.stdout.write(
    `checked ${results.length} manifests, ${errorCount} errors, ${warningCount} warnings\n`,
  );
}

if (errorCount > 0) {
  process.exitCode = 1;
}
