#!/usr/bin/env python3
"""Reset the Vultr-hosted production database and object storage.

Run this *inside* the backend container on the VPS:

    docker exec ai-deepfake-backend-1 python /app/reset_prod.py          # DB only
    docker exec ai-deepfake-backend-1 python /app/reset_prod.py --all    # DB + bucket

Or locally (with backend/.env.production values sourced):

    DATABASE_URL=... python reset_prod.py --all
"""

import asyncio
import os
import sys

TABLES = ["hash_matches", "image_hashes", "claims", "accounts"]


async def reset_database():
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    url = os.environ.get("DATABASE_URL", "")
    if not url:
        try:
            from app.core.config import settings
            url = settings.DATABASE_URL
        except Exception:
            print("  ERROR: DATABASE_URL not set and cannot import app config.")
            return False

    engine = create_async_engine(url)
    async with engine.begin() as conn:
        result = await conn.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        ))
        existing = {row[0] for row in result.fetchall()}
        to_truncate = [t for t in TABLES if t in existing]

        if to_truncate:
            await conn.execute(text(f"TRUNCATE {', '.join(to_truncate)} CASCADE"))
            print(f"  Truncated: {', '.join(to_truncate)}")
        else:
            print("  No matching tables found — database already clean.")

        skipped = [t for t in TABLES if t not in existing]
        if skipped:
            print(f"  Skipped (not found): {', '.join(skipped)}")

    await engine.dispose()
    return True


def reset_bucket():
    import boto3

    endpoint = os.environ.get("OBJECT_STORAGE_ENDPOINT_URL", "")
    bucket = os.environ.get("OBJECT_STORAGE_BUCKET", "")
    access_key = os.environ.get("OBJECT_STORAGE_ACCESS_KEY_ID", "")
    secret_key = os.environ.get("OBJECT_STORAGE_SECRET_ACCESS_KEY", "")
    region = os.environ.get("OBJECT_STORAGE_REGION", "us-east-1")
    prefix = os.environ.get("OBJECT_STORAGE_PREFIX", "uploads")

    if not all([endpoint, bucket, access_key, secret_key]):
        try:
            from app.core.config import settings
            endpoint = endpoint or settings.OBJECT_STORAGE_ENDPOINT_URL
            bucket = bucket or settings.OBJECT_STORAGE_BUCKET
            access_key = access_key or settings.OBJECT_STORAGE_ACCESS_KEY_ID
            secret_key = secret_key or settings.OBJECT_STORAGE_SECRET_ACCESS_KEY
            region = region or settings.OBJECT_STORAGE_REGION
            prefix = prefix or settings.OBJECT_STORAGE_PREFIX
        except Exception:
            print("  ERROR: Object storage env vars not set and cannot import app config.")
            return

    if not all([endpoint, bucket, access_key, secret_key]):
        print("  ERROR: Missing object storage credentials.")
        return

    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=region,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
    )

    paginator = s3.get_paginator("list_objects_v2")
    deleted = 0
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        objects = page.get("Contents", [])
        if objects:
            s3.delete_objects(
                Bucket=bucket,
                Delete={"Objects": [{"Key": obj["Key"]} for obj in objects]},
            )
            deleted += len(objects)

    print(f"  Deleted {deleted} object(s) from s3://{bucket}/{prefix}")


def main():
    clean_all = "--all" in sys.argv

    print("=" * 50)
    print("  Production Reset — Vultr DB + Object Storage")
    print("=" * 50)

    print("\n[1/2] Truncating PostgreSQL tables...")
    asyncio.run(reset_database())

    if clean_all:
        print("\n[2/2] Clearing Vultr Object Storage bucket...")
        reset_bucket()
    else:
        print("\n[2/2] Bucket preserved (use --all to clear uploaded images too)")

    print("\nDone! No restart needed — tables are empty but intact.")


if __name__ == "__main__":
    main()
