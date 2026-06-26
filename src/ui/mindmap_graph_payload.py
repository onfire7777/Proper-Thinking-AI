"""
Graph payload for the Obsidian-style mindmap (WebView + vis-network).

Single filtering rules for framework → JSON (Phases 1–3). Matches former QGraphics mindmap:
- Section (TOC) nodes excluded.
- Only edges whose type is in MINDMAP_VISIBLE_EDGE_TYPES and that do not touch a section node.
- Only nodes that participate in at least one such edge (non-section).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

# Phase 6: payloads at or above this node count include meta.large_graph for lighter physics + LOD hints in JS.
LARGE_GRAPH_NODE_THRESHOLD = 220

# Same set as legacy mindmap: only these edge types appear on the graph canvas.
MINDMAP_VISIBLE_EDGE_TYPES = frozenset(
    {
        "leads_to",
        "implemented_by",
        "drives_step",
        "warns",
        "constrains",
        "uses_definition",
        "supports",
    }
)


def _node_type_lower(n: Dict[str, Any]) -> str:
    return (n.get("node_type") or n.get("type") or "section").strip().lower()


def _hidden_section_ids(nodes: List[Dict[str, Any]]) -> Set[int]:
    out: Set[int] = set()
    for n in nodes or []:
        if _node_type_lower(n) != "section":
            continue
        try:
            out.add(int(n.get("id")))
        except (TypeError, ValueError):
            continue
    return out


def build_graph_payload(framework: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Build GraphPayload v1 for the interactive graph view.

    Returns:
        ``{"version": 1, "nodes": [...], "edges": [...]}``
        Node ids are strings; ``label`` is display title; ``edge_type`` is lowercased when present.
    """
    empty: Dict[str, Any] = {"version": 1, "nodes": [], "edges": []}
    if not framework:
        return empty

    nodes: List[Dict[str, Any]] = framework.get("nodes") or []
    edges: List[Dict[str, Any]] = framework.get("edges") or []

    visible_edges: List[Dict[str, Any]] = []
    for e in edges:
        et = (e.get("edge_type") or "").strip().lower()
        if et in MINDMAP_VISIBLE_EDGE_TYPES:
            visible_edges.append(e)

    hidden = _hidden_section_ids(nodes)
    mindmap_edges: List[Dict[str, Any]] = []
    for e in visible_edges:
        try:
            fid = int(e.get("from_node_id"))
            tid = int(e.get("to_node_id"))
        except (TypeError, ValueError):
            continue
        if fid in hidden or tid in hidden:
            continue
        mindmap_edges.append(e)

    node_ids_in_edges: Set[int] = set()
    for e in mindmap_edges:
        try:
            node_ids_in_edges.add(int(e.get("from_node_id")))
            node_ids_in_edges.add(int(e.get("to_node_id")))
        except (TypeError, ValueError):
            pass

    by_id: Dict[int, Dict[str, Any]] = {}
    for n in nodes:
        if n.get("id") is None:
            continue
        try:
            nid = int(n["id"])
        except (TypeError, ValueError):
            continue
        by_id[nid] = n

    nodes_out: List[Dict[str, Any]] = []
    for nid in sorted(node_ids_in_edges):
        n = by_id.get(nid)
        if n is not None and _node_type_lower(n) == "section":
            continue
        if n is not None:
            title = (n.get("title") or "").strip() or f"Node {nid}"
            nt = _node_type_lower(n)
        else:
            title = f"Node {nid}"
            nt = "unknown"
        nodes_out.append(
            {
                "id": str(nid),
                "label": title,
                "node_type": nt,
            }
        )

    edges_out: List[Dict[str, Any]] = []
    for e in mindmap_edges:
        try:
            fid = int(e.get("from_node_id"))
            tid = int(e.get("to_node_id"))
        except (TypeError, ValueError):
            continue
        et = (e.get("edge_type") or "").strip().lower()
        edges_out.append(
            {
                "from": str(fid),
                "to": str(tid),
                "edge_type": et,
            }
        )

    result: Dict[str, Any] = {"version": 1, "nodes": nodes_out, "edges": edges_out}
    if len(nodes_out) >= LARGE_GRAPH_NODE_THRESHOLD:
        result["meta"] = {
            "large_graph": True,
            "node_count": len(nodes_out),
            "edge_count": len(edges_out),
        }
    return result
