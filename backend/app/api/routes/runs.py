import asyncio
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import audit, get_current_owner, owner_from_token
from app.db.session import get_db, get_sessionmaker
from app.models import AgentRun, Owner, Project, ResearchTarget

router = APIRouter(tags=["runs"])
ACTIVE = {"queued", "running", "paused"}


def serialize_run(r: AgentRun, db: Session) -> dict:
    target = None
    tid = (r.input or {}).get("target_id")
    if tid:
        t = db.get(ResearchTarget, uuid.UUID(tid))
        if t is not None and t.project_id == r.project_id:
            target = {"id": str(t.id), "value": t.value, "canonical_url": t.canonical_url}
    return {
        "id": str(r.id), "agent_key": r.agent_key, "status": r.status, "progress": r.progress,
        "current_url": r.current_url, "control": r.control, "error": r.error,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "finished_at": r.finished_at.isoformat() if r.finished_at else None, "target": target,
    }


def owned_runs(db: Session, owner_id: uuid.UUID, limit: int = 30) -> list[AgentRun]:
    return list(db.scalars(
        select(AgentRun).join(Project, Project.id == AgentRun.project_id)
        .where(Project.owner_id == owner_id).order_by(AgentRun.created_at.desc()).limit(limit)
    ).all())


@router.get("/api/runs")
def recent_runs(owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    return [serialize_run(r, db) for r in owned_runs(db, owner.id)]


def _control(run_id: uuid.UUID, command: str | None, owner: Owner, db: Session, request=None) -> dict:
    run = db.scalar(select(AgentRun).join(Project, Project.id == AgentRun.project_id)
                    .where(AgentRun.id == run_id, Project.owner_id == owner.id))
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    if run.status not in ACTIVE:
        raise HTTPException(status.HTTP_409_CONFLICT, "This run has already finished")
    if command is None and run.control != "pause":
        raise HTTPException(status.HTTP_409_CONFLICT, "This run is not paused")
    run.control = command
    audit(db, owner.id, f"run.{command or 'resume'}", request, run_id=str(run.id))
    db.commit()
    return serialize_run(run, db)


@router.post("/api/runs/{run_id}/pause")
def pause_run(run_id: uuid.UUID, owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    return _control(run_id, "pause", owner, db)


@router.post("/api/runs/{run_id}/resume")
def resume_run(run_id: uuid.UUID, owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    return _control(run_id, None, owner, db)


@router.post("/api/runs/{run_id}/stop")
def stop_run(run_id: uuid.UUID, owner: Owner = Depends(get_current_owner), db: Session = Depends(get_db)):
    return _control(run_id, "stop", owner, db)


def get_ws_session_factory():
    return get_sessionmaker()


@router.websocket("/ws/runs")
async def runs_socket(ws: WebSocket, session_factory=Depends(get_ws_session_factory)):
    """Live run updates. The token is sent as the first message (never in the URL, which gets logged)."""
    from app.core.config import get_settings

    origin = ws.headers.get("origin")
    if origin and origin not in get_settings().cors_origin_list:
        await ws.close(code=4403)
        return
    await ws.accept()
    try:
        first = json.loads(await asyncio.wait_for(ws.receive_text(), timeout=5))
        token = first["token"]
        with session_factory() as db:
            owner_id = await asyncio.to_thread(lambda: owner_from_token(token, db).id)
    except (HTTPException, asyncio.TimeoutError, KeyError, ValueError, TypeError):
        await ws.close(code=4401)
        return
    except WebSocketDisconnect:
        return

    last = None
    try:
        while True:
            def snapshot():
                with session_factory() as db:
                    return [serialize_run(r, db) for r in owned_runs(db, owner_id)]

            data = await asyncio.to_thread(snapshot)
            if data != last:
                await ws.send_json({"runs": data})
                last = data
            await asyncio.sleep(1)
    except (WebSocketDisconnect, RuntimeError):
        return
