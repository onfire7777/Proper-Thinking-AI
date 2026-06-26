# Proper Thinking AI — CLI reference

Run from the **repository root** with your virtual environment active. Uses the same backend as the desktop app, HTTP API, and MCP (`data/`, `.env`, `data/config.json`).

```text
python -m src.cli <group> <command> [arguments]
```

For top-level help:

```text
python -m src.cli --help
python -m src.cli books --help
python -m src.cli frameworks --help
```

---

## Books

### List all books

```text
python -m src.cli books list
```

Lists every uploaded book with id, title, filename, page count, chunk count, and whether embeddings exist.

---

### Show one book

```text
python -m src.cli books show <book_id>
```

Shows metadata for a single book (example: `python -m src.cli books show 1`).

---

### Upload a PDF

```text
python -m src.cli books upload <path_to_pdf>
```

Uploads a PDF into the library and prepares it for chunking and embeddings.

---

### Delete a book

```text
python -m src.cli books delete <book_id>
```

Permanently deletes a book and its chunks, embeddings, and frameworks.

---

### Semantic search in a book

```text
python -m src.cli books search <book_id> -q "<query>" [-k <top_k>]
```

Runs semantic search over book chunks and returns the best-matching excerpts (default `top_k` is 5).

---

### Ask a question about a book (RAG)

```text
python -m src.cli books ask <book_id> -q "<question>" [-k <top_k>]
```

Answers a question using retrieved book chunks and the configured LLM (requires embeddings).

---

### Check embedding status

```text
python -m src.cli books embeddings status <book_id>
```

Reports whether embeddings have been generated for the book.

---

### Generate embeddings

```text
python -m src.cli books embeddings generate <book_id>
```

Builds vector embeddings for a book (required before search, book Q&A, and framework generation).

---

## Frameworks

### List frameworks for a book

```text
python -m src.cli frameworks list <book_id>
```

Lists saved frameworks for a book with id, name, and generation status.

---

### Get a framework

```text
python -m src.cli frameworks get <book_id> <framework_id> [--view definitive|full] [--markdown] [--compact]
```

Loads one framework. Default `view=definitive` returns only the nine-section `definitive_document` (AI-safe). `view=full` includes nodes, edges, audits, and `display.*`. `--markdown` prints only the definitive markdown to stdout. While generation is running or failed, returns job status only (no partial framework body).

---

### Generate a framework

```text
python -m src.cli frameworks generate <book_id> --name "<framework_name>" [--async] [--max-chunks <n>]
```

Starts framework generation for a book. **Default:** blocks until complete and prints progress to stderr. With `--async`, returns immediately and runs the job in a detached process; poll with `frameworks wait` or `frameworks get`. `max-chunks` 0 means default.

---

### Regenerate a framework

```text
python -m src.cli frameworks regenerate <book_id> <framework_id> [--async] [--max-chunks <n>]
```

Re-runs extraction for an existing framework (overwrites nodes and definitive document). Default waits until complete; use `--async` for immediate return plus polling.

---

### Wait for framework generation (poll)

```text
python -m src.cli frameworks wait <book_id> <framework_id> [--interval <seconds>] [--timeout <seconds>] [--compact]
```

Polls until generation completes or fails (default poll every 30 seconds, timeout 7200 seconds). Use after `generate` / `regenerate` with `--async`. Progress lines go to stderr; final JSON to stdout.

---

### Delete a framework

```text
python -m src.cli frameworks delete <book_id> <framework_id>
```

Deletes a framework and its stored nodes and edges.

---

### Ask a question about a framework

```text
python -m src.cli frameworks ask <book_id> <framework_id> -q "<question>" [-k <top_k>]
```

Answers a question using the framework definitive document plus relevant book chunks.

---

### Export framework to DOCX

```text
python -m src.cli frameworks export-docx <book_id> <framework_id> -o <output_path>
```

Exports the definitive nine-section document to a Word file.

---

### Export framework to PDF

```text
python -m src.cli frameworks export-pdf <book_id> <framework_id> -o <output_path>
```

Exports the definitive document to a PDF file.

---

## Typical workflow (terminal)

**Option A — one command (default, recommended for CLI testing):**

```text
python -m src.cli books list
python -m src.cli books embeddings status 1
python -m src.cli frameworks generate 1 --name "My Framework"
python -m src.cli frameworks get 1 <framework_id> --markdown
```

The terminal stays busy until generation finishes; progress appears on stderr.

**Option B — async + poll (same pattern as MCP / Claude):**

```text
python -m src.cli frameworks generate 1 --name "My Framework" --async
python -m src.cli frameworks wait 1 <framework_id>
python -m src.cli frameworks get 1 <framework_id> --markdown
```
