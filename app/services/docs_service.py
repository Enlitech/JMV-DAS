from __future__ import annotations

from pathlib import Path


class DocsService:
    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root is not None else Path(__file__).resolve().parents[2]

    def path_for(self, doc_name: str) -> Path:
        return self.root / "docs" / str(doc_name)

    def read_markdown(self, doc_name: str) -> str:
        return self.path_for(doc_name).read_text(encoding="utf-8")
