"""Storage interface. Local disk for development, S3-compatible for production."""
import hashlib
import re
from pathlib import Path
from typing import Protocol

from app.core.config import get_settings

SAFE_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,500}$")


class Storage(Protocol):
    backend: str

    def put(self, key: str, data: bytes, content_type: str | None = None) -> dict: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...


def _validate_key(key: str) -> str:
    if not SAFE_KEY.match(key) or ".." in key.split("/"):
        raise ValueError("Invalid storage key")
    return key


class LocalStorage:
    backend = "local"

    def __init__(self, root: str):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.root / _validate_key(key)).resolve()
        if self.root not in path.parents:
            raise ValueError("Invalid storage key")
        return path

    def put(self, key, data, content_type=None):
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return {"key": key, "size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}

    def get(self, key):
        return self._path(key).read_bytes()

    def delete(self, key):
        self._path(key).unlink(missing_ok=True)


class S3Storage:
    backend = "s3"

    def __init__(self):
        import boto3  # imported lazily; add boto3 to requirements when enabling S3

        s = get_settings()
        self.bucket = s.s3_bucket
        self.client = boto3.client(
            "s3", endpoint_url=s.s3_endpoint_url or None,
            aws_access_key_id=s.s3_access_key_id, aws_secret_access_key=s.s3_secret_access_key,
        )

    def put(self, key, data, content_type=None):
        _validate_key(key)
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type or "application/octet-stream")
        return {"key": key, "size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}

    def get(self, key):
        return self.client.get_object(Bucket=self.bucket, Key=_validate_key(key))["Body"].read()

    def delete(self, key):
        self.client.delete_object(Bucket=self.bucket, Key=_validate_key(key))


def get_storage() -> Storage:
    s = get_settings()
    if s.s3_bucket and s.s3_access_key_id:
        return S3Storage()
    return LocalStorage(s.local_storage_dir)
