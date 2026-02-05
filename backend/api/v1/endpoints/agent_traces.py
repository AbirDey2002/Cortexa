"""
SSE endpoint for streaming agent traces in real-time.
"""
import asyncio
import logging
import uuid
from typing import Any, Dict

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from deps import get_db, get_current_user
from db.session import get_db_context
from deps import get_db
from models.agent.trace import AgentTrace
from models.usecase.usecase import UsecaseMetadata
from models.user.user import User

logger = logging.getLogger(__name__)

router = APIRouter()


async def _stream_traces(usecase_id: uuid.UUID, last_step: int = 0):
    """
    Generator that yields SSE events for agent traces.
    First yields all existing traces (handles race condition where agent finished before SSE connected),
    then polls for new traces if still processing.
    """
    import json
    current_step = last_step
    max_idle_seconds = 120  # Stop after 2 minutes of no activity
    idle_count = 0
    poll_interval = 0.05  # Poll every 50ms for real-time feel
    
    try:
        with get_db_context() as db:
            # First, yield ALL existing traces from this usecase
            existing_traces = db.query(AgentTrace).filter(
                AgentTrace.usecase_id == usecase_id,
                AgentTrace.step_number > current_step
            ).order_by(AgentTrace.step_number.asc()).all()
            
            for trace in existing_traces:
                current_step = trace.step_number
                trace_data = {
                    "step_number": trace.step_number,
                    "step_type": trace.step_type,
                    "content": trace.content,
                    "created_at": trace.created_at.isoformat() if trace.created_at else None,
                }
                yield f"event: trace\ndata: {json.dumps(trace_data)}\n\n"
            
            # Check if already completed
            usecase = db.query(UsecaseMetadata).filter(
                UsecaseMetadata.usecase_id == usecase_id,
                UsecaseMetadata.is_deleted == False
            ).first()
            
            if not usecase:
                yield f"event: error\ndata: {{\"error\": \"Usecase not found\"}}\n\n"
                return
            
            if usecase.status == "Completed":
                yield f"event: done\ndata: {{\"status\": \"completed\", \"last_step\": {current_step}}}\n\n"
                return
    except Exception as e:
        logger.error(f"Error fetching initial traces for {usecase_id}: {e}")
        yield f"event: error\ndata: {{\"error\": \"{str(e)}\"}}\n\n"
        return
    
    # Continue polling for new traces while agent is running
    while True:
        try:
            with get_db_context() as db:
                # Check if usecase is still processing
                usecase = db.query(UsecaseMetadata).filter(
                    UsecaseMetadata.usecase_id == usecase_id,
                    UsecaseMetadata.is_deleted == False
                ).first()
                
                if not usecase:
                    yield f"event: error\ndata: {{\"error\": \"Usecase not found\"}}\n\n"
                    break
                
                # Get new traces since last step
                new_traces = db.query(AgentTrace).filter(
                    AgentTrace.usecase_id == usecase_id,
                    AgentTrace.step_number > current_step
                ).order_by(AgentTrace.step_number.asc()).all()
                
                if new_traces:
                    idle_count = 0  # Reset idle counter
                    for trace in new_traces:
                        current_step = trace.step_number
                        trace_data = {
                            "step_number": trace.step_number,
                            "step_type": trace.step_type,
                            "content": trace.content,
                            "created_at": trace.created_at.isoformat() if trace.created_at else None,
                        }
                        yield f"event: trace\ndata: {json.dumps(trace_data)}\n\n"
                else:
                    idle_count += 1
                
                # Check if processing is complete
                if usecase.status == "Completed":
                    yield f"event: done\ndata: {{\"status\": \"completed\", \"last_step\": {current_step}}}\n\n"
                    break
                
                # Check for idle timeout
                if idle_count * poll_interval >= max_idle_seconds:
                    yield f"event: timeout\ndata: {{\"status\": \"timeout\", \"last_step\": {current_step}}}\n\n"
                    break
                    
        except Exception as e:
            logger.error(f"Error streaming traces for {usecase_id}: {e}")
            yield f"event: error\ndata: {{\"error\": \"{str(e)}\"}}\n\n"
            break
        
        await asyncio.sleep(poll_interval)


@router.get("/{usecase_id}/agent-thinking/stream")
async def stream_agent_thinking(
    usecase_id: uuid.UUID,
    last_step: int = Query(0, description="Last step number received (cursor)"),
    user: User = Depends(get_current_user),
):
    """
    SSE endpoint to stream agent thinking steps in real-time.
    
    Connect to this endpoint after sending a chat message to receive
    intermediate thoughts and tool calls as they happen.
    
    Events:
    - `trace`: A new trace step (thought, tool_start, tool_end)
    - `done`: Processing complete
    - `error`: An error occurred
    - `timeout`: No activity for too long
    """
    # Verify ownership before streaming
    with get_db_context() as db:
        record = db.query(UsecaseMetadata).filter(
            UsecaseMetadata.usecase_id == usecase_id,
            UsecaseMetadata.user_id == user.id,
            UsecaseMetadata.is_deleted == False
        ).first()
        if not record:
            raise HTTPException(status_code=404, detail="Usecase not found or access denied")

    return StreamingResponse(
        _stream_traces(usecase_id, last_step),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )


@router.get("/{usecase_id}/agent-thinking/history")
def get_agent_thinking_history(
    usecase_id: uuid.UUID,
    turn_id: uuid.UUID = Query(None, description="Filter by turn ID"),
    limit: int = Query(50, description="Max traces to return"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get recent agent thinking history for a usecase.
    Optionally filter by turn_id to get traces for a specific chat message.
    """
    # Verify ownership
    query = db.query(AgentTrace).join(
        UsecaseMetadata, AgentTrace.usecase_id == UsecaseMetadata.usecase_id
    ).filter(
        AgentTrace.usecase_id == usecase_id,
        UsecaseMetadata.user_id == user.id,
        UsecaseMetadata.is_deleted == False
    )
    
    # Filter by turn_id if provided
    if turn_id:
        query = query.filter(AgentTrace.turn_id == turn_id)
    
    traces = query.order_by(AgentTrace.step_number.desc()).limit(limit).all()
    
    # Return in chronological order
    traces = list(reversed(traces))
    
    return {
        "usecase_id": str(usecase_id),
        "turn_id": str(turn_id) if turn_id else None,
        "traces": [
            {
                "step_number": t.step_number,
                "step_type": t.step_type,
                "content": t.content,
                "turn_id": str(t.turn_id) if t.turn_id else None,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in traces
        ],
        "count": len(traces),
    }
