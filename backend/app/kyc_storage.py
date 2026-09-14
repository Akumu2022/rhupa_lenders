"""CLAUDE.md §16: KYC documents are never served from a static/guessable path.
Files are written outside the web root under a per-company/per-user directory,
named with a generated UUID (the original filename is discarded beyond its
extension). Nothing here mounts this directory as static — a real serving
endpoint (authenticated, tenant-scoped, role-gated) is added in M3.
"""

import uuid
from pathlib import Path

from fastapi import UploadFile

from .config import settings

_ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}
_MAX_UPLOAD_BYTES = 8 * 1024 * 1024  # 8MB


def _customer_dir(company_id: int, user_id: int) -> Path:
    return settings.kyc_storage_root / str(company_id) / str(user_id)


async def save_kyc_document(company_id: int, user_id: int, upload: UploadFile, *, field_name: str) -> str:
    """Returns a path relative to kyc_storage_root — stored on Profile, never
    a filesystem absolute path or anything a client could turn into a URL."""
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in _ALLOWED_EXTENSIONS:
        raise ValueError(f"{field_name}: unsupported file type '{suffix or 'unknown'}'")

    contents = await upload.read()
    if len(contents) > _MAX_UPLOAD_BYTES:
        raise ValueError(f"{field_name}: file too large (max 8MB)")

    directory = _customer_dir(company_id, user_id)
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{suffix}"
    (directory / filename).write_bytes(contents)

    return f"{company_id}/{user_id}/{filename}"
