#!/usr/bin/env python3
"""Set `ref: <new>` in each consumer's agentkit checkout block.

Assumes the standard block shape:
    repository: SoHu-Labs/agentkit
    [ref: <old>]
    path: vendor/agentkit
"""
from __future__ import annotations

import sys
from pathlib import Path

# Workflow files relative to the Prototypes parent of this agentkit repo.
_PARENT = Path(__file__).resolve().parents[4]  # .../Prototypes
_WORKFLOWS = [
    _PARENT / "email-digest/.github/workflows/test.yml",
    _PARENT / "invoice-admin/.github/workflows/ci.yml",
    _PARENT / "decisionmaker/.github/workflows/ci.yml",
]


def bump(path: Path, new_ref: str) -> bool:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    out: list[str] = []
    changed = False
    i = 0
    while i < len(lines):
        out.append(lines[i])
        if "repository: SoHu-Labs/agentkit" in lines[i]:
            indent = lines[i][: len(lines[i]) - len(lines[i].lstrip())]
            # Does a ref: line follow within the block?
            if i + 1 < len(lines) and lines[i + 1].strip().startswith("ref:"):
                out.append(f"{indent}ref: {new_ref}\n")
                i += 2  # skip old ref line
                changed = True
                continue
            out.append(f"{indent}ref: {new_ref}\n")
            changed = True
        i += 1
    if changed:
        path.write_text("".join(out), encoding="utf-8")
    return changed


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: bump_agentkit.py <ref>", file=sys.stderr)
        return 2
    new_ref = sys.argv[1]
    for wf in _WORKFLOWS:
        if not wf.is_file():
            print(f"skip (missing): {wf}")
            continue
        print(f"{'bumped' if bump(wf, new_ref) else 'unchanged'}: {wf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
