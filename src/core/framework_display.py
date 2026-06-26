"""
Canonical framework presentation for API / MCP / generate responses.

Mirrors the desktop Framework tab: definitive nine-section markdown (same headings as
``mechanical_audit``), Quality Audit as plain markdown, and the static generation pipeline blurb.
"""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple

from src.core.logic_audit_normalize import prepare_audit_result_for_ui
from src.core.mechanical_audit import definitive_document_for_export

# Same heading variants as mechanical_audit.definitive_document_sections (order = UI / v2 doc).
SECTION_DEFINITIONS: Tuple[Tuple[frozenset, str, str], ...] = (
    (frozenset({"## 1. Metadata", "## 1 Metadata"}), "metadata", "1. Metadata"),
    (frozenset({"## 2. Overview", "## 2 Overview"}), "overview", "2. Overview"),
    (frozenset({"## 3. Definitions", "## 3 Definitions"}), "definitions", "3. Definitions"),
    (frozenset({"## 4. Principles", "## 4 Principles"}), "principles", "4. Principles"),
    (frozenset({"## 5. Steps", "## 5 Steps"}), "steps", "5. Steps"),
    (frozenset({"## 6. Warnings", "## 6 Warnings"}), "warnings", "6. Warnings"),
    (frozenset({"## 7. Constraints", "## 7 Constraints"}), "constraints", "7. Constraints"),
    (frozenset({"## 8. Dependency Map", "## 8 Dependency Map"}), "dependency_map", "8. Dependency Map"),
    (frozenset({"## 9. Scope and Limits", "## 9 Scope and Limits"}), "scope_and_limits", "9. Scope and Limits"),
)

GENERATION_PIPELINE_MARKDOWN = "\n".join(
    [
        "1. **Retrieval.** Fetch relevant book excerpts for definitions, principles, steps, warnings (multi-bucket retrieval).",
        "2. **Extraction.** Generate structured node tree from excerpts only — no outside knowledge (extraction agent).",
        "3. **Context excerpts.** Validate node types; attach raw book excerpts per node (±500-word window, light normalization; no context-refinement LLM).",
        "4. **Mindmap.** Build relationships between nodes (edge agent + dependency rules).",
        "5. **Epistemic pass.** Label claims as fact, interpretation, or assumption.",
        "6. **Logic Audit.** Flag contradictions, gaps, and assumptions.",
        "7. **Meta & scope.** Infer purpose/assumptions (internal) and extract claimed vs evidenced scope for the definitive Overview.",
        "8. **Governor.** Surface audit result for the Quality Audit section.",
        "9. **Definitive document.** Render fixed-structure markdown from nodes and edges; run mechanical checks.",
    ]
)


def split_definitive_sections(markdown: str) -> Dict[str, Any]:
    """
    Split definitive markdown on the nine canonical ``## N. …`` headings.

    Returns ordered section bodies plus preamble (lines before the first matched heading).
    """
    md = (markdown or "").strip()
    if not md:
        return {
            "preamble_markdown": "",
            "ordered_sections": [],
            "sections_by_id": {},
            "missing_section_ids": [s[1] for s in SECTION_DEFINITIONS],
            "missing_section_titles": [s[2] for s in SECTION_DEFINITIONS],
            "nine_sections_complete": False,
        }

    lines = md.splitlines()
    found: Dict[str, Tuple[int, str, str]] = {}
    for i, raw in enumerate(lines):
        stripped = raw.strip()
        for headings, key, title in SECTION_DEFINITIONS:
            if stripped in headings:
                if key not in found:
                    found[key] = (i, title, stripped)
                break

    ordered_meta = sorted(found.items(), key=lambda kv: kv[1][0])
    preamble_lines = lines[: ordered_meta[0][1][0]] if ordered_meta else lines
    preamble = "\n".join(preamble_lines).strip()

    ordered_sections: List[Dict[str, Any]] = []
    sections_by_id: Dict[str, str] = {}
    for j, (key, (idx, title, heading_line)) in enumerate(ordered_meta):
        next_idx = ordered_meta[j + 1][1][0] if j + 1 < len(ordered_meta) else len(lines)
        body = "\n".join(lines[idx + 1 : next_idx]).strip()
        ordered_sections.append(
            {
                "id": key,
                "ordinal": j + 1,
                "title": title,
                "heading_line": heading_line,
                "markdown": body,
            }
        )
        sections_by_id[key] = body

    expected_ids = [s[1] for s in SECTION_DEFINITIONS]
    missing_ids = [k for k in expected_ids if k not in found]
    missing_titles = [s[2] for s in SECTION_DEFINITIONS if s[1] in missing_ids]

    return {
        "preamble_markdown": preamble,
        "ordered_sections": ordered_sections,
        "sections_by_id": sections_by_id,
        "missing_section_ids": missing_ids,
        "missing_section_titles": missing_titles,
        "nine_sections_complete": len(missing_ids) == 0,
    }


def _append_bullets(lines: List[str], title: str, items: List[str], limit: int = 40) -> None:
    if not items:
        return
    lines.append(f"**{title}** ({len(items)})")
    for it in items[:limit]:
        lines.append(f"- {it}")
    if len(items) > limit:
        lines.append(f"- … and {len(items) - limit} more.")


def format_quality_audit_markdown(framework: Dict[str, Any]) -> str:
    """Plain-markdown summary aligned with the Framework tab Quality Audit panel."""
    lines: List[str] = []
    mech = framework.get("mechanical_audit_result")
    has_doc = bool((framework.get("definitive_document") or "").strip())
    if isinstance(mech, dict):
        lines.append("## Mechanical audit (Phase 3)")
        lines.append(f"- **Passed:** {mech.get('passed', True)}")
        ct = mech.get("checked_at")
        if ct:
            lines.append(f"- **Checked at:** {ct}")
        for flist, label in (
            (mech.get("failures") or [], "Failures"),
            (mech.get("warnings") or [], "Warnings"),
        ):
            if not flist:
                continue
            lines.append(f"- **{label}:**")
            for f in flist[:30]:
                if not isinstance(f, dict):
                    lines.append(f"  - {f}")
                    continue
                cid = f.get("check_id") or "check"
                msg = (f.get("message") or "").replace("\n", " ")
                det = (f.get("detail") or "").replace("\n", " ")
                extra = f" — _{det}_" if det else ""
                lines.append(f"  - **{cid}**: {msg}{extra}")
            if len(flist) > 30:
                lines.append(f"  - … and {len(flist) - 30} more.")
    elif has_doc and mech is None:
        lines.append("## Mechanical audit (Phase 3)")
        lines.append(
            "- _No mechanical audit on file — run **Regenerate** in the app to record Phase 3 checks._"
        )

    ar = framework.get("audit_result")
    if not isinstance(ar, dict) or not ar:
        if lines:
            lines.append("")
        lines.append("## Logic Auditor (Governor)")
        lines.append("- _No Logic Auditor data available._")
        return "\n".join(lines).strip()

    lines.append("")
    lines.append("## Logic Auditor (Governor)")
    norm = prepare_audit_result_for_ui(ar)
    gc = norm.get("graph_critical_issues") or []
    lc = norm.get("logic_critical_issues") or []
    hc = norm.get("hybrid_critical_issues") or []
    lw = norm.get("logic_warnings") or []
    hw = norm.get("hybrid_warnings") or []

    if not (gc or lc or hc):
        lines.append(
            "- **Review:** no critical issues in graph, framework logic, or hybrid categories."
        )
    else:
        _append_bullets(lines, "Graph — critical", gc)
        _append_bullets(lines, "Framework — critical", lc)
        _append_bullets(lines, "Hybrid — critical", hc)

    if lw or hw:
        _append_bullets(lines, "Logic warnings", lw)
        _append_bullets(lines, "Hybrid warnings", hw)

    p4 = norm.get("phase4") if isinstance(norm.get("phase4"), dict) else None
    if p4:
        lines.append("")
        lines.append("### Phase 4 judgment")
        lines.append(f"```json\n{json.dumps(p4, ensure_ascii=False, indent=2)[:8000]}\n```")

    note = norm.get("reasoning_quality_note")
    if note:
        lines.append("")
        lines.append(f"_Quality note:_ {note}")

    return "\n".join(lines).strip()


def build_display_payload(framework: Dict[str, Any]) -> Dict[str, Any]:
    """Structured view matching the Framework tab (content + audit + pipeline blurb)."""
    doc = definitive_document_for_export(framework).strip()
    split = split_definitive_sections(doc)
    overview = framework.get("overview_prose")
    claimed = framework.get("claimed_scope")
    evidenced = framework.get("evidenced_scope")
    return {
        "definitive_document_markdown": doc,
        "overview_prose": overview if isinstance(overview, dict) else None,
        "claimed_scope": claimed,
        "evidenced_scope": evidenced,
        "preamble_markdown": split["preamble_markdown"],
        "sections": split["ordered_sections"],
        "sections_by_id": split["sections_by_id"],
        "nine_sections_complete": split["nine_sections_complete"],
        "missing_section_ids": split["missing_section_ids"],
        "missing_section_titles": split["missing_section_titles"],
        "quality_audit_markdown": format_quality_audit_markdown(framework),
        "generation_pipeline_markdown": GENERATION_PIPELINE_MARKDOWN,
    }


def is_framework_content_gated(framework: Dict[str, Any]) -> bool:
    """While running or failed, consumers must not see partial nodes/display/document."""
    status = (framework.get("generation_status") or "").strip().lower()
    return status in ("running", "failed")


FRAMEWORK_GET_VIEW_FULL = "full"
FRAMEWORK_GET_VIEW_DEFINITIVE = "definitive"


def normalize_framework_get_view(view: Optional[str], *, default: str = FRAMEWORK_GET_VIEW_FULL) -> str:
    """Map API/MCP view aliases to ``full`` or ``definitive``."""
    v = (view or "").strip().lower()
    if v in ("definitive", "slim", "document", "doc", "markdown", "ai"):
        return FRAMEWORK_GET_VIEW_DEFINITIVE
    if v in ("full", "complete", "all", "verbose", "graph"):
        return FRAMEWORK_GET_VIEW_FULL
    if not v:
        return default
    raise ValueError(f"Invalid framework view {view!r}; use 'definitive' or 'full'.")


def build_framework_definitive_payload(framework: Dict[str, Any]) -> Dict[str, Any]:
    """
    Slim framework retrieval for AI context: nine-section definitive markdown only.

    Excludes nodes, edges, audits, and display.* duplicates to avoid token abuse.
    """
    doc = definitive_document_for_export(framework).strip()
    split = split_definitive_sections(doc)
    fid = framework.get("id")
    status = (framework.get("generation_status") or "").strip() or "completed"
    return {
        "view": FRAMEWORK_GET_VIEW_DEFINITIVE,
        "framework_id": fid,
        "id": fid,
        "book_id": framework.get("book_id"),
        "name": framework.get("name"),
        "generation_status": status,
        "definitive_document": doc,
        "nine_sections_complete": split["nine_sections_complete"],
        "missing_section_ids": split["missing_section_ids"],
        "missing_section_titles": split["missing_section_titles"],
        "usage_note": (
            "Canonical framework text for AI: use definitive_document verbatim (nine sections). "
            "For mindmap graph data use mindmap_* tools, not framework_get view=full."
        ),
    }


def build_framework_job_status_payload(framework: Dict[str, Any]) -> Dict[str, Any]:
    """Slim poll response for async generation (no nodes, edges, or display)."""
    status = (framework.get("generation_status") or "").strip().lower() or None
    fid = framework.get("id")
    note: Optional[str] = None
    if status == "running":
        note = (
            "Generation in progress. Poll framework_get until generation_status "
            "is completed or failed."
        )
    elif status == "failed":
        note = (
            "Generation failed. Review generation_error and call framework_regenerate to retry."
        )
    return {
        "view": "job",
        "framework_id": fid,
        "id": fid,
        "book_id": framework.get("book_id"),
        "name": framework.get("name"),
        "generation_status": framework.get("generation_status"),
        "generation_error": framework.get("generation_error"),
        "generation_started_at": framework.get("generation_started_at"),
        "generation_finished_at": framework.get("generation_finished_at"),
        "generation_last_log_line": framework.get("generation_last_log_line"),
        "note": note,
    }


def enrich_framework_dict(framework: Dict[str, Any]) -> Dict[str, Any]:
    """Deep copy + ``display`` block for API/MCP consumers (does not mutate input)."""
    out = deepcopy(framework)
    out["display"] = build_display_payload(out)
    return out


def augmentation_for_framework_response(framework: Dict[str, Any]) -> Dict[str, Any]:
    """Small dict to merge into ``generate_framework`` / ``regenerate_framework`` results."""
    disp = build_display_payload(framework)
    return {
        "definitive_document": (framework.get("definitive_document") or "").strip(),
        "display": disp,
    }
