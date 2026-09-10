import hashlib
import io
import os
import re
import warnings
from pathlib import Path

from PIL import Image
from pypdf import PdfReader

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


def validate_document_contents(data: bytes, media_type: str) -> None:
    try:
        if media_type == "application/pdf":
            pdf = PdfReader(io.BytesIO(data), strict=True)
            if pdf.is_encrypted or not 1 <= len(pdf.pages) <= 20:
                raise ValueError("Unsupported PDF")
            if any(key in pdf.trailer["/Root"] for key in ("/OpenAction", "/AA")):
                raise ValueError("Active PDF")
        else:
            expected = {"image/jpeg": "JPEG", "image/jpg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}[media_type]
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(data)) as image:
                    if image.format != expected or image.width * image.height > 20_000_000:
                        raise ValueError("Invalid image")
                    image.verify()
                with Image.open(io.BytesIO(data)) as image:
                    image.load()
    except Exception:
        raise WorkflowError("INVALID_FILE_CONTENT", "Upload a valid, supported image or PDF (up to 20 pages).", 422) from None


def compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class StorageService:
    def __init__(self, base_dir: Path | None = None):
        self.base_dir = (base_dir or get_upload_dir()).resolve()

    def _resolve_path(self, object_key: str) -> Path:
        # Prevent directory traversal attacks
        key = Path(object_key)
        resolved = (self.base_dir / key).resolve()
        if key.is_absolute() or not resolved.is_relative_to(self.base_dir) or resolved == self.base_dir:
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
