"""S3-compatible object storage helpers (e.g. Vultr Object Storage)."""

from __future__ import annotations

import asyncio
import io
import mimetypes

import boto3

from app.core.config import settings


def _client():
    return boto3.client(
        "s3",
        endpoint_url=settings.OBJECT_STORAGE_ENDPOINT_URL or None,
        region_name=settings.OBJECT_STORAGE_REGION or None,
        aws_access_key_id=settings.OBJECT_STORAGE_ACCESS_KEY_ID or None,
        aws_secret_access_key=settings.OBJECT_STORAGE_SECRET_ACCESS_KEY or None,
    )


def _guess_content_type(filename: str, fallback: str = "application/octet-stream") -> str:
    ct, _ = mimetypes.guess_type(filename)
    return ct or fallback


async def put_bytes(*, key: str, data: bytes, filename: str) -> str:
    """Upload bytes to object storage and return an s3:// reference."""
    if not settings.OBJECT_STORAGE_ENABLED:
        raise RuntimeError("Object storage is disabled")
    if not settings.OBJECT_STORAGE_BUCKET:
        raise RuntimeError("OBJECT_STORAGE_BUCKET is not set")

    bucket = settings.OBJECT_STORAGE_BUCKET
    content_type = _guess_content_type(filename)

    def _upload():
        s3 = _client()
        s3.upload_fileobj(
            io.BytesIO(data),
            bucket,
            key,
            ExtraArgs={"ContentType": content_type},
        )

    await asyncio.to_thread(_upload)
    return f"s3://{bucket}/{key}"