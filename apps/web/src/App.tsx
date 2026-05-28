import {
  ChangeEvent,
  DragEvent,
  FormEvent,
  Fragment,
  MouseEvent as ReactMouseEvent,
  PointerEvent as ReactPointerEvent,
  useEffect,
  useMemo,
  useRef,
  useState
} from "react";
import * as pdfjsLib from "pdfjs-dist";
import pdfWorkerUrl from "pdfjs-dist/build/pdf.worker.mjs?url";

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfWorkerUrl;

const documents: DocumentItem[] = [
  {
    documentId: "doc-cooling-drawing",
    folderId: "folder-cooling-system",
    type: "PDF",
    name: "1호기_도면.pdf",
    meta: "냉각시스템 / 현장 공개",
    category: "1호기 설비 / 냉각시스템",
    version: "v3",
    owner: "김최고 관리자",
    publishedAt: "2026-05-22 14:10",
    securityLevel: "현장 공개",
    pageCount: 12,
    summary: "냉각 배관, 밸브 위치, 점검 기준을 포함한 현장 열람용 도면입니다.",
    tags: ["도면", "냉각", "배관", "설비", "현장공개"],
    versions: [
      {
        version: "v3",
        publishedAt: "2026-05-22 14:10",
        owner: "김최고 관리자",
        changeNote: "현장 점검 기준과 밸브 위치 변경 사항 반영",
        fileName: "1호기_도면_v3.pdf",
        status: "CURRENT"
      },
      {
        version: "v2",
        publishedAt: "2026-05-12 10:20",
        owner: "박MES 사용자",
        changeNote: "냉각 배관 라인 표기 보완",
        fileName: "1호기_도면_v2.pdf",
        status: "ARCHIVED"
      },
      {
        version: "v1",
        publishedAt: "2026-05-01 09:00",
        owner: "김최고 관리자",
        changeNote: "최초 등록",
        fileName: "1호기_도면_v1.pdf",
        status: "ARCHIVED"
      }
    ],
    history: ["김최고 관리자가 v3을 공개", "홍POP 반장이 열람", "생산 1조가 작업 전 확인"]
  },
  {
    documentId: "doc-pipe-manual",
    folderId: "folder-pipe",
    type: "PDF",
    name: "배관매뉴얼.pdf",
    meta: "1호기 설비 / v3",
    category: "1호기 설비 / 배관",
    version: "v3",
    owner: "박MES 사용자",
    publishedAt: "2026-05-20 09:30",
    securityLevel: "사내 열람",
    pageCount: 28,
    summary: "배관 유지보수 절차와 주요 부품 교체 기준을 정리한 매뉴얼입니다.",
    tags: ["배관", "작업표준", "설비"],
    versions: [
      {
        version: "v3",
        publishedAt: "2026-05-20 09:30",
        owner: "박MES 사용자",
        changeNote: "부품 교체 주기와 작업 전 안전 확인 항목 추가",
        fileName: "배관매뉴얼_v3.pdf",
        status: "CURRENT"
      },
      {
        version: "v2",
        publishedAt: "2026-05-08 15:15",
        owner: "김최고 관리자",
        changeNote: "유지보수 절차 문구 수정",
        fileName: "배관매뉴얼_v2.pdf",
        status: "ARCHIVED"
      }
    ],
    history: ["박MES 사용자가 v3 등록", "김최고 관리자가 승인", "홍POP 반장이 열람"]
  },
  {
    documentId: "doc-checklist",
    folderId: "folder-checklist",
    type: "EXCEL",
    name: "체크리스트.xlsx",
    meta: "점검 양식 / 뷰어 전용",
    category: "점검 양식",
    version: "v1",
    owner: "김최고 관리자",
    publishedAt: "2026-05-18 16:40",
    securityLevel: "뷰어 전용",
    pageCount: 3,
    summary: "일일 설비 점검 항목과 확인 결과 입력 기준을 담은 문서입니다.",
    tags: ["점검", "양식"],
    versions: [
      {
        version: "v1",
        publishedAt: "2026-05-18 16:40",
        owner: "김최고 관리자",
        changeNote: "최초 등록",
        fileName: "체크리스트_v1.xlsx",
        status: "CURRENT"
      }
    ],
    history: ["김최고 관리자가 양식 등록", "이일반 사용자가 열람"]
  }
];

type Role = "super-admin" | "mes-user" | "pop-user" | "general-user";

type SessionUser = {
  userId: string;
  loginId: string;
  displayName: string;
  roles: Role[];
  primaryRole: Role;
};

type ManagedUser = {
  userId: string;
  loginId: string;
  displayName: string;
  status: "ACTIVE" | "LOCKED" | "DISABLED";
  roleId: Role;
  roleName: string;
};

type DocumentItem = {
  documentId: string;
  folderId: string;
  type: "PDF" | "EXCEL" | "PPT" | "IMAGE" | "JOURNAL";
  name: string;
  meta: string;
  category: string;
  version: string;
  owner: string;
  publishedAt: string;
  securityLevel: string;
  pageCount: number;
  summary: string;
  contentUrl?: string | null;
  canEdit?: boolean;
  editorFormat?: string | null;
  tags: string[];
  journal?: JournalDocument | null;
  versions: DocumentVersion[];
  history: string[];
};

type JournalReply = {
  replyId: string;
  text: string;
  type: "COMMENT" | "ACTION" | "QUESTION";
  createdBy: string;
  createdAt: string;
  version: string | null;
};

type JournalDocument = {
  journalId: string;
  memo: string | null;
  isHandover: boolean;
  handoverTo: string | null;
  createdBy: string;
  createdAt: string;
  replies: JournalReply[];
};

type DocumentVersion = {
  version: string;
  publishedAt: string;
  owner: string;
  changeNote: string;
  fileName: string;
  status: "CURRENT" | "ARCHIVED";
};

type DocumentFolder = {
  folderId: string;
  parentFolderId: string | null;
  name: string;
  sortOrder: number;
  createdBy: string | null;
  createdAt: string;
  updatedAt: string;
};

type DocumentEditorDraft = {
  documentId: string;
  documentType: "PDF" | "EXCEL";
  editorFormat: string;
  fileName: string;
  body: string;
  spreadsheetCells: Array<{
    column: number;
    row: number;
    value: string;
  }>;
  summary: string;
  tags: string;
};

type PdfEditorBlock =
  | {
      id: string;
      text: string;
      type: "text";
    }
  | {
      alt: string;
      dataUrl: string;
      id: string;
      type: "image";
      widthPercent: number;
    };

type DocumentFolderTreeItem = DocumentFolder & {
  depth: number;
};

type WorkSequenceItem = {
  sequenceItemId: string;
  sequenceNo: number;
  title: string;
  productCode: string | null;
  assignedTeam: string | null;
  targetQuantity: number | null;
  linkedDocumentId: string | null;
  linkedDocumentName: string | null;
  status: "WAITING" | "IN_PROGRESS" | "HOLD" | "DONE" | "CANCELED";
  memo: string | null;
  detail: string | null;
  createdBy: string | null;
  updatedAt: string;
};

type FieldJournalEntry = {
  journalId: string;
  documentId: string;
  memo: string | null;
  photoFileName: string | null;
  photoUrl: string | null;
  isHandover: boolean;
  handoverTo: string | null;
  handoverStatus: "NONE" | "PENDING" | "CONFIRMED";
  readBy: {
    readId: number | string;
    userId: string | null;
    displayName: string;
    readAt: string;
  }[];
  replies: JournalReply[];
  createdBy: string;
  createdAt: string;
};

type WorkSequenceForm = {
  title: string;
  productCode: string;
  assignedTeam: string;
  targetQuantity: string;
  linkedDocumentId: string;
  linkedDocumentName: string;
  linkedDocumentSearch: string;
  memo: string;
  sequenceNo: string;
  status: WorkSequenceItem["status"];
};

type SystemHistoryItem = {
  historyId: number | string;
  eventType: "CREATED" | "UPDATED" | "REORDERED" | string;
  actorName: string;
  targetName: string;
  message: string;
  createdAt: string;
};

type NotificationItem = {
  notificationId: string;
  eventType: string;
  sourceType: "DOCUMENT" | "JOURNAL" | "SEQUENCE" | "SYSTEM";
  sourceDocumentId: string | null;
  sourceJournalId: string | null;
  sourceSequenceItemId: string | null;
  title: string;
  message: string;
  actorName: string | null;
  readAt: string | null;
  createdAt: string;
};

type AppPage =
  | "dashboard"
  | "documents"
  | "document"
  | "journal"
  | "sequence"
  | "notifications"
  | "members"
  | "history";

function getAppPageFromHash(hash = window.location.hash): AppPage {
  const normalizedHash = hash.replace(/^#\/?/, "").toLocaleLowerCase("ko-KR");

  if (
    normalizedHash === "documents" ||
    normalizedHash === "journal" ||
    normalizedHash === "sequence" ||
    normalizedHash === "notifications" ||
    normalizedHash === "members" ||
    normalizedHash === "history"
  ) {
    return normalizedHash;
  }

  if (normalizedHash === "document") {
    return "documents";
  }

  return "dashboard";
}

function getHashForAppPage(page: AppPage) {
  return page === "document" ? "#documents" : `#${page}`;
}

function getDocumentVersionContentUrl(documentId: string, version: string) {
  return `/api/v1/document-files/${encodeURIComponent(
    documentId
  )}/content?version=${encodeURIComponent(version)}`;
}

const roleLabels: Record<Role, string> = {
  "super-admin": "최고관리자",
  "mes-user": "MES 사용자",
  "pop-user": "POP 사용자",
  "general-user": "일반 사용자"
};

const availableRoles = Object.entries(roleLabels).map(([roleId, label]) => ({
  roleId: roleId as Role,
  label
}));

const sequenceStatusLabels: Record<WorkSequenceItem["status"], string> = {
  WAITING: "대기",
  IN_PROGRESS: "진행",
  HOLD: "보류",
  DONE: "완료",
  CANCELED: "취소"
};

const handoverStatusLabels: Record<FieldJournalEntry["handoverStatus"], string> = {
  NONE: "일반",
  PENDING: "확인 이력",
  CONFIRMED: "확인 이력"
};

const journalReplyTypeLabels: Record<JournalReply["type"], string> = {
  COMMENT: "댓글",
  ACTION: "조치",
  QUESTION: "질문"
};

const notificationSourceLabels: Record<NotificationItem["sourceType"], string> = {
  DOCUMENT: "문서",
  JOURNAL: "작업일지",
  SEQUENCE: "작업순서",
  SYSTEM: "시스템"
};

const sequenceStatusOrder: WorkSequenceItem["status"][] = [
  "IN_PROGRESS",
  "WAITING",
  "HOLD",
  "DONE",
  "CANCELED"
];

const editableSequenceRoles: Role[] = ["super-admin", "mes-user", "pop-user"];

const historyEventLabels: Record<string, string> = {
  CREATED: "입력",
  UPDATED: "수정",
  REORDERED: "순서 변경",
  DOCUMENT_CREATED: "문서 업로드",
  DOCUMENT_VERSION_CREATED: "버전 등록",
  DOCUMENT_TAG_UPDATED: "태그 수정",
  FIELD_JOURNAL_CREATED: "작업일지",
  FIELD_HANDOVER_READ: "인수인계 확인",
  FIELD_JOURNAL_REPLY_CREATED: "작업일지 응답"
};

const emptySequenceForm: WorkSequenceForm = {
  title: "",
  productCode: "",
  assignedTeam: "",
  targetQuantity: "",
  linkedDocumentId: "",
  linkedDocumentName: "",
  linkedDocumentSearch: "",
  memo: "",
  sequenceNo: "",
  status: "WAITING"
};

function toSequenceForm(item: WorkSequenceItem): WorkSequenceForm {
  return {
    title: item.title,
    productCode: item.productCode ?? "",
    assignedTeam: item.assignedTeam ?? "",
    targetQuantity: item.targetQuantity?.toString() ?? "",
    linkedDocumentId: item.linkedDocumentId ?? "",
    linkedDocumentName: item.linkedDocumentName ?? "",
    linkedDocumentSearch: item.linkedDocumentName ?? "",
    memo: item.memo ?? "",
    sequenceNo: item.sequenceNo.toString(),
    status: item.status
  };
}

function orderSequenceItems(items: WorkSequenceItem[]) {
  return [...items].sort((left, right) => left.sequenceNo - right.sequenceNo);
}

function resequenceItems(items: WorkSequenceItem[]) {
  return items.map((item, index) => ({
    ...item,
    sequenceNo: (index + 1) * 10
  }));
}

function moveSequenceItem(
  items: WorkSequenceItem[],
  draggedItemId: string,
  targetItemId: string,
  insertAfterTarget: boolean
) {
  if (draggedItemId === targetItemId) {
    return items;
  }

  const draggedItem = items.find((item) => item.sequenceItemId === draggedItemId);

  if (!draggedItem) {
    return items;
  }

  const withoutDraggedItem = items.filter(
    (item) => item.sequenceItemId !== draggedItemId
  );
  const targetIndex = withoutDraggedItem.findIndex(
    (item) => item.sequenceItemId === targetItemId
  );

  if (targetIndex === -1) {
    return items;
  }

  const nextItems = [...withoutDraggedItem];
  nextItems.splice(targetIndex + (insertAfterTarget ? 1 : 0), 0, draggedItem);

  return resequenceItems(nextItems);
}

function getDocumentSelectLabel(document: DocumentItem) {
  const details = [document.category, document.version, document.type].filter(Boolean);
  return details.length > 0
    ? `${document.name} - ${details.join(" / ")}`
    : document.name;
}

function getDocumentSizeLabel(document: DocumentItem) {
  if (document.pageCount > 0) {
    return `${document.pageCount}쪽`;
  }

  if (document.type === "IMAGE") {
    return "사진";
  }

  if (document.type === "JOURNAL") {
    return "메모";
  }

  return "실제 파일";
}

function wrapCanvasText(
  context: CanvasRenderingContext2D,
  text: string,
  maxWidth: number
) {
  const lines: string[] = [];

  for (const paragraph of text.split("\n")) {
    let currentLine = "";

    for (const character of paragraph) {
      const nextLine = `${currentLine}${character}`;

      if (context.measureText(nextLine).width > maxWidth && currentLine) {
        lines.push(currentLine);
        currentLine = character;
      } else {
        currentLine = nextLine;
      }
    }

    lines.push(currentLine);
  }

  return lines;
}

function createPdfEditorBlockId() {
  return `block_${crypto.randomUUID().replaceAll("-", "")}`;
}

function createTextPdfEditorBlock(text = ""): PdfEditorBlock {
  return {
    id: createPdfEditorBlockId(),
    text,
    type: "text"
  };
}

function parsePdfEditorBlocks(body: string): PdfEditorBlock[] {
  if (!body.trim()) {
    return [createTextPdfEditorBlock()];
  }

  try {
    const parsedBody = JSON.parse(body) as {
      blocks?: Array<Partial<PdfEditorBlock>>;
      version?: number;
    };

    if (parsedBody.version === 1 && Array.isArray(parsedBody.blocks)) {
      const blocks = parsedBody.blocks.flatMap((block): PdfEditorBlock[] => {
        if (block.type === "image" && typeof block.dataUrl === "string") {
          return [
            {
              alt: typeof block.alt === "string" ? block.alt : "삽입 이미지",
              dataUrl: block.dataUrl,
              id:
                typeof block.id === "string" && block.id
                  ? block.id
                  : createPdfEditorBlockId(),
              type: "image",
              widthPercent:
                typeof block.widthPercent === "number"
                  ? Math.min(100, Math.max(35, block.widthPercent))
                  : 100
            }
          ];
        }

        if (block.type === "text") {
          return [
            {
              id:
                typeof block.id === "string" && block.id
                  ? block.id
                  : createPdfEditorBlockId(),
              text: typeof block.text === "string" ? block.text : "",
              type: "text"
            }
          ];
        }

        return [];
      });

      return blocks.length > 0 ? blocks : [createTextPdfEditorBlock()];
    }
  } catch {
    // Older PDF documents store plain text directly in the draft body.
  }

  return [createTextPdfEditorBlock(body)];
}

function serializePdfEditorBlocks(blocks: PdfEditorBlock[]) {
  return JSON.stringify({
    blocks,
    version: 1
  });
}

function getPdfEditorPlainText(body: string) {
  return parsePdfEditorBlocks(body)
    .filter((block): block is Extract<PdfEditorBlock, { type: "text" }> =>
      block.type === "text"
    )
    .map((block) => block.text)
    .join("\n")
    .trim();
}

function loadImageElement(dataUrl: string) {
  return new Promise<HTMLImageElement>((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("Image load failed"));
    image.src = dataUrl;
  });
}

async function resizeImageFileToDataUrl(file: File) {
  const sourceDataUrl = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.onerror = () => reject(new Error("Image read failed"));
    reader.readAsDataURL(file);
  });
  const image = await loadImageElement(sourceDataUrl);
  const maxSide = 1400;
  const scale = Math.min(1, maxSide / Math.max(image.naturalWidth, image.naturalHeight));
  const canvas = document.createElement("canvas");
  const width = Math.max(1, Math.round(image.naturalWidth * scale));
  const height = Math.max(1, Math.round(image.naturalHeight * scale));
  const context = canvas.getContext("2d");

  if (!context) {
    return sourceDataUrl;
  }

  canvas.width = width;
  canvas.height = height;
  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, width, height);
  context.drawImage(image, 0, 0, width, height);

  return canvas.toDataURL("image/jpeg", 0.86);
}

async function createA4DocumentPageImage(fileName: string, body: string) {
  const canvas = document.createElement("canvas");
  const width = 1240;
  const height = 1754;
  const marginX = 120;
  const contentWidth = width - marginX * 2;
  const context = canvas.getContext("2d");

  if (!context) {
    return "";
  }

  canvas.width = width;
  canvas.height = height;
  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, width, height);
  context.fillStyle = "#101828";
  context.font =
    "700 38px system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
  context.fillText(fileName.replace(/\.pdf$/i, ""), marginX, 150);
  context.strokeStyle = "#e4e7ec";
  context.lineWidth = 2;
  context.beginPath();
  context.moveTo(marginX, 190);
  context.lineTo(width - marginX, 190);
  context.stroke();
  context.font =
    "400 28px system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";

  let y = 260;

  for (const block of parsePdfEditorBlocks(body)) {
    if (block.type === "text") {
      const lines = wrapCanvasText(context, block.text, contentWidth);

      for (const line of lines) {
        if (y > height - 130) {
          context.fillStyle = "#667085";
          context.fillText("...", marginX, y);
          return canvas.toDataURL("image/jpeg", 0.92);
        }

        context.fillStyle = "#101828";
        context.fillText(line, marginX, y);
        y += 44;
      }

      y += 18;
      continue;
    }

    try {
      const image = await loadImageElement(block.dataUrl);
      const imageWidth = Math.round(contentWidth * (block.widthPercent / 100));
      const imageHeight = Math.round(
        imageWidth * (image.naturalHeight / image.naturalWidth)
      );

      if (y + imageHeight > height - 130) {
        context.fillStyle = "#667085";
        context.fillText("...", marginX, y);
        return canvas.toDataURL("image/jpeg", 0.92);
      }

      context.drawImage(image, marginX, y, imageWidth, imageHeight);
      y += imageHeight + 34;
    } catch {
      context.fillStyle = "#b42318";
      context.fillText("이미지를 렌더링하지 못했습니다.", marginX, y);
      y += 44;
    }
  }

  return canvas.toDataURL("image/jpeg", 0.92);
}

const spreadsheetColumnLabels = Array.from({ length: 16 }, (_, index) =>
  String.fromCharCode(65 + index)
);
const spreadsheetRowCount = 32;

function createEmptySpreadsheetCells() {
  return Array.from({ length: spreadsheetRowCount }, () =>
    Array.from({ length: spreadsheetColumnLabels.length }, () => "")
  );
}

function serializeSpreadsheetCells(cells: string[][]) {
  return cells.flatMap((row, rowIndex) =>
    row
      .map((value, columnIndex) => ({
        column: columnIndex + 1,
        row: rowIndex + 1,
        value: value.trim()
      }))
      .filter((cell) => cell.value)
  );
}

function hydrateSpreadsheetCells(
  cells: DocumentEditorDraft["spreadsheetCells"]
) {
  const nextCells = createEmptySpreadsheetCells();

  for (const cell of cells) {
    const rowIndex = cell.row - 1;
    const columnIndex = cell.column - 1;

    if (
      rowIndex >= 0 &&
      rowIndex < nextCells.length &&
      columnIndex >= 0 &&
      columnIndex < nextCells[rowIndex].length
    ) {
      nextCells[rowIndex][columnIndex] = cell.value;
    }
  }

  return nextCells;
}

type SpreadsheetEditorProps = {
  disabled: boolean;
  initialCells: string[][];
  onCellsChange: (cells: string[][]) => void;
};

type PdfDocumentEditorProps = {
  body: string;
  disabled: boolean;
  onBodyChange: (body: string) => void;
};

type SpreadsheetRibbonTab = "home" | "formula" | "data";

function PdfDocumentEditor({
  body,
  disabled,
  onBodyChange
}: PdfDocumentEditorProps) {
  const imageInputRef = useRef<HTMLInputElement | null>(null);
  const blocks = useMemo(() => parsePdfEditorBlocks(body), [body]);
  const [imageMessage, setImageMessage] = useState("");

  function updateBlocks(nextBlocks: PdfEditorBlock[]) {
    onBodyChange(serializePdfEditorBlocks(nextBlocks));
  }

  function updateTextBlock(blockId: string, text: string) {
    updateBlocks(
      blocks.map((block) =>
        block.id === blockId && block.type === "text" ? { ...block, text } : block
      )
    );
  }

  function updateImageWidth(blockId: string, widthPercent: number) {
    updateBlocks(
      blocks.map((block) =>
        block.id === blockId && block.type === "image"
          ? { ...block, widthPercent }
          : block
      )
    );
  }

  function removeBlock(blockId: string) {
    const nextBlocks = blocks.filter((block) => block.id !== blockId);
    updateBlocks(nextBlocks.length > 0 ? nextBlocks : [createTextPdfEditorBlock()]);
  }

  function addTextBlock() {
    updateBlocks([...blocks, createTextPdfEditorBlock()]);
  }

  async function handleImageInputChange(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    event.target.value = "";

    if (files.length === 0) {
      return;
    }

    setImageMessage("이미지를 문서에 삽입하는 중입니다.");

    try {
      const imageBlocks = await Promise.all(
        files
          .filter((file) => file.type.startsWith("image/"))
          .map(async (file): Promise<PdfEditorBlock> => ({
            alt: file.name,
            dataUrl: await resizeImageFileToDataUrl(file),
            id: createPdfEditorBlockId(),
            type: "image",
            widthPercent: 100
          }))
      );

      if (imageBlocks.length === 0) {
        setImageMessage("삽입할 수 있는 이미지 파일을 선택해 주세요.");
        return;
      }

      updateBlocks([...blocks, ...imageBlocks]);
      setImageMessage("");
    } catch {
      setImageMessage("이미지를 삽입하지 못했습니다.");
    }
  }

  return (
    <div className="pdf-document-editor">
      <div className="pdf-editor-toolbar">
        <button
          disabled={disabled}
          onClick={() => imageInputRef.current?.click()}
          type="button"
        >
          이미지 삽입
        </button>
        <button disabled={disabled} onClick={addTextBlock} type="button">
          텍스트 추가
        </button>
        <input
          accept="image/*"
          disabled={disabled}
          hidden
          multiple
          onChange={(event) => void handleImageInputChange(event)}
          ref={imageInputRef}
          type="file"
        />
      </div>
      {imageMessage ? <p className="pdf-editor-message">{imageMessage}</p> : null}
      <div className="document-page-editor" aria-label="A4 PDF 문서 편집기">
        {blocks.map((block) =>
          block.type === "text" ? (
            <section className="pdf-editor-block" key={block.id}>
              <textarea
                aria-label="문서 텍스트"
                disabled={disabled}
                onChange={(event) => updateTextBlock(block.id, event.target.value)}
                placeholder="A4 문서에 들어갈 내용을 입력하세요."
                value={block.text}
              />
              {blocks.length > 1 ? (
                <button
                  aria-label="텍스트 블록 삭제"
                  disabled={disabled}
                  onClick={() => removeBlock(block.id)}
                  type="button"
                >
                  삭제
                </button>
              ) : null}
            </section>
          ) : (
            <section className="pdf-editor-block pdf-editor-image-block" key={block.id}>
              <img alt={block.alt} src={block.dataUrl} style={{ width: `${block.widthPercent}%` }} />
              <div className="pdf-editor-image-controls">
                <label>
                  <span>이미지 크기</span>
                  <input
                    disabled={disabled}
                    max="100"
                    min="35"
                    onChange={(event) =>
                      updateImageWidth(block.id, Number(event.target.value))
                    }
                    type="range"
                    value={block.widthPercent}
                  />
                </label>
                <button
                  disabled={disabled}
                  onClick={() => removeBlock(block.id)}
                  type="button"
                >
                  이미지 삭제
                </button>
              </div>
            </section>
          )
        )}
      </div>
    </div>
  );
}

function getSpreadsheetColumnName(columnNumber: number) {
  let value = columnNumber;
  let columnName = "";

  while (value > 0) {
    const remainder = (value - 1) % 26;
    columnName = `${String.fromCharCode(65 + remainder)}${columnName}`;
    value = Math.floor((value - 1) / 26);
  }

  return columnName;
}

function getSpreadsheetCellName(columnIndex: number, rowIndex: number) {
  return `${getSpreadsheetColumnName(columnIndex + 1)}${rowIndex + 1}`;
}

function isProtectedDocumentFolder(folder: Pick<DocumentFolder, "folderId" | "name">) {
  return folder.folderId === "folder-my-pc-journal";
}

function containsProtectedDocumentFolder(
  folders: DocumentFolder[],
  folderId: string
) {
  const folderIds = getDocumentFolderDescendantIds(folders, folderId);

  return folders.some(
    (folder) => folderIds.has(folder.folderId) && isProtectedDocumentFolder(folder)
  );
}

function SpreadsheetEditor({
  disabled,
  initialCells,
  onCellsChange
}: SpreadsheetEditorProps) {
  const [activeRibbonTab, setActiveRibbonTab] =
    useState<SpreadsheetRibbonTab>("home");
  const [activeCellName, setActiveCellName] = useState("A1");
  const [formulaValue, setFormulaValue] = useState("");
  const gridTemplateColumns = `3rem repeat(${spreadsheetColumnLabels.length}, 4.5rem)`;

  function commitFormulaValue() {
    if (disabled) {
      return;
    }

    const [columnName, rowName] = activeCellName.match(/[A-Z]+|\d+/g) ?? [];
    const columnIndex = columnName ? spreadsheetColumnLabels.indexOf(columnName) : -1;
    const rowIndex = Number(rowName) - 1;

    if (columnIndex >= 0 && rowIndex >= 0) {
      updateCell(rowIndex, columnIndex, formulaValue);
    }
  }

  function getCellValue(rowIndex: number, columnIndex: number) {
    return initialCells[rowIndex]?.[columnIndex] ?? "";
  }

  function cloneSpreadsheetCells() {
    const nextCells = createEmptySpreadsheetCells();

    for (let rowIndex = 0; rowIndex < spreadsheetRowCount; rowIndex += 1) {
      for (
        let columnIndex = 0;
        columnIndex < spreadsheetColumnLabels.length;
        columnIndex += 1
      ) {
        nextCells[rowIndex][columnIndex] = getCellValue(rowIndex, columnIndex);
      }
    }

    return nextCells;
  }

  function updateCell(rowIndex: number, columnIndex: number, value: string) {
    const nextCells = cloneSpreadsheetCells();
    nextCells[rowIndex][columnIndex] = value;
    onCellsChange(nextCells);
  }

  function selectCell(rowIndex: number, columnIndex: number) {
    setActiveCellName(getSpreadsheetCellName(columnIndex, rowIndex));
    setFormulaValue(getCellValue(rowIndex, columnIndex));
  }

  useEffect(() => {
    const [columnName, rowName] = activeCellName.match(/[A-Z]+|\d+/g) ?? [];
    const columnIndex = columnName ? spreadsheetColumnLabels.indexOf(columnName) : -1;
    const rowIndex = Number(rowName) - 1;

    if (columnIndex >= 0 && rowIndex >= 0) {
      setFormulaValue(getCellValue(rowIndex, columnIndex));
    }
  }, [initialCells, activeCellName]);

  return (
    <div className="spreadsheet-workbook">
      <div className="spreadsheet-ribbon-tabs" role="tablist" aria-label="Excel 메뉴">
        <button
          className={activeRibbonTab === "home" ? "active" : ""}
          onClick={() => setActiveRibbonTab("home")}
          role="tab"
          type="button"
        >
          시작
        </button>
        <button
          className={activeRibbonTab === "formula" ? "active" : ""}
          onClick={() => setActiveRibbonTab("formula")}
          role="tab"
          type="button"
        >
          수식
        </button>
        <button
          className={activeRibbonTab === "data" ? "active" : ""}
          onClick={() => setActiveRibbonTab("data")}
          role="tab"
          type="button"
        >
          데이터
        </button>
      </div>
      <div className="spreadsheet-ribbon" aria-label="스프레드시트 도구">
        {activeRibbonTab === "home" ? (
          <>
            <div className="spreadsheet-tool-group">
              <button
                aria-label="실행 취소"
                disabled
                type="button"
              >
                ↶
              </button>
              <button
                aria-label="다시 실행"
                disabled
                type="button"
              >
                ↷
              </button>
            </div>
            <div className="spreadsheet-tool-group wide">
              <select aria-label="글꼴" defaultValue="Arial" disabled={disabled}>
                <option>Arial</option>
                <option>맑은 고딕</option>
                <option>Inter</option>
              </select>
              <select aria-label="글꼴 크기" defaultValue="11" disabled={disabled}>
                <option>10</option>
                <option>11</option>
                <option>12</option>
                <option>14</option>
              </select>
            </div>
            <div className="spreadsheet-tool-group">
              <button
                disabled={disabled}
                type="button"
              >
                B
              </button>
              <button
                disabled={disabled}
                type="button"
              >
                I
              </button>
              <button
                disabled={disabled}
                type="button"
              >
                U
              </button>
              <button
                disabled={disabled}
                type="button"
              >
                S
              </button>
            </div>
            <div className="spreadsheet-tool-group">
              <button
                aria-label="왼쪽 정렬"
                disabled={disabled}
                type="button"
              >
                ≡
              </button>
              <button
                aria-label="가운데 정렬"
                disabled={disabled}
                type="button"
              >
                ≣
              </button>
              <button
                aria-label="오른쪽 정렬"
                disabled={disabled}
                type="button"
              >
                ≡
              </button>
            </div>
            <div className="spreadsheet-tool-group">
              <button
                disabled={disabled}
                type="button"
              >
                A
              </button>
              <button
                aria-label="셀 배경색"
                disabled={disabled}
                type="button"
              >
                ▣
              </button>
              <select aria-label="표시 형식" defaultValue="일반" disabled={disabled}>
                <option>일반</option>
                <option>숫자</option>
                <option>통화</option>
                <option>퍼센트</option>
              </select>
            </div>
          </>
        ) : null}
        {activeRibbonTab === "formula" ? (
          <div className="spreadsheet-tool-group formula-tools">
            <button
              disabled={disabled}
              onClick={() => setFormulaValue("=SUM()")}
              type="button"
            >
              SUM
            </button>
            <button
              disabled={disabled}
              onClick={() => setFormulaValue("=AVERAGE()")}
              type="button"
            >
              AVERAGE
            </button>
            <button
              disabled={disabled}
              onClick={() => setFormulaValue("=IF()")}
              type="button"
            >
              IF
            </button>
          </div>
        ) : null}
        {activeRibbonTab === "data" ? (
          <div className="spreadsheet-tool-group formula-tools">
            <button disabled={disabled} type="button">
              정렬
            </button>
            <button disabled={disabled} type="button">
              필터
            </button>
            <button disabled={disabled} type="button">
              데이터 확인
            </button>
          </div>
        ) : null}
      </div>
      <div className="spreadsheet-formula-bar">
        <span className="spreadsheet-name-box">{activeCellName}</span>
        <button
          aria-label="수식 입력 취소"
          disabled={disabled}
          onClick={() => {
            const [columnName, rowName] = activeCellName.match(/[A-Z]+|\d+/g) ?? [];
            const columnIndex = columnName
              ? spreadsheetColumnLabels.indexOf(columnName)
              : -1;
            const rowIndex = Number(rowName) - 1;
            const value =
              columnIndex >= 0 && rowIndex >= 0
                ? getCellValue(rowIndex, columnIndex)
                : "";
            setFormulaValue(String(value ?? ""));
          }}
          type="button"
        >
          ×
        </button>
        <button
          aria-label="수식 입력 적용"
          disabled={disabled}
          onClick={commitFormulaValue}
          type="button"
        >
          ✓
        </button>
        <span className="spreadsheet-formula-icon">ƒx</span>
        <input
          aria-label="수식 입력줄"
          disabled={disabled}
          onChange={(event) => setFormulaValue(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              commitFormulaValue();
            }
          }}
          value={formulaValue}
        />
      </div>
      <div className="spreadsheet-grid-host">
        <div
          className="spreadsheet-grid"
          role="grid"
          style={{ gridTemplateColumns }}
        >
          <div className="spreadsheet-grid-corner" />
          {spreadsheetColumnLabels.map((columnLabel) => (
            <div className="spreadsheet-grid-column-header" key={columnLabel}>
              {columnLabel}
            </div>
          ))}
          {Array.from({ length: spreadsheetRowCount }, (_, rowIndex) => (
            <Fragment key={`row-${rowIndex}`}>
              <div className="spreadsheet-grid-row-header">{rowIndex + 1}</div>
              {spreadsheetColumnLabels.map((columnLabel, columnIndex) => {
                const cellName = getSpreadsheetCellName(columnIndex, rowIndex);
                const isActive = activeCellName === cellName;

                return (
                  <input
                    aria-label={cellName}
                    className={isActive ? "active" : ""}
                    key={cellName}
                    onChange={(event) =>
                      updateCell(rowIndex, columnIndex, event.target.value)
                    }
                    onFocus={() => selectCell(rowIndex, columnIndex)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        event.preventDefault();
                      }
                    }}
                    readOnly={disabled}
                    value={getCellValue(rowIndex, columnIndex)}
                  />
                );
              })}
            </Fragment>
          ))}
        </div>
      </div>
    </div>
  );
}

function findDocumentByAutocompleteValue(
  documentOptions: DocumentItem[],
  value: string
) {
  const normalizedValue = value.trim();

  if (!normalizedValue) {
    return null;
  }

  return (
    documentOptions.find(
      (document) => getDocumentSelectLabel(document) === normalizedValue
    ) ??
    documentOptions.find((document) => document.name === normalizedValue) ??
    null
  );
}

function sortDocumentFolders(folders: DocumentFolder[]) {
  return [...folders].sort((left, right) => {
    if (left.sortOrder !== right.sortOrder) {
      return left.sortOrder - right.sortOrder;
    }

    return left.name.localeCompare(right.name, "ko-KR");
  });
}

function buildDocumentFolderTree(folders: DocumentFolder[]) {
  const childrenByParentId = new Map<string | null, DocumentFolder[]>();

  for (const folder of folders) {
    const parentFolderId = folder.parentFolderId ?? null;
    const children = childrenByParentId.get(parentFolderId) ?? [];
    children.push(folder);
    childrenByParentId.set(parentFolderId, children);
  }

  const treeItems: DocumentFolderTreeItem[] = [];

  function appendChildren(parentFolderId: string | null, depth: number) {
    const children = sortDocumentFolders(childrenByParentId.get(parentFolderId) ?? []);

    for (const child of children) {
      treeItems.push({ ...child, depth });
      appendChildren(child.folderId, depth + 1);
    }
  }

  appendChildren(null, 0);

  return treeItems;
}

function buildDocumentFolderChildCount(folders: DocumentFolder[]) {
  const childCountByFolderId = new Map<string, number>();

  for (const folder of folders) {
    if (!folder.parentFolderId) {
      continue;
    }

    childCountByFolderId.set(
      folder.parentFolderId,
      (childCountByFolderId.get(folder.parentFolderId) ?? 0) + 1
    );
  }

  return childCountByFolderId;
}

function filterVisibleDocumentFolderTree(
  treeItems: DocumentFolderTreeItem[],
  expandedFolderIds: Set<string>,
  childCountByFolderId: Map<string, number>
) {
  const visibleTreeItems: DocumentFolderTreeItem[] = [];
  let collapsedDepth: number | null = null;

  for (const item of treeItems) {
    if (collapsedDepth !== null && item.depth > collapsedDepth) {
      continue;
    }

    if (collapsedDepth !== null && item.depth <= collapsedDepth) {
      collapsedDepth = null;
    }

    visibleTreeItems.push(item);

    if (
      childCountByFolderId.has(item.folderId) &&
      !expandedFolderIds.has(item.folderId)
    ) {
      collapsedDepth = item.depth;
    }
  }

  return visibleTreeItems;
}

function getDocumentFolderDescendantIds(
  folders: DocumentFolder[],
  folderId: string
) {
  const childrenByParentId = new Map<string, DocumentFolder[]>();

  for (const folder of folders) {
    if (!folder.parentFolderId) {
      continue;
    }

    const children = childrenByParentId.get(folder.parentFolderId) ?? [];
    children.push(folder);
    childrenByParentId.set(folder.parentFolderId, children);
  }

  const descendantIds = new Set<string>([folderId]);
  const pendingFolderIds = [folderId];

  while (pendingFolderIds.length > 0) {
    const currentFolderId = pendingFolderIds.pop();

    if (!currentFolderId) {
      continue;
    }

    for (const child of childrenByParentId.get(currentFolderId) ?? []) {
      descendantIds.add(child.folderId);
      pendingFolderIds.push(child.folderId);
    }
  }

  return descendantIds;
}

function formatExplorerDate(value?: string) {
  if (!value) {
    return "";
  }

  return new Date(value).toLocaleString("ko-KR", {
    hour: "2-digit",
    minute: "2-digit",
    year: "numeric",
    month: "2-digit",
    day: "2-digit"
  });
}

type PdfPageCommand = {
  direction: "next" | "previous";
  id: number;
};

function ExcelDocumentViewer({ documentItem }: { documentItem: DocumentItem }) {
  const [cells, setCells] = useState<string[][]>(createEmptySpreadsheetCells);
  const [message, setMessage] = useState("");

  useEffect(() => {
    let canceled = false;

    async function loadSpreadsheet() {
      setMessage("Excel 문서를 불러오는 중입니다.");
      setCells(createEmptySpreadsheetCells());

      try {
        const response = await fetch(
          `/api/v1/document-files/${encodeURIComponent(
            documentItem.documentId
          )}/spreadsheet?version=${encodeURIComponent(documentItem.version)}`,
          {
            credentials: "include"
          }
        );

        if (!response.ok) {
          throw new Error("Spreadsheet load failed");
        }

        const data = (await response.json()) as {
          spreadsheet: {
            cells: DocumentEditorDraft["spreadsheetCells"];
          };
        };

        if (!canceled) {
          setCells(hydrateSpreadsheetCells(data.spreadsheet.cells));
          setMessage("");
        }
      } catch {
        if (!canceled) {
          setMessage("Excel 문서를 표시하지 못했습니다.");
        }
      }
    }

    void loadSpreadsheet();

    return () => {
      canceled = true;
    };
  }, [documentItem.documentId, documentItem.version]);

  return (
    <div className="excel-viewer">
      {message ? <p className="pdf-viewer-message">{message}</p> : null}
      <SpreadsheetEditor
        disabled
        initialCells={cells}
        onCellsChange={() => {
          // Viewer is read-only.
        }}
      />
    </div>
  );
}

function PdfDocumentViewer({
  documentItem,
  pageCommand
}: {
  documentItem: DocumentItem;
  pageCommand?: PdfPageCommand | null;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const renderTaskRef = useRef<{ cancel: () => void } | null>(null);
  const [pageNumber, setPageNumber] = useState(1);
  const [pageCount, setPageCount] = useState(0);
  const [scale, setScale] = useState(1.15);
  const [viewerMessage, setViewerMessage] = useState("");

  useEffect(() => {
    setPageNumber(1);
    setPageCount(0);
    setViewerMessage("");
  }, [documentItem.documentId, documentItem.version]);

  useEffect(() => {
    if (documentItem.type !== "PDF" || !documentItem.contentUrl) {
      return;
    }

    let canceled = false;

    async function renderPdfPage() {
      try {
        const canvas = canvasRef.current;

        if (!canvas) {
          return;
        }

        setViewerMessage("PDF를 불러오는 중입니다.");
        renderTaskRef.current?.cancel();

        const loadingTask = pdfjsLib.getDocument({
          url: documentItem.contentUrl ?? "",
          withCredentials: true
        });
        const pdfDocument = await loadingTask.promise;

        if (canceled) {
          await loadingTask.destroy();
          return;
        }

        setPageCount(pdfDocument.numPages);
        const safePageNumber = Math.min(pageNumber, pdfDocument.numPages);
        const page = await pdfDocument.getPage(safePageNumber);
        const viewport = page.getViewport({ scale });
        const context = canvas.getContext("2d");

        if (!context) {
          setViewerMessage("PDF 화면을 준비하지 못했습니다.");
          await loadingTask.destroy();
          return;
        }

        canvas.height = viewport.height;
        canvas.width = viewport.width;
        context.clearRect(0, 0, canvas.width, canvas.height);

        const renderTask = page.render({
          canvas,
          canvasContext: context,
          viewport
        });
        renderTaskRef.current = renderTask;
        await renderTask.promise;
        await loadingTask.destroy();

        if (!canceled) {
          setViewerMessage("");
        }
      } catch (error) {
        if (!canceled && (error as { name?: string }).name !== "RenderingCancelledException") {
          setViewerMessage("PDF를 표시하지 못했습니다.");
        }
      }
    }

    void renderPdfPage();

    return () => {
      canceled = true;
      renderTaskRef.current?.cancel();
    };
  }, [documentItem.contentUrl, documentItem.type, documentItem.version, pageNumber, scale]);

  useEffect(() => {
    if (!pageCommand || documentItem.type !== "PDF" || pageCount <= 0) {
      return;
    }

    setPageNumber((currentPage) =>
      pageCommand.direction === "next"
        ? Math.min(pageCount, currentPage + 1)
        : Math.max(1, currentPage - 1)
    );
  }, [documentItem.type, pageCommand, pageCount]);

  if (documentItem.type === "IMAGE" && documentItem.contentUrl) {
    return (
      <div className="viewer-surface viewer-image">
        <figure className="image-viewer-page">
          <img alt={documentItem.name} src={documentItem.contentUrl} />
          {documentItem.summary ? <figcaption>{documentItem.summary}</figcaption> : null}
        </figure>
      </div>
    );
  }

  if (documentItem.type === "JOURNAL" && documentItem.journal) {
    return (
      <div className="viewer-surface viewer-journal">
        <article className="journal-document-page">
          <header>
            <p className="eyebrow">
              {documentItem.journal.isHandover ? "인수인계" : "현장 작업일지"}
            </p>
            <h3>{documentItem.name}</h3>
            <small>
              {documentItem.journal.createdBy} /{" "}
              {formatExplorerDate(documentItem.journal.createdAt)}
            </small>
          </header>
          <section>
            <h4>원문</h4>
            <p>{documentItem.journal.memo || "메모 없음"}</p>
          </section>
          {documentItem.journal.replies.length > 0 ? (
            <section>
              <h4>응답</h4>
              <div className="journal-document-replies">
                {documentItem.journal.replies.map((reply) => (
                  <article key={reply.replyId}>
                    <div>
                      <strong>{journalReplyTypeLabels[reply.type] ?? reply.type}</strong>
                      {reply.version ? <span>{reply.version}</span> : null}
                    </div>
                    <p>{reply.text}</p>
                    <small>
                      {reply.createdBy} / {formatExplorerDate(reply.createdAt)}
                    </small>
                  </article>
                ))}
              </div>
            </section>
          ) : null}
        </article>
      </div>
    );
  }

  if (documentItem.type === "EXCEL") {
    return <ExcelDocumentViewer documentItem={documentItem} />;
  }

  if (documentItem.type !== "PDF" || !documentItem.contentUrl) {
    return (
      <div className={`viewer-surface viewer-${documentItem.type.toLowerCase()}`}>
        <div className="viewer-page">
          <strong>{documentItem.name}</strong>
          <p>{documentItem.summary}</p>
          <div className="viewer-lines" aria-hidden="true">
            <span />
            <span />
            <span />
            <span />
            <span />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="pdf-viewer">
      <div className="pdf-viewer-toolbar">
        <button
          className="secondary-button"
          disabled={pageNumber <= 1}
          onClick={() => setPageNumber((currentPage) => Math.max(1, currentPage - 1))}
          type="button"
        >
          이전
        </button>
        <span>
          {pageNumber} / {pageCount || "-"}
        </span>
        <button
          className="secondary-button"
          disabled={pageCount > 0 && pageNumber >= pageCount}
          onClick={() =>
            setPageNumber((currentPage) =>
              pageCount > 0 ? Math.min(pageCount, currentPage + 1) : currentPage
            )
          }
          type="button"
        >
          다음
        </button>
        <button
          className="secondary-button"
          onClick={() => setScale((currentScale) => Math.max(0.8, currentScale - 0.15))}
          type="button"
        >
          축소
        </button>
        <button
          className="secondary-button"
          onClick={() => setScale((currentScale) => Math.min(2.2, currentScale + 0.15))}
          type="button"
        >
          확대
        </button>
      </div>
      {viewerMessage ? <p className="pdf-viewer-message">{viewerMessage}</p> : null}
      <div className="pdf-canvas-wrap">
        <canvas ref={canvasRef} />
      </div>
    </div>
  );
}

export function App() {
  const [sessionUser, setSessionUser] = useState<SessionUser | null>(null);
  const [loginId, setLoginId] = useState("admin");
  const [password, setPassword] = useState("1234");
  const [loginError, setLoginError] = useState("");
  const [authChecking, setAuthChecking] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [userMessage, setUserMessage] = useState("");
  const [historyItems, setHistoryItems] = useState<SystemHistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyMessage, setHistoryMessage] = useState("");
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [notificationUnreadCount, setNotificationUnreadCount] = useState(0);
  const [notificationLoading, setNotificationLoading] = useState(false);
  const [notificationMessage, setNotificationMessage] = useState("");
  const [selectedDocument, setSelectedDocument] = useState<DocumentItem | null>(null);
  const [selectedDocumentVersion, setSelectedDocumentVersion] = useState("");
  const [documentItems, setDocumentItems] = useState<DocumentItem[]>(documents);
  const [documentFolders, setDocumentFolders] = useState<DocumentFolder[]>([]);
  const [documentCurrentFolderId, setDocumentCurrentFolderId] = useState(
    "folder-field-documents"
  );
  const [documentCanManage, setDocumentCanManage] = useState(false);
  const [documentExplorerLoading, setDocumentExplorerLoading] = useState(false);
  const [newFolderOpen, setNewFolderOpen] = useState(false);
  const [newFolderName, setNewFolderName] = useState("");
  const [folderMessage, setFolderMessage] = useState("");
  const [newDocumentType, setNewDocumentType] = useState<"PDF" | "EXCEL">("PDF");
  const [newDocumentOpen, setNewDocumentOpen] = useState(false);
  const [newDocumentName, setNewDocumentName] = useState("");
  const [newDocumentSummary, setNewDocumentSummary] = useState("");
  const [newDocumentBody, setNewDocumentBody] = useState("");
  const [newSpreadsheetCells, setNewSpreadsheetCells] = useState<string[][]>(
    createEmptySpreadsheetCells
  );
  const [newDocumentTags, setNewDocumentTags] = useState("");
  const [newDocumentChangeNote, setNewDocumentChangeNote] = useState("");
  const [newDocumentCreating, setNewDocumentCreating] = useState(false);
  const [newDocumentMessage, setNewDocumentMessage] = useState("");
  const [editingDocument, setEditingDocument] = useState<DocumentItem | null>(null);
  const [editDocumentLoadingId, setEditDocumentLoadingId] = useState("");
  const [documentContextMenu, setDocumentContextMenu] = useState({
    open: false,
    x: 0,
    y: 0
  });
  const [folderContextMenu, setFolderContextMenu] = useState<{
    open: boolean;
    x: number;
    y: number;
    folder: DocumentFolder | null;
  }>({
    open: false,
    x: 0,
    y: 0,
    folder: null
  });
  const [renamingFolder, setRenamingFolder] = useState<DocumentFolder | null>(null);
  const [renameFolderName, setRenameFolderName] = useState("");
  const [renameFolderMessage, setRenameFolderMessage] = useState("");
  const [renameFolderSubmitting, setRenameFolderSubmitting] = useState(false);
  const [deletingFolder, setDeletingFolder] = useState<DocumentFolder | null>(null);
  const [deleteFolderMessage, setDeleteFolderMessage] = useState("");
  const [deleteFolderSubmitting, setDeleteFolderSubmitting] = useState(false);
  const [documentUploadMessage, setDocumentUploadMessage] = useState("");
  const [documentUploadTags, setDocumentUploadTags] = useState("");
  const [pendingUploadFiles, setPendingUploadFiles] = useState<File[]>([]);
  const [documentUploading, setDocumentUploading] = useState(false);
  const [documentDragOver, setDocumentDragOver] = useState(false);
  const [journalEntries, setJournalEntries] = useState<FieldJournalEntry[]>([]);
  const [journalMemo, setJournalMemo] = useState("");
  const [journalPhoto, setJournalPhoto] = useState<File | null>(null);
  const [journalIsHandover, setJournalIsHandover] = useState(false);
  const [journalHandoverTo, setJournalHandoverTo] = useState("");
  const [journalReplyDrafts, setJournalReplyDrafts] = useState<Record<string, string>>({});
  const [journalReplySubmittingId, setJournalReplySubmittingId] = useState("");
  const [journalMessage, setJournalMessage] = useState("");
  const [journalLoading, setJournalLoading] = useState(false);
  const [journalSubmitting, setJournalSubmitting] = useState(false);
  const [selectedJournalPhoto, setSelectedJournalPhoto] =
    useState<FieldJournalEntry | null>(null);
  const [journalPhotoScale, setJournalPhotoScale] = useState(1);
  const [journalPhotoOffset, setJournalPhotoOffset] = useState({ x: 0, y: 0 });
  const [journalPhotoDragging, setJournalPhotoDragging] = useState(false);
  const [sequenceItems, setSequenceItems] = useState<WorkSequenceItem[]>([]);
  const [sequenceCanEdit, setSequenceCanEdit] = useState(false);
  const [sequenceLoading, setSequenceLoading] = useState(false);
  const [sequenceMessage, setSequenceMessage] = useState("");
  const [selectedSequenceDocument, setSelectedSequenceDocument] =
    useState<DocumentItem | null>(null);
  const [sequenceDocumentScale, setSequenceDocumentScale] = useState(1);
  const [sequenceDocumentPageCommand, setSequenceDocumentPageCommand] =
    useState<PdfPageCommand | null>(null);
  const [sequenceFormOpen, setSequenceFormOpen] = useState(false);
  const [sequenceSubmitting, setSequenceSubmitting] = useState(false);
  const [sequenceForm, setSequenceForm] =
    useState<WorkSequenceForm>(emptySequenceForm);
  const [documentAutocompleteField, setDocumentAutocompleteField] =
    useState<"" | "create" | "edit">("");
  const [editingSequenceItem, setEditingSequenceItem] =
    useState<WorkSequenceItem | null>(null);
  const [editSequenceForm, setEditSequenceForm] =
    useState<WorkSequenceForm>(emptySequenceForm);
  const [editSequenceSubmitting, setEditSequenceSubmitting] = useState(false);
  const [draggingSequenceItemId, setDraggingSequenceItemId] = useState("");
  const [dragOverSequenceItemId, setDragOverSequenceItemId] = useState("");
  const [topSearch, setTopSearch] = useState("");
  const [expandedFolderIds, setExpandedFolderIds] = useState<Set<string>>(
    () => new Set(["folder-my-pc", "folder-field-documents", "folder-line-1"])
  );
  const [activePage, setActivePage] = useState<AppPage>(() => getAppPageFromHash());
  const activePageRef = useRef(activePage);
  const ignoreNextHashChangeRef = useRef(false);
  const sequenceItemsRef = useRef<WorkSequenceItem[]>([]);
  const dragStartSequenceIdsRef = useRef<string[]>([]);
  const journalPhotoDragRef = useRef({ startX: 0, startY: 0, x: 0, y: 0 });
  const documentContextLongPressTimerRef = useRef<number | null>(null);
  const documentContextPointerStartRef = useRef<{ x: number; y: number } | null>(
    null
  );
  const folderContextLongPressTimerRef = useRef<number | null>(null);
  const folderContextPointerStartRef = useRef<{
    folderId: string;
    x: number;
    y: number;
  } | null>(null);
  const folderContextLongPressOpenedRef = useRef(false);
  const journalPhotoPointersRef = useRef(new Map<number, { x: number; y: number }>());
  const journalPhotoPinchRef = useRef({
    centerX: 0,
    centerY: 0,
    distance: 0,
    offsetX: 0,
    offsetY: 0,
    scale: 1
  });
  const journalPhotoScaleRef = useRef(1);
  const journalPhotoOffsetRef = useRef({ x: 0, y: 0 });
  const sequenceDocumentPointersRef = useRef(
    new Map<number, { x: number; y: number }>()
  );
  const sequenceDocumentPinchRef = useRef({ distance: 0, scale: 1 });
  const sequenceDocumentSwipeRef = useRef({
    pinching: false,
    startTime: 0,
    startX: 0,
    startY: 0
  });
  const sequenceDocumentScaleRef = useRef(1);

  const isSuperAdmin = Boolean(sessionUser?.roles.includes("super-admin"));
  const canOpenSequenceForm = Boolean(
    sessionUser?.roles.some((roleId) => editableSequenceRoles.includes(roleId))
  );
  const documentFolderTree = buildDocumentFolderTree(documentFolders);
  const documentFolderChildCount = buildDocumentFolderChildCount(documentFolders);
  const visibleDocumentFolderTree = filterVisibleDocumentFolderTree(
    documentFolderTree,
    expandedFolderIds,
    documentFolderChildCount
  );
  const currentDocumentFolder = documentFolders.find(
    (folder) => folder.folderId === documentCurrentFolderId
  );
  const currentExplorerFolders = sortDocumentFolders(
    documentFolders.filter(
      (folder) => folder.parentFolderId === documentCurrentFolderId
    )
  );
  const normalizedTopSearch = topSearch.trim().toLocaleLowerCase("ko-KR");
  const filteredExplorerFolders = normalizedTopSearch
    ? []
    : currentExplorerFolders;
  const filteredDocuments = normalizedTopSearch
    ? documentItems.filter((document) =>
        [
          document.name,
          document.meta,
          document.category,
          document.summary,
          document.owner,
          document.securityLevel,
          document.type,
          document.journal?.memo,
          ...(document.journal?.replies.map((reply) => reply.text) ?? []),
          ...document.tags
        ]
          .join(" ")
          .toLocaleLowerCase("ko-KR")
          .includes(normalizedTopSearch)
      )
    : documentItems.filter((document) => document.folderId === documentCurrentFolderId);
  const documentById = new Map(
    documentItems.map((document) => [document.documentId, document])
  );
  const sequenceDocumentOptions = [...documentItems].sort((left, right) =>
    left.name.localeCompare(right.name, "ko-KR")
  );

  function resolveLinkedDocumentFormValue(form: WorkSequenceForm) {
    const linkedDocumentSearch = form.linkedDocumentSearch.trim();

    if (!linkedDocumentSearch) {
      return {
        linkedDocumentId: "",
        linkedDocumentName: ""
      };
    }

    if (form.linkedDocumentId && form.linkedDocumentName) {
      const selectedDocument = documentById.get(form.linkedDocumentId);

      if (
        linkedDocumentSearch === form.linkedDocumentName ||
        (selectedDocument &&
          linkedDocumentSearch === getDocumentSelectLabel(selectedDocument))
      ) {
        return {
          linkedDocumentId: form.linkedDocumentId,
          linkedDocumentName: form.linkedDocumentName
        };
      }
    }

    const linkedDocument = findDocumentByAutocompleteValue(
      sequenceDocumentOptions,
      linkedDocumentSearch
    );

    if (!linkedDocument) {
      return null;
    }

    return {
      linkedDocumentId: linkedDocument.documentId,
      linkedDocumentName: linkedDocument.name
    };
  }

  function getSequenceDocumentMatches(searchValue: string) {
    const normalizedSearch = searchValue.trim().toLocaleLowerCase("ko-KR");
    const matchingDocuments = normalizedSearch
      ? sequenceDocumentOptions.filter((document) =>
          [
            document.name,
            document.category,
            document.version,
            document.type,
            document.meta,
            ...document.tags
          ]
            .join(" ")
            .toLocaleLowerCase("ko-KR")
            .includes(normalizedSearch)
        )
      : sequenceDocumentOptions;

    return matchingDocuments.slice(0, 8);
  }

  function selectSequenceDocument(
    document: DocumentItem,
    field: "create" | "edit"
  ) {
    const nextValue = {
      linkedDocumentId: document.documentId,
      linkedDocumentName: document.name,
      linkedDocumentSearch: getDocumentSelectLabel(document)
    };

    if (field === "create") {
      setSequenceForm((form) => ({
        ...form,
        ...nextValue
      }));
    } else {
      setEditSequenceForm((form) => ({
        ...form,
        ...nextValue
      }));
    }

    setDocumentAutocompleteField("");
  }

  function renderLinkedDocumentAutocomplete(
    form: WorkSequenceForm,
    field: "create" | "edit"
  ) {
    const documentMatches = getSequenceDocumentMatches(form.linkedDocumentSearch);
    const isOpen = documentAutocompleteField === field;

    return (
      <label className="span-2 linked-document-field">
        <span>연결 문서</span>
        <input
          onBlur={() => {
            window.setTimeout(() => setDocumentAutocompleteField(""), 120);
          }}
          onClick={() => setDocumentAutocompleteField(field)}
          onChange={(event) => {
            const linkedDocument = findDocumentByAutocompleteValue(
              sequenceDocumentOptions,
              event.target.value
            );
            const nextValue = {
              linkedDocumentId: linkedDocument?.documentId ?? "",
              linkedDocumentName: linkedDocument?.name ?? "",
              linkedDocumentSearch: event.target.value
            };

            if (field === "create") {
              setSequenceForm((currentForm) => ({
                ...currentForm,
                ...nextValue
              }));
            } else {
              setEditSequenceForm((currentForm) => ({
                ...currentForm,
                ...nextValue
              }));
            }
          }}
          onFocus={() => setDocumentAutocompleteField(field)}
          onMouseDown={() => setDocumentAutocompleteField(field)}
          placeholder="문서명, 폴더, 버전으로 검색"
          value={form.linkedDocumentSearch}
        />
        {isOpen ? (
          <div className="document-autocomplete-list" role="listbox">
            {documentMatches.length > 0 ? (
              documentMatches.map((document) => (
                <button
                  key={document.documentId}
                  onMouseDown={(event) => {
                    event.preventDefault();
                    selectSequenceDocument(document, field);
                  }}
                  type="button"
                >
                  <strong>{document.name}</strong>
                  <small>
                    {document.category} / {document.version} / {document.type}
                  </small>
                </button>
              ))
            ) : (
              <p>검색 결과가 없습니다.</p>
            )}
          </div>
        ) : null}
      </label>
    );
  }

  function findSequenceLinkedDocument(item: WorkSequenceItem) {
    if (item.linkedDocumentId) {
      const linkedDocument = documentById.get(item.linkedDocumentId);

      if (linkedDocument) {
        return linkedDocument;
      }
    }

    const linkedDocumentName = item.linkedDocumentName?.trim();

    if (!linkedDocumentName) {
      return null;
    }

    const normalizedLinkedDocumentName =
      linkedDocumentName.toLocaleLowerCase("ko-KR");

    return (
      documentItems.find(
        (document) =>
          document.name.toLocaleLowerCase("ko-KR") ===
            normalizedLinkedDocumentName ||
          getDocumentSelectLabel(document).toLocaleLowerCase("ko-KR") ===
            normalizedLinkedDocumentName
      ) ?? null
    );
  }

  useEffect(() => {
    sequenceItemsRef.current = sequenceItems;
  }, [sequenceItems]);

  useEffect(() => {
    journalPhotoScaleRef.current = journalPhotoScale;
  }, [journalPhotoScale]);

  useEffect(() => {
    journalPhotoOffsetRef.current = journalPhotoOffset;
  }, [journalPhotoOffset]);

  useEffect(() => {
    sequenceDocumentScaleRef.current = sequenceDocumentScale;
  }, [sequenceDocumentScale]);

  useEffect(() => {
    activePageRef.current = activePage;
  }, [activePage]);

  useEffect(() => {
    let active = true;

    async function loadCurrentUser() {
      try {
        const response = await fetch("/api/v1/auth/me", {
          credentials: "include"
        });

        if (!active) {
          return;
        }

        if (response.ok) {
          const data = (await response.json()) as { user: SessionUser };
          setSessionUser(data.user);
        }
      } finally {
        if (active) {
          setAuthChecking(false);
        }
      }
    }

    loadCurrentUser();

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    function handleHashChange() {
      if (ignoreNextHashChangeRef.current) {
        ignoreNextHashChangeRef.current = false;
        return;
      }

      const page = getAppPageFromHash();

      setActivePage(page);

      if (page !== "document") {
        setSelectedDocument(null);
        setSelectedDocumentVersion("");
      }
    }

    window.addEventListener("hashchange", handleHashChange);

    return () => {
      window.removeEventListener("hashchange", handleHashChange);
    };
  }, []);

  useEffect(() => {
    function getCurrentAppUrl() {
      return `${window.location.pathname}${window.location.search}${getHashForAppPage(
        activePageRef.current
      )}`;
    }

    window.history.replaceState(
      { ...(window.history.state ?? {}), flowNoteApp: true },
      "",
      getCurrentAppUrl()
    );
    window.history.pushState({ flowNoteBackGuard: true }, "", getCurrentAppUrl());

    function ignoreBrowserBack() {
      ignoreNextHashChangeRef.current = true;
      window.history.pushState(
        { flowNoteBackGuard: true },
        "",
        getCurrentAppUrl()
      );
    }

    window.addEventListener("popstate", ignoreBrowserBack);

    return () => {
      window.removeEventListener("popstate", ignoreBrowserBack);
    };
  }, []);

  useEffect(() => {
    const nextHash = getHashForAppPage(activePage);

    if (window.location.hash !== nextHash) {
      window.history.replaceState(
        null,
        "",
        `${window.location.pathname}${window.location.search}${nextHash}`
      );
    }
  }, [activePage]);

  useEffect(() => {
    if (authChecking) {
      return;
    }

    if (!sessionUser && activePage !== "sequence" && activePage !== "dashboard") {
      setActivePage("dashboard");
    }
  }, [activePage, authChecking, sessionUser]);

  useEffect(() => {
    if (!isSuperAdmin || activePage !== "members") {
      setUsers([]);
      return;
    }

    loadUsers();
  }, [activePage, isSuperAdmin]);

  useEffect(() => {
    if (!isSuperAdmin || activePage !== "history") {
      setHistoryItems([]);
      return;
    }

    loadSystemHistory();
  }, [activePage, isSuperAdmin]);

  useEffect(() => {
    if (!sessionUser) {
      setNotifications([]);
      setNotificationUnreadCount(0);
      return;
    }

    loadNotifications();
  }, [sessionUser]);

  useEffect(() => {
    if (!sessionUser || activePage !== "notifications") {
      return;
    }

    loadNotifications();
  }, [activePage, sessionUser]);

  useEffect(() => {
    if (authChecking) {
      return;
    }

    if (!isSuperAdmin && (activePage === "members" || activePage === "history")) {
      setActivePage("dashboard");
    }
  }, [activePage, authChecking, isSuperAdmin]);

  useEffect(() => {
    if (activePage === "document") {
      setActivePage("documents");
    }
  }, [activePage]);

  useEffect(() => {
    if (!selectedDocument) {
      return;
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        closeDocumentViewer();
      }
    }

    window.addEventListener("keydown", handleKeyDown);

    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [selectedDocument]);

  useEffect(() => {
    if (!sessionUser) {
      return;
    }

    if (
      activePage !== "dashboard" &&
      activePage !== "documents" &&
      activePage !== "journal" &&
      activePage !== "sequence"
    ) {
      return;
    }

    loadDocumentExplorer();
  }, [activePage, sessionUser]);

  useEffect(() => {
    if (!sessionUser || activePage !== "journal") {
      return;
    }

    loadFieldJournalEntries();
  }, [activePage, sessionUser]);

  useEffect(() => {
    if (
      !normalizedTopSearch ||
      activePage === "documents" ||
      activePage === "document"
    ) {
      return;
    }

    setSelectedDocument(null);
    setSelectedDocumentVersion("");
    setActivePage("documents");
  }, [activePage, normalizedTopSearch]);

  useEffect(() => {
    if (activePage !== "sequence") {
      return;
    }

    loadSequenceItems();
  }, [activePage, sessionUser]);

  useEffect(() => {
    if (!documentContextMenu.open && !folderContextMenu.open) {
      return;
    }

    function closeContextMenu() {
      setDocumentContextMenu((menu) => ({ ...menu, open: false }));
      setFolderContextMenu((menu) => ({ ...menu, open: false }));
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        closeContextMenu();
      }
    }

    window.addEventListener("pointerdown", closeContextMenu);
    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("scroll", closeContextMenu, true);

    return () => {
      window.removeEventListener("pointerdown", closeContextMenu);
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("scroll", closeContextMenu, true);
    };
  }, [documentContextMenu.open, folderContextMenu.open]);

  useEffect(() => {
    if (!editingSequenceItem && !sequenceFormOpen) {
      return;
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setEditingSequenceItem(null);
        if (!sequenceSubmitting) {
          setSequenceFormOpen(false);
        }
      }
    }

    window.addEventListener("keydown", handleKeyDown);

    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [editingSequenceItem, sequenceFormOpen, sequenceSubmitting]);

  useEffect(() => {
    if (!draggingSequenceItemId) {
      return;
    }

    function handlePointerMove(event: PointerEvent) {
      const targetElement = document
        .elementFromPoint(event.clientX, event.clientY)
        ?.closest<HTMLElement>("[data-sequence-id]");
      const targetItemId = targetElement?.dataset.sequenceId;

      if (!targetElement || !targetItemId || targetItemId === draggingSequenceItemId) {
        return;
      }

      const targetRect = targetElement.getBoundingClientRect();
      const insertAfterTarget =
        event.clientY > targetRect.top + targetRect.height / 2;
      setDragOverSequenceItemId(targetItemId);
      setSequenceItems((currentItems) => {
        const nextItems = moveSequenceItem(
          currentItems,
          draggingSequenceItemId,
          targetItemId,
          insertAfterTarget
        );
        sequenceItemsRef.current = nextItems;
        return nextItems;
      });
    }

    function handlePointerUp() {
      const currentIds = sequenceItemsRef.current.map((item) => item.sequenceItemId);
      const startIds = dragStartSequenceIdsRef.current;
      const orderChanged =
        currentIds.length === startIds.length &&
        currentIds.some((itemId, index) => itemId !== startIds[index]);

      document.body.classList.remove("dragging-sequence");
      setDraggingSequenceItemId("");
      setDragOverSequenceItemId("");
      dragStartSequenceIdsRef.current = [];

      if (orderChanged) {
        void saveSequenceOrder(currentIds);
      }
    }

    document.body.classList.add("dragging-sequence");
    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp);
    window.addEventListener("pointercancel", handlePointerUp);

    return () => {
      document.body.classList.remove("dragging-sequence");
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
      window.removeEventListener("pointercancel", handlePointerUp);
    };
  }, [draggingSequenceItemId]);

  async function loadUsers() {
    const response = await fetch("/api/v1/users", {
      credentials: "include"
    });

    if (!response.ok) {
      setUserMessage("회원 목록을 불러오지 못했습니다.");
      return;
    }

    const data = (await response.json()) as { users: ManagedUser[] };
    setUsers(data.users);
  }

  async function loadSequenceItems() {
    setSequenceLoading(true);
    setSequenceMessage("");

    try {
      const response = await fetch("/api/v1/work-sequence/items", {
        credentials: "include"
      });

      if (!response.ok) {
        setSequenceMessage("작업 순서를 불러오지 못했습니다.");
        return;
      }

      const data = (await response.json()) as {
        items: WorkSequenceItem[];
        canEdit: boolean;
      };
      setSequenceItems(orderSequenceItems(data.items));
      setSequenceCanEdit(data.canEdit);
    } catch {
      setSequenceMessage("작업 순서 서버에 연결할 수 없습니다.");
    } finally {
      setSequenceLoading(false);
    }
  }

  async function loadSystemHistory() {
    setHistoryLoading(true);
    setHistoryMessage("");

    try {
      const response = await fetch("/api/v1/system-history", {
        credentials: "include"
      });

      if (!response.ok) {
        setHistoryMessage("시스템 이력을 불러오지 못했습니다.");
        return;
      }

      const data = (await response.json()) as { history: SystemHistoryItem[] };
      setHistoryItems(data.history);
    } catch {
      setHistoryMessage("시스템 이력 서버에 연결할 수 없습니다.");
    } finally {
      setHistoryLoading(false);
    }
  }

  async function loadNotifications() {
    setNotificationLoading(true);
    setNotificationMessage("");

    try {
      const response = await fetch("/api/v1/notifications", {
        credentials: "include"
      });

      if (!response.ok) {
        setNotificationMessage("알림을 불러오지 못했습니다.");
        return;
      }

      const data = (await response.json()) as {
        notifications: NotificationItem[];
        unreadCount: number;
      };
      setNotifications(data.notifications);
      setNotificationUnreadCount(data.unreadCount);
    } catch {
      setNotificationMessage("알림 서버에 연결할 수 없습니다.");
    } finally {
      setNotificationLoading(false);
    }
  }

  async function openNotification(notification: NotificationItem) {
    setNotificationMessage("");

    try {
      const response = await fetch(
        `/api/v1/notifications/${notification.notificationId}/read`,
        {
          credentials: "include",
          method: "PATCH"
        }
      );

      if (response.ok) {
        const data = (await response.json()) as {
          notification: NotificationItem;
          unreadCount: number;
        };
        setNotifications((currentNotifications) =>
          currentNotifications.map((currentNotification) =>
            currentNotification.notificationId === notification.notificationId
              ? data.notification
              : currentNotification
          )
        );
        setNotificationUnreadCount(data.unreadCount);
      }
    } catch {
      setNotificationMessage("알림 읽음 처리에 실패했습니다.");
    }

    if (notification.sourceType === "DOCUMENT" && notification.sourceDocumentId) {
      const loadedDocuments = await loadDocumentExplorer();
      const linkedDocument = loadedDocuments.find(
        (document) => document.documentId === notification.sourceDocumentId
      );

      if (linkedDocument) {
        openDocument(linkedDocument);
        return;
      }

      setActivePage("documents");
      return;
    }

    if (notification.sourceType === "JOURNAL") {
      setActivePage("journal");
      return;
    }

    if (notification.sourceType === "SEQUENCE") {
      setActivePage("sequence");
      return;
    }

    setActivePage("notifications");
  }

  async function loadDocumentExplorer(): Promise<DocumentItem[]> {
    setDocumentExplorerLoading(true);
    setFolderMessage("");

    try {
      const response = await fetch("/api/v1/document-explorer", {
        credentials: "include"
      });

      if (!response.ok) {
        setFolderMessage("문서 폴더를 불러오지 못했습니다.");
        return [];
      }

      const data = (await response.json()) as {
        currentFolderId: string;
        folders: DocumentFolder[];
        documents: DocumentItem[];
        currentFolders: DocumentFolder[];
        canManage: boolean;
      };
      setDocumentCurrentFolderId((currentFolderId) =>
        data.folders.some((folder) => folder.folderId === currentFolderId)
          ? currentFolderId
          : data.currentFolderId
      );
      setDocumentFolders(data.folders);
      setDocumentItems(data.documents);
      setDocumentCanManage(data.canManage);
      return data.documents;
    } catch {
      setFolderMessage("문서 폴더 서버에 연결할 수 없습니다.");
      return [];
    } finally {
      setDocumentExplorerLoading(false);
    }
  }

  async function loadFieldJournalEntries() {
    setJournalLoading(true);
    setJournalMessage("");

    try {
      const response = await fetch("/api/v1/field-journal-entries", {
        credentials: "include"
      });

      if (!response.ok) {
        setJournalMessage("작업일지를 불러오지 못했습니다.");
        return;
      }

      const data = (await response.json()) as { entries: FieldJournalEntry[] };
      setJournalEntries(data.entries);
    } catch {
      setJournalMessage("작업일지 서버에 연결할 수 없습니다.");
    } finally {
      setJournalLoading(false);
    }
  }

  async function submitLogin(targetPage: AppPage = "dashboard") {
    setSubmitting(true);
    setLoginError("");

    try {
      const response = await fetch("/api/v1/auth/login", {
        body: JSON.stringify({
          loginId: loginId.trim(),
          password
        }),
        credentials: "include",
        headers: {
          "Content-Type": "application/json"
        },
        method: "POST"
      });

      if (!response.ok) {
        setLoginError("아이디 또는 비밀번호가 올바르지 않습니다.");
        return;
      }

      const data = (await response.json()) as { user: SessionUser };
      setActivePage(targetPage);
      setSessionUser(data.user);
    } catch {
      setLoginError("로그인 서버에 연결할 수 없습니다.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await submitLogin();
  }

  async function handleLogout() {
    await fetch("/api/v1/auth/logout", {
      credentials: "include",
      method: "POST"
    });
    setSessionUser(null);
    setUsers([]);
    setHistoryItems([]);
    setNotifications([]);
    setNotificationUnreadCount(0);
    setSelectedDocument(null);
    setDocumentFolders([]);
    setDocumentItems(documents);
    setDocumentCanManage(false);
    setNewDocumentType("PDF");
    setNewDocumentOpen(false);
    setEditingDocument(null);
    setNewDocumentName("");
    setNewDocumentSummary("");
    setNewDocumentBody("");
    setNewSpreadsheetCells(createEmptySpreadsheetCells());
    setNewDocumentTags("");
    setNewDocumentMessage("");
    setJournalEntries([]);
    setJournalMemo("");
    setJournalPhoto(null);
    setJournalIsHandover(false);
    setJournalHandoverTo("");
    setJournalReplyDrafts({});
    setJournalReplySubmittingId("");
    setJournalMessage("");
    setSequenceItems([]);
    setSequenceCanEdit(false);
    setActivePage("dashboard");
  }

  function openDocument(document: DocumentItem) {
    setSelectedDocument(document);
    setSelectedDocumentVersion(document.version);
  }

  function closeDocumentViewer() {
    setSelectedDocument(null);
    setSelectedDocumentVersion("");
  }

  function toggleDocumentFolder(folderId: string) {
    setExpandedFolderIds((currentIds) => {
      const nextIds = new Set(currentIds);

      if (nextIds.has(folderId)) {
        nextIds.delete(folderId);
      } else {
        nextIds.add(folderId);
      }

      return nextIds;
    });
  }

  async function handleCreateFolder(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedFolderName = newFolderName.trim();

    if (!trimmedFolderName) {
      setFolderMessage("폴더명을 입력해 주세요.");
      return;
    }

    const normalizedFolderName = trimmedFolderName.toLocaleLowerCase("ko-KR");
    const folderExists = documentFolders.some(
      (folder) =>
        folder.parentFolderId === documentCurrentFolderId &&
        folder.name.toLocaleLowerCase("ko-KR") === normalizedFolderName
    );

    if (folderExists) {
      setFolderMessage("이미 같은 이름의 폴더가 있습니다.");
      return;
    }

    try {
      const response = await fetch("/api/v1/document-folders", {
        body: JSON.stringify({
          folderName: trimmedFolderName,
          parentFolderId: documentCurrentFolderId
        }),
        credentials: "include",
        headers: {
          "Content-Type": "application/json"
        },
        method: "POST"
      });

      if (!response.ok) {
        const data = (await response.json().catch(() => null)) as
          | { error?: { message?: string } }
          | null;
        setFolderMessage(data?.error?.message ?? "폴더를 만들지 못했습니다.");
        return;
      }

      const data = (await response.json()) as {
        folder: DocumentFolder;
        folders: DocumentFolder[];
        currentFolders: DocumentFolder[];
      };
      setDocumentFolders(data.folders);
      setExpandedFolderIds((currentIds) => {
        const nextIds = new Set(currentIds);
        nextIds.add(documentCurrentFolderId);
        return nextIds;
      });
      setNewFolderName("");
      setNewFolderOpen(false);
      setFolderMessage(`${data.folder.name} 폴더를 만들었습니다.`);
    } catch {
      setFolderMessage("문서 폴더 서버에 연결할 수 없습니다.");
    }
  }

  function openRenameFolderDialog(folder: DocumentFolder) {
    setFolderContextMenu((menu) => ({ ...menu, open: false }));
    setRenamingFolder(folder);
    setRenameFolderName(folder.name);
    setRenameFolderMessage("");
  }

  function closeRenameFolderDialog() {
    if (renameFolderSubmitting) {
      return;
    }

    setRenamingFolder(null);
    setRenameFolderName("");
    setRenameFolderMessage("");
  }

  async function handleRenameFolder(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!renamingFolder) {
      return;
    }

    const trimmedFolderName = renameFolderName.trim();

    if (!trimmedFolderName) {
      setRenameFolderMessage("폴더명을 입력해 주세요.");
      return;
    }

    if (trimmedFolderName.length > 80) {
      setRenameFolderMessage("폴더명은 80자 이하로 입력해 주세요.");
      return;
    }

    const normalizedFolderName = trimmedFolderName.toLocaleLowerCase("ko-KR");
    const folderExists = documentFolders.some(
      (folder) =>
        folder.folderId !== renamingFolder.folderId &&
        folder.parentFolderId === renamingFolder.parentFolderId &&
        folder.name.toLocaleLowerCase("ko-KR") === normalizedFolderName
    );

    if (folderExists) {
      setRenameFolderMessage("이미 같은 이름의 폴더가 있습니다.");
      return;
    }

    setRenameFolderSubmitting(true);
    setRenameFolderMessage("");

    try {
      const response = await fetch(
        `/api/v1/document-folders/${encodeURIComponent(renamingFolder.folderId)}`,
        {
          body: JSON.stringify({ folderName: trimmedFolderName }),
          credentials: "include",
          headers: {
            "Content-Type": "application/json"
          },
          method: "PATCH"
        }
      );

      if (!response.ok) {
        const data = (await response.json().catch(() => null)) as
          | { error?: { message?: string } }
          | null;
        setRenameFolderMessage(
          data?.error?.message ?? "폴더명을 변경하지 못했습니다."
        );
        return;
      }

      const data = (await response.json()) as {
        folder: DocumentFolder;
        folders: DocumentFolder[];
      };
      setDocumentFolders(data.folders);
      setRenamingFolder(null);
      setRenameFolderName("");
      setRenameFolderMessage("");
      setFolderMessage(`${data.folder.name} 폴더명으로 변경했습니다.`);
    } catch {
      setRenameFolderMessage("문서 폴더 서버에 연결할 수 없습니다.");
    } finally {
      setRenameFolderSubmitting(false);
    }
  }

  function openDeleteFolderDialog(folder: DocumentFolder) {
    setFolderContextMenu((menu) => ({ ...menu, open: false }));

    if (
      isProtectedDocumentFolder(folder) ||
      containsProtectedDocumentFolder(documentFolders, folder.folderId)
    ) {
      setFolderMessage("작업일지 폴더는 삭제할 수 없습니다.");
      return;
    }

    setDeletingFolder(folder);
    setDeleteFolderMessage("");
  }

  function closeDeleteFolderDialog() {
    if (deleteFolderSubmitting) {
      return;
    }

    setDeletingFolder(null);
    setDeleteFolderMessage("");
  }

  async function handleDeleteFolder() {
    if (!deletingFolder) {
      return;
    }

    if (
      isProtectedDocumentFolder(deletingFolder) ||
      containsProtectedDocumentFolder(documentFolders, deletingFolder.folderId)
    ) {
      setDeleteFolderMessage("작업일지 폴더는 삭제할 수 없습니다.");
      return;
    }

    setDeleteFolderSubmitting(true);
    setDeleteFolderMessage("");

    const deletedFolderIds = getDocumentFolderDescendantIds(
      documentFolders,
      deletingFolder.folderId
    );
    const fallbackFolderId =
      deletingFolder.parentFolderId ??
      (documentFolders.some((folder) => folder.folderId === "folder-field-documents")
        ? "folder-field-documents"
        : "folder-my-pc");

    try {
      const response = await fetch(
        `/api/v1/document-folders/${encodeURIComponent(deletingFolder.folderId)}`,
        {
          credentials: "include",
          method: "DELETE"
        }
      );

      if (!response.ok) {
        const data = (await response.json().catch(() => null)) as
          | { error?: { message?: string } }
          | null;
        setDeleteFolderMessage(
          data?.error?.message ?? "폴더를 삭제하지 못했습니다."
        );
        return;
      }

      const data = (await response.json()) as {
        deletedFolderId: string;
        parentFolderId: string | null;
        folders: DocumentFolder[];
      };
      setDocumentFolders(data.folders);
      setDocumentCurrentFolderId((currentFolderId) =>
        deletedFolderIds.has(currentFolderId)
          ? data.folders.some(
              (folder) => folder.folderId === (data.parentFolderId ?? fallbackFolderId)
            )
            ? data.parentFolderId ?? fallbackFolderId
            : (data.folders[0]?.folderId ?? fallbackFolderId)
          : currentFolderId
      );
      setExpandedFolderIds((currentIds) => {
        const nextIds = new Set(currentIds);

        for (const deletedFolderId of deletedFolderIds) {
          nextIds.delete(deletedFolderId);
        }

        return nextIds;
      });
      setDeletingFolder(null);
      setDeleteFolderMessage("");
      setFolderMessage(`${deletingFolder.name} 폴더를 삭제했습니다.`);
    } catch {
      setDeleteFolderMessage("문서 폴더 서버에 연결할 수 없습니다.");
    } finally {
      setDeleteFolderSubmitting(false);
    }
  }

  function openNewDocumentDialog(documentType: "PDF" | "EXCEL" = "PDF") {
    if (newDocumentCreating) {
      return;
    }

    setDocumentContextMenu((menu) => ({ ...menu, open: false }));
    setFolderContextMenu((menu) => ({ ...menu, open: false }));
    setEditingDocument(null);
    setNewDocumentType(documentType);
    setNewDocumentOpen(true);
    setNewDocumentName("");
    setNewDocumentSummary("");
    setNewDocumentBody("");
    setNewSpreadsheetCells(createEmptySpreadsheetCells());
    setNewDocumentTags("");
    setNewDocumentChangeNote("");
    setNewDocumentMessage("");
  }

  function closeNewDocumentDialog() {
    if (newDocumentCreating) {
      return;
    }

    setNewDocumentOpen(false);
    setEditingDocument(null);
    setNewDocumentType("PDF");
    setNewDocumentName("");
    setNewDocumentSummary("");
    setNewDocumentBody("");
    setNewSpreadsheetCells(createEmptySpreadsheetCells());
    setNewDocumentTags("");
    setNewDocumentChangeNote("");
    setNewDocumentMessage("");
  }

  async function openEditDocumentDialog(document: DocumentItem) {
    if (newDocumentCreating || editDocumentLoadingId) {
      return;
    }

    setEditDocumentLoadingId(document.documentId);
    setNewDocumentMessage("");

    try {
      const response = await fetch(
        `/api/v1/document-files/${encodeURIComponent(document.documentId)}/editor`,
        {
          credentials: "include"
        }
      );

      if (!response.ok) {
        const data = (await response.json().catch(() => null)) as
          | { error?: { message?: string } }
          | null;
        setFolderMessage(data?.error?.message ?? "수정 가능한 원본을 불러오지 못했습니다.");
        return;
      }

      const data = (await response.json()) as { draft: DocumentEditorDraft };
      setEditingDocument(document);
      setNewDocumentType(data.draft.documentType);
      setNewDocumentOpen(true);
      setNewDocumentName(data.draft.fileName);
      setNewDocumentSummary(data.draft.summary);
      setNewDocumentBody(data.draft.body);
      setNewSpreadsheetCells(hydrateSpreadsheetCells(data.draft.spreadsheetCells));
      setNewDocumentTags(data.draft.tags);
      setNewDocumentChangeNote("");
      setNewDocumentMessage("");
    } catch {
      setFolderMessage("수정 가능한 원본을 불러오지 못했습니다.");
    } finally {
      setEditDocumentLoadingId("");
    }
  }

  async function handleCreateDocument(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const trimmedDocumentName = newDocumentName.trim();

    if (!trimmedDocumentName) {
      setNewDocumentMessage("파일명을 입력해 주세요.");
      return;
    }

    const isEditingDocument = Boolean(editingDocument);
    const trimmedChangeNote = newDocumentChangeNote.trim();

    if (isEditingDocument && !trimmedChangeNote) {
      setNewDocumentMessage("수정 사유를 입력해 주세요.");
      return;
    }

    setNewDocumentCreating(true);
    setNewDocumentMessage(
      `${newDocumentType === "EXCEL" ? "Excel" : "PDF"} 문서를 ${
        isEditingDocument ? "새 버전으로 저장하는 중입니다." : "만드는 중입니다."
      }`
    );
    setFolderMessage("");

    try {
      const normalizedFileName =
        newDocumentType === "EXCEL"
          ? /\.xlsx?$/i.test(trimmedDocumentName)
            ? trimmedDocumentName.replace(/\.xls$/i, ".xlsx")
            : `${trimmedDocumentName}.xlsx`
          : /\.pdf$/i.test(trimmedDocumentName)
            ? trimmedDocumentName
            : `${trimmedDocumentName}.pdf`;
      const pageImageDataUrl =
        newDocumentType === "PDF"
          ? await createA4DocumentPageImage(normalizedFileName, newDocumentBody)
          : "";
      const pdfPlainText = getPdfEditorPlainText(newDocumentBody);
      const documentSummary =
        newDocumentType === "EXCEL"
          ? `${normalizedFileName} Excel 문서입니다.`
          : (pdfPlainText.split("\n").find(Boolean)?.slice(0, 800) ??
            newDocumentSummary);
      const response = await fetch(
        isEditingDocument && editingDocument
          ? `/api/v1/document-files/${encodeURIComponent(
              editingDocument.documentId
            )}/editor`
          : "/api/v1/document-files/create",
        {
          body: JSON.stringify({
            fileName: trimmedDocumentName,
            documentType: newDocumentType,
            editorBody: newDocumentType === "PDF" ? newDocumentBody : "",
            folderId: documentCurrentFolderId,
            pageImageDataUrl,
            spreadsheetCells:
              newDocumentType === "EXCEL"
                ? serializeSpreadsheetCells(newSpreadsheetCells)
                : [],
            summary: documentSummary,
            changeNote: trimmedChangeNote,
            tags: newDocumentTags
          }),
          credentials: "include",
          headers: {
            "Content-Type": "application/json"
          },
          method: isEditingDocument ? "PUT" : "POST"
        }
      );

      if (!response.ok) {
        const data = (await response.json().catch(() => null)) as
          | { error?: { message?: string } }
          | null;
        setNewDocumentMessage(
          data?.error?.message ??
            (isEditingDocument
              ? "문서를 새 버전으로 저장하지 못했습니다."
              : "문서를 만들지 못했습니다.")
        );
        return;
      }

      const data = (await response.json()) as {
        document: DocumentItem;
        documents: DocumentItem[];
      };
      setDocumentItems(data.documents);
      setSelectedDocument(data.document);
      setSelectedDocumentVersion(data.document.version);
      setNewDocumentOpen(false);
      setEditingDocument(null);
      setNewDocumentType("PDF");
      setNewDocumentName("");
      setNewDocumentSummary("");
      setNewDocumentBody("");
      setNewSpreadsheetCells(createEmptySpreadsheetCells());
      setNewDocumentTags("");
      setNewDocumentChangeNote("");
      setNewDocumentMessage("");
      setDocumentUploadMessage(
        isEditingDocument
          ? `${data.document.name} ${data.document.version} 버전으로 저장했습니다.`
          : `${data.document.name} 문서를 만들었습니다.`
      );
      void loadNotifications();
    } catch {
      setNewDocumentMessage(
        isEditingDocument
          ? "문서 수정 서버에 연결할 수 없습니다."
          : "문서 생성 서버에 연결할 수 없습니다."
      );
    } finally {
      setNewDocumentCreating(false);
    }
  }

  function clearDocumentContextLongPress() {
    if (documentContextLongPressTimerRef.current) {
      window.clearTimeout(documentContextLongPressTimerRef.current);
      documentContextLongPressTimerRef.current = null;
    }

    documentContextPointerStartRef.current = null;
  }

  function clearFolderContextLongPress() {
    if (folderContextLongPressTimerRef.current) {
      window.clearTimeout(folderContextLongPressTimerRef.current);
      folderContextLongPressTimerRef.current = null;
    }

    folderContextPointerStartRef.current = null;
  }

  function openDocumentContextMenu(clientX: number, clientY: number) {
    if (!documentCanManage) {
      return;
    }

    const menuWidth = 190;
    const menuHeight = 96;
    setDocumentContextMenu({
      open: true,
      x: Math.min(clientX, Math.max(12, window.innerWidth - menuWidth)),
      y: Math.min(clientY, Math.max(12, window.innerHeight - menuHeight))
    });
    setFolderContextMenu((menu) => ({ ...menu, open: false }));
  }

  function openFolderContextMenu(
    folder: DocumentFolder,
    clientX: number,
    clientY: number
  ) {
    if (!documentCanManage) {
      return;
    }

    const menuWidth = 190;
    const menuHeight = 56;
    setFolderContextMenu({
      open: true,
      folder,
      x: Math.min(clientX, Math.max(12, window.innerWidth - menuWidth)),
      y: Math.min(clientY, Math.max(12, window.innerHeight - menuHeight))
    });
    setDocumentContextMenu((menu) => ({ ...menu, open: false }));
  }

  function handleDocumentContextMenu(event: ReactMouseEvent<HTMLDivElement>) {
    if (!documentCanManage) {
      return;
    }

    event.preventDefault();
    clearDocumentContextLongPress();
    openDocumentContextMenu(event.clientX, event.clientY);
  }

  function handleFolderContextMenu(
    event: ReactMouseEvent<HTMLButtonElement>,
    folder: DocumentFolder
  ) {
    if (!documentCanManage) {
      return;
    }

    event.preventDefault();
    event.stopPropagation();
    clearFolderContextLongPress();
    openFolderContextMenu(folder, event.clientX, event.clientY);
  }

  function handleFolderPointerDown(
    event: ReactPointerEvent<HTMLButtonElement>,
    folder: DocumentFolder
  ) {
    if (!documentCanManage || event.pointerType === "mouse") {
      return;
    }

    clearFolderContextLongPress();
    folderContextLongPressOpenedRef.current = false;
    folderContextPointerStartRef.current = {
      folderId: folder.folderId,
      x: event.clientX,
      y: event.clientY
    };
    folderContextLongPressTimerRef.current = window.setTimeout(() => {
      folderContextLongPressTimerRef.current = null;
      folderContextLongPressOpenedRef.current = true;
      openFolderContextMenu(folder, event.clientX, event.clientY);
    }, 650);
  }

  function handleFolderPointerMove(event: ReactPointerEvent<HTMLButtonElement>) {
    const startPoint = folderContextPointerStartRef.current;

    if (!startPoint) {
      return;
    }

    const movedDistance = Math.hypot(
      event.clientX - startPoint.x,
      event.clientY - startPoint.y
    );

    if (movedDistance > 10) {
      clearFolderContextLongPress();
    }
  }

  function handleFolderPointerUp() {
    clearFolderContextLongPress();
  }

  function handleDocumentFilesPointerDown(
    event: ReactPointerEvent<HTMLDivElement>
  ) {
    if (!documentCanManage || event.pointerType === "mouse") {
      return;
    }

    clearDocumentContextLongPress();
    documentContextPointerStartRef.current = {
      x: event.clientX,
      y: event.clientY
    };
    documentContextLongPressTimerRef.current = window.setTimeout(() => {
      documentContextLongPressTimerRef.current = null;
      openDocumentContextMenu(event.clientX, event.clientY);
    }, 650);
  }

  function handleDocumentFilesPointerMove(
    event: ReactPointerEvent<HTMLDivElement>
  ) {
    const startPoint = documentContextPointerStartRef.current;

    if (!startPoint) {
      return;
    }

    const movedDistance = Math.hypot(
      event.clientX - startPoint.x,
      event.clientY - startPoint.y
    );

    if (movedDistance > 10) {
      clearDocumentContextLongPress();
    }
  }

  function openDocumentUploadDialog(files: FileList | File[]) {
    const selectedFiles = Array.from(files).filter((file) => file.size > 0);

    if (selectedFiles.length === 0 || documentUploading) {
      return;
    }

    setPendingUploadFiles(selectedFiles);
    setDocumentUploadMessage("");
    setDocumentUploadTags("");
  }

  function closeDocumentUploadDialog() {
    if (documentUploading) {
      return;
    }

    setPendingUploadFiles([]);
    setDocumentUploadTags("");
    setDocumentUploadMessage("");
  }

  async function uploadDocumentFiles(files: File[]) {
    if (files.length === 0 || documentUploading) {
      return;
    }

    setDocumentUploading(true);
    setDocumentUploadMessage("파일을 업로드하는 중입니다.");
    setFolderMessage("");

    try {
      let uploadedCount = 0;

      for (const file of files) {
        const formData = new FormData();
        formData.append("folderId", documentCurrentFolderId);
        formData.append("file", file);
        formData.append("tags", documentUploadTags);

        const response = await fetch("/api/v1/document-files/upload", {
          body: formData,
          credentials: "include",
          method: "POST"
        });

        if (!response.ok) {
          const data = (await response.json().catch(() => null)) as {
            error?: { message?: string };
          } | null;
          throw new Error(data?.error?.message ?? "파일 업로드에 실패했습니다.");
        }

        const data = (await response.json()) as {
          document: DocumentItem;
          documents: DocumentItem[];
        };
        setDocumentItems(data.documents);
        uploadedCount += 1;
      }

      setDocumentUploadMessage(`${uploadedCount}개 파일을 업로드했습니다.`);
      void loadNotifications();
      setPendingUploadFiles([]);
      setDocumentUploadTags("");
    } catch (error) {
      setDocumentUploadMessage(
        error instanceof Error ? error.message : "파일 업로드에 실패했습니다."
      );
    } finally {
      setDocumentUploading(false);
      setDocumentDragOver(false);
    }
  }

  function handleDocumentDragOver(event: DragEvent<HTMLDivElement>) {
    if (!documentCanManage) {
      return;
    }

    event.preventDefault();
    setDocumentDragOver(true);
  }

  function handleDocumentDragLeave(event: DragEvent<HTMLDivElement>) {
    if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
      setDocumentDragOver(false);
    }
  }

  function handleDocumentDrop(event: DragEvent<HTMLDivElement>) {
    if (!documentCanManage) {
      return;
    }

    event.preventDefault();
    setDocumentDragOver(false);
    openDocumentUploadDialog(event.dataTransfer.files);
  }

  async function handleJournalSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (journalSubmitting) {
      return;
    }

    setJournalSubmitting(true);
    setJournalMessage("작업일지를 저장하는 중입니다.");

    try {
      const formData = new FormData();
      formData.append("memo", journalMemo);
      formData.append("isHandover", journalIsHandover ? "true" : "false");
      formData.append("handoverTo", journalHandoverTo);

      if (journalPhoto) {
        formData.append("photo", journalPhoto);
      }

      const response = await fetch("/api/v1/field-journal-entries", {
        body: formData,
        credentials: "include",
        method: "POST"
      });

      if (!response.ok) {
        const data = (await response.json().catch(() => null)) as
          | { error?: { message?: string } }
          | null;
        setJournalMessage(data?.error?.message ?? "작업일지를 저장하지 못했습니다.");
        return;
      }

      const data = (await response.json()) as {
        entries: FieldJournalEntry[];
        documents: DocumentItem[];
      };
      setJournalEntries(data.entries);
      setDocumentItems(data.documents);
      setJournalMemo("");
      setJournalPhoto(null);
      setJournalIsHandover(false);
      setJournalHandoverTo("");
      setJournalMessage("작업일지를 저장했습니다.");
      void loadNotifications();
    } catch {
      setJournalMessage("작업일지 서버에 연결할 수 없습니다.");
    } finally {
      setJournalSubmitting(false);
    }
  }

  async function handleHandoverRead(entry: FieldJournalEntry) {
    if (!entry.isHandover) {
      return;
    }

    setJournalMessage("");

    try {
      const response = await fetch(
        `/api/v1/field-journal-entries/${entry.journalId}/handover-read`,
        {
          credentials: "include",
          method: "POST"
        }
      );

      if (!response.ok) {
        const data = (await response.json().catch(() => null)) as
          | { error?: { message?: string } }
          | null;
        setJournalMessage(data?.error?.message ?? "인수인계 확인을 남기지 못했습니다.");
        return;
      }

      const data = (await response.json()) as { entries: FieldJournalEntry[] };
      setJournalEntries(data.entries);
      setJournalMessage("인수인계 확인 이력을 남겼습니다.");
      void loadNotifications();
    } catch {
      setJournalMessage("작업일지 서버에 연결할 수 없습니다.");
    }
  }

  async function handleJournalReplySubmit(entry: FieldJournalEntry) {
    const replyText = (journalReplyDrafts[entry.journalId] ?? "").trim();

    if (!replyText || journalReplySubmittingId) {
      return;
    }

    setJournalReplySubmittingId(entry.journalId);
    setJournalMessage("");

    try {
      const response = await fetch(
        `/api/v1/field-journal-entries/${entry.journalId}/replies`,
        {
          body: JSON.stringify({
            replyText,
            replyType: "COMMENT"
          }),
          credentials: "include",
          headers: {
            "Content-Type": "application/json"
          },
          method: "POST"
        }
      );

      if (!response.ok) {
        const data = (await response.json().catch(() => null)) as
          | { error?: { message?: string } }
          | null;
        setJournalMessage(data?.error?.message ?? "응답을 저장하지 못했습니다.");
        return;
      }

      const data = (await response.json()) as {
        entries: FieldJournalEntry[];
        documents: DocumentItem[];
      };
      setJournalEntries(data.entries);
      setDocumentItems(data.documents);
      setJournalReplyDrafts((drafts) => ({
        ...drafts,
        [entry.journalId]: ""
      }));
      setJournalMessage("응답을 저장하고 문서 버전을 올렸습니다.");
      void loadNotifications();
    } catch {
      setJournalMessage("작업일지 서버에 연결할 수 없습니다.");
    } finally {
      setJournalReplySubmittingId("");
    }
  }

  function openJournalDocument(entry: FieldJournalEntry) {
    const linkedDocument = documentById.get(entry.documentId);

    if (linkedDocument) {
      openDocument(linkedDocument);
    }
  }

  function openJournalPhoto(entry: FieldJournalEntry) {
    setSelectedJournalPhoto(entry);
    setJournalPhotoScale(1);
    setJournalPhotoOffset({ x: 0, y: 0 });
    setJournalPhotoDragging(false);
    journalPhotoScaleRef.current = 1;
    journalPhotoOffsetRef.current = { x: 0, y: 0 };
    journalPhotoPointersRef.current.clear();
  }

  function closeJournalPhoto() {
    setSelectedJournalPhoto(null);
    setJournalPhotoDragging(false);
    journalPhotoPointersRef.current.clear();
  }

  function moveJournalPhoto(deltaX: number, deltaY: number) {
    setJournalPhotoOffset((currentOffset) => ({
      x: currentOffset.x + deltaX,
      y: currentOffset.y + deltaY
    }));
    journalPhotoOffsetRef.current = {
      x: journalPhotoOffsetRef.current.x + deltaX,
      y: journalPhotoOffsetRef.current.y + deltaY
    };
  }

  function zoomJournalPhoto(delta: number) {
    setJournalPhotoScale((currentScale) => {
      const nextScale = Math.min(
        4,
        Math.max(0.5, Number((currentScale + delta).toFixed(2)))
      );
      journalPhotoScaleRef.current = nextScale;
      return nextScale;
    });
  }

  function resetJournalPhotoView() {
    setJournalPhotoScale(1);
    setJournalPhotoOffset({ x: 0, y: 0 });
    journalPhotoScaleRef.current = 1;
    journalPhotoOffsetRef.current = { x: 0, y: 0 };
  }

  function getJournalPhotoTouchMetrics() {
    const pointers = Array.from(journalPhotoPointersRef.current.values());
    const [firstPointer, secondPointer] = pointers;

    if (!firstPointer || !secondPointer) {
      return null;
    }

    const deltaX = secondPointer.x - firstPointer.x;
    const deltaY = secondPointer.y - firstPointer.y;

    return {
      centerX: (firstPointer.x + secondPointer.x) / 2,
      centerY: (firstPointer.y + secondPointer.y) / 2,
      distance: Math.hypot(deltaX, deltaY)
    };
  }

  function handleJournalPhotoPointerDown(
    event: ReactPointerEvent<HTMLDivElement>
  ) {
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    journalPhotoPointersRef.current.set(event.pointerId, {
      x: event.clientX,
      y: event.clientY
    });

    if (journalPhotoPointersRef.current.size >= 2) {
      const touchMetrics = getJournalPhotoTouchMetrics();

      if (touchMetrics) {
        journalPhotoPinchRef.current = {
          ...touchMetrics,
          offsetX: journalPhotoOffsetRef.current.x,
          offsetY: journalPhotoOffsetRef.current.y,
          scale: journalPhotoScaleRef.current
        };
      }
    } else {
      journalPhotoDragRef.current = {
        startX: event.clientX,
        startY: event.clientY,
        x: journalPhotoOffsetRef.current.x,
        y: journalPhotoOffsetRef.current.y
      };
    }

    setJournalPhotoDragging(true);
  }

  function handleJournalPhotoPointerMove(
    event: ReactPointerEvent<HTMLDivElement>
  ) {
    if (!journalPhotoPointersRef.current.has(event.pointerId)) {
      return;
    }

    journalPhotoPointersRef.current.set(event.pointerId, {
      x: event.clientX,
      y: event.clientY
    });

    if (journalPhotoPointersRef.current.size >= 2) {
      const touchMetrics = getJournalPhotoTouchMetrics();
      const pinchStart = journalPhotoPinchRef.current;

      if (touchMetrics && pinchStart.distance > 0) {
        const nextScale = Math.min(
          4,
          Math.max(
            0.5,
            Number(
              (pinchStart.scale * (touchMetrics.distance / pinchStart.distance)).toFixed(2)
            )
          )
        );
        const nextOffset = {
          x: pinchStart.offsetX + touchMetrics.centerX - pinchStart.centerX,
          y: pinchStart.offsetY + touchMetrics.centerY - pinchStart.centerY
        };

        journalPhotoScaleRef.current = nextScale;
        journalPhotoOffsetRef.current = nextOffset;
        setJournalPhotoScale(nextScale);
        setJournalPhotoOffset(nextOffset);
      }

      return;
    }

    if (!journalPhotoDragging) {
      return;
    }

    const dragState = journalPhotoDragRef.current;
    const nextOffset = {
      x: dragState.x + event.clientX - dragState.startX,
      y: dragState.y + event.clientY - dragState.startY
    };
    journalPhotoOffsetRef.current = nextOffset;
    setJournalPhotoOffset(nextOffset);
  }

  function handleJournalPhotoPointerUp(event: ReactPointerEvent<HTMLDivElement>) {
    event.currentTarget.releasePointerCapture(event.pointerId);
    journalPhotoPointersRef.current.delete(event.pointerId);

    if (journalPhotoPointersRef.current.size === 1) {
      const remainingPointer = Array.from(journalPhotoPointersRef.current.values())[0];
      journalPhotoDragRef.current = {
        startX: remainingPointer.x,
        startY: remainingPointer.y,
        x: journalPhotoOffsetRef.current.x,
        y: journalPhotoOffsetRef.current.y
      };
      setJournalPhotoDragging(true);
      return;
    }

    if (journalPhotoPointersRef.current.size === 0) {
      setJournalPhotoDragging(false);
    }
  }

  async function handleRoleChange(userId: string, roleId: Role) {
    setUserMessage("");

    const response = await fetch(`/api/v1/users/${userId}/role`, {
      body: JSON.stringify({ roleId }),
      credentials: "include",
      headers: {
        "Content-Type": "application/json"
      },
      method: "PATCH"
    });

    if (!response.ok) {
      const data = (await response.json().catch(() => null)) as
        | { error?: { message?: string } }
        | null;
      setUserMessage(data?.error?.message ?? "회원 등급을 변경하지 못했습니다.");
      return;
    }

    const data = (await response.json()) as { user: ManagedUser };
    setUsers((currentUsers) =>
      currentUsers.map((user) => (user.userId === userId ? data.user : user))
    );
    setUserMessage("회원 등급을 변경했습니다.");
  }

  async function handleSequenceSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const linkedDocument = resolveLinkedDocumentFormValue(sequenceForm);

    if (!linkedDocument) {
      setSequenceMessage("연결 문서는 자동완성 목록에서 선택해 주세요.");
      return;
    }

    setSequenceSubmitting(true);
    setSequenceMessage("");

    try {
      const response = await fetch("/api/v1/work-sequence/items", {
        body: JSON.stringify({
          title: sequenceForm.title,
          productCode: sequenceForm.productCode,
          assignedTeam: sequenceForm.assignedTeam,
          targetQuantity: sequenceForm.targetQuantity,
          linkedDocumentId: linkedDocument.linkedDocumentId,
          linkedDocumentName: linkedDocument.linkedDocumentName,
          memo: sequenceForm.memo,
          sequenceNo: sequenceForm.sequenceNo
        }),
        credentials: "include",
        headers: {
          "Content-Type": "application/json"
        },
        method: "POST"
      });

      if (!response.ok) {
        const data = (await response.json().catch(() => null)) as
          | { error?: { message?: string } }
          | null;
        setSequenceMessage(data?.error?.message ?? "작업을 입력하지 못했습니다.");
        return;
      }

      const data = (await response.json()) as { item: WorkSequenceItem };
      setSequenceItems((currentItems) =>
        orderSequenceItems([...currentItems, data.item])
      );
      setSequenceForm(emptySequenceForm);
      setSequenceFormOpen(false);
      setSequenceMessage("작업 순서에 입력했습니다.");
      void loadNotifications();
    } catch {
      setSequenceMessage("작업 순서 서버에 연결할 수 없습니다.");
    } finally {
      setSequenceSubmitting(false);
    }
  }

  async function handleSequenceEditSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!editingSequenceItem) {
      return;
    }

    const linkedDocument = resolveLinkedDocumentFormValue(editSequenceForm);

    if (!linkedDocument) {
      setSequenceMessage("연결 문서는 자동완성 목록에서 선택해 주세요.");
      return;
    }

    setEditSequenceSubmitting(true);
    setSequenceMessage("");

    try {
      const response = await fetch(
        `/api/v1/work-sequence/items/${editingSequenceItem.sequenceItemId}`,
        {
          body: JSON.stringify({
            title: editSequenceForm.title,
            productCode: editSequenceForm.productCode,
            assignedTeam: editSequenceForm.assignedTeam,
            targetQuantity: editSequenceForm.targetQuantity,
            linkedDocumentId: linkedDocument.linkedDocumentId,
            linkedDocumentName: linkedDocument.linkedDocumentName,
            memo: editSequenceForm.memo,
            sequenceNo: editSequenceForm.sequenceNo,
            status: editSequenceForm.status
          }),
          credentials: "include",
          headers: {
            "Content-Type": "application/json"
          },
          method: "PATCH"
        }
      );

      if (!response.ok) {
        const data = (await response.json().catch(() => null)) as
          | { error?: { message?: string } }
          | null;
        setSequenceMessage(data?.error?.message ?? "작업을 수정하지 못했습니다.");
        return;
      }

      const data = (await response.json()) as { item: WorkSequenceItem };
      setSequenceItems((currentItems) =>
        orderSequenceItems(
          currentItems
            .map((item) =>
              item.sequenceItemId === data.item.sequenceItemId ? data.item : item
            )
            .filter((item) => item.status !== "CANCELED")
        )
      );
      setEditingSequenceItem(null);
      setSequenceMessage("작업 순서를 수정했습니다.");
      void loadNotifications();
    } catch {
      setSequenceMessage("작업 순서 서버에 연결할 수 없습니다.");
    } finally {
      setEditSequenceSubmitting(false);
    }
  }

  function openSequenceEditor(item: WorkSequenceItem) {
    setEditingSequenceItem(item);
    setEditSequenceForm(toSequenceForm(item));
  }

  function openSequenceDocument(document: DocumentItem) {
    setSelectedSequenceDocument(document);
    setSequenceDocumentScale(1);
    setSequenceDocumentPageCommand(null);
    sequenceDocumentScaleRef.current = 1;
    sequenceDocumentPointersRef.current.clear();
  }

  function closeSequenceDocument() {
    setSelectedSequenceDocument(null);
    setSequenceDocumentScale(1);
    setSequenceDocumentPageCommand(null);
    sequenceDocumentScaleRef.current = 1;
    sequenceDocumentPointersRef.current.clear();
  }

  function zoomSequenceDocument(delta: number) {
    setSequenceDocumentScale((currentScale) => {
      const nextScale = Math.min(
        2.4,
        Math.max(0.65, Number((currentScale + delta).toFixed(2)))
      );
      sequenceDocumentScaleRef.current = nextScale;
      return nextScale;
    });
  }

  function resetSequenceDocumentView() {
    setSequenceDocumentScale(1);
    sequenceDocumentScaleRef.current = 1;
  }

  function turnSequenceDocumentPage(direction: PdfPageCommand["direction"]) {
    setSequenceDocumentPageCommand((currentCommand) => ({
      direction,
      id: (currentCommand?.id ?? 0) + 1
    }));
  }

  function getSequenceDocumentTouchDistance() {
    const pointers = Array.from(sequenceDocumentPointersRef.current.values());
    const [firstPointer, secondPointer] = pointers;

    if (!firstPointer || !secondPointer) {
      return 0;
    }

    return Math.hypot(
      secondPointer.x - firstPointer.x,
      secondPointer.y - firstPointer.y
    );
  }

  function handleSequenceDocumentPointerDown(
    event: ReactPointerEvent<HTMLDivElement>
  ) {
    const target = event.target as HTMLElement;

    if (target.closest("button, input, select, textarea, a")) {
      return;
    }

    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    sequenceDocumentPointersRef.current.set(event.pointerId, {
      x: event.clientX,
      y: event.clientY
    });

    if (sequenceDocumentPointersRef.current.size >= 2) {
      sequenceDocumentSwipeRef.current.pinching = true;
      sequenceDocumentPinchRef.current = {
        distance: getSequenceDocumentTouchDistance(),
        scale: sequenceDocumentScaleRef.current
      };
      return;
    }

    sequenceDocumentSwipeRef.current = {
      pinching: false,
      startTime: Date.now(),
      startX: event.clientX,
      startY: event.clientY
    };
  }

  function handleSequenceDocumentPointerMove(
    event: ReactPointerEvent<HTMLDivElement>
  ) {
    if (!sequenceDocumentPointersRef.current.has(event.pointerId)) {
      return;
    }

    sequenceDocumentPointersRef.current.set(event.pointerId, {
      x: event.clientX,
      y: event.clientY
    });

    if (sequenceDocumentPointersRef.current.size < 2) {
      return;
    }

    event.preventDefault();
    sequenceDocumentSwipeRef.current.pinching = true;
    const pinchStart = sequenceDocumentPinchRef.current;
    const currentDistance = getSequenceDocumentTouchDistance();

    if (pinchStart.distance <= 0 || currentDistance <= 0) {
      return;
    }

    const nextScale = Math.min(
      2.4,
      Math.max(
        0.65,
        Number((pinchStart.scale * (currentDistance / pinchStart.distance)).toFixed(2))
      )
    );
    sequenceDocumentScaleRef.current = nextScale;
    setSequenceDocumentScale(nextScale);
  }

  function handleSequenceDocumentPointerUp(
    event: ReactPointerEvent<HTMLDivElement>
  ) {
    const hadPointer = sequenceDocumentPointersRef.current.has(event.pointerId);
    const wasPinching = sequenceDocumentSwipeRef.current.pinching;
    const swipeStart = sequenceDocumentSwipeRef.current;

    if (hadPointer && !wasPinching && sequenceDocumentPointersRef.current.size === 1) {
      const deltaX = event.clientX - swipeStart.startX;
      const deltaY = event.clientY - swipeStart.startY;
      const elapsed = Date.now() - swipeStart.startTime;

      if (
        elapsed < 900 &&
        Math.abs(deltaX) > 70 &&
        Math.abs(deltaX) > Math.abs(deltaY) * 1.4
      ) {
        turnSequenceDocumentPage(deltaX < 0 ? "next" : "previous");
      }
    }

    try {
      event.currentTarget.releasePointerCapture(event.pointerId);
    } catch {
      // Ignore release errors from browsers that already released the pointer.
    }

    sequenceDocumentPointersRef.current.delete(event.pointerId);

    if (sequenceDocumentPointersRef.current.size >= 2) {
      sequenceDocumentPinchRef.current = {
        distance: getSequenceDocumentTouchDistance(),
        scale: sequenceDocumentScaleRef.current
      };
      sequenceDocumentSwipeRef.current.pinching = true;
      return;
    }

    if (sequenceDocumentPointersRef.current.size === 1) {
      const remainingPointer = Array.from(sequenceDocumentPointersRef.current.values())[0];
      sequenceDocumentSwipeRef.current = {
        pinching: false,
        startTime: Date.now(),
        startX: remainingPointer.x,
        startY: remainingPointer.y
      };
      return;
    }

    sequenceDocumentSwipeRef.current.pinching = false;
  }

  function handleSequenceDragStart(
    event: ReactPointerEvent<HTMLElement>,
    sequenceItemId: string
  ) {
    if (!sequenceCanEdit) {
      return;
    }

    const target = event.target as HTMLElement;

    if (target.closest("button, input, select, textarea, a")) {
      return;
    }

    event.preventDefault();
    dragStartSequenceIdsRef.current = sequenceItemsRef.current.map(
      (item) => item.sequenceItemId
    );
    setDraggingSequenceItemId(sequenceItemId);
    setDragOverSequenceItemId(sequenceItemId);
  }

  async function saveSequenceOrder(sequenceItemIds: string[]) {
    setSequenceMessage("");

    try {
      const response = await fetch("/api/v1/work-sequence/items/order", {
        body: JSON.stringify({ sequenceItemIds }),
        credentials: "include",
        headers: {
          "Content-Type": "application/json"
        },
        method: "PATCH"
      });

      if (!response.ok) {
        const data = (await response.json().catch(() => null)) as
          | { error?: { message?: string } }
          | null;
        setSequenceMessage(data?.error?.message ?? "작업 순서를 저장하지 못했습니다.");
        await loadSequenceItems();
        return;
      }

      const data = (await response.json()) as { items: WorkSequenceItem[] };
      setSequenceItems(orderSequenceItems(data.items));
      setSequenceMessage("작업 순서를 변경했습니다.");
      void loadNotifications();
    } catch {
      setSequenceMessage("작업 순서 서버에 연결할 수 없습니다.");
      await loadSequenceItems();
    }
  }

  function renderSequenceSection() {
    return (
      <section id="sequence" className="panel">
        <div className="panel-heading">
          <h2>작업 순서 TV</h2>
          <div className="heading-actions">
            <span className="live">실시간</span>
            {sessionUser && (sequenceCanEdit || canOpenSequenceForm) ? (
              <button
                className="secondary-button"
                onClick={() => {
                  setSequenceMessage("");
                  setSequenceFormOpen(true);
                }}
                type="button"
              >
                작업 입력
              </button>
            ) : null}
          </div>
        </div>

        {sequenceMessage ? <p className="notice">{sequenceMessage}</p> : null}

        <div className="sequence-list">
          {sequenceLoading ? <p className="empty-state">작업 순서를 불러오는 중입니다.</p> : null}
          {!sequenceLoading && sequenceItems.length === 0 ? (
            <p className="empty-state">입력된 작업 순서가 없습니다.</p>
          ) : null}
          {sequenceItems.map((item) => {
            const linkedDocument = findSequenceLinkedDocument(item);

            return (
              <article
                className={`sequence-card ${
                  draggingSequenceItemId === item.sequenceItemId ? "dragging" : ""
                } ${dragOverSequenceItemId === item.sequenceItemId ? "drag-over" : ""}`}
                data-sequence-id={item.sequenceItemId}
                key={item.sequenceItemId}
                onPointerDown={(event) =>
                  handleSequenceDragStart(event, item.sequenceItemId)
                }
              >
                <div>
                  <h3>{item.title}</h3>
                  <p>{item.detail ?? item.memo ?? "상세 정보 없음"}</p>
                  <div className="sequence-meta">
                    <span>{sequenceStatusLabels[item.status]}</span>
                    {item.createdBy ? <span>입력 {item.createdBy}</span> : null}
                  </div>
                </div>
                <div className="sequence-card-actions">
                  {sessionUser && linkedDocument ? (
                    <button
                      className="sequence-document-button"
                      onClick={() => openSequenceDocument(linkedDocument)}
                      type="button"
                    >
                      문서 보기
                    </button>
                  ) : null}
                  {sequenceCanEdit ? (
                    <button
                      className="sequence-edit-button"
                      onClick={() => openSequenceEditor(item)}
                      type="button"
                    >
                      수정
                    </button>
                  ) : null}
                </div>
              </article>
            );
          })}
        </div>
      </section>
    );
  }

  if (authChecking) {
    return (
      <main className="login-shell">
        <section className="login-panel">
          <p className="eyebrow">FlowNote 로컬 파일럿</p>
          <h1>세션 확인 중</h1>
        </section>
      </main>
    );
  }

  if (!sessionUser && activePage === "sequence") {
    return (
      <main className="app-shell page-sequence public-sequence-shell">
        <header className="topbar">
          <nav className="top-nav" aria-label="주요 메뉴">
            <a className="active" href="#sequence">
              작업 순서
            </a>
          </nav>
          <button
            className="secondary-button"
            onClick={() => setActivePage("dashboard")}
            type="button"
          >
            로그인
          </button>
        </header>
        <div className="app-body">
          <section className="workspace">{renderSequenceSection()}</section>
        </div>
      </main>
    );
  }

  if (!sessionUser) {
    return (
      <main className="login-shell">
        <section className="login-panel" aria-labelledby="login-title">
          <div>
            <p className="eyebrow">FlowNote 로컬 파일럿</p>
            <h1 id="login-title">로그인</h1>
            <p className="login-copy">
              현장 문서, 작업순서, 작업일지 화면은 로그인 후 사용할 수 있습니다.
            </p>
          </div>

          <form className="login-form" onSubmit={handleLogin}>
            <label>
              <span>아이디</span>
              <input
                autoComplete="username"
                onChange={(event) => setLoginId(event.target.value)}
                value={loginId}
              />
            </label>
            <label>
              <span>비밀번호</span>
              <input
                autoComplete="current-password"
                onChange={(event) => setPassword(event.target.value)}
                type="password"
                value={password}
              />
            </label>
            {loginError ? <p className="login-error">{loginError}</p> : null}
            <button disabled={submitting} type="submit">
              {submitting ? "로그인 중" : "로그인"}
            </button>
          </form>

          <div className="dev-account-box">
            <strong>개발용 계정</strong>
            <span>최고관리자: admin / 1234</span>
            <span>MES 사용자: mes / 1234</span>
            <span>POP 사용자: pop / 1234</span>
            <span>일반 사용자: user / 1234</span>
          </div>

          <div className="login-shortcut-box" aria-label="바로가기">
            <strong>바로가기</strong>
            <button
              disabled={submitting}
              onClick={() => setActivePage("sequence")}
              type="button"
            >
              작업 순서
            </button>
          </div>
        </section>
      </main>
    );
  }

  const selectedVersionLabel = selectedDocumentVersion || selectedDocument?.version || "";
  const selectedVersionItem = selectedDocument?.versions.find(
    (version) => version.version === selectedVersionLabel
  );
  const isViewingCurrentDocumentVersion =
    !selectedDocument ||
    selectedVersionLabel === selectedDocument.version ||
    selectedVersionItem?.status === "CURRENT";
  const viewerDocument =
    selectedDocument && selectedVersionLabel
      ? {
          ...selectedDocument,
          name: selectedVersionItem?.fileName ?? selectedDocument.name,
          version: selectedVersionLabel,
          contentUrl: getDocumentVersionContentUrl(
            selectedDocument.documentId,
            selectedVersionLabel
          )
        }
      : selectedDocument;

  return (
    <main className={`app-shell page-${activePage}`}>
      <header className="topbar">
        <nav className="top-nav" aria-label="주요 메뉴">
          <a
            className={activePage === "dashboard" ? "active" : ""}
            href="#dashboard"
            onClick={(event) => {
              event.preventDefault();
              setSelectedDocument(null);
              setActivePage("dashboard");
            }}
          >
            대시보드
          </a>
          <a
            className={activePage === "documents" || activePage === "document" ? "active" : ""}
            href="#documents"
            onClick={(event) => {
              event.preventDefault();
              setSelectedDocument(null);
              setActivePage("documents");
            }}
          >
            문서 탐색기
          </a>
          <a
            className={activePage === "sequence" ? "active" : ""}
            href="#sequence"
            onClick={(event) => {
              event.preventDefault();
              setActivePage("sequence");
            }}
          >
            작업 순서
          </a>
          <a
            className={activePage === "journal" ? "active" : ""}
            href="#journal"
            onClick={(event) => {
              event.preventDefault();
              setActivePage("journal");
            }}
          >
            작업일지
          </a>
          <a
            className={activePage === "notifications" ? "active" : ""}
            href="#notifications"
            onClick={(event) => {
              event.preventDefault();
              setActivePage("notifications");
            }}
          >
            알림{notificationUnreadCount > 0 ? ` ${notificationUnreadCount}` : ""}
          </a>
          {isSuperAdmin ? (
            <a
              className={activePage === "members" ? "active" : ""}
              href="#members"
              onClick={(event) => {
                event.preventDefault();
                setActivePage("members");
              }}
            >
              회원관리
            </a>
          ) : null}
          {isSuperAdmin ? (
            <a
              className={activePage === "history" ? "active" : ""}
              href="#history"
              onClick={(event) => {
                event.preventDefault();
                setActivePage("history");
              }}
            >
              시스템 이력
            </a>
          ) : null}
        </nav>
        <label className="top-search">
          <span className="sr-only">검색</span>
          <input
            onChange={(event) => setTopSearch(event.target.value)}
            placeholder="검색"
            value={topSearch}
          />
        </label>
        <div className="session-actions">
          <div className="user-chip">
            <span className="user-icon" aria-hidden="true" />
            <strong>{sessionUser.displayName}</strong>
            <small>{roleLabels[sessionUser.primaryRole]}</small>
          </div>
          <button className="logout-button" onClick={handleLogout} type="button">
            로그아웃
          </button>
        </div>
      </header>

      <div className="app-body">
        <section className="workspace">
        {activePage === "dashboard" ? (
          <section id="dashboard" className="dashboard-page">
            <div className="dashboard-heading">
              <div>
                <p className="eyebrow">FlowNote</p>
                <h2>현장 문서와 작업 흐름</h2>
              </div>
              <button
                className="secondary-button"
                onClick={() => setActivePage("documents")}
                type="button"
              >
                문서 탐색기 열기
              </button>
            </div>
            <div className="dashboard-grid">
              <button
                className="dashboard-tile"
                onClick={() => setActivePage("documents")}
                type="button"
              >
                <span>문서</span>
                <strong>{documentItems.length}</strong>
                <small>등록된 문서와 작업일지</small>
              </button>
              <button
                className="dashboard-tile"
                onClick={() => setActivePage("sequence")}
                type="button"
              >
                <span>작업 순서</span>
                <strong>{sequenceItems.length || "-"}</strong>
                <small>현장 표시용 순서</small>
              </button>
              <button
                className="dashboard-tile"
                onClick={() => setActivePage("journal")}
                type="button"
              >
                <span>작업일지</span>
                <strong>{journalEntries.length || "-"}</strong>
                <small>사진 또는 메모 기록</small>
              </button>
            </div>
            <section className="panel dashboard-recent">
              <div className="panel-heading">
                <h2>최근 문서</h2>
                <button
                  className="secondary-button"
                  onClick={() => setActivePage("documents")}
                  type="button"
                >
                  전체 보기
                </button>
              </div>
              <div className="dashboard-document-list">
                {documentItems.slice(0, 6).map((document) => (
                  <button
                    key={document.documentId}
                    onClick={() => openDocument(document)}
                    type="button"
                  >
                    <span>{document.type}</span>
                    <strong>{document.name}</strong>
                    <small>{document.meta}</small>
                  </button>
                ))}
              </div>
            </section>
          </section>
        ) : null}

        {activePage === "documents" ? (
            <section id="documents" className="document-explorer">
              <div className="explorer-commandbar">
                {documentCanManage ? (
                  <button
                    onClick={() => {
                      setFolderMessage("");
                      setNewFolderOpen((open) => !open);
                    }}
                    type="button"
                  >
                    새 폴더
                  </button>
                ) : null}
                {documentCanManage ? (
                  <label className="upload-file-button">
                    <input
                      accept=".pdf,.xls,.xlsx,.ppt,.pptx"
                      disabled={documentUploading}
                      multiple
                      onChange={(event) => {
                        if (event.target.files) {
                          openDocumentUploadDialog(event.target.files);
                          event.target.value = "";
                        }
                      }}
                      type="file"
                    />
                    파일 업로드
                  </label>
                ) : null}
                <button type="button">정렬</button>
                <button type="button">보기</button>
              </div>
                <div className="explorer-layout">
                  <aside className="explorer-tree">
                    {documentCanManage ? (
                      <div className="explorer-tree-actions">
                        <button
                          onClick={() => {
                            setFolderMessage("");
                            setNewFolderOpen((open) => !open);
                          }}
                        type="button"
                      >
                        + 폴더 만들기
                      </button>
                    </div>
                  ) : null}
                  {newFolderOpen ? (
                    <form className="new-folder-form" onSubmit={handleCreateFolder}>
                      <label>
                        <span>폴더명</span>
                        <input
                          autoFocus
                          onChange={(event) => setNewFolderName(event.target.value)}
                          placeholder="새 폴더 이름"
                          value={newFolderName}
                        />
                      </label>
                      <div>
                        <button type="submit">만들기</button>
                        <button
                          className="secondary-button"
                          onClick={() => {
                            setNewFolderOpen(false);
                            setNewFolderName("");
                          }}
                          type="button"
                        >
                          취소
                        </button>
                      </div>
                    </form>
                  ) : null}
                  {folderMessage ? (
                    <p className="folder-message">{folderMessage}</p>
                  ) : null}
                  {documentExplorerLoading ? (
                    <p className="folder-message">폴더를 불러오는 중입니다.</p>
                  ) : null}
                  {visibleDocumentFolderTree.map((folder) => {
                    const hasChildren = documentFolderChildCount.has(folder.folderId);
                    const isExpanded = expandedFolderIds.has(folder.folderId);

                    return (
                    <button
                      className={
                        folder.folderId === documentCurrentFolderId ? "active" : ""
                      }
                      key={folder.folderId}
                      onClick={(event) => {
                        if (folderContextLongPressOpenedRef.current) {
                          event.preventDefault();
                          folderContextLongPressOpenedRef.current = false;
                          return;
                        }

                        setDocumentCurrentFolderId(folder.folderId);
                        setFolderMessage("");
                        setNewFolderOpen(false);
                        setNewDocumentOpen(false);
                      }}
                      onContextMenu={(event) => handleFolderContextMenu(event, folder)}
                      onDoubleClick={() => {
                        if (hasChildren) {
                          toggleDocumentFolder(folder.folderId);
                        }
                      }}
                      onPointerCancel={handleFolderPointerUp}
                      onPointerDown={(event) => handleFolderPointerDown(event, folder)}
                      onPointerMove={handleFolderPointerMove}
                      onPointerUp={handleFolderPointerUp}
                      style={{ paddingLeft: `${0.5 + folder.depth * 1.1}rem` }}
                      type="button"
                    >
                      <span
                        aria-label={`${folder.name} ${
                          isExpanded ? "접기" : "펼치기"
                        }`}
                        className="tree-toggle"
                        onClick={(event) => {
                          event.stopPropagation();

                          if (hasChildren) {
                            toggleDocumentFolder(folder.folderId);
                          }
                        }}
                        role="button"
                        tabIndex={-1}
                      >
                        {hasChildren ? (isExpanded ? "▾" : "›") : ""}
                      </span>
                      <span className="tree-folder-name">{folder.name}</span>
                    </button>
                    );
                  })}
                </aside>
                <div
                  className={`explorer-files ${
                    documentDragOver ? "drag-over" : ""
                  }`}
                  onDragLeave={handleDocumentDragLeave}
                  onDragOver={handleDocumentDragOver}
                  onDrop={handleDocumentDrop}
                  onContextMenu={handleDocumentContextMenu}
                  onPointerCancel={clearDocumentContextLongPress}
                  onPointerDown={handleDocumentFilesPointerDown}
                  onPointerLeave={clearDocumentContextLongPress}
                  onPointerMove={handleDocumentFilesPointerMove}
                  onPointerUp={clearDocumentContextLongPress}
                  role="table"
                  aria-label="문서 탐색기"
                >
                  {documentUploadMessage ? (
                    <p className="upload-message">{documentUploadMessage}</p>
                  ) : null}
                  <div className="explorer-row explorer-head" role="row">
                    <span role="columnheader">이름</span>
                    <span role="columnheader">버전</span>
                    <span role="columnheader">수정한 날짜</span>
                    <span role="columnheader">유형</span>
                    <span role="columnheader">크기</span>
                  </div>
                  {filteredExplorerFolders.map((folder) => (
                    <button
                      className="explorer-row"
                      key={folder.folderId}
                      onClick={(event) => {
                        if (folderContextLongPressOpenedRef.current) {
                          event.preventDefault();
                          folderContextLongPressOpenedRef.current = false;
                          return;
                        }

                        setDocumentCurrentFolderId(folder.folderId);
                        setFolderMessage("");
                        setNewFolderOpen(false);
                        setNewDocumentOpen(false);
                      }}
                      onContextMenu={(event) => handleFolderContextMenu(event, folder)}
                      onPointerCancel={handleFolderPointerUp}
                      onPointerDown={(event) => handleFolderPointerDown(event, folder)}
                      onPointerMove={handleFolderPointerMove}
                      onPointerUp={handleFolderPointerUp}
                      role="row"
                      type="button"
                    >
                      <span role="cell">📁 {folder.name}</span>
                      <span role="cell">-</span>
                      <span role="cell">{formatExplorerDate(folder.updatedAt)}</span>
                      <span role="cell">Folder</span>
                      <span role="cell" />
                    </button>
                  ))}
                  {filteredDocuments.map((document) => (
                    <button
                      className="explorer-row"
                      key={document.documentId}
                      onClick={() => openDocument(document)}
                      role="row"
                      type="button"
                    >
                      <span className="document-name-cell" role="cell">
                        <span>📄 {document.name}</span>
                        {document.tags.length > 0 ? (
                          <span className="document-row-tags">
                            {document.tags.map((tagName) => (
                              <span key={`${document.documentId}-${tagName}`}>
                                {tagName}
                              </span>
                            ))}
                          </span>
                        ) : null}
                      </span>
                      <span role="cell">{document.version}</span>
                      <span role="cell">{document.publishedAt}</span>
                      <span role="cell">{document.type}</span>
                      <span role="cell">{getDocumentSizeLabel(document)}</span>
                    </button>
                  ))}
                  {filteredExplorerFolders.length === 0 &&
                  filteredDocuments.length === 0 ? (
                    <p className="explorer-empty">
                      {normalizedTopSearch
                        ? "검색 결과가 없습니다."
                        : "이 폴더에는 항목이 없습니다."}
                    </p>
                  ) : null}
                </div>
              </div>
            </section>
        ) : null}

        {activePage === "journal" ? (
            <section id="journal" className="panel journal-page">
              <div className="panel-heading">
                <div>
                  <h2>현장 작업일지</h2>
                  <p>사진이나 짧은 메모를 작업일지 카테고리에 바로 남깁니다.</p>
                </div>
                <button
                  className="secondary-button"
                  onClick={() => {
                    setDocumentCurrentFolderId("folder-my-pc-journal");
                    setActivePage("documents");
                  }}
                  type="button"
                >
                  작업일지 폴더
                </button>
              </div>

              {journalMessage ? <p className="notice">{journalMessage}</p> : null}

              <form className="journal-form" onSubmit={handleJournalSubmit}>
                <label className="journal-handover-toggle">
                  <input
                    checked={journalIsHandover}
                    disabled={journalSubmitting}
                    onChange={(event) => setJournalIsHandover(event.target.checked)}
                    type="checkbox"
                  />
                  <span>인수인계로 남기기</span>
                </label>
                {journalIsHandover ? (
                  <label className="journal-handover-target">
                    <span>전달 대상</span>
                    <input
                      disabled={journalSubmitting}
                      onChange={(event) => setJournalHandoverTo(event.target.value)}
                      placeholder="예: 야간조, 생산 2조, 설비 담당"
                      value={journalHandoverTo}
                    />
                  </label>
                ) : null}
                <label className="journal-photo-picker">
                  <span>사진</span>
                  <input
                    accept="image/*"
                    disabled={journalSubmitting}
                    onChange={(event) =>
                      setJournalPhoto(event.target.files?.[0] ?? null)
                    }
                    type="file"
                  />
                  <strong>
                    {journalPhoto ? journalPhoto.name : "사진 선택"}
                  </strong>
                </label>
                <label>
                  <span>메모</span>
                  <textarea
                    disabled={journalSubmitting}
                    onChange={(event) => setJournalMemo(event.target.value)}
                    placeholder="현장 상황, 조치 내용, 전달 사항"
                    rows={5}
                    value={journalMemo}
                  />
                </label>
                <div className="journal-form-actions">
                  <button
                    className="secondary-button"
                    disabled={journalSubmitting || (!journalMemo && !journalPhoto)}
                    onClick={() => {
                      setJournalMemo("");
                      setJournalPhoto(null);
                      setJournalIsHandover(false);
                      setJournalHandoverTo("");
                    }}
                    type="button"
                  >
                    지우기
                  </button>
                  <button disabled={journalSubmitting} type="submit">
                    {journalSubmitting ? "저장 중" : "저장"}
                  </button>
                </div>
              </form>

              <section className="journal-entry-section">
                <div className="panel-heading">
                  <h3>최근 작업일지</h3>
                  <button
                    className="secondary-button"
                    onClick={loadFieldJournalEntries}
                    type="button"
                  >
                    새로고침
                  </button>
                </div>
                {journalLoading ? (
                  <p className="empty-state">작업일지를 불러오는 중입니다.</p>
                ) : null}
                {!journalLoading && journalEntries.length === 0 ? (
                  <p className="empty-state">저장된 작업일지가 없습니다.</p>
                ) : null}
                <div className="journal-entry-list">
                  {journalEntries.map((entry) => (
                    <article className="journal-entry" key={entry.journalId}>
                      {entry.photoUrl ? (
                        <button
                          className="journal-photo-thumb"
                          onClick={() => openJournalPhoto(entry)}
                          type="button"
                        >
                          <img
                            alt={entry.photoFileName ?? "작업일지 사진"}
                            src={entry.photoUrl}
                          />
                        </button>
                      ) : (
                        <div className="journal-entry-placeholder">메모</div>
                      )}
                      <div>
                        <div className="journal-entry-tags">
                          {entry.isHandover ? (
                            <span className="handover-badge">인수인계</span>
                          ) : null}
                          {entry.isHandover ? (
                            <span>
                              {handoverStatusLabels[entry.handoverStatus] ??
                                entry.handoverStatus}
                            </span>
                          ) : null}
                          {entry.handoverTo ? <span>{entry.handoverTo}</span> : null}
                        </div>
                        <p>{entry.memo || "메모 없음"}</p>
                        {entry.readBy.length > 0 ? (
                          <div className="handover-read-list">
                            <strong>확인 이력 {entry.readBy.length}건</strong>
                            {entry.readBy.map((read) => (
                              <span
                                key={`${entry.journalId}-${read.readId}`}
                              >
                                확인 {read.displayName} / {formatExplorerDate(read.readAt)}
                              </span>
                            ))}
                          </div>
                        ) : entry.isHandover ? (
                          <div className="handover-read-list pending">
                            <span>아직 확인 이력이 없습니다.</span>
                          </div>
                        ) : null}
                        {entry.replies.length > 0 ? (
                          <div className="journal-reply-list">
                            {entry.replies.map((reply) => (
                              <article key={reply.replyId}>
                                <strong>
                                  {journalReplyTypeLabels[reply.type] ?? reply.type}
                                  {reply.version ? ` ${reply.version}` : ""}
                                </strong>
                                <p>{reply.text}</p>
                                <small>
                                  {reply.createdBy} / {formatExplorerDate(reply.createdAt)}
                                </small>
                              </article>
                            ))}
                          </div>
                        ) : null}
                        <div className="journal-reply-form">
                          <textarea
                            onChange={(event) =>
                              setJournalReplyDrafts((drafts) => ({
                                ...drafts,
                                [entry.journalId]: event.target.value
                              }))
                            }
                            placeholder="댓글 또는 응답"
                            rows={2}
                            value={journalReplyDrafts[entry.journalId] ?? ""}
                          />
                          <button
                            className="secondary-button"
                            disabled={
                              journalReplySubmittingId === entry.journalId ||
                              !(journalReplyDrafts[entry.journalId] ?? "").trim()
                            }
                            onClick={() => void handleJournalReplySubmit(entry)}
                            type="button"
                          >
                            응답 저장
                          </button>
                        </div>
                        <small>
                          {entry.createdBy} / {formatExplorerDate(entry.createdAt)}
                        </small>
                      </div>
                      <div className="journal-entry-actions">
                        {entry.isHandover ? (
                          <button
                            onClick={() => void handleHandoverRead(entry)}
                            type="button"
                          >
                            읽음 기록
                          </button>
                        ) : null}
                        <button
                          className="secondary-button"
                          disabled={!documentById.has(entry.documentId)}
                          onClick={() => openJournalDocument(entry)}
                          type="button"
                        >
                          문서 열기
                        </button>
                      </div>
                    </article>
                  ))}
                </div>
              </section>
            </section>
        ) : null}

        {selectedDocument && viewerDocument ? (
          <div
            className="modal-backdrop document-viewer-backdrop"
            onClick={(event) => {
              if (event.target === event.currentTarget) {
                closeDocumentViewer();
              }
            }}
          >
            <section
              aria-label={`${viewerDocument.name} 문서 뷰어`}
              aria-modal="true"
              className="document-viewer-modal"
              role="dialog"
            >
            <div className="document-detail-layout">
              <section className="document-viewer-panel" aria-label="문서 뷰어">
                <div className="viewer-toolbar">
                  <button
                    className="viewer-back-button"
                    onClick={closeDocumentViewer}
                    type="button"
                  >
                    닫기
                  </button>
                  {documentCanManage &&
                  selectedDocument.canEdit &&
                  isViewingCurrentDocumentVersion ? (
                    <button
                      className="viewer-back-button"
                      disabled={editDocumentLoadingId === selectedDocument.documentId}
                      onClick={() => void openEditDocumentDialog(selectedDocument)}
                      type="button"
                    >
                      {editDocumentLoadingId === selectedDocument.documentId
                        ? "불러오는 중"
                        : "수정"}
                    </button>
                  ) : null}
                  <strong>{viewerDocument.name}</strong>
                  <span>{viewerDocument.type}</span>
                  <span>{viewerDocument.version}</span>
                  <span>{getDocumentSizeLabel(viewerDocument)}</span>
                </div>
                <PdfDocumentViewer documentItem={viewerDocument} />
              </section>

              <aside className="document-side-panel">
                <section>
                  <h3>문서 정보</h3>
                  <dl className="document-meta-list">
                    <div>
                      <dt>버전</dt>
                      <dd>{viewerDocument.version}</dd>
                    </div>
                    <div>
                      <dt>등록자</dt>
                      <dd>{selectedDocument.owner}</dd>
                    </div>
                    <div>
                      <dt>공개일</dt>
                      <dd>{selectedDocument.publishedAt}</dd>
                    </div>
                    <div>
                      <dt>보안</dt>
                      <dd>{selectedDocument.securityLevel}</dd>
                    </div>
                  </dl>
                </section>

                <section>
                  <h3>태그</h3>
                  {selectedDocument.tags.length > 0 ? (
                    <div className="document-tag-list">
                      {selectedDocument.tags.map((tagName) => (
                        <span key={`${selectedDocument.documentId}-${tagName}`}>
                          {tagName}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <p className="empty-note">등록된 태그가 없습니다.</p>
                  )}
                </section>

                <section>
                  <h3>버전 이력</h3>
                  <div className="document-version-list">
                    {selectedDocument.versions.map((version) => (
                      <button
                        className={`document-version-item ${
                          version.status === "CURRENT" ? "current" : ""
                        } ${
                          version.version === selectedVersionLabel ? "viewing" : ""
                        }`}
                        key={`${selectedDocument.documentId}-${version.version}`}
                        onClick={() => setSelectedDocumentVersion(version.version)}
                        type="button"
                      >
                        <div className="document-version-heading">
                          <strong>{version.version}</strong>
                          {version.status === "CURRENT" ? (
                            <span className="version-current">현재</span>
                          ) : null}
                          {version.version === selectedVersionLabel ? (
                            <span className="version-viewing">열람 중</span>
                          ) : null}
                        </div>
                        <p>{version.changeNote}</p>
                        <small>
                          {version.owner} · {version.publishedAt}
                        </small>
                        <span className="version-file-name">{version.fileName}</span>
                      </button>
                    ))}
                  </div>
                </section>

                <section>
                  <h3>열람 이력</h3>
                  <ul className="document-history">
                    {selectedDocument.history.map((history) => (
                      <li key={history}>{history}</li>
                    ))}
                  </ul>
                </section>
              </aside>
            </div>
          </section>
          </div>
        ) : null}

        {activePage === "notifications" ? (
          <section id="notifications" className="panel notification-page">
            <div className="panel-heading">
              <h2>알림</h2>
              <button
                className="secondary-button"
                onClick={loadNotifications}
                type="button"
              >
                새로고침
              </button>
            </div>
            {notificationMessage ? (
              <p className="notice">{notificationMessage}</p>
            ) : null}
            {notificationLoading ? (
              <p className="empty-state">알림을 불러오는 중입니다.</p>
            ) : null}
            {!notificationLoading && notifications.length === 0 ? (
              <p className="empty-state">받은 알림이 없습니다.</p>
            ) : null}
            <div className="notification-list">
              {notifications.map((notification) => (
                <button
                  className={`notification-item ${
                    notification.readAt ? "" : "unread"
                  }`}
                  key={notification.notificationId}
                  onClick={() => void openNotification(notification)}
                  type="button"
                >
                  <span>{notificationSourceLabels[notification.sourceType]}</span>
                  <div>
                    <strong>{notification.title}</strong>
                    <p>{notification.message}</p>
                    <small>
                      {notification.actorName ?? "시스템"} /{" "}
                      {formatExplorerDate(notification.createdAt)}
                    </small>
                  </div>
                </button>
              ))}
            </div>
          </section>
        ) : null}

        {activePage === "sequence" ? renderSequenceSection() : null}

        {activePage === "members" && isSuperAdmin ? (
          <section id="members" className="panel">
            <div className="panel-heading">
              <h2>회원관리</h2>
              <span className="live">최고관리자</span>
            </div>
            {userMessage ? <p className="notice">{userMessage}</p> : null}
            <div className="member-table" role="table" aria-label="회원관리">
              <div className="member-row member-head" role="row">
                <span role="columnheader">이름</span>
                <span role="columnheader">아이디</span>
                <span role="columnheader">상태</span>
                <span role="columnheader">등급</span>
              </div>
              {users.map((user) => (
                <div className="member-row" key={user.userId} role="row">
                  <span role="cell">{user.displayName}</span>
                  <span role="cell">{user.loginId}</span>
                  <span role="cell">{user.status}</span>
                  <label role="cell">
                    <span className="sr-only">{user.displayName} 등급</span>
                    <select
                      onChange={(event) =>
                        handleRoleChange(user.userId, event.target.value as Role)
                      }
                      value={user.roleId}
                    >
                      {availableRoles.map((role) => (
                        <option key={role.roleId} value={role.roleId}>
                          {role.label}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
              ))}
            </div>
          </section>
        ) : null}

        {activePage === "history" && isSuperAdmin ? (
          <section id="history" className="panel">
            <div className="panel-heading">
              <h2>시스템 이력</h2>
              <div className="heading-actions">
                <span className="live">관리자</span>
                <button
                  className="secondary-button"
                  onClick={loadSystemHistory}
                  type="button"
                >
                  새로고침
                </button>
              </div>
            </div>
            {historyMessage ? <p className="notice">{historyMessage}</p> : null}
            {historyLoading ? (
              <p className="empty-state">시스템 이력을 불러오는 중입니다.</p>
            ) : null}
            {!historyLoading && historyItems.length === 0 ? (
              <p className="empty-state">저장된 시스템 이력이 없습니다.</p>
            ) : null}
            <div className="history-list">
              {historyItems.map((history) => (
                <article className="history-item" key={history.historyId}>
                  <span className="history-type">
                    {historyEventLabels[history.eventType] ?? history.eventType}
                  </span>
                  <div>
                    <h3>{history.message}</h3>
                    <p>
                      {history.actorName} /{" "}
                      {new Date(history.createdAt).toLocaleString("ko-KR")}
                    </p>
                  </div>
                </article>
              ))}
            </div>
          </section>
        ) : null}
      </section>
      </div>

      {selectedSequenceDocument ? (
        <div
          className="modal-backdrop sequence-document-backdrop"
          onMouseDown={closeSequenceDocument}
          role="presentation"
        >
          <section
            aria-label="작업순서 연결 문서"
            aria-modal="true"
            className="sequence-document-modal"
            onMouseDown={(event) => event.stopPropagation()}
            role="dialog"
          >
            <div className="sequence-document-modal-toolbar">
              <div>
                <strong>{selectedSequenceDocument.name}</strong>
                <span>
                  {selectedSequenceDocument.type} / {selectedSequenceDocument.version} /{" "}
                  {Math.round(sequenceDocumentScale * 100)}%
                </span>
              </div>
              <div className="sequence-document-modal-actions">
                <button onClick={() => zoomSequenceDocument(-0.15)} type="button">
                  축소
                </button>
                <button onClick={() => zoomSequenceDocument(0.15)} type="button">
                  확대
                </button>
                <button onClick={resetSequenceDocumentView} type="button">
                  초기화
                </button>
                <button onClick={closeSequenceDocument} type="button">
                  닫기
                </button>
              </div>
            </div>
            <div
              className="sequence-document-modal-body"
              onPointerCancel={handleSequenceDocumentPointerUp}
              onPointerDown={handleSequenceDocumentPointerDown}
              onPointerMove={handleSequenceDocumentPointerMove}
              onPointerUp={handleSequenceDocumentPointerUp}
            >
              <div
                className="sequence-document-modal-content"
                style={{ transform: `scale(${sequenceDocumentScale})` }}
              >
                <PdfDocumentViewer
                  documentItem={selectedSequenceDocument}
                  pageCommand={sequenceDocumentPageCommand}
                />
              </div>
            </div>
          </section>
        </div>
      ) : null}

      {selectedJournalPhoto?.photoUrl ? (
        <div
          className="modal-backdrop photo-viewer-backdrop"
          onMouseDown={closeJournalPhoto}
          role="presentation"
        >
          <section
            aria-label="작업일지 사진"
            aria-modal="true"
            className="photo-viewer-modal"
            onMouseDown={(event) => event.stopPropagation()}
            role="dialog"
          >
            <div className="photo-viewer-toolbar">
              <div>
                <strong>{selectedJournalPhoto.photoFileName ?? "작업일지 사진"}</strong>
                <span>{Math.round(journalPhotoScale * 100)}%</span>
              </div>
              <div className="photo-viewer-actions">
                <button onClick={() => zoomJournalPhoto(-0.2)} type="button">
                  축소
                </button>
                <button onClick={() => zoomJournalPhoto(0.2)} type="button">
                  확대
                </button>
                <button onClick={() => moveJournalPhoto(-80, 0)} type="button">
                  왼쪽
                </button>
                <button onClick={() => moveJournalPhoto(80, 0)} type="button">
                  오른쪽
                </button>
                <button onClick={resetJournalPhotoView} type="button">
                  초기화
                </button>
                <button onClick={closeJournalPhoto} type="button">
                  닫기
                </button>
              </div>
            </div>
            <div
              className={`photo-viewer-stage ${
                journalPhotoDragging ? "dragging" : ""
              }`}
              onPointerCancel={handleJournalPhotoPointerUp}
              onPointerDown={handleJournalPhotoPointerDown}
              onPointerMove={handleJournalPhotoPointerMove}
              onPointerUp={handleJournalPhotoPointerUp}
            >
              <img
                alt={selectedJournalPhoto.photoFileName ?? "작업일지 사진"}
                draggable={false}
                src={selectedJournalPhoto.photoUrl}
                style={{
                  transform: `translate(${journalPhotoOffset.x}px, ${journalPhotoOffset.y}px) scale(${journalPhotoScale})`
                }}
              />
            </div>
          </section>
        </div>
      ) : null}

      {sequenceFormOpen ? (
        <div
          className="modal-backdrop"
          onMouseDown={() => {
            if (!sequenceSubmitting) {
              setSequenceFormOpen(false);
            }
          }}
          role="presentation"
        >
          <section
            aria-labelledby="sequence-create-title"
            aria-modal="true"
            className="modal-panel"
            onMouseDown={(event) => event.stopPropagation()}
            role="dialog"
          >
            <div className="modal-heading">
              <h2 id="sequence-create-title">작업 입력</h2>
              <button
                className="icon-button"
                disabled={sequenceSubmitting}
                onClick={() => setSequenceFormOpen(false)}
                type="button"
              >
                ×
              </button>
            </div>

            <form className="sequence-form modal-form" onSubmit={handleSequenceSubmit}>
              <label className="span-2">
                <span>작업명</span>
                <input
                  onChange={(event) =>
                    setSequenceForm((form) => ({
                      ...form,
                      title: event.target.value
                    }))
                  }
                  placeholder="예: A 제품 긴급 가공 생산"
                  required
                  value={sequenceForm.title}
                />
              </label>
              <label>
                <span>품번</span>
                <input
                  onChange={(event) =>
                    setSequenceForm((form) => ({
                      ...form,
                      productCode: event.target.value
                    }))
                  }
                  placeholder="A-102"
                  value={sequenceForm.productCode}
                />
              </label>
              <label>
                <span>담당</span>
                <input
                  onChange={(event) =>
                    setSequenceForm((form) => ({
                      ...form,
                      assignedTeam: event.target.value
                    }))
                  }
                  placeholder="생산 1조"
                  value={sequenceForm.assignedTeam}
                />
              </label>
              <label>
                <span>목표 수량</span>
                <input
                  min="0"
                  onChange={(event) =>
                    setSequenceForm((form) => ({
                      ...form,
                      targetQuantity: event.target.value
                    }))
                  }
                  placeholder="500"
                  type="number"
                  value={sequenceForm.targetQuantity}
                />
              </label>
              <label>
                <span>표시 순서</span>
                <input
                  min="1"
                  onChange={(event) =>
                    setSequenceForm((form) => ({
                      ...form,
                      sequenceNo: event.target.value
                    }))
                  }
                  placeholder="자동"
                  type="number"
                  value={sequenceForm.sequenceNo}
                />
              </label>
              <label>
                <span>상태</span>
                <select
                  onChange={(event) =>
                    setSequenceForm((form) => ({
                      ...form,
                      status: event.target.value as WorkSequenceItem["status"]
                    }))
                  }
                  value={sequenceForm.status}
                >
                  {Object.entries(sequenceStatusLabels).map(([statusId, label]) => (
                    <option key={statusId} value={statusId}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              {renderLinkedDocumentAutocomplete(sequenceForm, "create")}
              <label className="span-2">
                <span>메모</span>
                <textarea
                  onChange={(event) =>
                    setSequenceForm((form) => ({
                      ...form,
                      memo: event.target.value
                    }))
                  }
                  placeholder="사무실 확인 사항"
                  rows={3}
                  value={sequenceForm.memo}
                />
              </label>
              {sequenceMessage ? (
                <p className="notice span-2">{sequenceMessage}</p>
              ) : null}
              <div className="sequence-form-actions span-2">
                <button
                  className="secondary-button"
                  disabled={sequenceSubmitting}
                  onClick={() => setSequenceFormOpen(false)}
                  type="button"
                >
                  취소
                </button>
                <button disabled={sequenceSubmitting} type="submit">
                  {sequenceSubmitting ? "저장 중" : "저장"}
                </button>
              </div>
            </form>
          </section>
        </div>
      ) : null}

      {editingSequenceItem ? (
        <div
          className="modal-backdrop"
          onMouseDown={() => setEditingSequenceItem(null)}
          role="presentation"
        >
          <section
            aria-labelledby="sequence-edit-title"
            aria-modal="true"
            className="modal-panel"
            onMouseDown={(event) => event.stopPropagation()}
            role="dialog"
          >
            <div className="modal-heading">
              <h2 id="sequence-edit-title">작업 순서 수정</h2>
              <button
                className="icon-button"
                onClick={() => setEditingSequenceItem(null)}
                type="button"
              >
                ×
              </button>
            </div>

            <form className="sequence-form modal-form" onSubmit={handleSequenceEditSubmit}>
              <label className="span-2">
                <span>작업명</span>
                <input
                  onChange={(event) =>
                    setEditSequenceForm((form) => ({
                      ...form,
                      title: event.target.value
                    }))
                  }
                  required
                  value={editSequenceForm.title}
                />
              </label>
              <label>
                <span>품번</span>
                <input
                  onChange={(event) =>
                    setEditSequenceForm((form) => ({
                      ...form,
                      productCode: event.target.value
                    }))
                  }
                  value={editSequenceForm.productCode}
                />
              </label>
              <label>
                <span>담당</span>
                <input
                  onChange={(event) =>
                    setEditSequenceForm((form) => ({
                      ...form,
                      assignedTeam: event.target.value
                    }))
                  }
                  value={editSequenceForm.assignedTeam}
                />
              </label>
              <label>
                <span>목표 수량</span>
                <input
                  min="0"
                  onChange={(event) =>
                    setEditSequenceForm((form) => ({
                      ...form,
                      targetQuantity: event.target.value
                    }))
                  }
                  type="number"
                  value={editSequenceForm.targetQuantity}
                />
              </label>
              <label>
                <span>표시 순서</span>
                <input
                  min="1"
                  onChange={(event) =>
                    setEditSequenceForm((form) => ({
                      ...form,
                      sequenceNo: event.target.value
                    }))
                  }
                  required
                  type="number"
                  value={editSequenceForm.sequenceNo}
                />
              </label>
              <label>
                <span>상태</span>
                <select
                  onChange={(event) =>
                    setEditSequenceForm((form) => ({
                      ...form,
                      status: event.target.value as WorkSequenceItem["status"]
                    }))
                  }
                  value={editSequenceForm.status}
                >
                  {Object.entries(sequenceStatusLabels).map(([statusId, label]) => (
                    <option key={statusId} value={statusId}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              {renderLinkedDocumentAutocomplete(editSequenceForm, "edit")}
              <label className="span-2">
                <span>메모</span>
                <textarea
                  onChange={(event) =>
                    setEditSequenceForm((form) => ({
                      ...form,
                      memo: event.target.value
                    }))
                  }
                  rows={3}
                  value={editSequenceForm.memo}
                />
              </label>
              <div className="sequence-form-actions span-2">
                <button
                  className="secondary-button"
                  onClick={() => setEditingSequenceItem(null)}
                  type="button"
                >
                  취소
                </button>
                <button disabled={editSequenceSubmitting} type="submit">
                  {editSequenceSubmitting ? "저장 중" : "저장"}
                </button>
              </div>
            </form>
          </section>
        </div>
      ) : null}

      {folderContextMenu.open && folderContextMenu.folder ? (
        <div
          className="document-context-menu"
          onContextMenu={(event) => event.preventDefault()}
          onPointerDown={(event) => event.stopPropagation()}
          role="menu"
          style={{
            left: folderContextMenu.x,
            top: folderContextMenu.y
          }}
        >
          <button
            onClick={() => {
              if (folderContextMenu.folder) {
                openRenameFolderDialog(folderContextMenu.folder);
              }
            }}
            role="menuitem"
            type="button"
          >
            폴더 이름 변경
          </button>
          {folderContextMenu.folder &&
          !isProtectedDocumentFolder(folderContextMenu.folder) ? (
            <button
              className="danger-menu-item"
              onClick={() => {
                if (folderContextMenu.folder) {
                  openDeleteFolderDialog(folderContextMenu.folder);
                }
              }}
              role="menuitem"
              type="button"
            >
              폴더 삭제
            </button>
          ) : null}
        </div>
      ) : null}

      {documentContextMenu.open ? (
        <div
          className="document-context-menu"
          onContextMenu={(event) => event.preventDefault()}
          onPointerDown={(event) => event.stopPropagation()}
          role="menu"
          style={{
            left: documentContextMenu.x,
            top: documentContextMenu.y
          }}
        >
          <button
            onClick={() => openNewDocumentDialog("PDF")}
            role="menuitem"
            type="button"
          >
            새 PDF 문서
          </button>
          <button
            onClick={() => openNewDocumentDialog("EXCEL")}
            role="menuitem"
            type="button"
          >
            새 Excel 문서
          </button>
        </div>
      ) : null}

      {renamingFolder ? (
        <div
          className="modal-backdrop"
          onClick={(event) => {
            if (event.target === event.currentTarget) {
              closeRenameFolderDialog();
            }
          }}
        >
          <section
            aria-label={`${renamingFolder.name} 폴더 이름 변경`}
            aria-modal="true"
            className="modal-panel folder-rename-modal-panel"
            role="dialog"
          >
            <form className="modal-form" onSubmit={handleRenameFolder}>
              <div className="modal-heading">
                <h2>폴더 이름 변경</h2>
                <button
                  disabled={renameFolderSubmitting}
                  onClick={closeRenameFolderDialog}
                  type="button"
                >
                  ×
                </button>
              </div>
              <label>
                <span>폴더명</span>
                <input
                  autoFocus
                  disabled={renameFolderSubmitting}
                  maxLength={80}
                  onChange={(event) => setRenameFolderName(event.target.value)}
                  value={renameFolderName}
                />
              </label>
              {renameFolderMessage ? (
                <p className="modal-upload-message">{renameFolderMessage}</p>
              ) : null}
              <div className="modal-actions">
                <button
                  className="secondary-button"
                  disabled={renameFolderSubmitting}
                  onClick={closeRenameFolderDialog}
                  type="button"
                >
                  취소
                </button>
                <button disabled={renameFolderSubmitting} type="submit">
                  {renameFolderSubmitting ? "변경 중" : "변경"}
                </button>
              </div>
            </form>
          </section>
        </div>
      ) : null}

      {deletingFolder ? (
        <div
          className="modal-backdrop"
          onClick={(event) => {
            if (event.target === event.currentTarget) {
              closeDeleteFolderDialog();
            }
          }}
        >
          <section
            aria-label={`${deletingFolder.name} 폴더 삭제`}
            aria-modal="true"
            className="modal-panel folder-delete-modal-panel"
            role="dialog"
          >
            <div className="modal-form">
              <div className="modal-heading">
                <h2>폴더 삭제</h2>
                <button
                  disabled={deleteFolderSubmitting}
                  onClick={closeDeleteFolderDialog}
                  type="button"
                >
                  ×
                </button>
              </div>
              <p className="folder-delete-message">
                <strong>{deletingFolder.name}</strong> 폴더를 삭제합니다.
                하위에 폴더만 있으면 함께 삭제되며, 파일이 있으면 삭제되지
                않습니다.
              </p>
              {deleteFolderMessage ? (
                <p className="modal-upload-message">{deleteFolderMessage}</p>
              ) : null}
              <div className="modal-actions">
                <button
                  className="secondary-button"
                  disabled={deleteFolderSubmitting}
                  onClick={closeDeleteFolderDialog}
                  type="button"
                >
                  취소
                </button>
                <button
                  className="danger-button"
                  disabled={deleteFolderSubmitting}
                  onClick={() => void handleDeleteFolder()}
                  type="button"
                >
                  {deleteFolderSubmitting ? "삭제 중" : "삭제"}
                </button>
              </div>
            </div>
          </section>
        </div>
      ) : null}

      {newDocumentOpen ? (
        <div
          className="modal-backdrop"
          onMouseDown={closeNewDocumentDialog}
          role="presentation"
        >
          <section
            aria-labelledby="document-create-title"
            aria-modal="true"
            className={
              newDocumentType === "PDF"
                ? "modal-panel document-create-modal-panel document-editor-modal-panel"
                : "modal-panel document-create-modal-panel document-create-modal-panel-excel"
            }
            onMouseDown={(event) => event.stopPropagation()}
            role="dialog"
          >
            <form onSubmit={handleCreateDocument}>
              <div className="modal-heading">
                <h2 id="document-create-title">
                  {editingDocument
                    ? `${newDocumentType === "EXCEL" ? "Excel" : "PDF"} 문서 수정`
                    : newDocumentType === "EXCEL"
                      ? "새 Excel 문서"
                      : "새 PDF 문서"}
                </h2>
                <button
                  className="icon-button"
                  disabled={newDocumentCreating}
                  onClick={closeNewDocumentDialog}
                  type="button"
                >
                  ×
                </button>
              </div>

              {newDocumentType === "PDF" ? (
                <div className="document-editor-modal-body">
                  <aside className="document-editor-sidebar">
                    <p className="create-document-location">
                      위치:{" "}
                      {editingDocument?.category ||
                        currentDocumentFolder?.name ||
                        "선택한 폴더"}
                    </p>
                    <label className="upload-modal-tags">
                      <span>파일명</span>
                      <input
                        autoFocus
                        disabled={newDocumentCreating}
                        onChange={(event) => setNewDocumentName(event.target.value)}
                        placeholder="예: 점검보고서.pdf"
                        value={newDocumentName}
                      />
                    </label>
                    <label className="upload-modal-tags">
                      <span>태그</span>
                      <input
                        disabled={newDocumentCreating}
                        onChange={(event) => setNewDocumentTags(event.target.value)}
                        placeholder="점검, 보고서, 현장"
                        value={newDocumentTags}
                      />
                    </label>
                  </aside>
                  <div className="document-page-editor-wrap">
                    <PdfDocumentEditor
                      body={newDocumentBody}
                      disabled={newDocumentCreating}
                      onBodyChange={setNewDocumentBody}
                    />
                  </div>
                  {newDocumentMessage ? (
                    <p className="upload-message modal-upload-message">
                      {newDocumentMessage}
                    </p>
                  ) : null}
                </div>
              ) : (
                <div className="spreadsheet-editor-modal-body">
                  <aside className="document-editor-sidebar">
                    <p className="create-document-location">
                      위치:{" "}
                      {editingDocument?.category ||
                        currentDocumentFolder?.name ||
                        "선택한 폴더"}
                    </p>
                    <label className="upload-modal-tags">
                      <span>파일명</span>
                      <input
                        autoFocus
                        disabled={newDocumentCreating}
                        onChange={(event) => setNewDocumentName(event.target.value)}
                        placeholder="예: 생산계획.xlsx"
                        value={newDocumentName}
                      />
                    </label>
                    <label className="upload-modal-tags">
                      <span>태그</span>
                      <input
                        disabled={newDocumentCreating}
                        onChange={(event) => setNewDocumentTags(event.target.value)}
                        placeholder="엑셀, 계획, 생산"
                        value={newDocumentTags}
                      />
                    </label>
                  </aside>
                  <div className="spreadsheet-editor-wrap">
                    <SpreadsheetEditor
                      disabled={newDocumentCreating}
                      initialCells={newSpreadsheetCells}
                      onCellsChange={setNewSpreadsheetCells}
                    />
                  </div>
                  {newDocumentMessage ? (
                    <p className="upload-message modal-upload-message">
                      {newDocumentMessage}
                    </p>
                  ) : null}
                </div>
              )}

              {editingDocument ? (
                <label className="upload-modal-tags document-change-note-field">
                  <span>수정 사유</span>
                  <textarea
                    disabled={newDocumentCreating}
                    onChange={(event) => setNewDocumentChangeNote(event.target.value)}
                    placeholder="예: 점검 기준 변경 사항 반영"
                    rows={2}
                    value={newDocumentChangeNote}
                  />
                </label>
              ) : null}

              <div className="sequence-form-actions">
                <button
                  className="secondary-button"
                  disabled={newDocumentCreating}
                  onClick={closeNewDocumentDialog}
                  type="button"
                >
                  취소
                </button>
                <button disabled={newDocumentCreating} type="submit">
                  {newDocumentCreating
                    ? editingDocument
                      ? "저장 중"
                      : "생성 중"
                    : editingDocument
                      ? "새 버전 저장"
                      : "만들기"}
                </button>
              </div>
            </form>
          </section>
        </div>
      ) : null}

      {pendingUploadFiles.length > 0 ? (
        <div
          className="modal-backdrop"
          onMouseDown={closeDocumentUploadDialog}
          role="presentation"
        >
          <section
            aria-labelledby="document-upload-title"
            aria-modal="true"
            className="modal-panel upload-modal-panel"
            onMouseDown={(event) => event.stopPropagation()}
            role="dialog"
          >
            <div className="modal-heading">
              <h2 id="document-upload-title">문서 업로드</h2>
              <button
                className="icon-button"
                disabled={documentUploading}
                onClick={closeDocumentUploadDialog}
                type="button"
              >
                ×
              </button>
            </div>

            <div className="upload-modal-body">
              <section>
                <h3>업로드 파일</h3>
                <ul className="upload-file-list">
                  {pendingUploadFiles.map((file) => (
                    <li key={`${file.name}-${file.size}-${file.lastModified}`}>
                      <strong>{file.name}</strong>
                      <span>{(file.size / 1024 / 1024).toFixed(2)}MB</span>
                    </li>
                  ))}
                </ul>
              </section>
              <label className="upload-modal-tags">
                <span>태그</span>
                <input
                  autoFocus
                  disabled={documentUploading}
                  onChange={(event) => setDocumentUploadTags(event.target.value)}
                  placeholder="도면, 냉각, 점검"
                  value={documentUploadTags}
                />
              </label>
              {documentUploadMessage ? (
                <p className="upload-message modal-upload-message">
                  {documentUploadMessage}
                </p>
              ) : null}
            </div>

            <div className="sequence-form-actions">
              <button
                className="secondary-button"
                disabled={documentUploading}
                onClick={closeDocumentUploadDialog}
                type="button"
              >
                취소
              </button>
              <button
                disabled={documentUploading}
                onClick={() => void uploadDocumentFiles(pendingUploadFiles)}
                type="button"
              >
                {documentUploading ? "업로드 중" : "업로드"}
              </button>
            </div>
          </section>
        </div>
      ) : null}
    </main>
  );
}
