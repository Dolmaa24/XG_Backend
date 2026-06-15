import logging
import uuid
import magic
from pathlib import Path
from fastapi import UploadFile, HTTPException, status

from app.core.config import settings

logger = logging.getLogger(__name__)

# SECURITY [MEDIUM]: null-byte injection guard added to filename sanitizer
def _sanitize_filename(filename: str) -> str:
    # Strip null bytes first — can be used to bypass extension checks
    filename = filename.replace("\x00", "")
    name = Path(filename).name
    safe = "".join(c for c in name if c.isalnum() or c in (".", "-", "_"))
    return safe[:100] or "upload"  # cap length


async def validate_upload(file: UploadFile) -> bytes:
    content = await file.read()

    # SECURITY [HIGH]: size check before any processing
    if len(content) > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum allowed size of {settings.MAX_UPLOAD_SIZE_MB}MB",
        )

    # SECURITY [CRITICAL]: MIME type via libmagic (magic bytes), NOT file extension
    # Extension-based checks are trivially bypassed by renaming any file to .pdf
    detected_mime = magic.from_buffer(content[:2048], mime=True)
    if detected_mime not in settings.allowed_mime_types_list:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"File type '{detected_mime}' is not allowed. Upload PDF or DOCX only.",
        )

    # SECURITY [HIGH]: path traversal guard — check BEFORE sanitize so we catch
    # attempts that rely on URL encoding or OS-specific separators
    original = file.filename or "upload"
    if any(c in original for c in ("..", "/", "\\", "\x00")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filename",
        )

    return content


async def validate_image_upload(file: UploadFile) -> bytes:
    """SECURITY: validate avatar uploads — size + magic-byte MIME (images only)."""
    content = await file.read()

    if len(content) > settings.max_avatar_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Image exceeds maximum allowed size of {settings.MAX_AVATAR_SIZE_MB}MB",
        )

    detected_mime = magic.from_buffer(content[:2048], mime=True)
    if detected_mime not in settings.allowed_image_mime_types_list:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"File type '{detected_mime}' is not allowed. Upload PNG, JPEG, or WebP only.",
        )

    original = file.filename or "avatar"
    if any(c in original for c in ("..", "/", "\\", "\x00")):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename")

    return content


async def save_file(content: bytes, original_filename: str, user_id: str) -> str:
    safe_name = _sanitize_filename(original_filename)
    # SECURITY [MEDIUM]: user_id prefix scopes files per user, uuid prevents collisions
    unique_name = f"{user_id}/{uuid.uuid4()}_{safe_name}"

    if settings.STORAGE_BACKEND == "s3":
        return await _save_to_s3(content, unique_name)
    return await _save_locally(content, unique_name)


async def _save_locally(content: bytes, relative_path: str) -> str:
    # SECURITY [MEDIUM]: resolve path and confirm it stays within upload dir
    base = Path(settings.LOCAL_UPLOAD_DIR).resolve()
    full_path = (base / relative_path).resolve()

    if not str(full_path).startswith(str(base)):
        logger.error({"event": "path_traversal_blocked", "path": str(full_path)})
        raise HTTPException(status_code=400, detail="Invalid file path")

    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_bytes(content)
    logger.info({"event": "file_saved_local", "path": str(full_path)})
    return str(full_path)


async def _save_to_s3(content: bytes, key: str) -> str:
    import boto3
    s3 = boto3.client(
        "s3",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_REGION,
    )
    s3.put_object(Bucket=settings.AWS_S3_BUCKET, Key=key, Body=content)
    path = f"s3://{settings.AWS_S3_BUCKET}/{key}"
    logger.info({"event": "file_saved_s3", "path": path})
    return path


def read_file(file_path: str) -> bytes:
    if file_path.startswith("s3://"):
        return _read_from_s3(file_path)
    return Path(file_path).read_bytes()


def _read_from_s3(s3_path: str) -> bytes:
    import boto3
    parts = s3_path.replace("s3://", "").split("/", 1)
    bucket, key = parts[0], parts[1]
    s3 = boto3.client(
        "s3",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_REGION,
    )
    response = s3.get_object(Bucket=bucket, Key=key)
    return response["Body"].read()


def delete_file(file_path: str) -> None:
    """Best-effort delete of a stored file (local or S3). Never raises."""
    try:
        if file_path.startswith("s3://"):
            import boto3
            parts = file_path.replace("s3://", "").split("/", 1)
            bucket, key = parts[0], parts[1]
            s3 = boto3.client(
                "s3",
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_REGION,
            )
            s3.delete_object(Bucket=bucket, Key=key)
        else:
            p = Path(file_path)
            if p.exists():
                p.unlink()
        logger.info({"event": "file_deleted", "path": file_path})
    except Exception as e:
        logger.warning({"event": "file_delete_failed", "path": file_path, "error": str(e)})
