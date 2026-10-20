"""模型工件和备份的对象存储适配层。

默认使用本地目录，生产可切换到 S3/MinIO 兼容服务。未配置对象存储时不伪造
上传成功；S3 依赖按需懒加载，避免本地开发必须安装云厂商 SDK。
"""

from __future__ import annotations

import shutil
from pathlib import Path

from brandpulse.config.config import Config


class ObjectStorageError(RuntimeError):
    pass


class ObjectStorage:
    def __init__(self):
        self.backend = Config.OBJECT_STORAGE_BACKEND
        self.local_root = Config.OBJECT_STORAGE_LOCAL_DIR

    @staticmethod
    def _key(key: str) -> str:
        normalized = str(key or "").replace("\\", "/").lstrip("/")
        if not normalized or normalized == "." or ".." in normalized.split("/"):
            raise ObjectStorageError("对象键不合法")
        return normalized

    def put_file(self, source: str | Path, key: str) -> str:
        source_path = Path(source)
        if not source_path.is_file():
            raise ObjectStorageError(f"待上传文件不存在: {source_path}")
        object_key = self._key(key)
        if self.backend == "local":
            target = (self.local_root / object_key).resolve()
            root = self.local_root.resolve()
            if root != target and root not in target.parents:
                raise ObjectStorageError("对象路径越界")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_path, target)
            return f"file://{target}"
        if self.backend != "s3":
            raise ObjectStorageError(f"不支持的对象存储后端: {self.backend}")
        if not Config.OBJECT_STORAGE_BUCKET:
            raise ObjectStorageError("S3/MinIO 后端缺少 OBJECT_STORAGE_BUCKET")
        try:
            import boto3
        except ImportError as exc:
            raise ObjectStorageError("S3/MinIO 后端需要安装 boto3") from exc
        client = boto3.client(
            "s3",
            endpoint_url=Config.OBJECT_STORAGE_ENDPOINT or None,
            aws_access_key_id=Config.OBJECT_STORAGE_ACCESS_KEY or None,
            aws_secret_access_key=Config.OBJECT_STORAGE_SECRET_KEY or None,
            region_name=Config.OBJECT_STORAGE_REGION or None,
        )
        client.upload_file(str(source_path), Config.OBJECT_STORAGE_BUCKET, f"{Config.OBJECT_STORAGE_PREFIX}{object_key}")
        return f"s3://{Config.OBJECT_STORAGE_BUCKET}/{Config.OBJECT_STORAGE_PREFIX}{object_key}"
