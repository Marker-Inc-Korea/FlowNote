from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile


_SAFE_FILENAME_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class StoredFile:
    storage_key: str
    original_filename: str
    extension: str
    mime_type: str | None
    file_family: str
    size_bytes: int
    hash_sha256: str


class UploadTooLargeError(ValueError):
    pass


def file_family_from_extension(extension: str, mime_type: str | None = None) -> str:
    normalized = extension.lower().lstrip(".")
    if normalized == "pdf":
        return "pdf"
    if normalized in {"xls", "xlsx", "xlsm", "csv"}:
        return "excel"
    if normalized in {"png", "jpg", "jpeg", "gif", "bmp", "webp"}:
        return "image"
    if normalized in {"txt", "md"}:
        return "text"
    if normalized in {"doc", "docx"}:
        return "word"
    if normalized in {"ppt", "pptx"}:
        return "powerpoint"
    if normalized in {"dwg", "dxf"}:
        return "drawing"
    if mime_type:
        if mime_type == "application/pdf":
            return "pdf"
        if mime_type.startswith("image/"):
            return "image"
    return "other"


def safe_filename(filename: str) -> str:
    path_name = Path(filename).name.strip()
    stem = Path(path_name).stem or "upload"
    extension = Path(path_name).suffix
    safe_stem = _SAFE_FILENAME_PATTERN.sub("-", stem).strip(".-_") or "upload"
    return f"{safe_stem[:80]}{extension.lower()}"


def resolve_storage_root(storage_root: str) -> Path:
    return Path(storage_root).resolve()


def relative_storage_key(*parts: str) -> str:
    return "/".join(part.strip("/\\") for part in parts if part.strip("/\\"))


async def store_upload_file(
    upload: UploadFile,
    *,
    storage_root: Path,
    document_id: str,
    version_no: int,
    max_size_bytes: int | None = None,
) -> StoredFile:
    return await store_upload_file_at(
        upload,
        storage_root=storage_root,
        path_parts=("documents", document_id, f"v{version_no}"),
        max_size_bytes=max_size_bytes,
    )


async def store_upload_file_at(
    upload: UploadFile,
    *,
    storage_root: Path,
    path_parts: tuple[str, ...],
    max_size_bytes: int | None = None,
) -> StoredFile:
    original_filename = upload.filename or "upload.bin"
    stored_name = f"{uuid4().hex}_{safe_filename(original_filename)}"
    storage_key = relative_storage_key(*path_parts, stored_name)
    target_path = storage_root / Path(storage_key)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    digest = hashlib.sha256()
    size_bytes = 0
    with target_path.open("wb") as target:
        while chunk := await upload.read(1024 * 1024):
            size_bytes += len(chunk)
            if max_size_bytes is not None and size_bytes > max_size_bytes:
                await upload.close()
                target.close()
                target_path.unlink(missing_ok=True)
                raise UploadTooLargeError("Uploaded file exceeds the configured size limit.")
            digest.update(chunk)
            target.write(chunk)
    await upload.close()

    extension = Path(original_filename).suffix.lower()
    return StoredFile(
        storage_key=storage_key.replace("\\", "/"),
        original_filename=original_filename,
        extension=extension,
        mime_type=upload.content_type,
        file_family=file_family_from_extension(extension, upload.content_type),
        size_bytes=size_bytes,
        hash_sha256=digest.hexdigest(),
    )
