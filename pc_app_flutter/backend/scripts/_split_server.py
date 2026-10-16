"""One-shot P1-B4 splitter. Run from backend/: python scripts/_split_server.py"""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "core" / "server.py"
ROUTES = ROOT / "core" / "routes"
TEMPLATES = ROOT / "templates"


def classify(route: str) -> str:
    if route.startswith("/guest"):
        return "guest"
    if route.startswith("/recording"):
        return "recording"
    if route.startswith("/files/download") or route.startswith("/files/upload") or route in {
        "/files/transfers",
        "/files/download/zip",
        "/files/download/chunked",
        "/files/download/cancel",
        "/files/upload-destinations",
    }:
        return "transfer"
    if route.startswith("/files"):
        return "files"
    if route in {"/pair_device", "/paired-devices", "/unpair", "/connect-code"}:
        return "pairing"
    if (
        route.startswith("/screenshot")
        or route.startswith("/clipboard")
        or route.startswith("/open-link")
        or route.startswith("/type")
        or route.startswith("/keyboard")
        or route.startswith("/media")
    ):
        return "media"
    return "system"


HEADER = '''\
"""Flask blueprint extracted from core.server (P1-B4).

View functions keep their original endpoint names (``endpoint=``) so
``request.endpoint``, MEDIA_TOKEN_ROUTES, and the public-route tests stay stable.
Names that live on the server module are copied in at import time via ``_bind``.
"""
from __future__ import annotations

from flask import Blueprint, Response, jsonify, request, send_file, stream_with_context

from .bind import bind

bp = Blueprint({name!r}, __name__)
bind(globals())

'''


def main() -> None:
    source = SERVER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)

    # Map each routed FunctionDef to lineno/end_lineno
    chunks: dict[str, list[tuple[int, int, str]]] = {}
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        routes: list[str] = []
        for dec in node.decorator_list:
            call = dec
            if isinstance(dec, ast.Call) and getattr(dec.func, "attr", "") == "route":
                if dec.args and isinstance(dec.args[0], ast.Constant):
                    routes.append(str(dec.args[0].value))
        if not routes:
            continue
        # ping stays in server (app factory / middleware neighbour)
        if node.name in {"ping"}:
            continue
        dest = classify(routes[0])
        start = node.decorator_list[0].lineno  # 1-based
        end = node.end_lineno
        assert end
        chunks.setdefault(dest, []).append((start, end, node.name))

    ROUTES.mkdir(parents=True, exist_ok=True)
    (ROUTES / "__init__.py").write_text(
        '''\
"""Route blueprints. Registered at the bottom of core.server."""

from __future__ import annotations

from flask import Flask


def register_blueprints(app: Flask) -> None:
    from . import files, guest, media, pairing, recording, system, transfer

    for mod in (pairing, files, transfer, system, media, recording, guest):
        app.register_blueprint(mod.bp)
''',
        encoding="utf-8",
    )
    (ROUTES / "bind.py").write_text(
        '''\
"""Copy names from core.server into a blueprint module after server has loaded."""

from __future__ import annotations


def bind(module_globals: dict) -> None:
    import core.server as server

    for key, value in vars(server).items():
        if key.startswith("__"):
            continue
        if key in module_globals:
            continue
        module_globals[key] = value
''',
        encoding="utf-8",
    )

    remove: list[tuple[int, int]] = []
    for dest, items in chunks.items():
        parts = [HEADER.format(name=dest)]
        for start, end, fname in items:
            block = "".join(lines[start - 1 : end])
            # app.route -> bp.route, inject endpoint= if missing
            def _repl(m: re.Match[str], fname: str = fname) -> str:
                full = m.group(0)
                if "endpoint=" in full:
                    return full.replace("@app.route", "@bp.route", 1)
                inner = m.group(1)
                if inner.endswith(")"):
                    inner = inner[:-1] + f", endpoint={fname!r})"
                else:
                    inner = inner + f", endpoint={fname!r})"
                return "@bp.route" + inner

            block = re.sub(r"@app\.route(\([^)]*\))", _repl, block, count=1)
            # handle @app.route('/system/stream') without parens close on same... already in regex
            parts.append(block if block.endswith("\n") else block + "\n")
            parts.append("\n")
            remove.append((start, end))
        (ROUTES / f"{dest}.py").write_text("".join(parts), encoding="utf-8")
        print(f"wrote {dest}.py ({len(items)} views)")

    # Extract guest HTML from original before stripping — still in guest.py as f-string
    guest_path = ROUTES / "guest.py"
    gsrc = guest_path.read_text(encoding="utf-8")
    m = re.search(
        r'html_content = f"""(.*?)"""\n    return html_content, 200, \{\'Content-Type\': \'text/html; charset=utf-8\'\}',
        gsrc,
        re.S,
    )
    if not m:
        raise SystemExit("guest html f-string not found")
    raw = m.group(1)

    def f_to_jinja(text: str) -> str:
        out: list[str] = []
        i = 0
        while i < len(text):
            if text[i] == "{":
                if i + 1 < len(text) and text[i + 1] == "{":
                    out.append("{")
                    i += 2
                    continue
                # expression until matching }
                j = i + 1
                depth = 1
                while j < len(text) and depth:
                    if text[j] == "{":
                        depth += 1
                    elif text[j] == "}":
                        depth -= 1
                    j += 1
                expr = text[i + 1 : j - 1]
                out.append("{{ " + expr + " }}")
                i = j
                continue
            if text[i] == "}":
                if i + 1 < len(text) and text[i + 1] == "}":
                    out.append("}")
                    i += 2
                    continue
                out.append("}")
                i += 1
                continue
            out.append(text[i])
            i += 1
        return "".join(out)

    TEMPLATES.mkdir(parents=True, exist_ok=True)
    (TEMPLATES / "guest.html").write_text(f_to_jinja(raw), encoding="utf-8")
    gsrc = gsrc[: m.start()] + (
        "html_content = render_template('guest.html', is_drop=is_drop, token=token)\n"
        "    return html_content, 200, {'Content-Type': 'text/html; charset=utf-8'}"
    ) + gsrc[m.end() :]
    if "render_template" not in gsrc.split("from flask")[1][:400]:
        gsrc = gsrc.replace(
            "from flask import Blueprint, Response, jsonify, request, send_file, stream_with_context",
            "from flask import Blueprint, Response, jsonify, render_template, request, send_file, stream_with_context",
        )
    guest_path.write_text(gsrc, encoding="utf-8")
    print("extracted templates/guest.html")

    # Strip moved functions from server.py (bottom-up)
    new_lines = lines[:]
    for start, end in sorted(remove, reverse=True):
        # also drop a preceding comment line starting with # --- if adjacent
        s = start - 1
        while s > 0 and new_lines[s - 1].strip() == "":
            s -= 1
        if s > 0 and new_lines[s - 1].lstrip().startswith("# ---"):
            start = s
        del new_lines[start - 1 : end]

    text = "".join(new_lines)
    # Flask templates dir
    text = text.replace(
        "app = Flask(__name__)",
        "app = Flask(__name__, template_folder=str(Path(__file__).resolve().parent.parent / 'templates'))",
        1,
    )
    # register blueprints before __main__
    needle = "\nif __name__ == '__main__':"
    insert = (
        "\nfrom .routes import register_blueprints\n"
        "register_blueprints(app)\n"
        "\nif __name__ == '__main__':"
    )
    if needle not in text:
        raise SystemExit("no __main__")
    text = text.replace(needle, insert, 1)
    SERVER.write_text(text, encoding="utf-8")
    print("server.py now", text.count("\n"), "lines")


if __name__ == "__main__":
    main()
