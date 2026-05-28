import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { inflateRawSync } from "node:zlib";
import express from "express";
import multer from "multer";
import {
  clearSessionCookie,
  currentUser,
  isSuperAdmin,
  login,
  logout,
  setSessionCookie
} from "./auth.js";
import { pingDatabase, pool } from "./db.js";

const app = express();
const port = Number(process.env.PORT ?? 5184);
const documentStorageRoot = new URL("../storage/documents/", import.meta.url);
const upload = multer({
  limits: {
    fileSize: 100 * 1024 * 1024,
    files: 1
  },
  storage: multer.memoryStorage()
});
const allowedWorkSequenceStatuses = [
  "WAITING",
  "IN_PROGRESS",
  "HOLD",
  "DONE",
  "CANCELED"
];
const a4PortraitPage = {
  height: 842,
  width: 595
};

app.use(express.json({ limit: "15mb" }));

app.get("/api/v1/health", async (_req, res, next) => {
  try {
    const database = await pingDatabase();
    res.json({
      ok: true,
      service: "FlowNote API",
      database: database.database_name
    });
  } catch (error) {
    next(error);
  }
});

app.post("/api/v1/auth/login", async (req, res, next) => {
  try {
    const { loginId, password } = req.body ?? {};

    if (typeof loginId !== "string" || typeof password !== "string") {
      res.status(400).json({
        error: {
          code: "VALIDATION_ERROR",
          message: "loginId와 password가 필요합니다."
        }
      });
      return;
    }

    const result = await login(loginId.trim(), password);

    if (!result) {
      res.status(401).json({
        error: {
          code: "INVALID_CREDENTIALS",
          message: "아이디 또는 비밀번호가 올바르지 않습니다."
        }
      });
      return;
    }

    setSessionCookie(res, result.sessionId);
    res.json({ user: result.user });
  } catch (error) {
    next(error);
  }
});

app.get("/api/v1/auth/me", async (req, res, next) => {
  try {
    const user = await currentUser(req);

    if (!user) {
      res.status(401).json({
        error: {
          code: "LOGIN_REQUIRED",
          message: "로그인이 필요합니다."
        }
      });
      return;
    }

    res.json({ user });
  } catch (error) {
    next(error);
  }
});

app.post("/api/v1/auth/logout", async (req, res, next) => {
  try {
    await logout(req);
    clearSessionCookie(res);
    res.status(204).send();
  } catch (error) {
    next(error);
  }
});

async function requireSuperAdmin(req, res) {
  const user = await currentUser(req);

  if (!user) {
    res.status(401).json({
      error: {
        code: "LOGIN_REQUIRED",
        message: "로그인이 필요합니다."
      }
    });
    return null;
  }

  if (!isSuperAdmin(user)) {
    res.status(403).json({
      error: {
        code: "PERMISSION_DENIED",
        message: "최고관리자만 사용할 수 있습니다."
      }
    });
    return null;
  }

  return user;
}

async function requireLogin(req, res) {
  const user = await currentUser(req);

  if (!user) {
    res.status(401).json({
      error: {
        code: "LOGIN_REQUIRED",
        message: "로그인이 필요합니다."
      }
    });
    return null;
  }

  return user;
}

function canEditWorkSequence(user) {
  const editableRoles = ["super-admin", "mes-user", "pop-user"];
  return Boolean(user?.roles?.some((roleId) => editableRoles.includes(roleId)));
}

function canManageDocuments(user) {
  const editableRoles = ["super-admin", "mes-user", "pop-user"];
  return Boolean(user?.roles?.some((roleId) => editableRoles.includes(roleId)));
}

function isProtectedDocumentFolderRow(folder) {
  return folder?.folder_id === "folder-my-pc-journal";
}

function getDocumentFileType(fileName) {
  const extension = path.extname(fileName).toLocaleLowerCase();

  if (extension === ".pdf") {
    return "PDF";
  }

  if ([".xls", ".xlsx"].includes(extension)) {
    return "EXCEL";
  }

  if ([".ppt", ".pptx"].includes(extension)) {
    return "PPT";
  }

  return null;
}

function getJournalPhotoFileType(fileName, mimeType) {
  const extension = path.extname(fileName).toLocaleLowerCase();
  const allowedExtensions = new Set([
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".gif",
    ".heic",
    ".heif"
  ]);

  if (allowedExtensions.has(extension) || String(mimeType ?? "").startsWith("image/")) {
    return "IMAGE";
  }

  return null;
}

function formatJournalTimestamp(value = new Date()) {
  const pad = (part) => String(part).padStart(2, "0");

  return [
    value.getFullYear(),
    pad(value.getMonth() + 1),
    pad(value.getDate())
  ].join("") + `_${pad(value.getHours())}${pad(value.getMinutes())}${pad(value.getSeconds())}`;
}

function formatJournalDocumentTime(value = new Date()) {
  const pad = (part) => String(part).padStart(2, "0");

  return [
    value.getFullYear(),
    pad(value.getMonth() + 1),
    pad(value.getDate())
  ].join("-") + ` ${pad(value.getHours())}:${pad(value.getMinutes())}`;
}

function makeJournalDocumentName(value, isHandover, handoverTo) {
  const normalizedHandoverTo = normalizeOptionalText(handoverTo);
  const prefix = isHandover
    ? `인수인계${normalizedHandoverTo ? ` - ${normalizedHandoverTo}` : ""}`
    : "현장작업일지";

  return `${prefix} - ${formatJournalDocumentTime(value)}`;
}

function getNextVersionLabel(currentVersion) {
  const numericVersion = Number(String(currentVersion ?? "").replace(/^v/i, ""));

  if (!Number.isInteger(numericVersion) || numericVersion < 1) {
    return "v1";
  }

  return `v${numericVersion + 1}`;
}

function normalizeUploadedFileName(fileName) {
  const rawFileName = path.basename(fileName ?? "").trim();
  const decodedFileName = Buffer.from(rawFileName, "latin1").toString("utf8");

  if (decodedFileName.includes("\uFFFD")) {
    return rawFileName;
  }

  return decodedFileName;
}

function parseDocumentTags(value) {
  if (typeof value !== "string") {
    return [];
  }

  const tagNames = value
    .split(/[,#\n]/)
    .map((tagName) => tagName.trim())
    .filter(Boolean)
    .map((tagName) => tagName.slice(0, 80));

  return Array.from(new Set(tagNames)).slice(0, 20);
}

function normalizeBooleanFormValue(value) {
  return value === true || value === "true" || value === "1" || value === "on";
}

function makeJournalSummary(memo, hasPhoto, isHandover, handoverTo) {
  const normalizedMemo = normalizeOptionalText(memo);
  const normalizedHandoverTo = normalizeOptionalText(handoverTo);
  const prefix = isHandover
    ? `인수인계${normalizedHandoverTo ? ` - ${normalizedHandoverTo}` : ""}: `
    : "";

  if (normalizedMemo) {
    return `${prefix}${normalizedMemo}`.slice(0, 800);
  }

  if (isHandover) {
    return `${prefix}${hasPhoto ? "사진으로 등록한 인수인계입니다." : "내용 없는 인수인계입니다."}`.slice(0, 800);
  }

  return hasPhoto ? "사진으로 등록한 현장 작업일지입니다." : "내용 없는 현장 작업일지입니다.";
}

async function saveUploadedDocumentFile(file) {
  const originalFileName = normalizeUploadedFileName(file.originalname);
  const extension = path.extname(originalFileName).toLocaleLowerCase();
  return saveDocumentBuffer({
    buffer: file.buffer,
    extension,
    mimeType: file.mimetype,
    originalFileName
  });
}

async function saveDocumentBuffer({ buffer, extension, mimeType, originalFileName }) {
  const storageName = `${crypto.randomUUID()}${extension}`;
  const now = new Date();
  const storageFolder = [
    String(now.getFullYear()),
    String(now.getMonth() + 1).padStart(2, "0")
  ];
  const storageDir = new URL(`${storageFolder.join("/")}/`, documentStorageRoot);
  const storageRelativePath = storageFolder.concat(storageName).join("/");
  const storageUrl = new URL(storageRelativePath, documentStorageRoot);
  const sha256Hash = crypto.createHash("sha256").update(buffer).digest("hex");

  await fs.mkdir(storageDir, { recursive: true });
  await fs.writeFile(storageUrl, buffer, { flag: "wx" });

  return {
    originalFileName,
    storageRelativePath,
    mimeType,
    byteSize: buffer.byteLength,
    sha256Hash
  };
}

function buildPdfBuffer(objects) {
  const chunks = [Buffer.from("%PDF-1.4\n", "binary")];
  const offsets = [0];

  objects.forEach((object, index) => {
    offsets.push(Buffer.concat(chunks).byteLength);
    chunks.push(Buffer.from(`${index + 1} 0 obj\n`, "binary"));

    if (Buffer.isBuffer(object)) {
      chunks.push(object);
    } else {
      chunks.push(Buffer.from(object, "binary"));
    }

    chunks.push(Buffer.from("\nendobj\n", "binary"));
  });

  const xrefOffset = Buffer.concat(chunks).byteLength;
  chunks.push(Buffer.from(`xref\n0 ${objects.length + 1}\n`, "binary"));
  chunks.push(Buffer.from("0000000000 65535 f \n", "binary"));
  offsets.slice(1).forEach((offset) => {
    chunks.push(Buffer.from(`${String(offset).padStart(10, "0")} 00000 n \n`, "binary"));
  });
  chunks.push(
    Buffer.from(
      `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF\n`,
      "binary"
    )
  );

  return Buffer.concat(chunks);
}

function createBlankPdfBuffer() {
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${a4PortraitPage.width} ${a4PortraitPage.height}] /Resources << >> /Contents 4 0 R >>`,
    "<< /Length 0 >>\nstream\n\nendstream"
  ];

  return buildPdfBuffer(objects);
}

function getJpegDimensions(buffer) {
  if (buffer[0] !== 0xff || buffer[1] !== 0xd8) {
    return null;
  }

  let offset = 2;

  while (offset < buffer.length) {
    if (buffer[offset] !== 0xff) {
      offset += 1;
      continue;
    }

    const marker = buffer[offset + 1];
    const length = buffer.readUInt16BE(offset + 2);

    if (
      (marker >= 0xc0 && marker <= 0xc3) ||
      (marker >= 0xc5 && marker <= 0xc7) ||
      (marker >= 0xc9 && marker <= 0xcb) ||
      (marker >= 0xcd && marker <= 0xcf)
    ) {
      return {
        height: buffer.readUInt16BE(offset + 5),
        width: buffer.readUInt16BE(offset + 7)
      };
    }

    offset += 2 + length;
  }

  return null;
}

function parseJpegDataUrl(value) {
  if (typeof value !== "string" || !value.startsWith("data:image/jpeg;base64,")) {
    return null;
  }

  const buffer = Buffer.from(value.slice("data:image/jpeg;base64,".length), "base64");
  const dimensions = getJpegDimensions(buffer);

  if (!dimensions) {
    return null;
  }

  return {
    buffer,
    ...dimensions
  };
}

function createPdfBufferFromJpeg(jpeg) {
  const content = `q\n${a4PortraitPage.width} 0 0 ${a4PortraitPage.height} 0 0 cm\n/Im1 Do\nQ`;
  const imageHeader = Buffer.from(
    `<< /Type /XObject /Subtype /Image /Width ${jpeg.width} /Height ${jpeg.height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${jpeg.buffer.byteLength} >>\nstream\n`,
    "binary"
  );
  const imageFooter = Buffer.from("\nendstream", "binary");

  return buildPdfBuffer([
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${a4PortraitPage.width} ${a4PortraitPage.height}] /Resources << /XObject << /Im1 5 0 R >> >> /Contents 4 0 R >>`,
    `<< /Length ${Buffer.byteLength(content)} >>\nstream\n${content}\nendstream`,
    Buffer.concat([imageHeader, jpeg.buffer, imageFooter])
  ]);
}

function makeCrc32Table() {
  return Array.from({ length: 256 }, (_, index) => {
    let value = index;

    for (let bit = 0; bit < 8; bit += 1) {
      value = value & 1 ? 0xedb88320 ^ (value >>> 1) : value >>> 1;
    }

    return value >>> 0;
  });
}

const crc32Table = makeCrc32Table();

function crc32(buffer) {
  let crc = 0xffffffff;

  for (const byte of buffer) {
    crc = crc32Table[(crc ^ byte) & 0xff] ^ (crc >>> 8);
  }

  return (crc ^ 0xffffffff) >>> 0;
}

function createZipBuffer(entries) {
  const localParts = [];
  const centralParts = [];
  let offset = 0;

  for (const entry of entries) {
    const fileName = Buffer.from(entry.path, "utf8");
    const data = Buffer.isBuffer(entry.data)
      ? entry.data
      : Buffer.from(entry.data, "utf8");
    const checksum = crc32(data);
    const localHeader = Buffer.alloc(30);

    localHeader.writeUInt32LE(0x04034b50, 0);
    localHeader.writeUInt16LE(20, 4);
    localHeader.writeUInt16LE(0x0800, 6);
    localHeader.writeUInt16LE(0, 8);
    localHeader.writeUInt16LE(0, 10);
    localHeader.writeUInt16LE(0, 12);
    localHeader.writeUInt32LE(checksum, 14);
    localHeader.writeUInt32LE(data.byteLength, 18);
    localHeader.writeUInt32LE(data.byteLength, 22);
    localHeader.writeUInt16LE(fileName.byteLength, 26);
    localHeader.writeUInt16LE(0, 28);

    localParts.push(localHeader, fileName, data);

    const centralHeader = Buffer.alloc(46);
    centralHeader.writeUInt32LE(0x02014b50, 0);
    centralHeader.writeUInt16LE(20, 4);
    centralHeader.writeUInt16LE(20, 6);
    centralHeader.writeUInt16LE(0x0800, 8);
    centralHeader.writeUInt16LE(0, 10);
    centralHeader.writeUInt16LE(0, 12);
    centralHeader.writeUInt16LE(0, 14);
    centralHeader.writeUInt32LE(checksum, 16);
    centralHeader.writeUInt32LE(data.byteLength, 20);
    centralHeader.writeUInt32LE(data.byteLength, 24);
    centralHeader.writeUInt16LE(fileName.byteLength, 28);
    centralHeader.writeUInt16LE(0, 30);
    centralHeader.writeUInt16LE(0, 32);
    centralHeader.writeUInt16LE(0, 34);
    centralHeader.writeUInt16LE(0, 36);
    centralHeader.writeUInt32LE(0, 38);
    centralHeader.writeUInt32LE(offset, 42);
    centralParts.push(centralHeader, fileName);

    offset += localHeader.byteLength + fileName.byteLength + data.byteLength;
  }

  const centralDirectory = Buffer.concat(centralParts);
  const endRecord = Buffer.alloc(22);
  endRecord.writeUInt32LE(0x06054b50, 0);
  endRecord.writeUInt16LE(0, 4);
  endRecord.writeUInt16LE(0, 6);
  endRecord.writeUInt16LE(entries.length, 8);
  endRecord.writeUInt16LE(entries.length, 10);
  endRecord.writeUInt32LE(centralDirectory.byteLength, 12);
  endRecord.writeUInt32LE(offset, 16);
  endRecord.writeUInt16LE(0, 20);

  return Buffer.concat([...localParts, centralDirectory, endRecord]);
}

function escapeXml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
}

function getSpreadsheetColumnName(columnNumber) {
  let columnName = "";
  let value = columnNumber;

  while (value > 0) {
    const remainder = (value - 1) % 26;
    columnName = `${String.fromCharCode(65 + remainder)}${columnName}`;
    value = Math.floor((value - 1) / 26);
  }

  return columnName;
}

function normalizeSpreadsheetCells(value) {
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .map((cell) => ({
      column: Number(cell?.column),
      row: Number(cell?.row),
      value: typeof cell?.value === "string" ? cell.value.trim().slice(0, 1000) : ""
    }))
    .filter(
      (cell) =>
        Number.isInteger(cell.row) &&
        Number.isInteger(cell.column) &&
        cell.row >= 1 &&
        cell.row <= 200 &&
        cell.column >= 1 &&
        cell.column <= 50 &&
        cell.value
    )
    .slice(0, 2000);
}

function parseSpreadsheetDraftCells(body) {
  if (typeof body !== "string" || !body.trim()) {
    return [];
  }

  try {
    const parsedBody = JSON.parse(body);
    const firstSheet = Array.isArray(parsedBody?.sheets)
      ? parsedBody.sheets[0]
      : null;

    return normalizeSpreadsheetCells(firstSheet?.cells);
  } catch {
    return [];
  }
}

function unescapeXml(value) {
  return String(value)
    .replaceAll("&apos;", "'")
    .replaceAll("&quot;", '"')
    .replaceAll("&gt;", ">")
    .replaceAll("&lt;", "<")
    .replaceAll("&amp;", "&");
}

function getSpreadsheetColumnNumber(columnName) {
  return String(columnName)
    .toUpperCase()
    .split("")
    .reduce((value, character) => value * 26 + character.charCodeAt(0) - 64, 0);
}

function readZipEntries(buffer) {
  const entries = new Map();
  let offset = 0;

  while (offset + 30 <= buffer.byteLength && buffer.readUInt32LE(offset) === 0x04034b50) {
    const compressionMethod = buffer.readUInt16LE(offset + 8);
    const compressedSize = buffer.readUInt32LE(offset + 18);
    const fileNameLength = buffer.readUInt16LE(offset + 26);
    const extraLength = buffer.readUInt16LE(offset + 28);
    const fileNameStart = offset + 30;
    const dataStart = fileNameStart + fileNameLength + extraLength;
    const dataEnd = dataStart + compressedSize;
    const fileName = buffer.toString("utf8", fileNameStart, fileNameStart + fileNameLength);
    const compressedData = buffer.subarray(dataStart, dataEnd);

    if (compressionMethod === 0) {
      entries.set(fileName, compressedData.toString("utf8"));
    } else if (compressionMethod === 8) {
      entries.set(fileName, inflateRawSync(compressedData).toString("utf8"));
    }

    offset = dataEnd;
  }

  return entries;
}

function parseSharedStringsXml(sharedStringsXml) {
  if (!sharedStringsXml) {
    return [];
  }

  return Array.from(sharedStringsXml.matchAll(/<si\b[\s\S]*?<\/si>/g)).map((match) => {
    const textParts = Array.from(match[0].matchAll(/<t[^>]*>([\s\S]*?)<\/t>/g)).map(
      (textMatch) => unescapeXml(textMatch[1] ?? "")
    );

    return textParts.join("");
  });
}

function parseWorksheetCellsXml(worksheetXml, sharedStrings = []) {
  if (!worksheetXml) {
    return [];
  }

  return Array.from(worksheetXml.matchAll(/<c\b([^>]*)>([\s\S]*?)<\/c>/g))
    .map((match) => {
      const attributes = match[1] ?? "";
      const content = match[2] ?? "";
      const reference = attributes.match(/\br="([A-Z]+)(\d+)"/);

      if (!reference) {
        return null;
      }

      const type = attributes.match(/\bt="([^"]+)"/)?.[1] ?? "";
      const formula = content.match(/<f[^>]*>([\s\S]*?)<\/f>/)?.[1];
      const inlineText = content.match(/<is>[\s\S]*?<t[^>]*>([\s\S]*?)<\/t>[\s\S]*?<\/is>/)?.[1];
      const rawValue = content.match(/<v[^>]*>([\s\S]*?)<\/v>/)?.[1] ?? "";
      let value = "";

      if (typeof formula === "string") {
        value = `=${unescapeXml(formula)}`;
      } else if (typeof inlineText === "string") {
        value = unescapeXml(inlineText);
      } else if (type === "s") {
        value = sharedStrings[Number(rawValue)] ?? "";
      } else {
        value = unescapeXml(rawValue);
      }

      return {
        column: getSpreadsheetColumnNumber(reference[1]),
        row: Number(reference[2]),
        value
      };
    })
    .filter(Boolean)
    .filter((cell) => cell.value);
}

function parseXlsxCells(buffer) {
  try {
    const entries = readZipEntries(buffer);
    const sharedStrings = parseSharedStringsXml(entries.get("xl/sharedStrings.xml"));

    return normalizeSpreadsheetCells(
      parseWorksheetCellsXml(entries.get("xl/worksheets/sheet1.xml"), sharedStrings)
    );
  } catch {
    return [];
  }
}

function createWorksheetXml(cells) {
  const rowsByNumber = new Map();

  for (const cell of cells) {
    const rowCells = rowsByNumber.get(cell.row) ?? [];
    rowCells.push(cell);
    rowsByNumber.set(cell.row, rowCells);
  }

  const rowXml = Array.from(rowsByNumber.entries())
    .sort(([leftRow], [rightRow]) => leftRow - rightRow)
    .map(([rowNumber, rowCells]) => {
      const cellsXml = rowCells
        .sort((left, right) => left.column - right.column)
        .map((cell) => {
          const reference = `${getSpreadsheetColumnName(cell.column)}${cell.row}`;
          const trimmedValue = cell.value.trim();

          if (trimmedValue.startsWith("=") && trimmedValue.length > 1) {
            return `<c r="${reference}"><f>${escapeXml(
              trimmedValue.slice(1)
            )}</f><v></v></c>`;
          }

          if (/^-?\d+(\.\d+)?$/.test(trimmedValue)) {
            return `<c r="${reference}"><v>${trimmedValue}</v></c>`;
          }

          return `<c r="${reference}" t="inlineStr"><is><t>${escapeXml(
            trimmedValue
          )}</t></is></c>`;
        })
        .join("");

      return `<row r="${rowNumber}">${cellsXml}</row>`;
    })
    .join("");
  const maxRow = Math.max(1, ...cells.map((cell) => cell.row));
  const maxColumn = Math.max(1, ...cells.map((cell) => cell.column));
  const dimension = `A1:${getSpreadsheetColumnName(maxColumn)}${maxRow}`;

  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <dimension ref="${dimension}"/>
  <sheetViews>
    <sheetView workbookViewId="0"/>
  </sheetViews>
  <sheetFormatPr defaultRowHeight="15"/>
  <sheetData>${rowXml}</sheetData>
</worksheet>`;
}

function createBlankXlsxBuffer(cells = []) {
  const worksheetXml = createWorksheetXml(cells);

  return createZipBuffer([
    {
      path: "[Content_Types].xml",
      data: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>`
    },
    {
      path: "_rels/.rels",
      data: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>`
    },
    {
      path: "docProps/app.xml",
      data: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>FlowNote</Application>
</Properties>`
    },
    {
      path: "docProps/core.xml",
      data: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:creator>FlowNote</dc:creator>
  <cp:lastModifiedBy>FlowNote</cp:lastModifiedBy>
</cp:coreProperties>`
    },
    {
      path: "xl/workbook.xml",
      data: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Sheet1" sheetId="1" r:id="rId1"/>
  </sheets>
  <calcPr calcId="0" calcMode="auto" fullCalcOnLoad="1" forceFullCalc="1"/>
</workbook>`
    },
    {
      path: "xl/_rels/workbook.xml.rels",
      data: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>`
    },
    {
      path: "xl/worksheets/sheet1.xml",
      data: worksheetXml
    },
    {
      path: "xl/styles.xml",
      data: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>
  <fills count="1"><fill><patternFill patternType="none"/></fill></fills>
  <borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>
</styleSheet>`
    }
  ]);
}

async function ensureDocumentEditorDraftTable(connection) {
  await connection.execute(`
    CREATE TABLE IF NOT EXISTS document_editor_draft (
      id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
      document_file_id BIGINT UNSIGNED NOT NULL,
      editor_format VARCHAR(40) NOT NULL,
      title VARCHAR(220) NOT NULL,
      body MEDIUMTEXT NULL,
      updated_by BIGINT UNSIGNED NULL,
      created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      PRIMARY KEY (id),
      UNIQUE KEY uq_document_editor_draft_file (document_file_id),
      CONSTRAINT fk_document_editor_draft_file
        FOREIGN KEY (document_file_id) REFERENCES document_file (id)
        ON DELETE CASCADE,
      CONSTRAINT fk_document_editor_draft_updated_by
        FOREIGN KEY (updated_by) REFERENCES user_account (id)
        ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  `);
}

function normalizePdfFileName(fileName) {
  const trimmedFileName = typeof fileName === "string" ? fileName.trim() : "";

  if (!trimmedFileName) {
    return "";
  }

  if (trimmedFileName.includes("/") || trimmedFileName.includes("\\")) {
    return "";
  }

  const baseFileName = path.basename(trimmedFileName);
  const extension = path.extname(baseFileName).toLocaleLowerCase();

  if (!extension) {
    return `${baseFileName}.pdf`;
  }

  if (extension !== ".pdf") {
    return "";
  }

  return baseFileName;
}

function normalizeExcelFileName(fileName) {
  const trimmedFileName = typeof fileName === "string" ? fileName.trim() : "";

  if (!trimmedFileName) {
    return "";
  }

  if (trimmedFileName.includes("/") || trimmedFileName.includes("\\")) {
    return "";
  }

  const baseFileName = path.basename(trimmedFileName);
  const extension = path.extname(baseFileName).toLocaleLowerCase();

  if (!extension) {
    return `${baseFileName}.xlsx`;
  }

  if (![".xls", ".xlsx"].includes(extension)) {
    return "";
  }

  if (extension === ".xls") {
    return `${baseFileName.slice(0, -4)}.xlsx`;
  }

  return baseFileName;
}

async function findInternalUserId(publicUser) {
  const [rows] = await pool.execute(
    "SELECT id FROM user_account WHERE user_id = :userId LIMIT 1",
    { userId: publicUser.userId }
  );

  return rows[0]?.id ?? null;
}

async function listActiveNotificationTargetUserIds(connection, excludeUserIds = []) {
  const [rows] = await connection.execute(
    `
      SELECT id
      FROM user_account
      WHERE status = 'ACTIVE'
    `
  );
  const excludedIds = new Set(excludeUserIds.filter(Boolean).map(Number));

  return rows
    .map((row) => Number(row.id))
    .filter((userId) => !excludedIds.has(userId));
}

async function createNotifications(connection, targetUserIds, notification) {
  const uniqueTargetUserIds = Array.from(
    new Set(targetUserIds.filter(Boolean).map(Number))
  );

  for (const targetUserId of uniqueTargetUserIds) {
    await connection.execute(
      `
        INSERT INTO notification (
          notification_id,
          target_user_id,
          actor_user_id,
          event_type,
          source_type,
          source_document_id,
          source_journal_id,
          source_sequence_item_id,
          title,
          message
        )
        VALUES (
          :notificationId,
          :targetUserId,
          :actorUserId,
          :eventType,
          :sourceType,
          :sourceDocumentId,
          :sourceJournalId,
          :sourceSequenceItemId,
          :title,
          :message
        )
      `,
      {
        actorUserId: notification.actorUserId ?? null,
        eventType: notification.eventType,
        message: notification.message,
        notificationId: `noti_${crypto.randomUUID().replaceAll("-", "")}`,
        sourceDocumentId: notification.sourceDocumentId ?? null,
        sourceJournalId: notification.sourceJournalId ?? null,
        sourceSequenceItemId: notification.sourceSequenceItemId ?? null,
        sourceType: notification.sourceType ?? "SYSTEM",
        targetUserId,
        title: notification.title
      }
    );
  }
}

async function notifyActiveUsersExcept(connection, actorUserId, notification) {
  const targetUserIds = await listActiveNotificationTargetUserIds(connection, [
    actorUserId
  ]);

  await createNotifications(connection, targetUserIds, {
    ...notification,
    actorUserId
  });
}

async function getDefaultWorkSequenceBoardId(connection = pool) {
  const [rows] = await connection.execute(
    `
      SELECT id
      FROM work_sequence_board
      WHERE board_id = 'board-local-main'
      LIMIT 1
    `
  );

  return rows[0]?.id ?? null;
}

function toUserListItem(row) {
  return {
    userId: row.user_id,
    loginId: row.login_id,
    displayName: row.display_name,
    status: row.status,
    roleId: row.role_id,
    roleName: row.role_name,
    updatedAt: row.updated_at
  };
}

function toWorkSequenceItem(row) {
  const linkedDocumentName =
    row.linked_document_file_name ?? row.linked_document_name ?? null;
  const detailParts = [
    row.assigned_team,
    row.target_quantity ? `목표 ${row.target_quantity}개` : null,
    row.product_code,
    linkedDocumentName ? `문서 ${linkedDocumentName}` : null
  ].filter(Boolean);

  return {
    sequenceItemId: row.sequence_item_id,
    sequenceNo: row.sequence_no,
    title: row.title,
    productCode: row.product_code,
    assignedTeam: row.assigned_team,
    targetQuantity: row.target_quantity,
    linkedDocumentId: row.linked_document_id ?? null,
    linkedDocumentName,
    status: row.status,
    memo: row.memo,
    detail: detailParts.length > 0 ? detailParts.join(" / ") : row.memo,
    createdBy: row.created_by_name,
    updatedAt: row.updated_at
  };
}

function toDocumentFolder(row) {
  return {
    folderId: row.folder_id,
    parentFolderId: row.parent_folder_id,
    name: row.folder_name,
    sortOrder: row.sort_order,
    createdBy: row.created_by_name,
    createdAt: row.created_at,
    updatedAt: row.updated_at
  };
}

function formatDateTimeForClient(value) {
  if (!value) {
    return "";
  }

  if (typeof value === "string") {
    return value.slice(0, 16).replace("T", " ");
  }

  const pad = (part) => String(part).padStart(2, "0");

  return [
    value.getFullYear(),
    pad(value.getMonth() + 1),
    pad(value.getDate())
  ].join("-") + ` ${pad(value.getHours())}:${pad(value.getMinutes())}`;
}

function toDocumentVersion(row) {
  return {
    version: row.version_label,
    publishedAt: formatDateTimeForClient(row.published_at),
    owner: row.owner_name ?? "알 수 없는 사용자",
    changeNote: row.change_note,
    fileName: row.version_file_name,
    status: row.status
  };
}

function toDocumentItem(row, versions = [], journalReplies = []) {
  const journal = row.journal_id
    ? {
        journalId: row.journal_id,
        memo: row.journal_memo,
        isHandover: Boolean(row.is_handover),
        handoverTo: row.handover_to,
        createdBy: row.journal_created_by_name ?? row.owner_name ?? "알 수 없는 사용자",
        createdAt: row.journal_created_at,
        replies: journalReplies
      }
    : null;

  return {
    documentId: row.document_id,
    folderId: row.folder_id,
    type: row.file_type,
    name: row.file_name,
    meta: row.meta_text ?? "",
    category: row.category_path ?? "",
    version: row.current_version,
    owner: row.owner_name ?? "알 수 없는 사용자",
    publishedAt: formatDateTimeForClient(row.published_at),
    securityLevel: row.security_level,
    pageCount: Number(row.page_count ?? 0),
    summary: row.summary ?? "",
    contentUrl: row.current_storage_id
      ? `/api/v1/document-files/${row.document_id}/content?version=${encodeURIComponent(
          row.current_version
        )}`
      : null,
    canEdit: Boolean(row.editor_draft_id),
    editorFormat: row.editor_format ?? null,
    tags: row.tags ?? [],
    journal,
    versions,
    history: versions.map(
      (version) => `${version.owner}님이 ${version.version}을 등록했습니다.`
    )
  };
}

async function listDocumentFolders(connection = pool) {
  const [rows] = await connection.execute(`
    SELECT
      f.folder_id,
      parent.folder_id AS parent_folder_id,
      f.folder_name,
      f.sort_order,
      creator.display_name AS created_by_name,
      f.created_at,
      f.updated_at
    FROM document_folder f
    LEFT JOIN document_folder parent ON parent.id = f.parent_folder_id
    LEFT JOIN user_account creator ON creator.id = f.created_by
    ORDER BY
      CASE WHEN f.parent_folder_id IS NULL THEN 0 ELSE 1 END,
      COALESCE(parent.sort_order, 0),
      f.sort_order,
      f.folder_name
  `);

  return rows.map(toDocumentFolder);
}

async function replaceDocumentTags(connection, documentInternalId, tagNames, actorUserId) {
  await connection.execute(
    "DELETE FROM document_file_tag WHERE document_file_id = :documentInternalId",
    { documentInternalId }
  );

  for (const tagName of tagNames) {
    const tagId = `tag_${crypto.randomUUID().replaceAll("-", "")}`;

    await connection.execute(
      `
        INSERT INTO document_tag (
          tag_id,
          tag_name,
          created_by
        )
        VALUES (
          :tagId,
          :tagName,
          :actorUserId
        )
        ON DUPLICATE KEY UPDATE
          tag_name = VALUES(tag_name)
      `,
      {
        actorUserId,
        tagId,
        tagName
      }
    );

    const [tagRows] = await connection.execute(
      "SELECT id FROM document_tag WHERE tag_name = :tagName LIMIT 1",
      { tagName }
    );

    if (!tagRows[0]) {
      continue;
    }

    await connection.execute(
      `
        INSERT INTO document_file_tag (
          document_file_id,
          tag_id
        )
        VALUES (
          :documentInternalId,
          :tagInternalId
        )
        ON DUPLICATE KEY UPDATE
          tag_id = VALUES(tag_id)
      `,
      {
        documentInternalId,
        tagInternalId: tagRows[0].id
      }
    );
  }
}

async function listDocumentItems(connection = pool) {
  const [documentRows] = await connection.execute(`
    SELECT
      d.document_id,
      folder.folder_id,
      d.file_type,
      d.file_name,
      d.meta_text,
      d.category_path,
      d.current_version,
      owner.display_name AS owner_name,
      d.published_at,
      d.security_level,
      d.page_count,
      d.summary,
      draft.id AS editor_draft_id,
      draft.editor_format,
      journal.journal_id,
      journal.memo AS journal_memo,
      journal.is_handover,
      journal.handover_to,
      journal.created_at AS journal_created_at,
      journal_creator.display_name AS journal_created_by_name,
      current_storage.id AS current_storage_id
    FROM document_file d
    JOIN document_folder folder ON folder.id = d.folder_id
    LEFT JOIN user_account owner ON owner.id = d.owner_id
    LEFT JOIN field_journal_entry journal ON journal.document_file_id = d.id
    LEFT JOIN user_account journal_creator ON journal_creator.id = journal.created_by
    LEFT JOIN document_file_version current_version
      ON current_version.document_file_id = d.id
      AND current_version.version_label = d.current_version
    LEFT JOIN document_file_storage current_storage
      ON current_storage.document_file_version_id = current_version.id
    LEFT JOIN document_editor_draft draft
      ON draft.document_file_id = d.id
    ORDER BY folder.sort_order ASC, d.file_name ASC, d.id ASC
  `);

  const [versionRows] = await connection.execute(`
    SELECT
      d.document_id,
      v.version_label,
      v.file_name AS version_file_name,
      v.change_note,
      version_owner.display_name AS owner_name,
      v.published_at,
      v.status
    FROM document_file_version v
    JOIN document_file d ON d.id = v.document_file_id
    LEFT JOIN user_account version_owner ON version_owner.id = v.owner_id
    ORDER BY d.id ASC, v.published_at DESC, v.id DESC
  `);

  const versionsByDocumentId = new Map();

  for (const row of versionRows) {
    const versions = versionsByDocumentId.get(row.document_id) ?? [];
    versions.push(toDocumentVersion(row));
    versionsByDocumentId.set(row.document_id, versions);
  }

  const [tagRows] = await connection.execute(`
    SELECT
      d.document_id,
      t.tag_name
    FROM document_file_tag ft
    JOIN document_file d ON d.id = ft.document_file_id
    JOIN document_tag t ON t.id = ft.tag_id
    ORDER BY d.id ASC, t.tag_name ASC
  `);
  const tagsByDocumentId = new Map();

  for (const row of tagRows) {
    const tags = tagsByDocumentId.get(row.document_id) ?? [];
    tags.push(row.tag_name);
    tagsByDocumentId.set(row.document_id, tags);
  }

  const [replyRows] = await connection.execute(`
    SELECT
      d.document_id,
      r.reply_id,
      r.reply_text,
      r.reply_type,
      r.created_at,
      creator.display_name AS created_by_name,
      v.version_label
    FROM field_journal_reply r
    JOIN field_journal_entry e ON e.id = r.field_journal_entry_id
    JOIN document_file d ON d.id = e.document_file_id
    LEFT JOIN user_account creator ON creator.id = r.created_by
    LEFT JOIN document_file_version v ON v.id = r.document_file_version_id
    ORDER BY d.id ASC, r.created_at ASC, r.id ASC
  `);
  const repliesByDocumentId = new Map();

  for (const row of replyRows) {
    const replies = repliesByDocumentId.get(row.document_id) ?? [];
    replies.push({
      replyId: row.reply_id,
      text: row.reply_text,
      type: row.reply_type,
      createdBy: row.created_by_name ?? "알 수 없는 사용자",
      createdAt: row.created_at,
      version: row.version_label
    });
    repliesByDocumentId.set(row.document_id, replies);
  }

  return documentRows.map((row) =>
    toDocumentItem(
      {
        ...row,
        tags: tagsByDocumentId.get(row.document_id) ?? []
      },
      versionsByDocumentId.get(row.document_id) ?? [],
      repliesByDocumentId.get(row.document_id) ?? []
    )
  );
}

async function getOrCreateFieldJournalFolder(connection, actorUserId) {
  const [existingRows] = await connection.execute(
    "SELECT id, folder_id, folder_name FROM document_folder WHERE folder_id = 'folder-my-pc-journal' LIMIT 1"
  );

  if (existingRows[0]) {
    return existingRows[0];
  }

  const [parentRows] = await connection.execute(
    "SELECT id FROM document_folder WHERE folder_id = 'folder-my-pc' LIMIT 1"
  );
  let parentFolderId = parentRows[0]?.id ?? null;

  if (!parentFolderId) {
    const [rootResult] = await connection.execute(
      `
        INSERT INTO document_folder (
          folder_id,
          parent_folder_id,
          folder_name,
          sort_order,
          created_by
        )
        VALUES (
          'folder-my-pc',
          NULL,
          '문서함',
          10,
          :actorUserId
        )
      `,
      { actorUserId }
    );
    parentFolderId = rootResult.insertId;
  }

  await connection.execute(
    `
      INSERT INTO document_folder (
        folder_id,
        parent_folder_id,
        folder_name,
        sort_order,
        created_by
      )
      VALUES (
        'folder-my-pc-journal',
        :parentFolderId,
        '작업일지',
        20,
        :actorUserId
      )
      ON DUPLICATE KEY UPDATE
        parent_folder_id = VALUES(parent_folder_id),
        folder_name = VALUES(folder_name),
        sort_order = VALUES(sort_order)
    `,
    {
      actorUserId,
      parentFolderId
    }
  );

  const [folderRows] = await connection.execute(
    "SELECT id, folder_id, folder_name FROM document_folder WHERE folder_id = 'folder-my-pc-journal' LIMIT 1"
  );

  return folderRows[0];
}

function toFieldJournalEntry(row, readBy = [], replies = []) {
  return {
    journalId: row.journal_id,
    documentId: row.document_id,
    memo: row.memo,
    photoFileName: row.photo_file_name,
    isHandover: Boolean(row.is_handover),
    handoverTo: row.handover_to,
    handoverStatus: row.handover_status,
    readBy,
    replies,
    photoUrl: row.current_storage_id
      ? `/api/v1/document-files/${row.document_id}/content?version=${encodeURIComponent(
          row.current_version
        )}`
      : null,
    createdBy: row.created_by_name ?? "알 수 없는 사용자",
    createdAt: row.created_at
  };
}

async function listFieldJournalEntries(connection = pool) {
  const [rows] = await connection.execute(`
    SELECT
      e.id AS journal_internal_id,
      e.journal_id,
      e.memo,
      e.photo_file_name,
      e.is_handover,
      e.handover_to,
      e.handover_status,
      e.created_at,
      creator.display_name AS created_by_name,
      d.document_id,
      d.current_version,
      current_storage.id AS current_storage_id
    FROM field_journal_entry e
    JOIN document_file d ON d.id = e.document_file_id
    LEFT JOIN user_account creator ON creator.id = e.created_by
    LEFT JOIN document_file_version current_version
      ON current_version.document_file_id = d.id
      AND current_version.version_label = d.current_version
    LEFT JOIN document_file_storage current_storage
      ON current_storage.document_file_version_id = current_version.id
    ORDER BY e.created_at DESC, e.id DESC
    LIMIT 100
  `);

  if (rows.length === 0) {
    return [];
  }

  const journalInternalIds = rows.map((row) => row.journal_internal_id);
  const readPlaceholders = journalInternalIds
    .map((_, index) => `:journalInternalId${index}`)
    .join(", ");
  const readParams = Object.fromEntries(
    journalInternalIds.map((journalInternalId, index) => [
      `journalInternalId${index}`,
      journalInternalId
    ])
  );
  const [readRows] = await connection.execute(
    `
      SELECT
        r.id AS read_id,
        r.field_journal_entry_id,
        u.user_id,
        u.display_name,
        r.read_at
      FROM field_journal_handover_read r
      LEFT JOIN user_account u ON u.id = r.reader_user_id
      WHERE r.field_journal_entry_id IN (${readPlaceholders})
      ORDER BY r.read_at ASC, r.id ASC
    `,
    readParams
  );
  const readsByJournalInternalId = new Map();

  for (const row of readRows) {
    const reads = readsByJournalInternalId.get(row.field_journal_entry_id) ?? [];
    reads.push({
      readId: row.read_id,
      userId: row.user_id,
      displayName: row.display_name ?? "알 수 없는 사용자",
      readAt: row.read_at
    });
    readsByJournalInternalId.set(row.field_journal_entry_id, reads);
  }

  const [replyRows] = await connection.execute(
    `
      SELECT
        r.field_journal_entry_id,
        r.reply_id,
        r.reply_text,
        r.reply_type,
        r.created_at,
        creator.display_name AS created_by_name,
        v.version_label
      FROM field_journal_reply r
      LEFT JOIN user_account creator ON creator.id = r.created_by
      LEFT JOIN document_file_version v ON v.id = r.document_file_version_id
      WHERE r.field_journal_entry_id IN (${readPlaceholders})
      ORDER BY r.created_at ASC, r.id ASC
    `,
    readParams
  );
  const repliesByJournalInternalId = new Map();

  for (const row of replyRows) {
    const replies = repliesByJournalInternalId.get(row.field_journal_entry_id) ?? [];
    replies.push({
      replyId: row.reply_id,
      text: row.reply_text,
      type: row.reply_type,
      createdBy: row.created_by_name ?? "알 수 없는 사용자",
      createdAt: row.created_at,
      version: row.version_label
    });
    repliesByJournalInternalId.set(row.field_journal_entry_id, replies);
  }

  return rows.map((row) =>
    toFieldJournalEntry(
      row,
      readsByJournalInternalId.get(row.journal_internal_id) ?? [],
      repliesByJournalInternalId.get(row.journal_internal_id) ?? []
    )
  );
}

function parseJsonValue(value) {
  if (!value) {
    return null;
  }

  if (typeof value === "object") {
    return value;
  }

  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

function toSystemHistoryItem(row) {
  const beforeValue = parseJsonValue(row.before_value);
  const afterValue = parseJsonValue(row.after_value);
  const targetName =
    afterValue?.title ?? beforeValue?.title ?? row.current_title ?? "작업";
  const actorName = row.actor_name ?? "알 수 없는 사용자";
  let message = `${actorName}님이 ${targetName} 이력을 남겼습니다.`;

  if (row.event_type === "CREATED") {
    message = `${actorName}님이 ${targetName} 작업을 입력했습니다.`;
  }

  if (row.event_type === "UPDATED") {
    message = `${actorName}님이 ${targetName} 작업을 수정했습니다.`;
  }

  if (row.event_type === "REORDERED") {
    const beforePosition = beforeValue?.position ?? beforeValue?.sequenceNo;
    const afterPosition = afterValue?.position ?? afterValue?.sequenceNo;
    message = `${actorName}님이 ${targetName} 작업 순서를 ${beforePosition}에서 ${afterPosition}로 변경했습니다.`;
  }

  return {
    historyId: row.id,
    eventType: row.event_type,
    actorName,
    targetName,
    message,
    beforeValue,
    afterValue,
    createdAt: row.created_at
  };
}

function toDocumentHistoryItem(row) {
  const beforeValue = parseJsonValue(row.before_value);
  const afterValue = parseJsonValue(row.after_value);
  const targetName =
    afterValue?.fileName ?? beforeValue?.fileName ?? row.current_file_name ?? "문서";
  const actorName = row.actor_name ?? "알 수 없는 사용자";
  let message = `${actorName}님이 ${targetName} 문서 이력을 남겼습니다.`;

  if (row.event_type === "DOCUMENT_CREATED") {
    message = `${actorName}님이 ${targetName} 문서를 업로드했습니다.`;
  }

  if (row.event_type === "DOCUMENT_VERSION_CREATED") {
    const versionLabel = afterValue?.version ?? row.current_version;
    message = `${actorName}님이 ${targetName} 문서 ${versionLabel} 버전을 등록했습니다.`;
  }

  if (row.event_type === "DOCUMENT_TAG_UPDATED") {
    message = `${actorName}님이 ${targetName} 문서 태그를 수정했습니다.`;
  }

  if (row.event_type === "FIELD_JOURNAL_CREATED") {
    message = `${actorName}님이 ${targetName} 작업일지를 등록했습니다.`;
  }

  if (row.event_type === "FIELD_HANDOVER_READ") {
    const handoverTo = afterValue?.handoverTo;
    message = `${actorName}님이 ${targetName} 인수인계를 확인했습니다${
      handoverTo ? ` (${handoverTo})` : ""
    }.`;
  }

  if (row.event_type === "FIELD_JOURNAL_REPLY_CREATED") {
    const versionLabel = afterValue?.version;
    message = `${actorName}님이 ${targetName} 작업일지에 응답을 추가했습니다${
      versionLabel ? ` (${versionLabel})` : ""
    }.`;
  }

  return {
    historyId: `document-${row.id}`,
    eventType: row.event_type,
    actorName,
    targetName,
    message,
    beforeValue,
    afterValue,
    createdAt: row.created_at
  };
}

function toNotificationItem(row) {
  return {
    notificationId: row.notification_id,
    eventType: row.event_type,
    sourceType: row.source_type,
    sourceDocumentId: row.source_document_id,
    sourceJournalId: row.source_journal_id,
    sourceSequenceItemId: row.source_sequence_item_id,
    title: row.title,
    message: row.message,
    actorName: row.actor_name ?? null,
    readAt: row.read_at,
    createdAt: row.created_at
  };
}

function normalizeOptionalText(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function normalizeNullableInteger(value, fieldLabel, minimum = 0) {
  if (value === null || value === undefined || value === "") {
    return { value: null };
  }

  const numberValue = Number(value);

  if (!Number.isInteger(numberValue) || numberValue < minimum) {
    return {
      error: `${fieldLabel}은 ${minimum} 이상의 정수로 입력해 주세요.`
    };
  }

  return { value: numberValue };
}

async function resolveLinkedDocument(connection, linkedDocumentId, linkedDocumentName) {
  const normalizedDocumentId =
    typeof linkedDocumentId === "string" && linkedDocumentId.trim()
      ? linkedDocumentId.trim()
      : null;

  if (!normalizedDocumentId) {
    return {
      documentInternalId: null,
      documentName: normalizeOptionalText(linkedDocumentName)
    };
  }

  const [rows] = await connection.execute(
    `
      SELECT id, file_name
      FROM document_file
      WHERE document_id = :documentId
      LIMIT 1
    `,
    { documentId: normalizedDocumentId }
  );
  const document = rows[0];

  if (!document) {
    return {
      error: "선택한 연결 문서를 찾을 수 없습니다."
    };
  }

  return {
    documentInternalId: document.id,
    documentName: document.file_name
  };
}

async function listWorkSequenceItems(connection = pool) {
  const [rows] = await connection.execute(`
    SELECT
      i.sequence_item_id,
      i.sequence_no,
      i.title,
      i.product_code,
      i.assigned_team,
      i.target_quantity,
      linked_doc.document_id AS linked_document_id,
      linked_doc.file_name AS linked_document_file_name,
      i.linked_document_name,
      i.status,
      i.memo,
      creator.display_name AS created_by_name,
      i.updated_at
    FROM work_sequence_item i
    JOIN work_sequence_board b ON b.id = i.board_id
    LEFT JOIN document_file linked_doc ON linked_doc.id = i.linked_document_file_id
    LEFT JOIN user_account creator ON creator.id = i.created_by
    WHERE b.board_id = 'board-local-main'
      AND i.status <> 'CANCELED'
    ORDER BY i.sequence_no ASC, i.id ASC
  `);

  return rows.map(toWorkSequenceItem);
}

async function findWorkSequenceItem(connection, sequenceItemId) {
  const [rows] = await connection.execute(
    `
      SELECT
        i.id,
        i.sequence_item_id,
        i.sequence_no,
        i.title,
        i.product_code,
        i.assigned_team,
        i.target_quantity,
        linked_doc.document_id AS linked_document_id,
        linked_doc.file_name AS linked_document_file_name,
        i.linked_document_name,
        i.status,
        i.memo,
        creator.display_name AS created_by_name,
        i.updated_at
      FROM work_sequence_item i
      JOIN work_sequence_board b ON b.id = i.board_id
      LEFT JOIN document_file linked_doc ON linked_doc.id = i.linked_document_file_id
      LEFT JOIN user_account creator ON creator.id = i.created_by
      WHERE b.board_id = 'board-local-main'
        AND i.sequence_item_id = :sequenceItemId
      LIMIT 1
    `,
    { sequenceItemId }
  );

  return rows[0] ?? null;
}

app.get("/api/v1/users", async (req, res, next) => {
  try {
    const user = await requireSuperAdmin(req, res);

    if (!user) {
      return;
    }

    const [rows] = await pool.execute(`
      SELECT
        u.user_id,
        u.login_id,
        u.display_name,
        u.status,
        u.updated_at,
        r.role_id,
        r.role_name
      FROM user_account u
      LEFT JOIN user_role ur ON ur.user_id = u.id
      LEFT JOIN role r ON r.id = ur.role_id
      ORDER BY u.created_at ASC, u.id ASC
    `);

    res.json({
      users: rows.map(toUserListItem)
    });
  } catch (error) {
    next(error);
  }
});

app.patch("/api/v1/users/:userId/role", async (req, res, next) => {
  const allowedRoleIds = ["super-admin", "mes-user", "pop-user", "general-user"];

  try {
    const user = await requireSuperAdmin(req, res);

    if (!user) {
      return;
    }

    const { roleId } = req.body ?? {};

    if (!allowedRoleIds.includes(roleId)) {
      res.status(400).json({
        error: {
          code: "VALIDATION_ERROR",
          message: "지원하지 않는 회원 등급입니다."
        }
      });
      return;
    }

    const connection = await pool.getConnection();

    try {
      await connection.beginTransaction();

      const [targetRows] = await connection.execute(
        `
          SELECT
            u.id,
            u.user_id,
            r.role_id
          FROM user_account u
          LEFT JOIN user_role ur ON ur.user_id = u.id
          LEFT JOIN role r ON r.id = ur.role_id
          WHERE u.user_id = :userId
          LIMIT 1
        `,
        { userId: req.params.userId }
      );

      const targetUser = targetRows[0];

      if (!targetUser) {
        await connection.rollback();
        res.status(404).json({
          error: {
            code: "USER_NOT_FOUND",
            message: "회원을 찾을 수 없습니다."
          }
        });
        return;
      }

      if (targetUser.role_id === "super-admin" && roleId !== "super-admin") {
        const [countRows] = await connection.execute(
          `
            SELECT COUNT(*) AS super_admin_count
            FROM user_account u
            JOIN user_role ur ON ur.user_id = u.id
            JOIN role r ON r.id = ur.role_id
            WHERE r.role_id = 'super-admin'
              AND u.status = 'ACTIVE'
          `
        );

        if (Number(countRows[0].super_admin_count) <= 1) {
          await connection.rollback();
          res.status(409).json({
            error: {
              code: "LAST_SUPER_ADMIN",
              message: "마지막 최고관리자는 다른 등급으로 변경할 수 없습니다."
            }
          });
          return;
        }
      }

      const [roleRows] = await connection.execute(
        "SELECT id FROM role WHERE role_id = :roleId LIMIT 1",
        { roleId }
      );

      if (!roleRows[0]) {
        await connection.rollback();
        res.status(400).json({
          error: {
            code: "ROLE_NOT_FOUND",
            message: "회원 등급을 찾을 수 없습니다."
          }
        });
        return;
      }

      await connection.execute("DELETE FROM user_role WHERE user_id = :userId", {
        userId: targetUser.id
      });
      await connection.execute(
        "INSERT INTO user_role (user_id, role_id) VALUES (:userId, :roleId)",
        {
          userId: targetUser.id,
          roleId: roleRows[0].id
        }
      );

      await connection.commit();

      const [updatedRows] = await pool.execute(
        `
          SELECT
            u.user_id,
            u.login_id,
            u.display_name,
            u.status,
            u.updated_at,
            r.role_id,
            r.role_name
          FROM user_account u
          LEFT JOIN user_role ur ON ur.user_id = u.id
          LEFT JOIN role r ON r.id = ur.role_id
          WHERE u.user_id = :userId
          LIMIT 1
        `,
        { userId: req.params.userId }
      );

      res.json({
        user: toUserListItem(updatedRows[0])
      });
    } catch (error) {
      await connection.rollback();
      throw error;
    } finally {
      connection.release();
    }
  } catch (error) {
    next(error);
  }
});

app.get("/api/v1/notifications", async (req, res, next) => {
  try {
    const user = await requireLogin(req, res);

    if (!user) {
      return;
    }

    const actorUserId = await findInternalUserId(user);
    const [rows] = await pool.execute(
      `
        SELECT
          n.notification_id,
          n.event_type,
          n.source_type,
          n.source_document_id,
          n.source_journal_id,
          n.source_sequence_item_id,
          n.title,
          n.message,
          n.read_at,
          n.created_at,
          actor.display_name AS actor_name
        FROM notification n
        LEFT JOIN user_account actor ON actor.id = n.actor_user_id
        WHERE n.target_user_id = :targetUserId
        ORDER BY n.created_at DESC, n.id DESC
        LIMIT 100
      `,
      { targetUserId: actorUserId }
    );
    const [countRows] = await pool.execute(
      `
        SELECT COUNT(*) AS unread_count
        FROM notification
        WHERE target_user_id = :targetUserId
          AND read_at IS NULL
      `,
      { targetUserId: actorUserId }
    );

    res.json({
      notifications: rows.map(toNotificationItem),
      unreadCount: Number(countRows[0]?.unread_count ?? 0)
    });
  } catch (error) {
    next(error);
  }
});

app.patch("/api/v1/notifications/:notificationId/read", async (req, res, next) => {
  try {
    const user = await requireLogin(req, res);

    if (!user) {
      return;
    }

    const actorUserId = await findInternalUserId(user);

    await pool.execute(
      `
        UPDATE notification
        SET read_at = COALESCE(read_at, NOW())
        WHERE notification_id = :notificationId
          AND target_user_id = :targetUserId
      `,
      {
        notificationId: req.params.notificationId,
        targetUserId: actorUserId
      }
    );

    const [rows] = await pool.execute(
      `
        SELECT
          n.notification_id,
          n.event_type,
          n.source_type,
          n.source_document_id,
          n.source_journal_id,
          n.source_sequence_item_id,
          n.title,
          n.message,
          n.read_at,
          n.created_at,
          actor.display_name AS actor_name
        FROM notification n
        LEFT JOIN user_account actor ON actor.id = n.actor_user_id
        WHERE n.notification_id = :notificationId
          AND n.target_user_id = :targetUserId
        LIMIT 1
      `,
      {
        notificationId: req.params.notificationId,
        targetUserId: actorUserId
      }
    );

    if (!rows[0]) {
      res.status(404).json({
        error: {
          code: "NOTIFICATION_NOT_FOUND",
          message: "알림을 찾을 수 없습니다."
        }
      });
      return;
    }

    const [countRows] = await pool.execute(
      `
        SELECT COUNT(*) AS unread_count
        FROM notification
        WHERE target_user_id = :targetUserId
          AND read_at IS NULL
      `,
      { targetUserId: actorUserId }
    );

    res.json({
      notification: toNotificationItem(rows[0]),
      unreadCount: Number(countRows[0]?.unread_count ?? 0)
    });
  } catch (error) {
    next(error);
  }
});

app.get("/api/v1/document-explorer", async (req, res, next) => {
  try {
    const user = await requireLogin(req, res);

    if (!user) {
      return;
    }

    const folders = await listDocumentFolders();
    const documents = await listDocumentItems();

    res.json({
      currentFolderId: "folder-field-documents",
      folders,
      documents,
      currentFolders: folders.filter(
        (folder) => folder.parentFolderId === "folder-field-documents"
      ),
      canManage: canManageDocuments(user)
    });
  } catch (error) {
    next(error);
  }
});

app.get("/api/v1/field-journal-entries", async (req, res, next) => {
  try {
    const user = await requireLogin(req, res);

    if (!user) {
      return;
    }

    res.json({
      entries: await listFieldJournalEntries()
    });
  } catch (error) {
    next(error);
  }
});

app.post(
  "/api/v1/field-journal-entries",
  upload.single("photo"),
  async (req, res, next) => {
    let savedFile = null;

    try {
      const user = await requireLogin(req, res);

      if (!user) {
        return;
      }

      if (!canManageDocuments(user)) {
        res.status(403).json({
          error: {
            code: "PERMISSION_DENIED",
            message: "작업일지는 최고관리자, MES 사용자, POP 사용자만 입력할 수 있습니다."
          }
        });
        return;
      }

      const memo = normalizeOptionalText(req.body?.memo);
      const isHandover = normalizeBooleanFormValue(req.body?.isHandover);
      const handoverTo = isHandover ? normalizeOptionalText(req.body?.handoverTo) : null;
      const handoverStatus = isHandover ? "PENDING" : "NONE";
      const hasPhoto = Boolean(req.file);
      let originalFileName = null;

      if (req.file) {
        originalFileName = normalizeUploadedFileName(req.file.originalname);

        if (!getJournalPhotoFileType(originalFileName, req.file.mimetype)) {
          res.status(400).json({
            error: {
              code: "UNSUPPORTED_PHOTO_TYPE",
              message: "작업일지 사진은 이미지 파일만 업로드할 수 있습니다."
            }
          });
          return;
        }

        savedFile = await saveUploadedDocumentFile(req.file);
      }

      const connection = await pool.getConnection();

      try {
        await connection.beginTransaction();

        const actorUserId = await findInternalUserId(user);
        const targetFolder = await getOrCreateFieldJournalFolder(
          connection,
          actorUserId
        );
        const now = new Date();
        const journalId = `journal_${crypto.randomUUID().replaceAll("-", "")}`;
        const publicDocumentId = `doc_${journalId}`;
        const fileName = makeJournalDocumentName(now, isHandover, handoverTo);
        const fileType = savedFile ? "IMAGE" : "JOURNAL";
        const summary = makeJournalSummary(memo, hasPhoto, isHandover, handoverTo);

        const [documentInsertResult] = await connection.execute(
          `
            INSERT INTO document_file (
              document_id,
              folder_id,
              file_name,
              file_type,
              meta_text,
              category_path,
              current_version,
              owner_id,
              published_at,
              security_level,
              page_count,
              summary,
              created_by
            )
            VALUES (
              :documentId,
              :folderInternalId,
              :fileName,
              :fileType,
              :metaText,
              '문서함 / 작업일지',
              'v1',
              :actorUserId,
              NOW(),
              '현장 기록',
              0,
              :summary,
              :actorUserId
            )
          `,
          {
            actorUserId,
            documentId: publicDocumentId,
            fileName,
            fileType,
            folderInternalId: targetFolder.id,
            metaText: isHandover
              ? "작업일지 / 인수인계"
              : hasPhoto
                ? "작업일지 / 사진"
                : "작업일지 / 메모",
            summary
          }
        );
        const documentInternalId = documentInsertResult.insertId;

        const [versionInsertResult] = await connection.execute(
          `
            INSERT INTO document_file_version (
              document_file_id,
              version_label,
              file_name,
              change_note,
              owner_id,
              published_at,
              status
            )
            VALUES (
              :documentInternalId,
              'v1',
              :fileName,
              '현장 작업일지 등록',
              :actorUserId,
              NOW(),
              'CURRENT'
            )
          `,
          {
            actorUserId,
            documentInternalId,
            fileName
          }
        );

        if (savedFile) {
          await connection.execute(
            `
              INSERT INTO document_file_storage (
                document_file_version_id,
                storage_path,
                original_file_name,
                mime_type,
                byte_size,
                sha256_hash
              )
              VALUES (
                :documentFileVersionId,
                :storagePath,
                :originalFileName,
                :mimeType,
                :byteSize,
                :sha256Hash
              )
            `,
            {
              byteSize: savedFile.byteSize,
              documentFileVersionId: versionInsertResult.insertId,
              mimeType: savedFile.mimeType,
              originalFileName: savedFile.originalFileName,
              sha256Hash: savedFile.sha256Hash,
              storagePath: savedFile.storageRelativePath
            }
          );
        }

        await connection.execute(
          `
            INSERT INTO field_journal_entry (
              journal_id,
              document_file_id,
              memo,
              photo_file_name,
              is_handover,
              handover_to,
              handover_status,
              created_by
            )
            VALUES (
              :journalId,
              :documentInternalId,
              :memo,
              :photoFileName,
              :isHandover,
              :handoverTo,
              :handoverStatus,
              :actorUserId
            )
          `,
          {
            actorUserId,
            documentInternalId,
            handoverStatus,
            handoverTo,
            isHandover: isHandover ? 1 : 0,
            journalId,
            memo,
            photoFileName: originalFileName
          }
        );

        await replaceDocumentTags(
          connection,
          documentInternalId,
          isHandover ? ["작업일지", "인수인계"] : ["작업일지"],
          actorUserId
        );

        await connection.execute(
          `
            INSERT INTO document_history (
              document_file_id,
              document_file_version_id,
              event_type,
              before_value,
              after_value,
              actor_user_id
            )
            VALUES (
              :documentInternalId,
              :documentFileVersionId,
              'FIELD_JOURNAL_CREATED',
              NULL,
              :afterValue,
              :actorUserId
            )
          `,
          {
            actorUserId,
            afterValue: JSON.stringify({
              documentId: publicDocumentId,
              journalId,
              fileName,
              hasPhoto,
              handoverStatus,
              handoverTo,
              isHandover,
              memo
            }),
            documentFileVersionId: versionInsertResult.insertId,
            documentInternalId
          }
        );

        await notifyActiveUsersExcept(connection, actorUserId, {
          eventType: isHandover ? "FIELD_HANDOVER_CREATED" : "FIELD_JOURNAL_CREATED",
          message: summary,
          sourceDocumentId: publicDocumentId,
          sourceJournalId: journalId,
          sourceType: "JOURNAL",
          title: isHandover ? `새 인수인계: ${fileName}` : `새 작업일지: ${fileName}`
        });

        const documents = await listDocumentItems(connection);
        const entries = await listFieldJournalEntries(connection);
        const createdEntry = entries.find((entry) => entry.journalId === journalId);

        await connection.commit();

        res.status(201).json({
          entry: createdEntry,
          entries,
          documents
        });
      } catch (error) {
        await connection.rollback();
        throw error;
      } finally {
        connection.release();
      }
    } catch (error) {
      if (savedFile) {
        try {
          await fs.unlink(new URL(savedFile.storageRelativePath, documentStorageRoot));
        } catch {
          // Ignore cleanup errors; the API error is more useful to the caller.
        }
      }

      next(error);
    }
  }
);

app.post(
  "/api/v1/field-journal-entries/:journalId/handover-read",
  async (req, res, next) => {
    try {
      const user = await requireLogin(req, res);

      if (!user) {
        return;
      }

      const connection = await pool.getConnection();

      try {
        await connection.beginTransaction();

        const actorUserId = await findInternalUserId(user);
        const [entryRows] = await connection.execute(
          `
            SELECT
              e.id,
              e.journal_id,
              e.document_file_id,
              e.memo,
              e.handover_to,
              e.handover_status,
              e.is_handover,
              e.created_by,
              d.document_id,
              d.file_name,
              d.current_version,
              v.id AS document_file_version_id
            FROM field_journal_entry e
            JOIN document_file d ON d.id = e.document_file_id
            LEFT JOIN document_file_version v
              ON v.document_file_id = d.id
              AND v.version_label = d.current_version
            WHERE e.journal_id = :journalId
            LIMIT 1
          `,
          { journalId: req.params.journalId }
        );
        const entry = entryRows[0];

        if (!entry) {
          await connection.rollback();
          res.status(404).json({
            error: {
              code: "JOURNAL_NOT_FOUND",
              message: "작업일지를 찾을 수 없습니다."
            }
          });
          return;
        }

        if (!entry.is_handover) {
          await connection.rollback();
          res.status(400).json({
            error: {
              code: "NOT_HANDOVER",
              message: "인수인계 항목만 확인 처리할 수 있습니다."
            }
          });
          return;
        }

        await connection.execute(
          `
            INSERT INTO field_journal_handover_read (
              field_journal_entry_id,
              reader_user_id,
              read_at
            )
            VALUES (
              :journalEntryId,
              :actorUserId,
              NOW()
            )
          `,
          {
            actorUserId,
            journalEntryId: entry.id
          }
        );

        await connection.execute(
          `
            INSERT INTO document_history (
              document_file_id,
              document_file_version_id,
              event_type,
              before_value,
              after_value,
              actor_user_id
            )
            VALUES (
              :documentInternalId,
              :documentFileVersionId,
              'FIELD_HANDOVER_READ',
              :beforeValue,
              :afterValue,
              :actorUserId
            )
          `,
          {
            actorUserId,
            afterValue: JSON.stringify({
              documentId: entry.document_id,
              fileName: entry.file_name,
              handoverTo: entry.handover_to,
              journalId: entry.journal_id,
              memo: entry.memo,
              readerUserId: user.userId,
              readerName: user.displayName
            }),
            beforeValue: JSON.stringify({
              handoverStatus: entry.handover_status
            }),
            documentFileVersionId: entry.document_file_version_id,
            documentInternalId: entry.document_file_id
          }
        );

        await createNotifications(
          connection,
          [entry.created_by].filter((targetUserId) => targetUserId !== actorUserId),
          {
            actorUserId,
            eventType: "FIELD_HANDOVER_READ",
            message: `${user.displayName}님이 인수인계를 읽음 기록했습니다.`,
            sourceDocumentId: entry.document_id,
            sourceJournalId: entry.journal_id,
            sourceType: "JOURNAL",
            title: `인수인계 읽음 기록: ${entry.file_name}`
          }
        );

        const entries = await listFieldJournalEntries(connection);
        const updatedEntry = entries.find(
          (journalEntry) => journalEntry.journalId === entry.journal_id
        );

        await connection.commit();

        res.json({
          entry: updatedEntry,
          entries
        });
      } catch (error) {
        await connection.rollback();
        throw error;
      } finally {
        connection.release();
      }
    } catch (error) {
      next(error);
    }
  }
);

app.post(
  "/api/v1/field-journal-entries/:journalId/replies",
  async (req, res, next) => {
    try {
      const user = await requireLogin(req, res);

      if (!user) {
        return;
      }

      if (!canManageDocuments(user)) {
        res.status(403).json({
          error: {
            code: "PERMISSION_DENIED",
            message: "작업일지 응답은 최고관리자, MES 사용자, POP 사용자만 입력할 수 있습니다."
          }
        });
        return;
      }

      const replyText = normalizeOptionalText(req.body?.replyText);
      const replyType =
        typeof req.body?.replyType === "string" &&
        ["COMMENT", "ACTION", "QUESTION"].includes(req.body.replyType)
          ? req.body.replyType
          : "COMMENT";

      if (!replyText) {
        res.status(400).json({
          error: {
            code: "VALIDATION_ERROR",
            message: "응답 내용을 입력해 주세요."
          }
        });
        return;
      }

      const connection = await pool.getConnection();

      try {
        await connection.beginTransaction();

        const actorUserId = await findInternalUserId(user);
        const [entryRows] = await connection.execute(
          `
            SELECT
              e.id,
              e.journal_id,
              e.document_file_id,
              e.memo,
              e.handover_to,
              e.is_handover,
              e.created_by,
              d.document_id,
              d.file_name,
              d.current_version
            FROM field_journal_entry e
            JOIN document_file d ON d.id = e.document_file_id
            WHERE e.journal_id = :journalId
            LIMIT 1
          `,
          { journalId: req.params.journalId }
        );
        const entry = entryRows[0];

        if (!entry) {
          await connection.rollback();
          res.status(404).json({
            error: {
              code: "JOURNAL_NOT_FOUND",
              message: "작업일지를 찾을 수 없습니다."
            }
          });
          return;
        }

        const nextVersion = getNextVersionLabel(entry.current_version);
        const changeNote =
          replyType === "ACTION"
            ? "조치 응답 추가"
            : replyType === "QUESTION"
              ? "질문 응답 추가"
              : "댓글 추가";

        await connection.execute(
          `
            UPDATE document_file_version
            SET status = 'ARCHIVED'
            WHERE document_file_id = :documentInternalId
          `,
          { documentInternalId: entry.document_file_id }
        );

        const [versionInsertResult] = await connection.execute(
          `
            INSERT INTO document_file_version (
              document_file_id,
              version_label,
              file_name,
              change_note,
              owner_id,
              published_at,
              status
            )
            VALUES (
              :documentInternalId,
              :versionLabel,
              :fileName,
              :changeNote,
              :actorUserId,
              NOW(),
              'CURRENT'
            )
          `,
          {
            actorUserId,
            changeNote,
            documentInternalId: entry.document_file_id,
            fileName: entry.file_name,
            versionLabel: nextVersion
          }
        );

        await connection.execute(
          `
            UPDATE document_file
            SET current_version = :versionLabel,
                owner_id = :actorUserId,
                published_at = NOW(),
                summary = :summary
            WHERE id = :documentInternalId
          `,
          {
            actorUserId,
            documentInternalId: entry.document_file_id,
            summary: replyText.slice(0, 800),
            versionLabel: nextVersion
          }
        );

        const replyId = `reply_${crypto.randomUUID().replaceAll("-", "")}`;

        await connection.execute(
          `
            INSERT INTO field_journal_reply (
              reply_id,
              field_journal_entry_id,
              document_file_version_id,
              reply_text,
              reply_type,
              created_by
            )
            VALUES (
              :replyId,
              :journalEntryId,
              :documentFileVersionId,
              :replyText,
              :replyType,
              :actorUserId
            )
          `,
          {
            actorUserId,
            documentFileVersionId: versionInsertResult.insertId,
            journalEntryId: entry.id,
            replyId,
            replyText,
            replyType
          }
        );

        const [participantRows] = await connection.execute(
          `
            SELECT created_by AS user_id
            FROM field_journal_entry
            WHERE id = :journalEntryId
              AND created_by IS NOT NULL
            UNION
            SELECT created_by AS user_id
            FROM field_journal_reply
            WHERE field_journal_entry_id = :journalEntryId
              AND created_by IS NOT NULL
          `,
          { journalEntryId: entry.id }
        );

        await connection.execute(
          `
            INSERT INTO document_history (
              document_file_id,
              document_file_version_id,
              event_type,
              before_value,
              after_value,
              actor_user_id
            )
            VALUES (
              :documentInternalId,
              :documentFileVersionId,
              'FIELD_JOURNAL_REPLY_CREATED',
              :beforeValue,
              :afterValue,
              :actorUserId
            )
          `,
          {
            actorUserId,
            afterValue: JSON.stringify({
              documentId: entry.document_id,
              fileName: entry.file_name,
              journalId: entry.journal_id,
              replyId,
              replyText,
              replyType,
              version: nextVersion
            }),
            beforeValue: JSON.stringify({
              version: entry.current_version
            }),
            documentFileVersionId: versionInsertResult.insertId,
            documentInternalId: entry.document_file_id
          }
        );

        await createNotifications(
          connection,
          participantRows
            .map((row) => row.user_id)
            .filter((targetUserId) => Number(targetUserId) !== Number(actorUserId)),
          {
            actorUserId,
            eventType: "FIELD_JOURNAL_REPLY_CREATED",
            message: replyText,
            sourceDocumentId: entry.document_id,
            sourceJournalId: entry.journal_id,
            sourceType: "JOURNAL",
            title: `작업일지 응답 추가: ${entry.file_name}`
          }
        );

        const entries = await listFieldJournalEntries(connection);
        const documents = await listDocumentItems(connection);
        const updatedEntry = entries.find(
          (journalEntry) => journalEntry.journalId === entry.journal_id
        );

        await connection.commit();

        res.status(201).json({
          entry: updatedEntry,
          entries,
          documents
        });
      } catch (error) {
        await connection.rollback();
        throw error;
      } finally {
        connection.release();
      }
    } catch (error) {
      next(error);
    }
  }
);

app.post(
  "/api/v1/document-files/create",
  async (req, res, next) => {
    let savedFile = null;

    try {
      const user = await requireLogin(req, res);

      if (!user) {
        return;
      }

      if (!canManageDocuments(user)) {
        res.status(403).json({
          error: {
            code: "PERMISSION_DENIED",
            message: "문서 생성은 최고관리자, MES 사용자, POP 사용자만 사용할 수 있습니다."
          }
        });
        return;
      }

      const documentType = req.body?.documentType === "EXCEL" ? "EXCEL" : "PDF";
      const fileName =
        documentType === "EXCEL"
          ? normalizeExcelFileName(req.body?.fileName)
          : normalizePdfFileName(req.body?.fileName);
      const folderId =
        typeof req.body?.folderId === "string" && req.body.folderId.trim()
          ? req.body.folderId.trim()
          : "folder-field-documents";
      const summary =
        typeof req.body?.summary === "string" && req.body.summary.trim()
          ? req.body.summary.trim().slice(0, 800)
          : `${fileName || (documentType === "EXCEL" ? "새 Excel" : "새 PDF")} 문서입니다.`;
      const editorBody =
        typeof req.body?.editorBody === "string"
          ? req.body.editorBody.slice(0, 12_000_000)
          : "";
      const pageImage = parseJpegDataUrl(req.body?.pageImageDataUrl);
      const spreadsheetCells = normalizeSpreadsheetCells(req.body?.spreadsheetCells);
      const tagNames = parseDocumentTags(req.body?.tags);

      if (!fileName) {
        res.status(400).json({
          error: {
            code: "VALIDATION_ERROR",
            message:
              documentType === "EXCEL"
                ? "Excel 파일명을 입력해 주세요."
                : "PDF 파일명을 입력해 주세요."
          }
        });
        return;
      }

      if (fileName.length > 220) {
        res.status(400).json({
          error: {
            code: "VALIDATION_ERROR",
            message: "파일명은 220자 이하로 입력해 주세요."
          }
        });
        return;
      }

      if (documentType === "PDF" && req.body?.pageImageDataUrl && !pageImage) {
        res.status(400).json({
          error: {
            code: "INVALID_PAGE_IMAGE",
            message: "A4 문서 화면을 PDF로 변환하지 못했습니다."
          }
        });
        return;
      }

      savedFile = await saveDocumentBuffer({
        buffer:
          documentType === "EXCEL"
            ? createBlankXlsxBuffer(spreadsheetCells)
            : pageImage
              ? createPdfBufferFromJpeg(pageImage)
              : createBlankPdfBuffer(),
        extension: documentType === "EXCEL" ? ".xlsx" : ".pdf",
        mimeType:
          documentType === "EXCEL"
            ? "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            : "application/pdf",
        originalFileName: fileName
      });

      const connection = await pool.getConnection();

      try {
        await connection.beginTransaction();
        await ensureDocumentEditorDraftTable(connection);

        const actorUserId = await findInternalUserId(user);
        const [folderRows] = await connection.execute(
          "SELECT id, folder_name FROM document_folder WHERE folder_id = :folderId LIMIT 1",
          { folderId }
        );
        const targetFolder = folderRows[0];

        if (!targetFolder) {
          await connection.rollback();
          res.status(404).json({
            error: {
              code: "FOLDER_NOT_FOUND",
              message: "문서를 만들 폴더를 찾을 수 없습니다."
            }
          });
          return;
        }

        const [duplicateRows] = await connection.execute(
          `
            SELECT id
            FROM document_file
            WHERE folder_id = :folderInternalId
              AND file_name = :fileName
            LIMIT 1
          `,
          {
            folderInternalId: targetFolder.id,
            fileName
          }
        );

        if (duplicateRows[0]) {
          await connection.rollback();
          res.status(409).json({
            error: {
              code: "DUPLICATE_DOCUMENT_NAME",
              message: "이 폴더에 이미 같은 이름의 문서가 있습니다."
            }
          });
          return;
        }

        const publicDocumentId = `doc_${crypto.randomUUID().replaceAll("-", "")}`;
        const versionLabel = "v1";
        const [documentInsertResult] = await connection.execute(
          `
            INSERT INTO document_file (
              document_id,
              folder_id,
              file_name,
              file_type,
              meta_text,
              category_path,
              current_version,
              owner_id,
              published_at,
              security_level,
              page_count,
              summary,
              created_by
            )
            VALUES (
              :documentId,
              :folderInternalId,
              :fileName,
              :fileType,
              :metaText,
              :categoryPath,
              :versionLabel,
              :actorUserId,
              NOW(),
              '뷰어 전용',
              :pageCount,
              :summary,
              :actorUserId
            )
          `,
          {
            actorUserId,
            categoryPath: targetFolder.folder_name,
            documentId: publicDocumentId,
            fileType: documentType,
            fileName,
            folderInternalId: targetFolder.id,
            metaText: `${targetFolder.folder_name} / 새 ${
              documentType === "EXCEL" ? "Excel" : "PDF"
            }`,
            pageCount: documentType === "EXCEL" ? 0 : 1,
            summary,
            versionLabel
          }
        );
        const documentInternalId = documentInsertResult.insertId;
        const [versionInsertResult] = await connection.execute(
          `
            INSERT INTO document_file_version (
              document_file_id,
              version_label,
              file_name,
              change_note,
              owner_id,
              published_at,
              status
            )
            VALUES (
              :documentInternalId,
              :versionLabel,
              :fileName,
              :changeNote,
              :actorUserId,
              NOW(),
              'CURRENT'
            )
          `,
          {
            actorUserId,
            changeNote: `탐색기에서 새 ${
              documentType === "EXCEL" ? "Excel" : "PDF"
            } 문서 생성`,
            documentInternalId,
            fileName,
            versionLabel
          }
        );

        await connection.execute(
          `
            INSERT INTO document_file_storage (
              document_file_version_id,
              storage_path,
              original_file_name,
              mime_type,
              byte_size,
              sha256_hash
            )
            VALUES (
              :documentFileVersionId,
              :storagePath,
              :originalFileName,
              :mimeType,
              :byteSize,
              :sha256Hash
            )
          `,
          {
            byteSize: savedFile.byteSize,
            documentFileVersionId: versionInsertResult.insertId,
            mimeType: savedFile.mimeType,
            originalFileName: savedFile.originalFileName,
            sha256Hash: savedFile.sha256Hash,
            storagePath: savedFile.storageRelativePath
          }
        );

        await replaceDocumentTags(
          connection,
          documentInternalId,
          tagNames,
          actorUserId
        );

        await connection.execute(
          `
            INSERT INTO document_editor_draft (
              document_file_id,
              editor_format,
              title,
              body,
              updated_by
            )
            VALUES (
              :documentInternalId,
              :editorFormat,
              :title,
              :body,
              :actorUserId
            )
            ON DUPLICATE KEY UPDATE
              editor_format = VALUES(editor_format),
              title = VALUES(title),
              body = VALUES(body),
              updated_by = VALUES(updated_by)
          `,
          {
            actorUserId,
            body:
              documentType === "EXCEL"
                ? JSON.stringify({ sheets: [{ name: "Sheet1", cells: spreadsheetCells }] })
                : editorBody,
            documentInternalId,
            editorFormat: documentType === "EXCEL" ? "XLSX_BLANK_V1" : "A4_BLOCKS_V1",
            title: fileName
          }
        );

        await connection.execute(
          `
            INSERT INTO document_history (
              document_file_id,
              document_file_version_id,
              event_type,
              before_value,
              after_value,
              actor_user_id
            )
            VALUES (
              :documentInternalId,
              :documentFileVersionId,
              'DOCUMENT_CREATED',
              NULL,
              :afterValue,
              :actorUserId
            )
          `,
          {
            actorUserId,
            afterValue: JSON.stringify({
              documentId: publicDocumentId,
              fileName,
              version: versionLabel,
              folderId,
              tags: tagNames,
              storagePath: savedFile.storageRelativePath,
              createdFrom: "explorer",
              editorFormat: documentType === "EXCEL" ? "XLSX_BLANK_V1" : "A4_TEXT_V1"
            }),
            documentFileVersionId: versionInsertResult.insertId,
            documentInternalId
          }
        );

        await notifyActiveUsersExcept(connection, actorUserId, {
          eventType: "DOCUMENT_CREATED",
          message: `${fileName} 문서가 생성되었습니다.`,
          sourceDocumentId: publicDocumentId,
          sourceType: "DOCUMENT",
          title: "새 문서"
        });

        const documents = await listDocumentItems(connection);
        const createdDocument = documents.find(
          (document) => document.documentId === publicDocumentId
        );

        await connection.commit();

        res.status(201).json({
          document: createdDocument,
          documents
        });
      } catch (error) {
        await connection.rollback();
        throw error;
      } finally {
        connection.release();
      }
    } catch (error) {
      if (savedFile) {
        try {
          await fs.unlink(new URL(savedFile.storageRelativePath, documentStorageRoot));
        } catch {
          // Ignore cleanup errors; the API error is more useful to the caller.
        }
      }

      next(error);
    }
  }
);

app.get("/api/v1/document-files/:documentId/editor", async (req, res, next) => {
  try {
    const user = await requireLogin(req, res);

    if (!user) {
      return;
    }

    if (!canManageDocuments(user)) {
      res.status(403).json({
        error: {
          code: "PERMISSION_DENIED",
          message: "문서 수정은 최고관리자, MES 사용자, POP 사용자만 사용할 수 있습니다."
        }
      });
      return;
    }

    const documentId =
      typeof req.params.documentId === "string"
        ? req.params.documentId.trim()
        : "";

    const connection = await pool.getConnection();

    try {
      await ensureDocumentEditorDraftTable(connection);

      const [rows] = await connection.execute(
        `
          SELECT
            d.document_id,
            d.file_name,
            d.file_type,
            d.summary,
            draft.editor_format,
            draft.title,
            draft.body
          FROM document_file d
          JOIN document_editor_draft draft ON draft.document_file_id = d.id
          WHERE d.document_id = :documentId
          LIMIT 1
        `,
        { documentId }
      );
      const documentRow = rows[0];

      if (!documentRow) {
        res.status(404).json({
          error: {
            code: "EDITOR_DRAFT_NOT_FOUND",
            message: "수정 가능한 편집 원본을 찾을 수 없습니다."
          }
        });
        return;
      }

      const [tagRows] = await connection.execute(
        `
          SELECT t.tag_name
          FROM document_file_tag ft
          JOIN document_file d ON d.id = ft.document_file_id
          JOIN document_tag t ON t.id = ft.tag_id
          WHERE d.document_id = :documentId
          ORDER BY t.tag_name ASC
        `,
        { documentId }
      );

      res.json({
        draft: {
          documentId: documentRow.document_id,
          documentType: documentRow.file_type,
          editorFormat: documentRow.editor_format,
          fileName: documentRow.title || documentRow.file_name,
          body:
            documentRow.file_type === "EXCEL"
              ? ""
              : (documentRow.body ?? ""),
          spreadsheetCells:
            documentRow.file_type === "EXCEL"
              ? parseSpreadsheetDraftCells(documentRow.body)
              : [],
          summary: documentRow.summary ?? "",
          tags: tagRows.map((row) => row.tag_name).join(", ")
        }
      });
    } finally {
      connection.release();
    }
  } catch (error) {
    next(error);
  }
});

app.put("/api/v1/document-files/:documentId/editor", async (req, res, next) => {
  let savedFile = null;

  try {
    const user = await requireLogin(req, res);

    if (!user) {
      return;
    }

    if (!canManageDocuments(user)) {
      res.status(403).json({
        error: {
          code: "PERMISSION_DENIED",
          message: "문서 수정은 최고관리자, MES 사용자, POP 사용자만 사용할 수 있습니다."
        }
      });
      return;
    }

    const documentId =
      typeof req.params.documentId === "string"
        ? req.params.documentId.trim()
        : "";
    const editorBody =
      typeof req.body?.editorBody === "string"
        ? req.body.editorBody.slice(0, 12_000_000)
        : "";
    const pageImage = parseJpegDataUrl(req.body?.pageImageDataUrl);
    const spreadsheetCells = normalizeSpreadsheetCells(req.body?.spreadsheetCells);
    const tagNames = parseDocumentTags(req.body?.tags);
    const changeNote =
      typeof req.body?.changeNote === "string"
        ? req.body.changeNote.trim().slice(0, 500)
        : "";

    if (!changeNote) {
      res.status(400).json({
        error: {
          code: "VALIDATION_ERROR",
          message: "수정 사유를 입력해 주세요."
        }
      });
      return;
    }

    const connection = await pool.getConnection();

    try {
      await connection.beginTransaction();
      await ensureDocumentEditorDraftTable(connection);

      const actorUserId = await findInternalUserId(user);
      const [documentRows] = await connection.execute(
        `
          SELECT
            d.id,
            d.document_id,
            d.folder_id,
            d.file_name,
            d.file_type,
            d.current_version,
            d.page_count,
            folder.folder_id AS public_folder_id,
            folder.folder_name,
            draft.editor_format
          FROM document_file d
          JOIN document_folder folder ON folder.id = d.folder_id
          JOIN document_editor_draft draft ON draft.document_file_id = d.id
          WHERE d.document_id = :documentId
          LIMIT 1
        `,
        { documentId }
      );
      const documentRow = documentRows[0];

      if (!documentRow) {
        await connection.rollback();
        res.status(404).json({
          error: {
            code: "EDITOR_DRAFT_NOT_FOUND",
            message: "수정 가능한 편집 원본을 찾을 수 없습니다."
          }
        });
        return;
      }

      const documentType = documentRow.file_type === "EXCEL" ? "EXCEL" : "PDF";
      const fileName =
        documentType === "EXCEL"
          ? normalizeExcelFileName(req.body?.fileName || documentRow.file_name)
          : normalizePdfFileName(req.body?.fileName || documentRow.file_name);
      const summary =
        typeof req.body?.summary === "string" && req.body.summary.trim()
          ? req.body.summary.trim().slice(0, 800)
          : documentType === "EXCEL"
            ? `${fileName} Excel 문서입니다.`
            : (editorBody.trim().split("\n").find(Boolean)?.slice(0, 800) ??
              `${fileName} 문서입니다.`);

      if (!fileName) {
        await connection.rollback();
        res.status(400).json({
          error: {
            code: "VALIDATION_ERROR",
            message: "파일명을 입력해 주세요."
          }
        });
        return;
      }

      if (documentType === "PDF" && req.body?.pageImageDataUrl && !pageImage) {
        await connection.rollback();
        res.status(400).json({
          error: {
            code: "INVALID_PAGE_IMAGE",
            message: "A4 문서 화면을 PDF로 변환하지 못했습니다."
          }
        });
        return;
      }

      const [duplicateRows] = await connection.execute(
        `
          SELECT id
          FROM document_file
          WHERE id <> :documentInternalId
            AND folder_id = :folderInternalId
            AND file_name = :fileName
          LIMIT 1
        `,
        {
          documentInternalId: documentRow.id,
          folderInternalId: documentRow.folder_id,
          fileName
        }
      );

      if (duplicateRows[0]) {
        await connection.rollback();
        res.status(409).json({
          error: {
            code: "DUPLICATE_DOCUMENT_NAME",
            message: "이 폴더에 이미 같은 이름의 문서가 있습니다."
          }
        });
        return;
      }

      savedFile = await saveDocumentBuffer({
        buffer:
          documentType === "EXCEL"
            ? createBlankXlsxBuffer(spreadsheetCells)
            : pageImage
              ? createPdfBufferFromJpeg(pageImage)
              : createBlankPdfBuffer(),
        extension: documentType === "EXCEL" ? ".xlsx" : ".pdf",
        mimeType:
          documentType === "EXCEL"
            ? "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            : "application/pdf",
        originalFileName: fileName
      });

      const nextVersion = getNextVersionLabel(documentRow.current_version);

      await connection.execute(
        `
          UPDATE document_file_version
          SET status = 'ARCHIVED'
          WHERE document_file_id = :documentInternalId
        `,
        { documentInternalId: documentRow.id }
      );

      const [versionInsertResult] = await connection.execute(
        `
          INSERT INTO document_file_version (
            document_file_id,
            version_label,
            file_name,
            change_note,
            owner_id,
            published_at,
            status
          )
          VALUES (
            :documentInternalId,
            :versionLabel,
            :fileName,
            :changeNote,
            :actorUserId,
            NOW(),
            'CURRENT'
          )
        `,
        {
          actorUserId,
          changeNote,
          documentInternalId: documentRow.id,
          fileName,
          versionLabel: nextVersion
        }
      );

      await connection.execute(
        `
          INSERT INTO document_file_storage (
            document_file_version_id,
            storage_path,
            original_file_name,
            mime_type,
            byte_size,
            sha256_hash
          )
          VALUES (
            :documentFileVersionId,
            :storagePath,
            :originalFileName,
            :mimeType,
            :byteSize,
            :sha256Hash
          )
        `,
        {
          byteSize: savedFile.byteSize,
          documentFileVersionId: versionInsertResult.insertId,
          mimeType: savedFile.mimeType,
          originalFileName: savedFile.originalFileName,
          sha256Hash: savedFile.sha256Hash,
          storagePath: savedFile.storageRelativePath
        }
      );

      await connection.execute(
        `
          UPDATE document_file
          SET file_name = :fileName,
              file_type = :fileType,
              current_version = :versionLabel,
              owner_id = :actorUserId,
              published_at = NOW(),
              meta_text = :metaText,
              security_level = '뷰어 전용',
              page_count = :pageCount,
              summary = :summary
          WHERE id = :documentInternalId
        `,
        {
          actorUserId,
          documentInternalId: documentRow.id,
          fileName,
          fileType: documentType,
          metaText: `${documentRow.folder_name} / ${nextVersion}`,
          pageCount: documentType === "EXCEL" ? 0 : 1,
          summary,
          versionLabel: nextVersion
        }
      );

      await connection.execute(
        `
          INSERT INTO document_editor_draft (
            document_file_id,
            editor_format,
            title,
            body,
            updated_by
          )
          VALUES (
            :documentInternalId,
            :editorFormat,
            :title,
            :body,
            :actorUserId
          )
          ON DUPLICATE KEY UPDATE
            editor_format = VALUES(editor_format),
            title = VALUES(title),
            body = VALUES(body),
            updated_by = VALUES(updated_by)
        `,
        {
          actorUserId,
          body:
            documentType === "EXCEL"
              ? JSON.stringify({ sheets: [{ name: "Sheet1", cells: spreadsheetCells }] })
              : editorBody,
          documentInternalId: documentRow.id,
          editorFormat: documentType === "EXCEL" ? "XLSX_BLANK_V1" : "A4_BLOCKS_V1",
          title: fileName
        }
      );

      await replaceDocumentTags(connection, documentRow.id, tagNames, actorUserId);

      await connection.execute(
        `
          INSERT INTO document_history (
            document_file_id,
            document_file_version_id,
            event_type,
            before_value,
            after_value,
            actor_user_id
          )
          VALUES (
            :documentInternalId,
            :documentFileVersionId,
            'DOCUMENT_VERSION_CREATED',
            :beforeValue,
            :afterValue,
            :actorUserId
          )
        `,
        {
          actorUserId,
          afterValue: JSON.stringify({
            documentId,
            fileName,
            version: nextVersion,
            folderId: documentRow.public_folder_id,
            tags: tagNames,
            storagePath: savedFile.storageRelativePath
          }),
          beforeValue: JSON.stringify({
            documentId,
            fileName: documentRow.file_name,
            version: documentRow.current_version
          }),
          documentFileVersionId: versionInsertResult.insertId,
          documentInternalId: documentRow.id
        }
      );

      await notifyActiveUsersExcept(connection, actorUserId, {
        eventType: "DOCUMENT_VERSION_CREATED",
        message: `${fileName} ${nextVersion} 버전이 저장되었습니다.`,
        sourceDocumentId: documentId,
        sourceType: "DOCUMENT",
        title: "문서 수정 저장"
      });

      const documents = await listDocumentItems(connection);
      const updatedDocument = documents.find(
        (document) => document.documentId === documentId
      );

      await connection.commit();

      res.json({
        document: updatedDocument,
        documents
      });
    } catch (error) {
      await connection.rollback();
      throw error;
    } finally {
      connection.release();
    }
  } catch (error) {
    if (savedFile) {
      try {
        await fs.unlink(new URL(savedFile.storageRelativePath, documentStorageRoot));
      } catch {
        // Ignore cleanup errors; the API error is more useful to the caller.
      }
    }

    next(error);
  }
});

app.post(
  "/api/v1/document-files/upload",
  upload.single("file"),
  async (req, res, next) => {
    let savedFile = null;

    try {
      const user = await requireLogin(req, res);

      if (!user) {
        return;
      }

      if (!canManageDocuments(user)) {
        res.status(403).json({
          error: {
            code: "PERMISSION_DENIED",
            message: "문서 업로드는 최고관리자, MES 사용자, POP 사용자만 사용할 수 있습니다."
          }
        });
        return;
      }

      if (!req.file) {
        res.status(400).json({
          error: {
            code: "VALIDATION_ERROR",
            message: "업로드할 파일이 필요합니다."
          }
        });
        return;
      }

      const originalFileName = normalizeUploadedFileName(req.file.originalname);
      const fileType = getDocumentFileType(originalFileName);
      const folderId =
        typeof req.body?.folderId === "string" && req.body.folderId.trim()
          ? req.body.folderId.trim()
          : "folder-field-documents";
      const tagNames = parseDocumentTags(req.body?.tags);

      if (!originalFileName || !fileType) {
        res.status(400).json({
          error: {
            code: "UNSUPPORTED_FILE_TYPE",
            message: "PDF, Excel, PPT 파일만 업로드할 수 있습니다."
          }
        });
        return;
      }

      savedFile = await saveUploadedDocumentFile(req.file);

      const connection = await pool.getConnection();

      try {
        await connection.beginTransaction();

        const actorUserId = await findInternalUserId(user);
        const [folderRows] = await connection.execute(
          "SELECT id, folder_name FROM document_folder WHERE folder_id = :folderId LIMIT 1",
          { folderId }
        );
        const targetFolder = folderRows[0];

        if (!targetFolder) {
          await connection.rollback();
          res.status(404).json({
            error: {
              code: "FOLDER_NOT_FOUND",
              message: "업로드할 폴더를 찾을 수 없습니다."
            }
          });
          return;
        }

        const [documentRows] = await connection.execute(
          `
            SELECT id, document_id, current_version
            FROM document_file
            WHERE folder_id = :folderInternalId
              AND file_name = :fileName
            LIMIT 1
          `,
          {
            folderInternalId: targetFolder.id,
            fileName: originalFileName
          }
        );
        const existingDocument = documentRows[0];
        const nextVersion = existingDocument
          ? getNextVersionLabel(existingDocument.current_version)
          : "v1";
        let documentInternalId = existingDocument?.id;
        let publicDocumentId = existingDocument?.document_id;

        if (existingDocument) {
          await connection.execute(
            `
              UPDATE document_file_version
              SET status = 'ARCHIVED'
              WHERE document_file_id = :documentInternalId
            `,
            { documentInternalId }
          );
          await connection.execute(
            `
              UPDATE document_file
              SET current_version = :versionLabel,
                  owner_id = :actorUserId,
                  published_at = NOW(),
                  file_type = :fileType,
                  meta_text = :metaText,
                  security_level = '뷰어 전용',
                  summary = :summary
              WHERE id = :documentInternalId
            `,
            {
              actorUserId,
              documentInternalId,
              fileType,
              metaText: `${targetFolder.folder_name} / ${nextVersion}`,
              summary: `${originalFileName} 업로드 문서입니다.`,
              versionLabel: nextVersion
            }
          );
        } else {
          publicDocumentId = `doc_${crypto.randomUUID().replaceAll("-", "")}`;
          const [insertResult] = await connection.execute(
            `
              INSERT INTO document_file (
                document_id,
                folder_id,
                file_name,
                file_type,
                meta_text,
                category_path,
                current_version,
                owner_id,
                published_at,
                security_level,
                page_count,
                summary,
                created_by
              )
              VALUES (
                :documentId,
                :folderInternalId,
                :fileName,
                :fileType,
                :metaText,
                :categoryPath,
                :versionLabel,
                :actorUserId,
                NOW(),
                '뷰어 전용',
                0,
                :summary,
                :actorUserId
              )
            `,
            {
              actorUserId,
              categoryPath: targetFolder.folder_name,
              documentId: publicDocumentId,
              fileName: originalFileName,
              fileType,
              folderInternalId: targetFolder.id,
              metaText: `${targetFolder.folder_name} / 업로드`,
              summary: `${originalFileName} 업로드 문서입니다.`,
              versionLabel: nextVersion
            }
          );
          documentInternalId = insertResult.insertId;
        }

        const [versionInsertResult] = await connection.execute(
          `
            INSERT INTO document_file_version (
              document_file_id,
              version_label,
              file_name,
              change_note,
              owner_id,
              published_at,
              status
            )
            VALUES (
              :documentInternalId,
              :versionLabel,
              :fileName,
              :changeNote,
              :actorUserId,
              NOW(),
              'CURRENT'
            )
          `,
          {
            actorUserId,
            changeNote: existingDocument
              ? "드래그앤드랍 업로드로 새 버전 등록"
              : "드래그앤드랍 업로드로 최초 등록",
            documentInternalId,
            fileName: originalFileName,
            versionLabel: nextVersion
          }
        );

        await connection.execute(
          `
            INSERT INTO document_file_storage (
              document_file_version_id,
              storage_path,
              original_file_name,
              mime_type,
              byte_size,
              sha256_hash
            )
            VALUES (
              :documentFileVersionId,
              :storagePath,
              :originalFileName,
              :mimeType,
              :byteSize,
              :sha256Hash
            )
          `,
          {
            byteSize: savedFile.byteSize,
            documentFileVersionId: versionInsertResult.insertId,
            mimeType: savedFile.mimeType,
            originalFileName: savedFile.originalFileName,
            sha256Hash: savedFile.sha256Hash,
            storagePath: savedFile.storageRelativePath
          }
        );

        await connection.execute(
          `
            INSERT INTO document_history (
              document_file_id,
              document_file_version_id,
              event_type,
              before_value,
              after_value,
              actor_user_id
            )
            VALUES (
              :documentInternalId,
              :documentFileVersionId,
              :eventType,
              :beforeValue,
              :afterValue,
              :actorUserId
            )
          `,
          {
            actorUserId,
            afterValue: JSON.stringify({
              documentId: publicDocumentId,
              fileName: originalFileName,
              version: nextVersion,
              folderId,
              tags: tagNames,
              storagePath: savedFile.storageRelativePath
            }),
            beforeValue: existingDocument
              ? JSON.stringify({
                  documentId: publicDocumentId,
                  fileName: originalFileName,
                  version: existingDocument.current_version
                })
              : null,
            documentFileVersionId: versionInsertResult.insertId,
            documentInternalId,
            eventType: existingDocument
              ? "DOCUMENT_VERSION_CREATED"
              : "DOCUMENT_CREATED"
          }
        );

        await notifyActiveUsersExcept(connection, actorUserId, {
          eventType: existingDocument
            ? "DOCUMENT_VERSION_CREATED"
            : "DOCUMENT_CREATED",
          message: existingDocument
            ? `${originalFileName} ${nextVersion} 버전이 등록되었습니다.`
            : `${originalFileName} 문서가 등록되었습니다.`,
          sourceDocumentId: publicDocumentId,
          sourceType: "DOCUMENT",
          title: existingDocument ? "문서 새 버전" : "새 문서"
        });

        if (tagNames.length > 0 || !existingDocument) {
          await replaceDocumentTags(
            connection,
            documentInternalId,
            tagNames,
            actorUserId
          );
        }

        const documents = await listDocumentItems(connection);
        const uploadedDocument = documents.find(
          (document) => document.documentId === publicDocumentId
        );

        await connection.commit();

        res.status(existingDocument ? 200 : 201).json({
          document: uploadedDocument,
          documents
        });
      } catch (error) {
        await connection.rollback();
        throw error;
      } finally {
        connection.release();
      }
    } catch (error) {
      if (savedFile) {
        try {
          await fs.unlink(new URL(savedFile.storageRelativePath, documentStorageRoot));
        } catch {
          // Ignore cleanup errors; the API error is more useful to the caller.
        }
      }

      next(error);
    }
  }
);

app.get("/api/v1/document-files/:documentId/content", async (req, res, next) => {
  try {
    const user = await requireLogin(req, res);

    if (!user) {
      return;
    }

    const requestedVersion =
      typeof req.query.version === "string" && req.query.version.trim()
        ? req.query.version.trim()
        : null;
    const [rows] = await pool.execute(
      `
        SELECT
          d.file_name,
          d.current_version,
          v.version_label,
          s.storage_path,
          s.original_file_name,
          s.mime_type
        FROM document_file d
        JOIN document_file_version v ON v.document_file_id = d.id
        JOIN document_file_storage s ON s.document_file_version_id = v.id
        WHERE d.document_id = :documentId
          AND v.version_label = COALESCE(:requestedVersion, d.current_version)
        LIMIT 1
      `,
      {
        documentId: req.params.documentId,
        requestedVersion
      }
    );
    const storedFile = rows[0];

    if (!storedFile) {
      res.status(404).json({
        error: {
          code: "DOCUMENT_FILE_NOT_FOUND",
          message: "문서 파일을 찾을 수 없습니다."
        }
      });
      return;
    }

    if (storedFile.storage_path.includes("..")) {
      res.status(400).json({
        error: {
          code: "INVALID_STORAGE_PATH",
          message: "문서 파일 경로가 올바르지 않습니다."
        }
      });
      return;
    }

    const fileUrl = new URL(storedFile.storage_path, documentStorageRoot);
    const filePath = fileURLToPath(fileUrl);

    await fs.access(fileUrl);
    res.setHeader("Content-Type", storedFile.mime_type ?? "application/octet-stream");
    res.setHeader(
      "Content-Disposition",
      `inline; filename*=UTF-8''${encodeURIComponent(storedFile.original_file_name)}`
    );
    res.sendFile(filePath);
  } catch (error) {
    if (error?.code === "ENOENT") {
      res.status(404).json({
        error: {
          code: "DOCUMENT_FILE_NOT_FOUND",
          message: "문서 파일을 찾을 수 없습니다."
        }
      });
      return;
    }

    next(error);
  }
});

app.get("/api/v1/document-files/:documentId/spreadsheet", async (req, res, next) => {
  try {
    const user = await requireLogin(req, res);

    if (!user) {
      return;
    }

    const requestedVersion =
      typeof req.query.version === "string" && req.query.version.trim()
        ? req.query.version.trim()
        : null;
    const [rows] = await pool.execute(
      `
        SELECT
          d.file_name,
          d.file_type,
          v.version_label,
          s.storage_path
        FROM document_file d
        JOIN document_file_version v ON v.document_file_id = d.id
        JOIN document_file_storage s ON s.document_file_version_id = v.id
        WHERE d.document_id = :documentId
          AND v.version_label = COALESCE(:requestedVersion, d.current_version)
        LIMIT 1
      `,
      {
        documentId: req.params.documentId,
        requestedVersion
      }
    );
    const storedFile = rows[0];

    if (!storedFile || storedFile.file_type !== "EXCEL") {
      res.status(404).json({
        error: {
          code: "SPREADSHEET_NOT_FOUND",
          message: "Excel 문서를 찾을 수 없습니다."
        }
      });
      return;
    }

    if (storedFile.storage_path.includes("..")) {
      res.status(400).json({
        error: {
          code: "INVALID_STORAGE_PATH",
          message: "문서 파일 경로가 올바르지 않습니다."
        }
      });
      return;
    }

    const fileUrl = new URL(storedFile.storage_path, documentStorageRoot);
    const buffer = await fs.readFile(fileUrl);

    res.json({
      spreadsheet: {
        cells: parseXlsxCells(buffer),
        fileName: storedFile.file_name,
        version: storedFile.version_label
      }
    });
  } catch (error) {
    if (error?.code === "ENOENT") {
      res.status(404).json({
        error: {
          code: "DOCUMENT_FILE_NOT_FOUND",
          message: "문서 파일을 찾을 수 없습니다."
        }
      });
      return;
    }

    next(error);
  }
});

app.post("/api/v1/document-folders", async (req, res, next) => {
  try {
    const user = await requireLogin(req, res);

    if (!user) {
      return;
    }

    if (!canManageDocuments(user)) {
      res.status(403).json({
        error: {
          code: "PERMISSION_DENIED",
          message: "문서 폴더는 최고관리자, MES 사용자, POP 사용자만 만들 수 있습니다."
        }
      });
      return;
    }

    const { folderName, parentFolderId = "folder-field-documents" } = req.body ?? {};
    const normalizedFolderName = typeof folderName === "string" ? folderName.trim() : "";
    const normalizedParentFolderId =
      typeof parentFolderId === "string" && parentFolderId.trim()
        ? parentFolderId.trim()
        : "folder-field-documents";

    if (!normalizedFolderName) {
      res.status(400).json({
        error: {
          code: "VALIDATION_ERROR",
          message: "폴더명을 입력해 주세요."
        }
      });
      return;
    }

    if (normalizedFolderName.length > 80) {
      res.status(400).json({
        error: {
          code: "VALIDATION_ERROR",
          message: "폴더명은 80자 이하로 입력해 주세요."
        }
      });
      return;
    }

    const connection = await pool.getConnection();

    try {
      await connection.beginTransaction();

      const [parentRows] = await connection.execute(
        "SELECT id FROM document_folder WHERE folder_id = :parentFolderId LIMIT 1",
        { parentFolderId: normalizedParentFolderId }
      );
      const parentFolder = parentRows[0];

      if (!parentFolder) {
        await connection.rollback();
        res.status(404).json({
          error: {
            code: "PARENT_FOLDER_NOT_FOUND",
            message: "상위 폴더를 찾을 수 없습니다."
          }
        });
        return;
      }

      const [duplicateRows] = await connection.execute(
        `
          SELECT id
          FROM document_folder
          WHERE parent_folder_id = :parentFolderInternalId
            AND folder_name = :folderName
          LIMIT 1
        `,
        {
          parentFolderInternalId: parentFolder.id,
          folderName: normalizedFolderName
        }
      );

      if (duplicateRows[0]) {
        await connection.rollback();
        res.status(409).json({
          error: {
            code: "DUPLICATE_FOLDER_NAME",
            message: "이미 같은 이름의 폴더가 있습니다."
          }
        });
        return;
      }

      const [orderRows] = await connection.execute(
        `
          SELECT COALESCE(MAX(sort_order), 0) + 10 AS next_sort_order
          FROM document_folder
          WHERE parent_folder_id = :parentFolderInternalId
        `,
        { parentFolderInternalId: parentFolder.id }
      );
      const actorUserId = await findInternalUserId(user);
      const folderId = `folder_${crypto.randomUUID().replaceAll("-", "")}`;

      await connection.execute(
        `
          INSERT INTO document_folder (
            folder_id,
            parent_folder_id,
            folder_name,
            sort_order,
            created_by
          )
          VALUES (
            :folderId,
            :parentFolderInternalId,
            :folderName,
            :sortOrder,
            :actorUserId
          )
        `,
        {
          folderId,
          parentFolderInternalId: parentFolder.id,
          folderName: normalizedFolderName,
          sortOrder: Number(orderRows[0].next_sort_order),
          actorUserId
        }
      );

      const folders = await listDocumentFolders(connection);
      const createdFolder = folders.find((folder) => folder.folderId === folderId);

      await connection.commit();

      res.status(201).json({
        folder: createdFolder,
        folders,
        currentFolders: folders.filter(
          (folder) => folder.parentFolderId === normalizedParentFolderId
        )
      });
    } catch (error) {
      await connection.rollback();
      throw error;
    } finally {
      connection.release();
    }
  } catch (error) {
    next(error);
  }
});

app.patch("/api/v1/document-folders/:folderId", async (req, res, next) => {
  try {
    const user = await requireLogin(req, res);

    if (!user) {
      return;
    }

    if (!canManageDocuments(user)) {
      res.status(403).json({
        error: {
          code: "PERMISSION_DENIED",
          message: "문서 폴더는 최고관리자, MES 사용자, POP 사용자만 변경할 수 있습니다."
        }
      });
      return;
    }

    const folderId =
      typeof req.params.folderId === "string" ? req.params.folderId.trim() : "";
    const folderName =
      typeof req.body?.folderName === "string" ? req.body.folderName.trim() : "";

    if (!folderId) {
      res.status(400).json({
        error: {
          code: "VALIDATION_ERROR",
          message: "변경할 폴더를 선택해 주세요."
        }
      });
      return;
    }

    if (!folderName) {
      res.status(400).json({
        error: {
          code: "VALIDATION_ERROR",
          message: "폴더명을 입력해 주세요."
        }
      });
      return;
    }

    if (folderName.length > 80) {
      res.status(400).json({
        error: {
          code: "VALIDATION_ERROR",
          message: "폴더명은 80자 이하로 입력해 주세요."
        }
      });
      return;
    }

    const connection = await pool.getConnection();

    try {
      await connection.beginTransaction();

      const [folderRows] = await connection.execute(
        `
          SELECT id, parent_folder_id
          FROM document_folder
          WHERE folder_id = :folderId
          LIMIT 1
        `,
        { folderId }
      );
      const targetFolder = folderRows[0];

      if (!targetFolder) {
        await connection.rollback();
        res.status(404).json({
          error: {
            code: "FOLDER_NOT_FOUND",
            message: "폴더를 찾을 수 없습니다."
          }
        });
        return;
      }

      const [duplicateRows] = await connection.execute(
        `
          SELECT id
          FROM document_folder
          WHERE id <> :folderInternalId
            AND parent_folder_id <=> :parentFolderInternalId
            AND folder_name = :folderName
          LIMIT 1
        `,
        {
          folderInternalId: targetFolder.id,
          parentFolderInternalId: targetFolder.parent_folder_id ?? null,
          folderName
        }
      );

      if (duplicateRows[0]) {
        await connection.rollback();
        res.status(409).json({
          error: {
            code: "DUPLICATE_FOLDER_NAME",
            message: "이미 같은 이름의 폴더가 있습니다."
          }
        });
        return;
      }

      await connection.execute(
        `
          UPDATE document_folder
          SET folder_name = :folderName,
              updated_at = CURRENT_TIMESTAMP
          WHERE id = :folderInternalId
        `,
        {
          folderInternalId: targetFolder.id,
          folderName
        }
      );

      const folders = await listDocumentFolders(connection);
      const updatedFolder = folders.find((folder) => folder.folderId === folderId);

      await connection.commit();

      res.json({
        folder: updatedFolder,
        folders,
        currentFolders: folders.filter(
          (folder) =>
            folder.parentFolderId === (updatedFolder?.parentFolderId ?? null)
        )
      });
    } catch (error) {
      await connection.rollback();
      throw error;
    } finally {
      connection.release();
    }
  } catch (error) {
    next(error);
  }
});

app.delete("/api/v1/document-folders/:folderId", async (req, res, next) => {
  try {
    const user = await requireLogin(req, res);

    if (!user) {
      return;
    }

    if (!canManageDocuments(user)) {
      res.status(403).json({
        error: {
          code: "PERMISSION_DENIED",
          message: "문서 폴더는 최고관리자, MES 사용자, POP 사용자만 삭제할 수 있습니다."
        }
      });
      return;
    }

    const folderId =
      typeof req.params.folderId === "string" ? req.params.folderId.trim() : "";

    if (!folderId) {
      res.status(400).json({
        error: {
          code: "VALIDATION_ERROR",
          message: "삭제할 폴더를 선택해 주세요."
        }
      });
      return;
    }

    const connection = await pool.getConnection();

    try {
      await connection.beginTransaction();

      const [folderRows] = await connection.execute(
        `
          SELECT
            folder.id,
            folder.folder_id,
            folder.folder_name,
            parent.folder_id AS parent_folder_id
          FROM document_folder folder
          LEFT JOIN document_folder parent ON parent.id = folder.parent_folder_id
          WHERE folder.folder_id = :folderId
          LIMIT 1
        `,
        { folderId }
      );
      const targetFolder = folderRows[0];

      if (!targetFolder) {
        await connection.rollback();
        res.status(404).json({
          error: {
            code: "FOLDER_NOT_FOUND",
            message: "폴더를 찾을 수 없습니다."
          }
        });
        return;
      }

      if (isProtectedDocumentFolderRow(targetFolder)) {
        await connection.rollback();
        res.status(409).json({
          error: {
            code: "PROTECTED_FOLDER",
            message: "작업일지 폴더는 삭제할 수 없습니다."
          }
        });
        return;
      }

      const [protectedRows] = await connection.execute(
        `
          WITH RECURSIVE folder_tree AS (
            SELECT id, folder_id, folder_name
            FROM document_folder
            WHERE id = :folderInternalId
            UNION ALL
            SELECT child.id, child.folder_id, child.folder_name
            FROM document_folder child
            JOIN folder_tree parent ON child.parent_folder_id = parent.id
          )
          SELECT folder_id, folder_name
          FROM folder_tree
          WHERE folder_id = 'folder-my-pc-journal'
          LIMIT 1
        `,
        { folderInternalId: targetFolder.id }
      );

      if (protectedRows[0]) {
        await connection.rollback();
        res.status(409).json({
          error: {
            code: "PROTECTED_FOLDER",
            message: "작업일지 폴더는 삭제할 수 없습니다."
          }
        });
        return;
      }

      const [fileRows] = await connection.execute(
        `
          WITH RECURSIVE folder_tree AS (
            SELECT id
            FROM document_folder
            WHERE id = :folderInternalId
            UNION ALL
            SELECT child.id
            FROM document_folder child
            JOIN folder_tree parent ON child.parent_folder_id = parent.id
          )
          SELECT COUNT(*) AS file_count
          FROM document_file file
          JOIN folder_tree tree ON tree.id = file.folder_id
        `,
        { folderInternalId: targetFolder.id }
      );
      const fileCount = Number(fileRows[0]?.file_count ?? 0);

      if (fileCount > 0) {
        await connection.rollback();
        res.status(409).json({
          error: {
            code: "FOLDER_HAS_FILES",
            message:
              "이 폴더 또는 하위 폴더에 파일이 있어 삭제할 수 없습니다."
          }
        });
        return;
      }

      await connection.execute("DELETE FROM document_folder WHERE id = :folderInternalId", {
        folderInternalId: targetFolder.id
      });

      const folders = await listDocumentFolders(connection);

      await connection.commit();

      res.json({
        deletedFolderId: targetFolder.folder_id,
        parentFolderId: targetFolder.parent_folder_id ?? null,
        folders
      });
    } catch (error) {
      await connection.rollback();
      throw error;
    } finally {
      connection.release();
    }
  } catch (error) {
    next(error);
  }
});

app.get("/api/v1/system-history", async (req, res, next) => {
  try {
    const user = await requireSuperAdmin(req, res);

    if (!user) {
      return;
    }

    const [workRows] = await pool.execute(`
      SELECT
        h.id,
        h.event_type,
        h.before_value,
        h.after_value,
        h.created_at,
        actor.display_name AS actor_name,
        item.title AS current_title
      FROM work_sequence_history h
      JOIN work_sequence_item item ON item.id = h.sequence_item_id
      LEFT JOIN user_account actor ON actor.id = h.actor_user_id
      ORDER BY h.created_at DESC, h.id DESC
      LIMIT 100
    `);
    const [documentRows] = await pool.execute(`
      SELECT
        h.id,
        h.event_type,
        h.before_value,
        h.after_value,
        h.created_at,
        actor.display_name AS actor_name,
        document_file.file_name AS current_file_name,
        document_file.current_version
      FROM document_history h
      JOIN document_file ON document_file.id = h.document_file_id
      LEFT JOIN user_account actor ON actor.id = h.actor_user_id
      ORDER BY h.created_at DESC, h.id DESC
      LIMIT 100
    `);
    const history = workRows
      .map(toSystemHistoryItem)
      .concat(documentRows.map(toDocumentHistoryItem))
      .sort((left, right) => new Date(right.createdAt) - new Date(left.createdAt))
      .slice(0, 100);

    res.json({
      history
    });
  } catch (error) {
    next(error);
  }
});

app.get("/api/v1/work-sequence/items", async (req, res, next) => {
  try {
    const user = await currentUser(req);

    res.json({
      items: await listWorkSequenceItems(),
      canEdit: canEditWorkSequence(user)
    });
  } catch (error) {
    next(error);
  }
});

app.patch("/api/v1/work-sequence/items/order", async (req, res, next) => {
  try {
    const user = await requireLogin(req, res);

    if (!user) {
      return;
    }

    if (!canEditWorkSequence(user)) {
      res.status(403).json({
        error: {
          code: "PERMISSION_DENIED",
          message: "작업 순서는 최고관리자, MES 사용자, POP 사용자만 변경할 수 있습니다."
        }
      });
      return;
    }

    const { sequenceItemIds } = req.body ?? {};

    if (
      !Array.isArray(sequenceItemIds) ||
      sequenceItemIds.length === 0 ||
      sequenceItemIds.some((itemId) => typeof itemId !== "string" || !itemId.trim())
    ) {
      res.status(400).json({
        error: {
          code: "VALIDATION_ERROR",
          message: "변경할 작업 순서 목록이 필요합니다."
        }
      });
      return;
    }

    const connection = await pool.getConnection();

    try {
      await connection.beginTransaction();

      const boardId = await getDefaultWorkSequenceBoardId(connection);
      const actorUserId = await findInternalUserId(user);

      if (!boardId) {
        await connection.rollback();
        res.status(500).json({
          error: {
            code: "BOARD_NOT_FOUND",
            message: "기본 작업 순서 화면이 준비되지 않았습니다."
          }
        });
        return;
      }

      const [currentRows] = await connection.execute(
        `
          SELECT id, sequence_item_id, sequence_no, title
          FROM work_sequence_item
          WHERE board_id = :boardId
            AND status <> 'CANCELED'
          ORDER BY sequence_no ASC, id ASC
        `,
        { boardId }
      );
      const beforeIndexByPublicId = new Map(
        currentRows.map((row, index) => [row.sequence_item_id, index + 1])
      );
      const currentIds = new Set(currentRows.map((row) => row.sequence_item_id));
      const requestedIds = sequenceItemIds.map((itemId) => itemId.trim());
      const requestedIdSet = new Set(requestedIds);

      if (
        requestedIdSet.size !== requestedIds.length ||
        requestedIds.length !== currentRows.length ||
        requestedIds.some((itemId) => !currentIds.has(itemId))
      ) {
        await connection.rollback();
        res.status(400).json({
          error: {
            code: "VALIDATION_ERROR",
            message: "현재 표시 중인 작업 전체 순서가 필요합니다."
          }
        });
        return;
      }

      const currentByPublicId = new Map(
        currentRows.map((row) => [row.sequence_item_id, row])
      );

      for (const [index, sequenceItemId] of requestedIds.entries()) {
        const nextSequenceNo = (index + 1) * 10;
        const currentItem = currentByPublicId.get(sequenceItemId);

        await connection.execute(
          `
            UPDATE work_sequence_item
            SET sequence_no = :sequenceNo,
                updated_by = :actorUserId
            WHERE id = :id
          `,
          {
            id: currentItem.id,
            sequenceNo: nextSequenceNo,
            actorUserId
          }
        );

        if (Number(currentItem.sequence_no) !== nextSequenceNo) {
          const beforeIndex = beforeIndexByPublicId.get(sequenceItemId);
          const afterIndex = index + 1;

          await connection.execute(
            `
              INSERT INTO work_sequence_history (
                sequence_item_id,
                event_type,
                before_value,
                after_value,
                actor_user_id
              )
              VALUES (
                :itemId,
                'REORDERED',
                :beforeValue,
                :afterValue,
                :actorUserId
              )
            `,
            {
              itemId: currentItem.id,
              beforeValue: JSON.stringify({
                sequenceItemId,
                title: currentItem.title,
                sequenceNo: currentItem.sequence_no,
                position: beforeIndex
              }),
              afterValue: JSON.stringify({
                sequenceItemId,
                title: currentItem.title,
                sequenceNo: nextSequenceNo,
                position: afterIndex
              }),
              actorUserId
            }
          );
        }
      }

      const items = await listWorkSequenceItems(connection);

      await notifyActiveUsersExcept(connection, actorUserId, {
        eventType: "WORK_SEQUENCE_REORDERED",
        message: "작업 순서가 변경되었습니다.",
        sourceType: "SEQUENCE",
        title: "작업 순서 변경"
      });

      await connection.commit();

      res.json({ items });
    } catch (error) {
      await connection.rollback();
      throw error;
    } finally {
      connection.release();
    }
  } catch (error) {
    next(error);
  }
});

app.post("/api/v1/work-sequence/items", async (req, res, next) => {
  try {
    const user = await requireLogin(req, res);

    if (!user) {
      return;
    }

    if (!canEditWorkSequence(user)) {
      res.status(403).json({
        error: {
          code: "PERMISSION_DENIED",
          message: "작업 순서는 최고관리자, MES 사용자, POP 사용자만 입력할 수 있습니다."
        }
      });
      return;
    }

    const {
      title,
      productCode,
      assignedTeam,
      targetQuantity,
      linkedDocumentId,
      linkedDocumentName,
      memo,
      sequenceNo,
      status
    } = req.body ?? {};

    const normalizedTitle = typeof title === "string" ? title.trim() : "";

    if (!normalizedTitle) {
      res.status(400).json({
        error: {
          code: "VALIDATION_ERROR",
          message: "작업명을 입력해 주세요."
        }
      });
      return;
    }

    const normalizedTargetQuantityResult = normalizeNullableInteger(
      targetQuantity,
      "목표 수량",
      0
    );

    if (normalizedTargetQuantityResult.error) {
      res.status(400).json({
        error: {
          code: "VALIDATION_ERROR",
          message: normalizedTargetQuantityResult.error
        }
      });
      return;
    }

    const requestedSequenceNoResult = normalizeNullableInteger(
      sequenceNo,
      "표시 순서",
      1
    );

    if (requestedSequenceNoResult.error) {
      res.status(400).json({
        error: {
          code: "VALIDATION_ERROR",
          message: requestedSequenceNoResult.error
        }
      });
      return;
    }

    const normalizedStatus =
      typeof status === "string" && allowedWorkSequenceStatuses.includes(status)
        ? status
        : "WAITING";

    const connection = await pool.getConnection();

    try {
      await connection.beginTransaction();

      const boardId = await getDefaultWorkSequenceBoardId(connection);

      if (!boardId) {
        await connection.rollback();
        res.status(500).json({
          error: {
            code: "BOARD_NOT_FOUND",
            message: "기본 작업 순서 화면이 준비되지 않았습니다."
          }
        });
        return;
      }

      const [orderRows] = await connection.execute(
        `
          SELECT COALESCE(MAX(sequence_no), 0) + 10 AS next_sequence_no
          FROM work_sequence_item
          WHERE board_id = :boardId
        `,
        { boardId }
      );
      const actorUserId = await findInternalUserId(user);
      const nextSequenceNo =
        requestedSequenceNoResult.value ?? Number(orderRows[0].next_sequence_no);
      const sequenceItemId = `seq_${crypto.randomUUID().replaceAll("-", "")}`;
      const linkedDocument = await resolveLinkedDocument(
        connection,
        linkedDocumentId,
        linkedDocumentName
      );

      if (linkedDocument.error) {
        await connection.rollback();
        res.status(400).json({
          error: {
            code: "VALIDATION_ERROR",
            message: linkedDocument.error
          }
        });
        return;
      }

      await connection.execute(
        `
          INSERT INTO work_sequence_item (
            sequence_item_id,
            board_id,
            sequence_no,
            title,
            product_code,
            assigned_team,
            target_quantity,
            linked_document_name,
            linked_document_file_id,
            status,
            memo,
            created_by,
            updated_by
          )
          VALUES (
            :sequenceItemId,
            :boardId,
            :sequenceNo,
            :title,
            :productCode,
            :assignedTeam,
            :targetQuantity,
            :linkedDocumentName,
            :linkedDocumentFileId,
            :status,
            :memo,
            :actorUserId,
            :actorUserId
          )
        `,
        {
          sequenceItemId,
          boardId,
          sequenceNo: nextSequenceNo,
          title: normalizedTitle,
          productCode: normalizeOptionalText(productCode),
          assignedTeam: normalizeOptionalText(assignedTeam),
          targetQuantity: normalizedTargetQuantityResult.value,
          linkedDocumentName: linkedDocument.documentName,
          linkedDocumentFileId: linkedDocument.documentInternalId,
          status: normalizedStatus,
          memo: normalizeOptionalText(memo),
          actorUserId
        }
      );

      const [createdRows] = await connection.execute(
        `
          SELECT
            i.id,
            i.sequence_item_id,
            i.sequence_no,
            i.title,
            i.product_code,
            i.assigned_team,
            i.target_quantity,
            linked_doc.document_id AS linked_document_id,
            linked_doc.file_name AS linked_document_file_name,
            i.linked_document_name,
            i.status,
            i.memo,
            creator.display_name AS created_by_name,
            i.updated_at
          FROM work_sequence_item i
          LEFT JOIN document_file linked_doc ON linked_doc.id = i.linked_document_file_id
          LEFT JOIN user_account creator ON creator.id = i.created_by
          WHERE i.sequence_item_id = :sequenceItemId
          LIMIT 1
        `,
        { sequenceItemId }
      );

      const createdItem = toWorkSequenceItem(createdRows[0]);

      await connection.execute(
        `
          INSERT INTO work_sequence_history (
            sequence_item_id,
            event_type,
            after_value,
            actor_user_id
          )
          VALUES (
            :itemId,
            'CREATED',
            :afterValue,
            :actorUserId
          )
        `,
        {
          itemId: createdRows[0].id,
          afterValue: JSON.stringify(createdItem),
          actorUserId
        }
      );

      await notifyActiveUsersExcept(connection, actorUserId, {
        eventType: "WORK_SEQUENCE_CREATED",
        message: `${createdItem.title} 작업이 입력되었습니다.`,
        sourceSequenceItemId: createdItem.sequenceItemId,
        sourceType: "SEQUENCE",
        title: "새 작업 순서"
      });

      await connection.commit();

      res.status(201).json({
        item: createdItem
      });
    } catch (error) {
      await connection.rollback();
      throw error;
    } finally {
      connection.release();
    }
  } catch (error) {
    next(error);
  }
});

app.patch("/api/v1/work-sequence/items/:sequenceItemId", async (req, res, next) => {
  try {
    const user = await requireLogin(req, res);

    if (!user) {
      return;
    }

    if (!canEditWorkSequence(user)) {
      res.status(403).json({
        error: {
          code: "PERMISSION_DENIED",
          message: "작업 순서는 최고관리자, MES 사용자, POP 사용자만 수정할 수 있습니다."
        }
      });
      return;
    }

    const {
      title,
      productCode,
      assignedTeam,
      targetQuantity,
      linkedDocumentId,
      linkedDocumentName,
      memo,
      sequenceNo,
      status
    } = req.body ?? {};
    const normalizedTitle = typeof title === "string" ? title.trim() : "";

    if (!normalizedTitle) {
      res.status(400).json({
        error: {
          code: "VALIDATION_ERROR",
          message: "작업명을 입력해 주세요."
        }
      });
      return;
    }

    if (!allowedWorkSequenceStatuses.includes(status)) {
      res.status(400).json({
        error: {
          code: "VALIDATION_ERROR",
          message: "지원하지 않는 작업 상태입니다."
        }
      });
      return;
    }

    const normalizedTargetQuantityResult = normalizeNullableInteger(
      targetQuantity,
      "목표 수량",
      0
    );

    if (normalizedTargetQuantityResult.error) {
      res.status(400).json({
        error: {
          code: "VALIDATION_ERROR",
          message: normalizedTargetQuantityResult.error
        }
      });
      return;
    }

    const requestedSequenceNoResult = normalizeNullableInteger(
      sequenceNo,
      "표시 순서",
      1
    );

    if (requestedSequenceNoResult.error || requestedSequenceNoResult.value === null) {
      res.status(400).json({
        error: {
          code: "VALIDATION_ERROR",
          message: requestedSequenceNoResult.error ?? "표시 순서를 입력해 주세요."
        }
      });
      return;
    }

    const connection = await pool.getConnection();

    try {
      await connection.beginTransaction();

      const existingRow = await findWorkSequenceItem(
        connection,
        req.params.sequenceItemId
      );

      if (!existingRow) {
        await connection.rollback();
        res.status(404).json({
          error: {
            code: "WORK_SEQUENCE_ITEM_NOT_FOUND",
            message: "작업 순서를 찾을 수 없습니다."
          }
        });
        return;
      }

      const actorUserId = await findInternalUserId(user);
      const beforeItem = toWorkSequenceItem(existingRow);
      const linkedDocument = await resolveLinkedDocument(
        connection,
        linkedDocumentId,
        linkedDocumentName
      );

      if (linkedDocument.error) {
        await connection.rollback();
        res.status(400).json({
          error: {
            code: "VALIDATION_ERROR",
            message: linkedDocument.error
          }
        });
        return;
      }

      await connection.execute(
        `
          UPDATE work_sequence_item
          SET sequence_no = :sequenceNo,
              title = :title,
              product_code = :productCode,
              assigned_team = :assignedTeam,
              target_quantity = :targetQuantity,
              linked_document_name = :linkedDocumentName,
              linked_document_file_id = :linkedDocumentFileId,
              status = :status,
              memo = :memo,
              updated_by = :actorUserId
          WHERE id = :id
        `,
        {
          id: existingRow.id,
          sequenceNo: requestedSequenceNoResult.value,
          title: normalizedTitle,
          productCode: normalizeOptionalText(productCode),
          assignedTeam: normalizeOptionalText(assignedTeam),
          targetQuantity: normalizedTargetQuantityResult.value,
          linkedDocumentName: linkedDocument.documentName,
          linkedDocumentFileId: linkedDocument.documentInternalId,
          status,
          memo: normalizeOptionalText(memo),
          actorUserId
        }
      );

      const updatedRow = await findWorkSequenceItem(
        connection,
        req.params.sequenceItemId
      );
      const updatedItem = toWorkSequenceItem(updatedRow);

      await connection.execute(
        `
          INSERT INTO work_sequence_history (
            sequence_item_id,
            event_type,
            before_value,
            after_value,
            actor_user_id
          )
          VALUES (
            :itemId,
            'UPDATED',
            :beforeValue,
            :afterValue,
            :actorUserId
          )
        `,
        {
          itemId: existingRow.id,
          beforeValue: JSON.stringify(beforeItem),
          afterValue: JSON.stringify(updatedItem),
          actorUserId
        }
      );

      await notifyActiveUsersExcept(connection, actorUserId, {
        eventType: "WORK_SEQUENCE_UPDATED",
        message: `${updatedItem.title} 작업이 수정되었습니다.`,
        sourceSequenceItemId: updatedItem.sequenceItemId,
        sourceType: "SEQUENCE",
        title: "작업 순서 수정"
      });

      await connection.commit();

      res.json({ item: updatedItem });
    } catch (error) {
      await connection.rollback();
      throw error;
    } finally {
      connection.release();
    }
  } catch (error) {
    next(error);
  }
});

app.use((error, _req, res, _next) => {
  if (error instanceof multer.MulterError) {
    const message =
      error.code === "LIMIT_FILE_SIZE"
        ? "파일은 100MB 이하로 업로드해 주세요."
        : "파일 업로드 요청을 처리할 수 없습니다.";

    res.status(error.code === "LIMIT_FILE_SIZE" ? 413 : 400).json({
      error: {
        code: error.code,
        message
      }
    });
    return;
  }

  console.error(error);
  res.status(500).json({
    error: {
      code: "INTERNAL_SERVER_ERROR",
      message: "서버 오류가 발생했습니다."
    }
  });
});

app.listen(port, "127.0.0.1", () => {
  console.log(`FlowNote API listening on http://127.0.0.1:${port}`);
});
