import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from uuid import UUID

from .errors import IntegrityError


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest_bytes(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


class FileArtifacts:
    """Atomic create-only local artifacts. S3 and retention are not implemented."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, project, kind, digest):
        project = str(UUID(project))
        if kind not in {"dataset", "config", "report"} or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
            raise ValueError("Invalid artifact identity")
        path = (self.root / project / kind / (digest[7:] + ".json")).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Artifact escapes storage root")
        return path

    def put(self, project, kind, document):
        data = canonical_bytes(document)
        digest = digest_bytes(data)
        path = self.path(project, kind, digest)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Link fully flushed bytes atomically; never expose a partially written destination.
        fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".pending-")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary, path)
            except FileExistsError:
                if path.read_bytes() != data:
                    raise IntegrityError("Existing immutable content differs") from None
        finally:
            os.unlink(temporary)
        return digest, path.relative_to(self.root).as_posix()

    def get(self, project, kind, digest):
        data = self.path(project, kind, digest).read_bytes()
        if digest_bytes(data) != digest:
            raise IntegrityError("Artifact checksum mismatch")
        return json.loads(data)
