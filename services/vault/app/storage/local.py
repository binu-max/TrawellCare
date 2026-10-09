from pathlib import Path


class LocalFilesystemStorage:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, object_key: str) -> Path:
        target = (self.root / object_key).resolve()
        if not str(target).startswith(str(self.root.resolve())):
            raise ValueError("Invalid object key")
        return target

    def reserve(self, object_key: str) -> Path:
        path = self.path_for(object_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def write_bytes(self, object_key: str, data: bytes) -> None:
        path = self.reserve(object_key)
        path.write_bytes(data)

    def read_bytes(self, object_key: str) -> bytes:
        path = self.path_for(object_key)
        if not path.is_file():
            raise FileNotFoundError(object_key)
        return path.read_bytes()

    def size(self, object_key: str) -> int:
        path = self.path_for(object_key)
        return path.stat().st_size
