import hashlib
import os
import re
from pathlib import Path

from app.core.errors import WorkflowError

MAX_DOCUMENT_BYTES = 10 * 1024 * 1024  # 10 MB

ALLOWED_MEDIA_TYPES = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
}

DEFAULT_UPLOAD_DIR = Path(__file__).resolve().parents[3] / ".runtime" / "uploads"


def get_upload_dir() -> Path:
    custom = os.getenv("STORAGE_LOCAL_DIR")
    base = Path(custom).resolve() if custom else DEFAULT_UPLOAD_DIR
    base.mkdir(parents=True, exist_ok=True)
    return base


def sanitize_filename(filename: str) -> str:
    cleaned = re.sub(r"[^\w\.-]", "_", filename).strip("._")
    return cleaned[:80] if cleaned else "document"


def validate_document_media_type(content_type: str | None) -> str:
    if not content_type:
        raise WorkflowError("INVALID_MEDIA_TYPE", "Content-Type is required for uploaded documents.", 422)

    normalized = content_type.strip().lower().split(";")[0].strip()
    if normalized not in ALLOWED_MEDIA_TYPES:
        raise WorkflowError(
            "INVALID_MEDIA_TYPE",
            f"Unsupported document format '{content_type}'. Allowed: JPEG, PNG, WebP, PDF.",
            422,
        )
    return normalized


def validate_document_file(content_type: str | None, size_bytes: int) -> str:
    media_type = validate_document_media_type(content_type)

    if size_bytes > MAX_DOCUMENT_BYTES:
        raise WorkflowError(
            "FILE_TOO_LARGE",
            f"Document exceeds maximum size of {MAX_DOCUMENT_BYTES // (1024 * 1024)}MB.",
            422,
        )

    if size_bytes == 0:
        raise WorkflowError("EMPTY_FILE", "Uploaded document is empty.", 422)

    return media_type


def compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class StorageService:
    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or get_upload_dir()

    def _resolve_path(self, object_key: str) -> Path:
        # Prevent directory traversal attacks
        cleaned_key = os.path.normpath(object_key).lstrip("\\/")
        resolved = (self.base_dir / cleaned_key).resolve()
        if not str(resolved).startswith(str(self.base_dir)):
            raise WorkflowError("INVALID_OBJECT_KEY", "Access to path outside upload directory is forbidden.", 403)
        return resolved

    def save_file(
        self,
        session_id: str,
        doc_id: str,
        filename: str,
        data: bytes,
    ) -> tuple[str, str, int]:
        clean_name = sanitize_filename(filename)
        object_key = f"documents/{session_id}/{doc_id}_{clean_name}"
        dest_path = self._resolve_path(object_key)
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        dest_path.write_bytes(data)
        sha256 = compute_sha256(data)
        return object_key, sha256, len(data)

    def get_file_bytes(self, object_key: str) -> bytes:
        file_path = self._resolve_path(object_key)
        if not file_path.is_file():
            raise WorkflowError("FILE_NOT_FOUND", "Document file not found on disk.", 404)
        return file_path.read_bytes()

    def get_file_path(self, object_key: str) -> Path:
        file_path = self._resolve_path(object_key)
        if not file_path.is_file():
            raise WorkflowError("FILE_NOT_FOUND", "Document file not found on disk.", 404)
        return file_path

    def delete_file(self, object_key: str) -> bool:
        try:
            file_path = self._resolve_path(object_key)
            if file_path.is_file():
                file_path.unlink()
                return True
        except Exception:
            pass
        return False


default_storage = StorageService()
