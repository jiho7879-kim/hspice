"""Loopback-only HTTP service: static UI, JSON API, and ONE worker thread that owns the GP.

Runs are queued, so a 40-second window never blocks the browser or times out a
request; the page polls /api/runs/<id> for progress. Stdlib only, like the repo's
other two local tools.
"""
from __future__ import annotations

import json
import mimetypes
import queue
import re
import threading
import time
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

from . import analyses, store
from .config import AXES, CORNERS, LIMITING, SCENARIOS, SERVICE
from .engine import Engine, resolve_z
from .scenario import COMMON_DEFAULTS, SpecError

WEB = SERVICE / "web"
MAX_BODY = 2_000_000
NAME_RE = re.compile(r"^[A-Za-z0-9가-힣_\-]{1,80}$")
LOOPBACK = {"127.0.0.1", "localhost", "::1"}


def engine_summary(engine: Engine) -> dict:
    return {m: dict(source=mm.source, checkpoint=mm.checkpoint_sha) for m, mm in engine.modes.items()}


def execute(engine: Engine, spec: dict, run_id: str | None = None, progress=lambda _m: None) -> dict:
    """Run one spec end to end and persist it. Shared by the server and the CLI."""
    kind = str(spec.get("kind", ""))
    run_id = run_id or store.new_id(re.sub(r"[^a-z_]", "", kind) or "run")
    entry = analyses.REGISTRY.get(kind, {})
    header = dict(id=run_id, kind=kind, title=spec.get("title") or entry.get("title", kind),
                  description=spec.get("description", ""), preset=spec.get("_preset", ""),
                  created=time.strftime("%Y-%m-%d %H:%M:%S"), engine=engine_summary(engine))
    t0 = time.time()
    try:
        full, res = analyses.run(spec, engine, progress)
    except SpecError as ex:
        return store.save_error(run_id, spec, header | dict(elapsed_s=round(time.time() - t0, 2)), str(ex))
    except Exception as ex:  # surfaced to the user; the traceback stays in the console
        traceback.print_exc()
        return store.save_error(run_id, spec, header | dict(elapsed_s=round(time.time() - t0, 2)),
                                f"내부 오류: {type(ex).__name__}: {ex}")
    z, z_text = resolve_z(full["z"])
    header.update(elapsed_s=round(time.time() - t0, 2), z=z, z_text=z_text, target=full.get("target"),
                  reference_vmin=full.get("reference_vmin"))
    return store.save(run_id, full | {"title": header["title"]}, res, header)


def presets() -> list[dict]:
    out = []
    for p in sorted(SCENARIOS.rglob("*.json")):
        try:
            s = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        name = p.relative_to(SCENARIOS).with_suffix("").as_posix()
        out.append(dict(name=name, kind=s.get("kind"), title=s.get("title", name),
                        description=s.get("description", ""), group=s.get("group", "user" if "/" in name else ""),
                        expect=len(s.get("expect") or [])))
    return out


def preset(name: str) -> dict:
    p = (SCENARIOS / f"{name}.json").resolve()
    if SCENARIOS.resolve() not in p.parents or not p.is_file():
        raise FileNotFoundError(name)
    return json.loads(p.read_text(encoding="utf-8"))


class Jobs:
    def __init__(self, engine: Engine):
        self.engine = engine
        self.q: queue.Queue = queue.Queue()
        self.state: dict[str, dict] = {}
        self.lock = threading.Lock()
        threading.Thread(target=self._work, daemon=True).start()

    def submit(self, spec: dict) -> str:
        kind = re.sub(r"[^a-z_]", "", str(spec.get("kind", ""))) or "run"
        rid = store.new_id(kind)
        with self.lock:
            self.state[rid] = dict(id=rid, status="queued", progress="대기 중",
                                   queue=self.q.qsize() + 1)
        self.q.put((rid, spec))
        return rid

    def get(self, rid: str) -> dict | None:
        with self.lock:
            s = self.state.get(rid)
            return dict(s) if s else None

    def _set(self, rid: str, **kw) -> None:
        with self.lock:
            self.state.setdefault(rid, {}).update(kw)

    def _work(self) -> None:
        while True:
            rid, spec = self.q.get()
            self._set(rid, status="running", progress="시작", started=time.time())
            out = execute(self.engine, spec, rid, progress=lambda m, rid=rid: self._set(rid, progress=m))
            self._set(rid, status=out["status"], progress="")


class Server(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, addr, engine: Engine, checks: list[dict]):
        super().__init__(addr, Handler)
        self.engine = engine
        self.jobs = Jobs(engine)
        self.meta = dict(
            app="SRAM Vmin Studio", axes=AXES, corners=CORNERS, limiting=LIMITING,
            modes=engine.info(), defaults=COMMON_DEFAULTS, analyses=analyses.catalogue(),
            selfcheck=checks, z_default=resolve_z(COMMON_DEFAULTS["z"]))


class Handler(BaseHTTPRequestHandler):
    server: Server
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:
        if "/api/runs/" not in (args[0] if args else ""):   # polling is noise
            print(f"[web] {fmt % args}")

    def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200) -> None:
        self._send(code, json.dumps(store.clean(obj), ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def _error(self, code: int, msg: str) -> None:
        self._json({"error": msg}, code)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            raise SpecError("요청이 너무 큽니다")
        data = json.loads(self.rfile.read(n) or b"{}")
        if not isinstance(data, dict):
            raise SpecError("JSON object가 필요합니다")
        return data

    def _file(self, path, download: bool = False) -> None:
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/json", "application/javascript"):
            ctype += "; charset=utf-8"
        extra = {"Content-Disposition": f'attachment; filename="{path.name}"'} if download else None
        self._send(200, path.read_bytes(), ctype, extra)

    def do_GET(self) -> None:  # noqa: N802
        url = urlparse(self.path)
        parts = [unquote(p) for p in url.path.split("/") if p]
        try:
            if not parts:
                return self._file(WEB / "index.html")
            if parts[0] == "web" and len(parts) == 2 and not parts[1].startswith("."):
                p = WEB / parts[1]
                if p.is_file():
                    return self._file(p)
            if parts[:2] == ["api", "meta"]:
                return self._json(self.server.meta)
            if parts[:2] == ["api", "presets"]:
                return self._json(preset("/".join(parts[2:])) if len(parts) > 2 else presets())
            if parts[:2] == ["api", "runs"]:
                if len(parts) == 2:
                    return self._json(store.listing())
                live = self.server.jobs.get(parts[2])
                if live and live["status"] in ("queued", "running"):
                    return self._json(live)
                return self._json(store.load(parts[2]))
            if parts[0] == "runs" and len(parts) == 3:
                return self._file(store.file_path(parts[1], parts[2]), download="dl" in url.query)
        except FileNotFoundError:
            pass
        except json.JSONDecodeError:
            return self._error(500, "저장된 결과 파일이 손상되었습니다")
        self._error(404, "없는 경로입니다")

    def do_POST(self) -> None:  # noqa: N802
        parts = [p for p in urlparse(self.path).path.split("/") if p]
        try:
            body = self._body()
            if parts == ["api", "runs"]:
                if body.get("kind") not in analyses.REGISTRY:
                    raise SpecError(f"알 수 없는 분석 '{body.get('kind')}'")
                return self._json({"id": self.server.jobs.submit(body)}, 202)
            if parts == ["api", "presets"]:
                name, spec = str(body.get("name", "")), body.get("spec")
                if not NAME_RE.match(name) or not isinstance(spec, dict):
                    raise SpecError("이름은 영문·한글·숫자·_·- 80자 이내, spec은 object여야 합니다")
                d = SCENARIOS / "user"
                d.mkdir(parents=True, exist_ok=True)
                store.write_json(d / f"{name}.json", spec | {"group": "내 시나리오"})
                return self._json({"name": f"user/{name}"}, 201)
        except (SpecError, json.JSONDecodeError) as ex:
            return self._error(400, str(ex))
        self._error(404, "없는 경로입니다")


def serve(engine: Engine, host: str, port: int, open_browser: bool) -> None:
    if host not in LOOPBACK:
        raise SystemExit(f"host {host!r} 거부 — 모델이 기밀이라 loopback(127.0.0.1)에만 엽니다.")
    checks = engine.selfcheck()
    bad = [c for c in checks if not c["ok"]]
    print(f"self-check: {len(checks) - len(bad)}/{len(checks)} saved §V-D corners reproduced"
          + (f" — MISMATCH {[(c['mode'], c['corner']) for c in bad]}" if bad else ""))
    httpd = Server((host, port), engine, checks)
    url = f"http://{host}:{httpd.server_address[1]}/"
    print(f"SRAM Vmin Studio  {url}   (Ctrl+C to stop)")
    if open_browser:
        import webbrowser
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
