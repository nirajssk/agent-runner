"""
Discovers agent definitions by scanning for *.agent.py files.

Convention — a file is a valid agent definition if it contains at least a
PROMPT (or AGENT_PROMPT) module-level string assignment.  All other variables
are optional:

    NAME        = "My Agent"          # defaults to filename
    DESCRIPTION = "Does things"       # optional
    PROMPT      = "..."               # required (use triple-quotes in real files)
    TOOLS       = ["Read", "Glob"]    # defaults to ["Read","Glob","Grep"]
    MAX_TURNS   = 20                  # defaults to 20
    PERMISSION_MODE = "acceptEdits"   # defaults to "acceptEdits"

Files are parsed with ast.parse — no code is ever executed.
"""

from __future__ import annotations

import ast
from pathlib import Path


def _str_val(node: ast.expr) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    # support implicit string concatenation  "foo" "bar"
    if isinstance(node, ast.JoinedStr):
        return None  # f-strings: skip
    return None


def _int_val(node: ast.expr) -> int | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return node.value
    return None


def _list_val(node: ast.expr) -> list[str] | None:
    if not isinstance(node, ast.List):
        return None
    items = []
    for elt in node.elts:
        v = _str_val(elt)
        if v:
            items.append(v)
    return items or None


_WANTED = {"NAME", "DESCRIPTION", "PROMPT", "AGENT_PROMPT", "TOOLS", "MAX_TURNS", "PERMISSION_MODE"}


def _extract_vars(tree: ast.Module) -> dict:
    """Walk top-level assignments and pull out known variable names."""
    result: dict = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name) or target.id not in _WANTED:
                continue
            name = target.id
            if name in ("NAME", "DESCRIPTION", "PROMPT", "AGENT_PROMPT", "PERMISSION_MODE"):
                val = _str_val(node.value)
            elif name == "MAX_TURNS":
                val = _int_val(node.value)
            elif name == "TOOLS":
                val = _list_val(node.value)
            else:
                val = None
            if val is not None:
                result[name] = val
    return result


def scan_agents(scan_dir: str | Path) -> list[dict]:
    """
    Recursively scan *scan_dir* for ``*.agent.py`` files and return a list of
    agent definition dicts.  Files without a PROMPT/AGENT_PROMPT are skipped.
    """
    root = Path(scan_dir)
    if not root.exists():
        return []

    agents: list[dict] = []
    for path in sorted(root.rglob("*.agent.py")):
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            continue

        v = _extract_vars(tree)
        prompt = v.get("PROMPT") or v.get("AGENT_PROMPT")
        if not prompt:
            continue

        stem = path.stem  # e.g. "code_review.agent"
        default_name = stem.replace(".agent", "").replace("_", " ").title()

        agents.append({
            "name":            v.get("NAME", default_name),
            "description":     v.get("DESCRIPTION"),
            "prompt":          prompt,
            "tools":           v.get("TOOLS", ["Read", "Glob", "Grep"]),
            "max_turns":       v.get("MAX_TURNS", 20),
            "permission_mode": v.get("PERMISSION_MODE", "acceptEdits"),
            "source_file":     str(path),
        })

    return agents
