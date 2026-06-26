import json
import os
import shutil
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..ingestion.pdf_parser import extract_text_from_pdf, get_book_metadata
from ..ingestion.chunker import chunk_by_paragraphs
from ..storage.database import BookDatabase
from ..storage.vector_store import VectorStore
from .app_config import data_dir, project_root
from .llm_client import LLMClient
from .reasoning import ReasoningEngine
from .mechanical_audit import run_mechanical_audit
from .phase4_metrics import log_phase4_iteration_metrics

log = logging.getLogger(__name__)


def _phase4_max_iterations() -> int:
    """Phase 4 (v2 §III): cap re-extract loops; default 2 passes total. Env PHASE4_MAX_ITERATIONS (1–5)."""
    raw = os.getenv("PHASE4_MAX_ITERATIONS", "2")
    try:
        n = int(raw)
    except ValueError:
        n = 2
    return max(1, min(n, 5))


MECHANICAL_AUDIT_REPAIR_ROUNDS = 5


# Framework generation uses ReasoningEngine.prepare_framework_nodes (includes run_definitive_fields_pass),
# then shared helpers below for edges + post-edge finalization — keep generate/regenerate in sync.

def _merge_mindmap_edge_lists(
    llm_edges: Optional[List[Dict[str, Any]]],
    dep_edges: Optional[List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """Dedupe by (from, to, type); LLM edges first, then deterministic dependency edges."""
    merged: List[Dict[str, Any]] = []
    seen: set = set()
    for e in (llm_edges or []) + (dep_edges or []):
        key = (e.get("from_node_id"), e.get("to_node_id"), e.get("edge_type"))
        if key in seen:
            continue
        seen.add(key)
        merged.append(e)
    return merged


# Manages book upload, parsing, and storage operations
class BookManager:
    
    # Initialize book manager with directories and database
    def __init__(self, books_dir: Optional[str] = None, db_path: Optional[str] = None):
        root = project_root()
        if books_dir is None:
            books_dir = str(root / "books")
        if db_path is None:
            db_path = str(data_dir() / "books.db")
        self.books_dir = books_dir
        self.db = BookDatabase(db_path)
        self.vector_store = VectorStore(persist_directory=str(data_dir() / "chroma_db"))
        self.llm_client = LLMClient()  # Uses OPENAI_API_KEY, OPENAI_MODEL from .env
        self.reasoning = ReasoningEngine(self.db, self.vector_store, self.llm_client)
        os.makedirs(books_dir, exist_ok=True)

    def _build_and_save_mindmap_edges(self, framework_id: int, log_tag: str = "") -> None:
        """
        Stage 2: LLM mindmap + deterministic deps + taxonomy + inferred uses_definition.
        log_tag: e.g. ' (regenerate)' for log lines only.
        """
        from . import langchain_framework

        nodes_with_ids = self.db.get_framework_nodes(framework_id)
        llm_edges = langchain_framework.run_mindmap_edges(nodes_with_ids)
        dep_edges = langchain_framework.build_dependency_edges(nodes_with_ids)
        merged = _merge_mindmap_edge_lists(llm_edges, dep_edges)
        merged = langchain_framework.finalize_framework_edge_list(nodes_with_ids, merged)
        if merged:
            self.db.add_framework_edges(framework_id, merged)
            log.info(
                "Framework %s%s: saved %s mindmap edge(s) (LLM=%s, deps=%s).",
                framework_id,
                log_tag,
                len(merged),
                len(llm_edges or []),
                len(dep_edges or []),
            )
        else:
            log.info("Framework %s%s: no mindmap edges generated.", framework_id, log_tag)

    def _run_extraction_phase4_loop(
        self,
        book_id: int,
        framework_id: int,
        name: str,
        max_chunks: Optional[int],
        progress_callback: Optional[Callable[[str], None]],
    ) -> Dict[str, Any]:
        """
        Definitive_System_Feedback_v2 Section III: extract → edges → agents → mechanical,
        then judgment audit; optionally re-extract with instructions until cap or no warrant.

        Re-extraction requires **mechanical audit to pass**; if it fails, the loop stops even when
        judgment would warrant another extract pass.

        Retrieval trace (chunk assembly) logs: `langchain_framework` — search log lines
        ``Framework retrieval: raw=… after_dedup=…`` and ``trimmed to ~… chars``.
        Phase 0 metrics: ``Phase 4 metrics`` / ``Phase 4 metrics detail`` after each pass.
        """
        from . import langchain_framework

        def _progress(msg: str) -> None:
            if progress_callback:
                progress_callback(msg)

        max_it = _phase4_max_iterations()
        phase4_instructions: Optional[str] = None
        judgment_history: List[Dict[str, Any]] = []
        merged_audit: Dict[str, Any] = {}

        for iteration in range(max_it):
            tag = " [Phase 4 re-extract]" if phase4_instructions else ""
            _progress(f"Extracting structure (pass {iteration + 1}/{max_it})…{tag}")
            nodes = self.reasoning.prepare_framework_nodes(
                book_id,
                name,
                max_chunks=max_chunks,
                progress_callback=progress_callback,
                phase4_instructions=phase4_instructions,
            )
            if not nodes:
                raise ValueError(
                    "Framework nodes are empty. The model returned no usable structure. Please try again."
                )
            if iteration > 0:
                self.db.delete_framework_nodes(framework_id)
                self.db.delete_framework_edges(framework_id)
            self.db.add_framework_nodes(framework_id, nodes)

            _progress("Building mindmap edges…")
            try:
                self._build_and_save_mindmap_edges(
                    framework_id, log_tag="" if iteration == 0 else " (phase4)"
                )
            except Exception as exc:
                log.warning("Framework %s: mindmap edge generation failed: %s", framework_id, exc)

            _progress("Running quality checks (Logic Auditor, meta, scope)…")
            audit_result, _ = self._finalize_framework_after_edges(framework_id, book_id, name)
            final_audit = audit_result if isinstance(audit_result, dict) else {}

            fw = self.db.get_framework(framework_id)
            mech = fw.get("mechanical_audit_result") or {}
            mechanical_passed = bool(mech.get("passed"))

            nodes_f = fw.get("nodes") or []
            edges_f = fw.get("edges") or []
            digest = langchain_framework.FrameworkGraphDigest(nodes_f, edges_f or [])
            book_row = self.db.get_book_by_id(book_id) or {}
            judgment = langchain_framework.run_judgment_audit(
                nodes_f,
                edges_f,
                digest=digest,
                book_meta=book_row,
                logic_audit_result=final_audit,
            )
            log_phase4_iteration_metrics(
                framework_id,
                iteration,
                max_it,
                nodes_f,
                edges_f or [],
                judgment,
                tag=" [Phase 4]" if phase4_instructions else "",
            )
            judgment_history.append(
                {
                    "iteration": iteration + 1,
                    "warrants_reextract": judgment.get("warrants_reextract"),
                    "findings": judgment.get("findings") or [],
                }
            )

            merged_audit = dict(final_audit)
            merged_audit["phase4"] = {
                "max_iterations": max_it,
                "completed_iterations": iteration + 1,
                "judgment_history": judgment_history,
                "last_judgment": judgment,
            }
            self.db.update_framework(
                framework_id,
                "",
                audit_result=merged_audit,
                claimed_scope=fw.get("claimed_scope"),
                evidenced_scope=fw.get("evidenced_scope"),
            )

            if not mechanical_passed:
                log.info(
                    "Phase 4: mechanical audit did not pass (pass %s); "
                    "stopping — re-extraction requires mechanical audit to pass.",
                    iteration + 1,
                )
                break

            if not judgment.get("warrants_reextract"):
                log.info(
                    "Phase 4: judgment does not warrant re-extraction (pass %s).",
                    iteration + 1,
                )
                break

            if iteration >= max_it - 1:
                log.info("Phase 4: reached max iterations (%s).", max_it)
                break

            nxt = (judgment.get("extractor_instructions") or "").strip()
            if len(nxt) < 24:
                log.info("Phase 4: empty or short extractor instructions; stopping.")
                break
            phase4_instructions = nxt

        return merged_audit

    def _persisting_progress_callback(
        self,
        framework_id: int,
        progress_callback: Optional[Callable[[str], None]],
    ) -> Callable[[str], None]:
        def _progress(msg: str) -> None:
            try:
                self.db.set_framework_generation_progress(framework_id, msg)
            except Exception:
                log.exception(
                    "Failed to persist generation progress (framework_id=%s)", framework_id
                )
            if progress_callback:
                progress_callback(msg)

        return _progress

    def _async_job_payload(self, framework_id: int) -> Dict[str, Any]:
        from src.core.framework_display import build_framework_job_status_payload

        fw = self.db.get_framework(framework_id)
        if not fw:
            raise ValueError(f"Framework with ID {framework_id} not found")
        return build_framework_job_status_payload(fw)

    def _execute_framework_generation_job(
        self,
        book_id: int,
        framework_id: int,
        name: str,
        max_chunks: Optional[int],
        progress_callback: Optional[Callable[[str], None]],
    ) -> Dict[str, Any]:
        """Run Phase 4 extraction loop and mark framework generation_status completed/failed."""
        progress = self._persisting_progress_callback(framework_id, progress_callback)
        try:
            audit_result = self._run_extraction_phase4_loop(
                book_id, framework_id, name, max_chunks, progress
            )
            self.db.mark_framework_generation_completed(framework_id)
            return audit_result
        except Exception as exc:
            self.db.mark_framework_generation_failed(framework_id, str(exc))
            raise
    def _finalize_framework_after_edges(
        self,
        framework_id: int,
        book_id: int,
        name: str,
    ) -> Tuple[Dict[str, Any], Optional[str]]:
        """
        Single canonical path: agents → persist scope/audit/epistemic → definitive document → mechanical audit.
        Returns (audit_result, definitive_md last written).
        """
        from . import langchain_framework

        fw = self.db.get_framework(framework_id)
        nodes_with_ids = fw.get("nodes") or []
        edges = fw.get("edges") or []
        book_row = self.db.get_book_by_id(book_id) or {}
        nodes_updated, audit_result, scope_row, edges_out = self.reasoning.run_agents_over_graph(
            nodes_with_ids, edges, name, book_meta=book_row, book_id=book_id
        )
        if langchain_framework.framework_edge_signature(edges) != langchain_framework.framework_edge_signature(
            edges_out
        ):
            self.db.add_framework_edges(framework_id, edges_out)
        book_row = self.db.get_book_by_id(book_id) or book_row
        self.db.update_framework(
            framework_id,
            "",
            audit_result=audit_result,
            claimed_scope=scope_row.get("claimed_scope"),
            evidenced_scope=scope_row.get("evidenced_scope"),
        )
        overview_prose = scope_row.get("overview_prose") or {}
        try:
            self.db.set_framework_overview_prose_json(
                framework_id,
                json.dumps(overview_prose, ensure_ascii=False) if overview_prose else None,
            )
        except Exception as exc:
            log.warning("Framework %s: overview prose JSON persist failed: %s", framework_id, exc)
        self.db.update_framework_nodes_epistemic(framework_id, nodes_updated)

        definitive_md: Optional[str] = None
        try:
            fw_full = self.db.get_framework(framework_id)
            fw_full["claimed_scope"] = scope_row.get("claimed_scope")
            fw_full["evidenced_scope"] = scope_row.get("evidenced_scope")
            fw_full["overview_prose"] = overview_prose
            definitive_md = langchain_framework.render_definitive_document(fw_full, book_row)
            if definitive_md:
                self.db.set_framework_definitive_document(framework_id, definitive_md)
        except Exception as exc:
            log.warning(
                "Framework %s: definitive document generation failed: %s",
                framework_id,
                exc,
            )

        self._run_and_store_mechanical_audit(framework_id, book_id, definitive_md)
        return audit_result, definitive_md

    def _run_and_store_mechanical_audit(
        self,
        framework_id: int,
        book_id: int,
        definitive_md: Optional[str] = None,
    ) -> None:
        """Phase 3: mechanical audit, deterministic repair loop (links/quotes), up to 5 rounds; final audit stored."""
        from . import langchain_framework
        from .mechanical_repair import apply_mechanical_repairs_for_audit

        try:
            book_row = self.db.get_book_by_id(book_id) or {}
            md: Optional[str] = definitive_md
            result: Dict[str, Any] = {"passed": True, "failures": [], "checks_run": []}

            for _ in range(MECHANICAL_AUDIT_REPAIR_ROUNDS):
                fw = self.db.get_framework(framework_id)
                if not fw:
                    return
                nodes = fw.get("nodes") or []
                edges = fw.get("edges") or []
                doc = (md if md is not None else (fw.get("definitive_document") or "")) or ""
                result = run_mechanical_audit(
                    nodes,
                    edges,
                    definitive_document=doc or None,
                    book_id=book_id,
                    db=self.db,
                )
                if result.get("passed"):
                    break
                _, _, changed = apply_mechanical_repairs_for_audit(nodes, edges, result)
                if not changed:
                    break
                self.db.sync_framework_nodes_graph_fields(framework_id, nodes)
                self.db.add_framework_edges(framework_id, edges)
                fw2 = self.db.get_framework(framework_id)
                md = langchain_framework.render_definitive_document(fw2, book_row)
                if md:
                    self.db.set_framework_definitive_document(framework_id, md)

            fw_final = self.db.get_framework(framework_id)
            if fw_final:
                doc_final = (md if md is not None else (fw_final.get("definitive_document") or "")) or ""
                result = run_mechanical_audit(
                    fw_final.get("nodes") or [],
                    fw_final.get("edges") or [],
                    definitive_document=doc_final or None,
                    book_id=book_id,
                    db=self.db,
                )
            self.db.set_framework_mechanical_audit(framework_id, result)
        except Exception as exc:
            log.warning("Framework %s: mechanical audit failed: %s", framework_id, exc)
    
    # Upload and process a PDF book
    def upload_book(self, file_path: str) -> Dict[str, any]:
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        if not file_path.lower().endswith('.pdf'):
            raise ValueError("Only PDF files are supported")
        
        filename = os.path.basename(file_path)
        dest_path = os.path.join(self.books_dir, filename)
        
        if os.path.exists(dest_path):
            dest_path = self._get_unique_filename(dest_path)
        
        shutil.copy2(file_path, dest_path)
        
        metadata = get_book_metadata(dest_path)
        pages_data = extract_text_from_pdf(dest_path)
        
        chunks = chunk_by_paragraphs(pages_data)
        
        book_id = self.db.add_book(
            title=metadata["title"],
            filename=metadata["filename"],
            file_path=dest_path,
            total_pages=metadata["total_pages"],
            author=metadata.get("author") or None,
            edition_isbn=metadata.get("edition_isbn") or None,
            page_numbering_basis=metadata.get("page_numbering_basis") or "Digital",
            target_audience=metadata.get("target_audience") or None,
        )
        
        self.db.add_chunks(book_id, chunks)

        try:
            from .structural_analysis import build_structural_analysis

            sa = build_structural_analysis(chunks, metadata.get("total_pages"))
            self.db.set_book_structural_analysis(book_id, sa)
        except Exception as exc:
            log.warning("Book %s: structural analysis (Rule 35) failed: %s", book_id, exc)

        return {
            'book_id': book_id,
            'title': metadata['title'],
            'filename': metadata['filename'],
            'total_pages': metadata['total_pages'],
            'chunk_count': len(chunks)
        }
    
    # Generate unique filename if file already exists
    def _get_unique_filename(self, file_path: str) -> str:
        base, ext = os.path.splitext(file_path)
        counter = 1
        while os.path.exists(file_path):
            file_path = f"{base}_{counter}{ext}"
            counter += 1
        return file_path
    
    # List all uploaded books
    def list_books(self) -> List[Dict[str, any]]:
        books = self.db.get_all_books()
        result = []
        
        for book in books:
            chunk_count = self.db.get_chunk_count(book['id'])
            embeddings_status = self.db.get_embeddings_status(book['id'])
            result.append({
                'id': book['id'],
                'title': book['title'],
                'filename': book['filename'],
                'upload_date': book['upload_date'],
                'total_pages': book['total_pages'],
                'chunk_count': chunk_count,
                'embeddings_generated': embeddings_status
            })
        
        return result
    
    # Get detailed information about a book
    def get_book_info(self, book_id: int) -> Dict[str, any]:
        book = self.db.get_book_by_id(book_id)
        if not book:
            raise ValueError(f"Book with ID {book_id} not found")
        
        chunks = self.db.get_chunks_by_book_id(book_id)
        
        embeddings_status = self.db.get_embeddings_status(book_id)
        return {
            'id': book['id'],
            'title': book['title'],
            'filename': book['filename'],
            'upload_date': book['upload_date'],
            'total_pages': book['total_pages'],
            'chunk_count': len(chunks),
            'file_path': book['file_path'],
            'embeddings_generated': embeddings_status
        }
    
    # Get all chunks for a book
    def get_book_chunks(self, book_id: int) -> List[Dict[str, any]]:
        
        book = self.db.get_book_by_id(book_id)
        if not book:
            raise ValueError(f"Book with ID {book_id} not found")
        
        return self.db.get_chunks_by_book_id(book_id)
    
    # Generate embeddings for all chunks of a book
    def generate_embeddings(self, book_id: int) -> Dict[str, any]:
        
        book = self.db.get_book_by_id(book_id)
        if not book:
            raise ValueError(f"Book with ID {book_id} not found")
        
        chunks = self.db.get_chunks_by_book_id(book_id)
        if not chunks:
            raise ValueError(f"No chunks found for book {book_id}")
        
        chunks_with_ids = [
            {
                'id': chunk['id'],
                'page_number': chunk['page_number'],
                'chunk_index': chunk['chunk_index'],
                'chunk_text': chunk['chunk_text']
            }
            for chunk in chunks
        ]
        
        self.vector_store.add_chunks(book_id, chunks_with_ids)
        self.db.set_embeddings_generated(book_id, 1)
        
        return {
            'book_id': book_id,
            'chunks_embedded': len(chunks),
            'status': 'success'
        }
    
    # Search for relevant chunks in a book using semantic search
    def search_book(self, book_id: int, query: str, top_k: int = 5) -> List[Dict[str, any]]:
        
        book = self.db.get_book_by_id(book_id)
        if not book:
            raise ValueError(f"Book with ID {book_id} not found")
        
        if not self.db.get_embeddings_status(book_id):
            raise ValueError(f"Embeddings not generated for book {book_id}. Run 'embed' command first.")
        
        search_results = self.vector_store.search(book_id, query, top_k)
        
        results = []
        for result in search_results:
            chunk_id = result['chunk_id']
            chunk = self.db.get_chunk_by_id(chunk_id)
            if chunk:
                results.append({
                    'chunk_id': chunk_id,
                    'page_number': result['page_number'],
                    'chunk_index': result['chunk_index'],
                    'text': result['text'],
                    'similarity': 1 - result['distance'] if result['distance'] is not None else None
                })
        
        return results

    # Answer a question about a specific book using strict source-grounded reasoning
    def answer_question(self, book_id: int, question: str, top_k: int = 5) -> Dict[str, any]:
        return self.reasoning.answer_question(book_id, question, top_k)

    # --- Chat UI persistence (per-book conversations) ---

    def chat_create_conversation(self, book_id: int, title: str = "") -> int:
        return self.db.create_chat_conversation(book_id, title)

    def chat_list_conversations(self, book_id: int) -> List[Dict[str, Any]]:
        return self.db.list_chat_conversations(book_id)

    def chat_get_conversation(self, conversation_id: int) -> Optional[Dict[str, Any]]:
        return self.db.get_chat_conversation(conversation_id)

    def chat_update_conversation_title(self, conversation_id: int, title: str) -> None:
        self.db.update_chat_conversation_title(conversation_id, title)

    def chat_delete_conversation(self, conversation_id: int) -> None:
        self.db.delete_chat_conversation(conversation_id)

    def chat_add_message(
        self,
        conversation_id: int,
        role: str,
        content: str,
        used_chunks: Optional[List[Dict[str, Any]]] = None,
        status: Optional[str] = None,
    ) -> int:
        return self.db.add_chat_message(conversation_id, role, content, used_chunks, status)

    def chat_list_messages(self, conversation_id: int) -> List[Dict[str, Any]]:
        return self.db.list_chat_messages(conversation_id)

    # Generate and save a framework for a book (node-based structure)
    def generate_framework(
        self,
        book_id: int,
        name: str,
        max_chunks: Optional[int] = None,
        progress_callback: Optional[Callable[[str], None]] = None,
        *,
        wait: bool = True,
    ) -> Dict[str, any]:
        book = self.db.get_book_by_id(book_id)
        if not book:
            raise ValueError(f"Book with ID {book_id} not found")
        framework_id = self.db.add_framework(
            book_id,
            name,
            "",
            audit_result=None,
            generation_status="running",
        )
        self.db.mark_framework_generation_running(framework_id)

        if not wait:
            from src.core.framework_job_spawn import spawn_detached_framework_job

            spawn_detached_framework_job(book_id, framework_id, name, max_chunks)
            return self._async_job_payload(framework_id)

        audit_result = self._execute_framework_generation_job(
            book_id, framework_id, name, max_chunks, progress_callback
        )

        fw = self.db.get_framework(framework_id)
        out = {
            "framework_id": framework_id,
            "book_id": book_id,
            "name": name,
            "content": fw["content"],
            "audit_result": audit_result,
        }
        from src.core.framework_display import augmentation_for_framework_response

        out.update(augmentation_for_framework_response(fw))
        return out

    # List saved frameworks for a book
    def list_frameworks(self, book_id: int) -> List[Dict[str, any]]:
        book = self.db.get_book_by_id(book_id)
        if not book:
            raise ValueError(f"Book with ID {book_id} not found")
        return self.db.list_frameworks_for_book(book_id)

    # Get a specific framework by ID (nodes, edges, definitive_document from DB)
    def get_framework(self, framework_id: int) -> Dict[str, any]:
        framework = self.db.get_framework(framework_id)
        if not framework:
            raise ValueError(f"Framework with ID {framework_id} not found")
        return framework

    # Get nodes for a framework (structured mind map); reuses nodes loaded by get_framework
    def get_framework_nodes(self, framework_id: int) -> List[Dict[str, any]]:
        fw = self.db.get_framework(framework_id)
        if not fw:
            raise ValueError(f"Framework with ID {framework_id} not found")
        return fw.get("nodes", [])

    # Re-run extraction for an existing framework (overwrites nodes)
    def regenerate_framework(
        self,
        framework_id: int,
        max_chunks: Optional[int] = None,
        progress_callback: Optional[Callable[[str], None]] = None,
        *,
        wait: bool = True,
    ) -> Dict[str, any]:
        fw = self.db.get_framework(framework_id)
        if not fw:
            raise ValueError(f"Framework with ID {framework_id} not found")
        book_id = fw["book_id"]
        name = fw["name"]

        self.db.mark_framework_generation_running(framework_id)
        self.db.delete_framework_nodes(framework_id)
        self.db.delete_framework_edges(framework_id)

        if not wait:
            from src.core.framework_job_spawn import spawn_detached_framework_job

            spawn_detached_framework_job(book_id, framework_id, name, max_chunks)
            return self._async_job_payload(framework_id)

        audit_result = self._execute_framework_generation_job(
            book_id, framework_id, name, max_chunks, progress_callback
        )

        fw = self.db.get_framework(framework_id)
        out = {
            "framework_id": framework_id,
            "book_id": book_id,
            "name": name,
            "content": fw["content"],
            "audit_result": audit_result,
        }
        from src.core.framework_display import augmentation_for_framework_response

        out.update(augmentation_for_framework_response(fw))
        return out

    # Delete a framework
    def delete_framework(self, framework_id: int) -> None:
        fw = self.db.get_framework(framework_id)
        if not fw:
            raise ValueError(f"Framework {framework_id} not found")
        self.db.delete_framework(framework_id)

    # Answer a question about a framework using framework + book sources
    def answer_question_about_framework(
        self, book_id: int, framework_id: int, question: str, top_k: int = 5
    ) -> Dict[str, any]:
        return self.reasoning.answer_question_about_framework(
            book_id, framework_id, question, top_k
        )

    # Pre-warm / validate OpenAI model access
    def prewarm_llm_model(self) -> bool:
        return self.llm_client.prewarm_model()
    
    # Delete a book and all associated data
    def delete_book(self, book_id: int):
        book = self.db.get_book_by_id(book_id)
        if not book:
            raise ValueError(f"Book with ID {book_id} not found")
        
        file_path = book.get('file_path')
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass
        
        self.vector_store.delete_collection(book_id)
        self.db.delete_book(book_id)

