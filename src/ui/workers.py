"""Modular background workers for long-running tasks. Keeps UI responsive."""

from typing import Any, Dict, List

from PyQt6.QtCore import QThread, pyqtSignal

from ..core.book_manager import BookManager


class BaseTaskWorker(QThread):
    """Base worker: run _run() in thread, emit finished(result) or error(str)."""

    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def run(self) -> None:
        try:
            result = self._run()
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))

    def _run(self) -> Any:
        """Override in subclasses. Return value is emitted as finished(result)."""
        raise NotImplementedError


class UploadBookWorker(BaseTaskWorker):
    """Runs book_manager.upload_book(file_path) in a background thread."""

    def __init__(self, book_manager: BookManager, file_path: str):
        super().__init__()
        self._manager = book_manager
        self._path = file_path

    def _run(self) -> Dict[str, Any]:
        return self._manager.upload_book(self._path)


class UploadBooksWorker(BaseTaskWorker):
    """Upload multiple PDFs sequentially. Best-effort: continues on per-file errors."""

    def __init__(self, book_manager: BookManager, file_paths: List[str]):
        super().__init__()
        self._manager = book_manager
        self._paths = list(file_paths)

    def _run(self) -> Dict[str, Any]:
        results: List[Dict[str, Any]] = []
        errors: List[Dict[str, str]] = []
        for path in self._paths:
            try:
                r = self._manager.upload_book(path)
                results.append(r)
            except Exception as exc:
                errors.append({"path": path, "message": str(exc)})
        return {"results": results, "errors": errors}


class GenerateEmbeddingsWorker(BaseTaskWorker):
    """Runs book_manager.generate_embeddings(book_id) in a background thread."""

    def __init__(self, book_manager: BookManager, book_id: int):
        super().__init__()
        self._manager = book_manager
        self._book_id = book_id

    def _run(self) -> Dict[str, Any]:
        return self._manager.generate_embeddings(self._book_id)
