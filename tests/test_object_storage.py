from pathlib import Path

import pytest

from brandpulse.config.config import Config
from brandpulse.storage.object_storage import ObjectStorage, ObjectStorageError


def test_local_object_storage_copies_file_without_path_escape(tmp_path: Path, monkeypatch):
    source = tmp_path / "source.dump"
    source.write_bytes(b"real-backup")
    root = tmp_path / "objects"
    monkeypatch.setattr(Config, "OBJECT_STORAGE_BACKEND", "local")
    monkeypatch.setattr(Config, "OBJECT_STORAGE_LOCAL_DIR", root)

    uri = ObjectStorage().put_file(source, "backups/2026/source.dump")

    assert uri.startswith("file://")
    assert (root / "backups/2026/source.dump").read_bytes() == b"real-backup"
    with pytest.raises(ObjectStorageError):
        ObjectStorage().put_file(source, "../outside.dump")
