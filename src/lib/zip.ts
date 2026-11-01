/** 无依赖的 store-only ZIP 写入：把拖入的 WFDB 文件夹/多文件打包成导入 API 接受的 .zip。 */
export interface DroppedFile {
  file: File;
  /** 相对路径，目录拖入时保留层级；用于 ZIP 内文件名。 */
  path: string;
  /** 打包时缓存的文件内容，避免重复读盘。 */
  data?: Uint8Array;
}

export const MAX_UPLOAD_BYTES = 200 * 1024 * 1024;
export const MAX_ARCHIVE_BYTES = 300 * 1024 * 1024;
export const MAX_ARCHIVE_FILES = 200;

const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let index = 0; index < 256; index += 1) {
    let value = index;
    for (let bit = 0; bit < 8; bit += 1) {
      value = value & 1 ? 0xedb88320 ^ (value >>> 1) : value >>> 1;
    }
    table[index] = value >>> 0;
  }
  return table;
})();

function crc32(data: Uint8Array): number {
  let crc = 0xffffffff;
  for (let index = 0; index < data.length; index += 1) {
    crc = CRC_TABLE[(crc ^ data[index]) & 0xff] ^ (crc >>> 8);
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function writeU16(view: DataView, offset: number, value: number) {
  view.setUint16(offset, value, true);
}

function writeU32(view: DataView, offset: number, value: number) {
  view.setUint32(offset, value >>> 0, true);
}

interface ZipEntry {
  nameBytes: Uint8Array;
  data: Uint8Array;
  crc: number;
  offset: number;
}

export function createStoreZip(files: DroppedFile[]): Blob {
  const encoder = new TextEncoder();
  const entries: ZipEntry[] = [];
  const chunks: BlobPart[] = [];
  let offset = 0;

  for (const item of files) {
    const nameBytes = encoder.encode(item.path.replace(/^\/+/, ""));
    const data = new Uint8Array(item.data ?? new Uint8Array());
    const crc = crc32(data);
    const header = new Uint8Array(30 + nameBytes.length);
    const view = new DataView(header.buffer);
    writeU32(view, 0, 0x04034b50);
    writeU16(view, 4, 20);
    writeU16(view, 6, 0x0800); // UTF-8 文件名
    writeU16(view, 8, 0); // store
    writeU16(view, 10, 0); // time
    writeU16(view, 12, 0x21); // 1980-01-01
    writeU32(view, 14, crc);
    writeU32(view, 18, data.length);
    writeU32(view, 22, data.length);
    writeU16(view, 26, nameBytes.length);
    writeU16(view, 28, 0);
    header.set(nameBytes, 30);
    chunks.push(header, data);
    entries.push({ nameBytes, data, crc, offset });
    offset += header.length + data.length;
  }

  const centralChunks: BlobPart[] = [];
  let centralSize = 0;
  for (const entry of entries) {
    const header = new Uint8Array(46 + entry.nameBytes.length);
    const view = new DataView(header.buffer);
    writeU32(view, 0, 0x02014b50);
    writeU16(view, 4, 20);
    writeU16(view, 6, 20);
    writeU16(view, 8, 0x0800);
    writeU16(view, 10, 0);
    writeU16(view, 12, 0);
    writeU16(view, 14, 0x21);
    writeU32(view, 16, entry.crc);
    writeU32(view, 20, entry.data.length);
    writeU32(view, 24, entry.data.length);
    writeU16(view, 28, entry.nameBytes.length);
    writeU16(view, 30, 0);
    writeU16(view, 32, 0);
    writeU16(view, 34, 0);
    writeU16(view, 36, 0);
    writeU32(view, 38, 0);
    writeU32(view, 42, entry.offset);
    header.set(entry.nameBytes, 46);
    centralChunks.push(header);
    centralSize += header.length;
  }

  const end = new Uint8Array(22);
  const endView = new DataView(end.buffer);
  writeU32(endView, 0, 0x06054b50);
  writeU16(endView, 4, 0);
  writeU16(endView, 6, 0);
  writeU16(endView, 8, entries.length);
  writeU16(endView, 10, entries.length);
  writeU32(endView, 12, centralSize);
  writeU32(endView, 16, offset);
  writeU16(endView, 20, 0);

  return new Blob([...chunks, ...centralChunks, end], {
    type: "application/zip",
  });
}

function readFileEntry(entry: FileSystemFileEntry): Promise<DroppedFile> {
  return new Promise((resolve, reject) => {
    entry.file(
      (file) => resolve({ file, path: entry.fullPath.replace(/^\/+/, "") }),
      reject,
    );
  });
}

async function readDirectory(
  entry: FileSystemDirectoryEntry,
): Promise<DroppedFile[]> {
  const reader = entry.createReader();
  const collected: DroppedFile[] = [];
  while (true) {
    const batch = await new Promise<FileSystemEntry[]>((resolve, reject) => {
      reader.readEntries(resolve, reject);
    });
    if (batch.length === 0) break;
    for (const child of batch) {
      if (child.isDirectory) {
        collected.push(...(await readDirectory(child as FileSystemDirectoryEntry)));
      } else {
        collected.push(await readFileEntry(child as FileSystemFileEntry));
      }
    }
  }
  return collected;
}

/** 读取拖入项；支持文件夹（webkitGetAsEntry），失败时退回 files。 */
export async function collectDroppedFiles(
  transfer: DataTransfer,
): Promise<DroppedFile[]> {
  const items = Array.from(transfer.items ?? []);
  const canReadEntries = items.some(
    (item) => typeof item.webkitGetAsEntry === "function",
  );

  if (!canReadEntries) {
    return Array.from(transfer.files).map((file) => ({ file, path: file.name }));
  }

  const collected: DroppedFile[] = [];
  for (const item of items) {
    if (item.kind !== "file") continue;
    const entry = item.webkitGetAsEntry();
    if (!entry) continue;
    if (entry.isDirectory) {
      collected.push(...(await readDirectory(entry as FileSystemDirectoryEntry)));
    } else {
      collected.push(await readFileEntry(entry as FileSystemFileEntry));
    }
  }
  return collected;
}

export function validateDroppedFiles(files: DroppedFile[]): void {
  if (files.length === 0) {
    throw new Error("empty_selection");
  }
  if (files.length > MAX_ARCHIVE_FILES) {
    throw new Error("too_many_files");
  }
  let total = 0;
  for (const item of files) {
    total += item.file.size;
  }
  if (total > MAX_ARCHIVE_BYTES) {
    throw new Error("archive_too_large");
  }
  if (files.length === 1 && files[0].file.size > MAX_UPLOAD_BYTES) {
    throw new Error("file_too_large");
  }
}

/** 单个文件直接上传；多文件/文件夹打包成 ZIP（store，不压缩）。 */
export async function prepareImportSource(
  files: DroppedFile[],
): Promise<File> {
  validateDroppedFiles(files);
  if (files.length === 1 && !files[0].path.includes("/")) {
    return files[0].file;
  }

  const withData: DroppedFile[] = [];
  for (const item of files) {
    const buffer = await item.file.arrayBuffer();
    withData.push({
      file: item.file,
      path: item.path || item.file.name,
      data: new Uint8Array(buffer),
    });
  }
  const zip = createStoreZip(withData);
  if (zip.size > MAX_UPLOAD_BYTES) {
    throw new Error("file_too_large");
  }
  return new File([zip], "import.zip", { type: "application/zip" });
}
