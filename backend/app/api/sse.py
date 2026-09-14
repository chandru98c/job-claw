import asyncio
import json
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database.database import get_db
from app.database.models import Task, TaskEvent, TaskStatus, TaskEventType

router = APIRouter(prefix="/sse", tags=["sse"])

async def event_stream(task_id: str, request: Request):
    """
    Generator that polls the database for new TaskEvents and yields them as SSE messages.
    """
    from app.database.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        # Verify task exists
        task = await db.get(Task, task_id)
        if not task:
            # yield error and terminate
            yield f"data: {json.dumps({'error': 'Task not found'})}\n\n"
            return

        last_event_time = None
        seen_event_ids = set()
        poll_interval = 1.0  # seconds

        while True:
            if await request.is_disconnected():
                break

            # Refresh session to see new DB commits
            await db.refresh(task)

            # Query events that we haven't seen yet
            stmt = select(TaskEvent).where(TaskEvent.task_id == task_id).order_by(TaskEvent.created_at.asc())
            result = await db.execute(stmt)
            events = result.scalars().all()

            for event in events:
                if event.id not in seen_event_ids:
                    seen_event_ids.add(event.id)
                    last_event_time = event.created_at
                    
                    payload = {
                        "id": event.id,
                        "event_type": event.event_type.value,
                        "payload": event.payload,
                        "timestamp": event.created_at.isoformat() if event.created_at else None
                    }
                    
                    # SSE Format: "data: <json>\n\n"
                    yield f"data: {json.dumps(payload)}\n\n"
                    
                    # Terminate stream cleanly if task reaches terminal state
                    if event.event_type in (TaskEventType.COMPLETED, TaskEventType.ERROR, TaskEventType.CANCELLED):
                        # Yield one final message to indicate completion stream closure
                        yield f"data: {json.dumps({'status': 'DONE'})}\n\n"
                        return

            # Terminal state check just in case we missed the terminal event (e.g., worker died)
            if task.status in (TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                yield f"data: {json.dumps({'status': 'DONE', 'task_status': task.status.value})}\n\n"
                return

            await asyncio.sleep(poll_interval)


@router.get("/tasks/{task_id}/events/stream")
async def stream_task_events(task_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """
    Returns an SSE streaming response for task events.
    """
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return StreamingResponse(
        event_stream(task_id, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    )
