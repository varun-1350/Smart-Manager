import hmac
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query
from fastapi import Path as PathParam
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.staticfiles import StaticFiles

from .schemas import (ApproveIn, ClearIn, MessageIn, RejectIn, RunIn, RunUndoIn,
                      SettingIn, UndoIn)
from .serialize import recovery_to_dict, turn_to_dict, undo_outcomes_to_dict


def create_app(assistant, token: str, allowed_hosts=("127.0.0.1", "localhost"),
               ui_dir=None, history=None, settings=None) -> FastAPI:
    if not isinstance(token, str) or len(token) < 16:
        raise ValueError("The session token must be at least 16 characters.")

    history = history if history is not None else getattr(assistant, "history", None)
    settings = settings if settings is not None else getattr(history, "settings", None)
    app = FastAPI(title="Smart Manager", docs_url=None, redoc_url=None, openapi_url=None)
    # Refuses any request whose Host isn't loopback (stops DNS-rebinding attacks).
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(allowed_hosts))

    # No CORS middleware on purpose: a web page in your browser can't read replies from us.

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "frame-ancestors 'none'; base-uri 'none'")
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store"
        return response

    gate = threading.Lock()          # one state-changing request at a time
    app.state.gate = gate

    def require_token(x_session_token: str | None = Header(default=None)) -> None:
        supplied = (x_session_token or "").encode("utf-8")
        if not hmac.compare_digest(supplied, token.encode("utf-8")):
            raise HTTPException(status_code=401, detail="Missing or wrong session token.")

    @contextmanager
    def exclusive():
        if not gate.acquire(blocking=False):
            raise HTTPException(status_code=409, detail="Another request is still running.")
        try:
            yield
        finally:
            gate.release()

    router = APIRouter(prefix="/api", dependencies=[Depends(require_token)])

    @router.post("/message")
    def message(body: MessageIn):
        with exclusive():
            return turn_to_dict(assistant.handle(body.text))

    @router.post("/approve")
    def approve(body: ApproveIn):
        with exclusive():
            return turn_to_dict(assistant.approve(body.turn_id, body.digest))

    @router.post("/reject")
    def reject(body: RejectIn):
        with exclusive():
            assistant.reject(body.turn_id)
        return {"ok": True}

    @router.get("/progress")
    def progress():
        return assistant.progress()              # not gated: the UI polls this during a run

    @router.post("/cancel")
    def cancel():
        assistant.request_cancel()               # deliberately NOT gated: it must work mid-run
        return {"ok": True}

    @router.get("/undo")
    def undo_preview():
        with exclusive():
            return {"steps": assistant.undo_preview()}

    @router.post("/undo")
    def undo(body: UndoIn):
        if not body.confirm:
            raise HTTPException(status_code=400, detail="Undo needs confirm=true.")
        with exclusive():
            return {"outcomes": undo_outcomes_to_dict(assistant.undo_last(confirmed=True))}

    @router.get("/interrupted")
    def interrupted():
        with exclusive():
            reports, errors = assistant.interrupted()
            return {"reports": [recovery_to_dict(r) for r in reports], "errors": errors}

    @router.post("/interrupted/dismiss")
    def dismiss(body: RunIn):
        with exclusive():
            try:
                assistant.dismiss_interrupted(body.run_id)
            except LookupError:
                raise HTTPException(status_code=404, detail="Unknown run.") from None
        return {"ok": True}

    @router.post("/interrupted/undo")
    def undo_interrupted(body: RunUndoIn):
        if not body.confirm:
            raise HTTPException(status_code=400, detail="Undo needs confirm=true.")
        with exclusive():
            try:
                outcomes = assistant.undo_interrupted(body.run_id, confirmed=True)
            except LookupError:
                raise HTTPException(status_code=404, detail="Unknown run.") from None
        return {"outcomes": undo_outcomes_to_dict(outcomes)}

    def _need(obj, what):
        if obj is None:
            raise HTTPException(status_code=503, detail=f"{what} isn't available.")
        return obj

    def _guard(fn):
        try:
            return fn()
        except sqlite3.Error as exc:
            raise HTTPException(status_code=503,
                                detail=f"The history database had a problem: {exc}") from None

    # History and settings never touch your files, so they don't wait for the run gate.
    @router.get("/history")
    def history_list(limit: int = Query(50, ge=1, le=200),
                     before_id: int | None = Query(None, ge=1, le=2**62)):
        store = _need(history, "History")
        items, next_before = _guard(lambda: store.recent(limit, before_id))
        return {"items": items, "next_before": next_before}

    @router.get("/history/{item_id}")
    def history_item(item_id: int = PathParam(..., ge=1, le=2**62)):
        store = _need(history, "History")
        row = _guard(lambda: store.get(item_id))
        if row is None:
            raise HTTPException(status_code=404, detail="No such history entry.")
        return row

    @router.post("/history/clear")
    def history_clear(body: ClearIn):
        if not body.confirm:
            raise HTTPException(status_code=400, detail="Clearing history needs confirm=true.")
        store = _need(history, "History")
        return {"deleted": _guard(store.clear)}

    @router.get("/settings")
    def settings_list():
        return {"settings": _guard(_need(settings, "Settings").describe)}

    @router.post("/settings")
    def settings_set(body: SettingIn):
        store = _need(settings, "Settings")
        try:
            _guard(lambda: store.set(body.key, body.value))
        except KeyError:
            raise HTTPException(status_code=404, detail="Unknown setting.") from None
        return {"settings": _guard(store.describe)}

    app.include_router(router)

    ui = Path(ui_dir) if ui_dir else Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if (ui / "index.html").is_file():          # mounted last, so it can never shadow /api
        app.mount("/", StaticFiles(directory=ui, html=True), name="ui")
    return app