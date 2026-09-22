"""Start the local-only browser GUI for SRAM Vmin inverse demonstrations.

Normal source run:
    .venv/bin/python manuscript/gui/demo_server.py

The server binds to 127.0.0.1 only.  It neither uploads model data nor accepts
remote connections.  Prepare ``demo_bundle/`` first with prepare_bundle.py.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
from pathlib import Path
import sys
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, cast
import webbrowser

from demo_config import DEFAULT_BUNDLE_DIR, STATIC_DIR
from demo_engine import DemoEngine, DemoInputError

MAX_BODY_BYTES = 1_000_000


def _runtime_static_dir() -> Path:
    """Resolve bundled assets under PyInstaller or source-tree execution."""
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root is not None:
        candidate = Path(str(frozen_root)) / "static"
        if candidate.is_dir():
            return candidate
    return STATIC_DIR


def _default_bundle_dir() -> Path:
    """Prefer a bundle next to a frozen Windows executable when present."""
    executable_bundle = Path(sys.executable).resolve().parent / "demo_bundle"
    if executable_bundle.is_dir():
        return executable_bundle
    env_path = os.environ.get("SRAM_VMIN_DEMO_BUNDLE")
    return Path(env_path).expanduser() if env_path else DEFAULT_BUNDLE_DIR


class PresentationHTTPServer(ThreadingHTTPServer):
    """Server container with a shared serialized inference engine."""

    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address: tuple[str, int], engine: DemoEngine, static_dir: Path) -> None:
        super().__init__(address, PresentationRequestHandler)
        self.engine = engine
        self.static_dir = static_dir.resolve()
        self.inference_lock = threading.Lock()


class PresentationRequestHandler(BaseHTTPRequestHandler):
    """Tiny JSON API and static-asset handler; no third-party web framework."""

    server: PresentationHTTPServer
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: object) -> None:
        """Keep terminal logging useful without echoing coordinate payloads."""
        print(f"[web] {self.address_string()} {format % args}")

    def _send_bytes(self, status: HTTPStatus, content: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(content)

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self._send_bytes(status, body, "application/json; charset=utf-8")

    def _error(self, status: HTTPStatus, message: str) -> None:
        self._send_json(status, {"ok": False, "error": message})

    def _read_json(self) -> dict[str, Any]:
        header = self.headers.get("Content-Length")
        if header is None:
            raise DemoInputError("Content-Length is required")
        try:
            length = int(header)
        except ValueError as exc:
            raise DemoInputError("invalid Content-Length") from exc
        if not 0 <= length <= MAX_BODY_BYTES:
            raise DemoInputError("request body is too large")
        raw = self.rfile.read(length)
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DemoInputError("request body must be valid UTF-8 JSON") from exc
        if not isinstance(value, dict):
            raise DemoInputError("request JSON must be an object")
        return cast(dict[str, Any], value)

    def _serve_static(self, request_path: str) -> None:
        relative = "index.html" if request_path in {"", "/"} else request_path.lstrip("/")
        if relative.startswith("api/"):
            self._error(HTTPStatus.NOT_FOUND, "unknown API route")
            return
        candidate = (self.server.static_dir / relative).resolve()
        try:
            candidate.relative_to(self.server.static_dir)
        except ValueError:
            self._error(HTTPStatus.FORBIDDEN, "invalid static path")
            return
        if not candidate.is_file():
            self._error(HTTPStatus.NOT_FOUND, "file not found")
            return
        content_type, _ = mimetypes.guess_type(candidate.name)
        self._send_bytes(
            HTTPStatus.OK,
            candidate.read_bytes(),
            content_type or "application/octet-stream",
        )

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        try:
            if path == "/api/health":
                self._send_json(HTTPStatus.OK, {"ok": True, "scope": "127.0.0.1 only"})
            elif path == "/api/metadata":
                self._send_json(HTTPStatus.OK, {"ok": True, "data": self.server.engine.metadata()})
            elif path == "/api/scenario":
                self._send_json(HTTPStatus.OK, {"ok": True, "data": self.server.engine.paper_scenario()})
            elif path == "/api/sensitivity":
                self._send_json(HTTPStatus.OK, {"ok": True, "data": self.server.engine.sensitivity()})
            else:
                self._serve_static(path)
        except (DemoInputError, FileNotFoundError, ValueError) as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:  # pragma: no cover - preserves a safe browser error
            print(f"[web] unexpected GET error: {exc!r}", file=sys.stderr)
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "local application error")

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        try:
            payload = self._read_json()
            with self.server.inference_lock:
                if path == "/api/predict":
                    result = self.server.engine.predict(payload.get("mode", "read"), payload.get("coordinates"))
                elif path == "/api/inverse":
                    result = self.server.engine.solve_axis(
                        payload.get("mode", "read"),
                        payload.get("coordinates"),
                        payload.get("axis", "cn"),
                        payload.get("target_vmin"),
                        int(payload.get("scan_points", 81)),
                    )
                elif path == "/api/plane":
                    result = self.server.engine.plane(
                        payload.get("mode", "read"),
                        payload.get("coordinates"),
                        payload.get("x_axis", "cn"),
                        payload.get("y_axis", "pu"),
                        int(payload.get("points", 31)),
                    )
                else:
                    self._error(HTTPStatus.NOT_FOUND, "unknown API route")
                    return
            self._send_json(HTTPStatus.OK, {"ok": True, "data": result})
        except (DemoInputError, TypeError, ValueError) as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:  # pragma: no cover - preserves a safe browser error
            print(f"[web] unexpected POST error: {exc!r}", file=sys.stderr)
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "local application error")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=_default_bundle_dir(),
                        help="trusted local bundle directory")
    parser.add_argument("--source", action="store_true",
                        help="development only: reconstruct models from protected source XLSX files")
    parser.add_argument("--host", default="127.0.0.1",
                        help="must be 127.0.0.1 or localhost (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=0,
                        help="local port; 0 selects a free port")
    parser.add_argument("--no-browser", action="store_true",
                        help="do not open the default browser automatically")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    # ThreadingHTTPServer uses an IPv4 socket by default.  Explicitly support
    # the two IPv4 loopback spellings rather than accepting ::1 then failing
    # later with an address-family error.
    if args.host not in {"127.0.0.1", "localhost"}:
        raise SystemExit("refusing non-loopback host; use 127.0.0.1 or localhost")
    engine = DemoEngine.from_source() if args.source else DemoEngine.from_bundle(args.bundle)
    static_dir = _runtime_static_dir()
    if not static_dir.is_dir():
        raise SystemExit(f"missing UI assets: {static_dir}")
    server = PresentationHTTPServer((args.host, args.port), engine, static_dir)
    address = server.server_address
    host = "127.0.0.1" if address[0] in {"0.0.0.0", "::"} else address[0]
    url = f"http://{host}:{address[1]}/"
    print(f"\n{url}\nLocal-only server: model and query data do not leave this PC.\nPress Ctrl+C to stop.\n")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping local presentation server.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
