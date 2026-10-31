"""Export the API contract: docs/openapi.json (machine-readable) and docs/API.md (human-readable).

    uv run python scripts/export_openapi.py            # rewrite both files
    uv run python scripts/export_openapi.py --check    # exit 1 if they are stale (used in CI)
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # run from anywhere: `python scripts/export_openapi.py`

from app.main import app  # noqa: E402
from app.public_routes import PUBLIC  # noqa: E402

DOCS = Path(__file__).resolve().parents[2] / "docs"
METHODS = ("get", "post", "put", "patch", "delete")


def render_markdown(spec: dict) -> str:
    groups: dict[str, list[tuple[str, str, str, str]]] = {}
    for path, ops in sorted(spec["paths"].items()):
        for method in METHODS:
            op = ops.get(method)
            if not op:
                continue
            tag = (op.get("tags") or ["other"])[0]
            summary = (op.get("description") or op.get("summary") or "").strip().split("\n")[0].rstrip(".")
            auth = "public" if (method.upper(), path) in PUBLIC else "session"
            groups.setdefault(tag, []).append((method.upper(), path, summary, auth))
    total = sum(len(v) for v in groups.values())
    lines = [
        "# API reference",
        "",
        f"{total} operations. Generated from the running application by `backend/scripts/export_openapi.py`; "
        "the full machine-readable contract is [`openapi.json`](openapi.json). Interactive docs are at `/docs` on a running API.",
        "",
        "**Conventions.** Everything is JSON under `/api`. Authentication is an `HttpOnly` session cookie; state-changing requests must "
        "come from the app's own origin. Errors always look like `{\"error\": {\"code\", \"message\", \"field?\", \"request_id?\"}}`; "
        "branch on `code`, never on `message`. Money is in rupees with `currency: \"INR\"`; calculators return `calculation_id`, "
        "`formula_version`, `assumptions` and `missing`. Every response carries `X-Request-ID`.",
        "",
        "**Auth column.** *public* operations are the explicit allow-list in `app/public_routes.py` (each with its justification); "
        "everything else needs a signed-in session and only ever touches the caller's own objects.",
        "",
    ]
    for tag in sorted(groups):
        lines += [f"## {tag}", "", "| Method | Path | What it does | Auth |", "|---|---|---|---|"]
        lines += [f"| {m} | `{p}` | {s} | {a} |" for m, p, s, a in groups[tag]]
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    check = ap.parse_args().check
    spec = app.openapi()
    outputs = {DOCS / "openapi.json": json.dumps(spec, indent=2, sort_keys=True, ensure_ascii=False) + "\n", DOCS / "API.md": render_markdown(spec) + "\n"}
    stale = [p.name for p, text in outputs.items() if not p.exists() or p.read_text() != text]
    if check:
        if stale:
            print(f"stale: {', '.join(stale)}: run `uv run python scripts/export_openapi.py` and commit", file=sys.stderr)
        return 1 if stale else 0
    for p, text in outputs.items():
        p.write_text(text)
    print("wrote", ", ".join(p.name for p in outputs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
