import hmac
import threading
from contextlib import contextmanager

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .schemas import ApproveIn, MessageIn, RejectIn, RunIn, RunUndoIn, UndoIn
from .serialize import recovery_to_dict, turn_to_dict, undo_outcomes_to_dict


def create_app(assistant, token: str, allowed_hosts=("127.0.0.1", "localhost")) -> FastAPI:
    if not isinstance(token, str) or len(token) < 16:
        raise ValueError("The session token must be at least 16 characters.")

    app = FastAPI(title="Smart Manager", docs_url=None, redoc_url=None, openapi_url=None)
    # Refuses any request whose Host isn't loopback (stops DNS-rebinding attacks).
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(allowed_hosts))
    # No CORS middleware on purpose: a web page in your browser can't read replies from us.

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

    app.include_router(router)
    return app