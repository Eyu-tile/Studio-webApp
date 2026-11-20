"""S3-compatible object storage. The browser uploads and plays media with presigned URLs; the API never carries
media bytes. Works with AWS S3, Cloudflare R2 and MinIO (set S3_ENDPOINT_URL)."""
import logging
import math
from functools import lru_cache

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from .config import get_settings

PART_SIZE = 16 * 1024 * 1024          # 16 MiB parts: 10,000-part S3 limit covers files up to ~156 GiB
MAX_PARTS = 10_000


def _client(endpoint):
    s = get_settings()
    return boto3.client("s3", region_name=s.s3_region, endpoint_url=endpoint,
                        aws_access_key_id=s.s3_access_key_id, aws_secret_access_key=s.s3_secret_access_key,
                        config=Config(signature_version="s3v4", s3={"addressing_style": "path"} if endpoint else {}))


@lru_cache
def client():
    return _client(get_settings().s3_endpoint_url)


@lru_cache
def signer():
    """Client whose presigned URLs the browser can reach (differs from `client` inside docker networks)."""
    s = get_settings()
    return _client(s.s3_public_endpoint_url or s.s3_endpoint_url)


def bucket() -> str:
    return get_settings().s3_bucket


def ensure_bucket() -> None:
    """Dev convenience: create the bucket with a CORS rule for the web app."""
    s = get_settings()
    c = client()
    existing = {b["Name"] for b in c.list_buckets().get("Buckets", [])}
    if s.s3_bucket not in existing:
        kw = {} if s.s3_region == "us-east-1" else {"CreateBucketConfiguration": {"LocationConstraint": s.s3_region}}
        c.create_bucket(Bucket=s.s3_bucket, **kw)
    try:
        c.put_bucket_cors(Bucket=s.s3_bucket, CORSConfiguration={"CORSRules": [{
            "AllowedOrigins": [s.public_url], "AllowedMethods": ["GET", "PUT", "HEAD"], "AllowedHeaders": ["*"],
            "ExposeHeaders": ["ETag"], "MaxAgeSeconds": 3600}]})
    except ClientError as e:   # MinIO has no per-bucket CORS (it allows any origin unless configured otherwise)
        logging.getLogger(__name__).info("bucket CORS not set: %s", e.response["Error"].get("Code"))


def part_plan(size: int) -> tuple[int, int]:
    part = max(PART_SIZE, math.ceil(size / MAX_PARTS))
    return part, max(1, math.ceil(size / part))


def start_multipart(key: str, mime: str) -> str:
    return client().create_multipart_upload(Bucket=bucket(), Key=key, ContentType=mime)["UploadId"]


def presign_parts(key: str, upload_id: str, parts: list[int]) -> dict[int, str]:
    ttl = get_settings().s3_presign_ttl * 4
    return {n: signer().generate_presigned_url("upload_part", ExpiresIn=ttl, Params={
        "Bucket": bucket(), "Key": key, "UploadId": upload_id, "PartNumber": n}) for n in parts}


def complete_multipart(key: str, upload_id: str, parts: list[dict]) -> None:
    client().complete_multipart_upload(Bucket=bucket(), Key=key, UploadId=upload_id, MultipartUpload={
        "Parts": [{"PartNumber": p["part_number"], "ETag": p["etag"]} for p in sorted(parts, key=lambda p: p["part_number"])]})


def abort_multipart(key: str, upload_id: str) -> None:
    client().abort_multipart_upload(Bucket=bucket(), Key=key, UploadId=upload_id)


def head(key: str) -> dict:
    return client().head_object(Bucket=bucket(), Key=key)


def presign_get(key: str, filename: str | None = None, download: bool = False) -> str:
    params = {"Bucket": bucket(), "Key": key}
    if download and filename:
        params["ResponseContentDisposition"] = f'attachment; filename="{filename}"'
    return signer().generate_presigned_url("get_object", Params=params, ExpiresIn=get_settings().s3_presign_ttl)


def presign_put(key: str, mime: str) -> str:
    """One PUT for a small file (packshots, logos): the browser sends it with this Content-Type."""
    return signer().generate_presigned_url("put_object", Params={"Bucket": bucket(), "Key": key, "ContentType": mime},
                                           ExpiresIn=get_settings().s3_presign_ttl)


def delete(key: str) -> None:
    client().delete_object(Bucket=bucket(), Key=key)


def upload_file(path, key: str, mime: str) -> None:
    client().upload_file(str(path), bucket(), key, ExtraArgs={"ContentType": mime})


def download_file(key: str, path) -> None:
    client().download_file(bucket(), key, str(path))


def delete_prefix(prefix: str) -> None:
    c = client()
    for page in c.get_paginator("list_objects_v2").paginate(Bucket=bucket(), Prefix=prefix):
        objs = [{"Key": o["Key"]} for o in page.get("Contents", [])]
        if objs:
            c.delete_objects(Bucket=bucket(), Delete={"Objects": objs})


def project_prefix(brand_id, project_id) -> str:
    return f"brands/{brand_id}/projects/{project_id}/"
