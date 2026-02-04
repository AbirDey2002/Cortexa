import logging
import uuid
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from langchain_core.messages import BaseMessage, AIMessage

from db.session import get_db_context
from models.agent.trace import AgentTrace

logger = logging.getLogger(__name__)

class DatabaseTraceCallback(BaseCallbackHandler):
    """
    Callback handler that logs agent steps (thoughts, tool calls) to the database.
    """
    
    def __init__(self, usecase_id: UUID, turn_id: UUID = None, initial_step: int = 0):
        self.usecase_id = usecase_id
        self.turn_id = turn_id  # Links traces to specific chat turn
        self.step_counter = initial_step
        self.current_run_id = None

    def on_llm_start(
        self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any
    ) -> Any:
        # We could log inputs here if needed
        pass

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> Any:
        """Run when LLM ends running."""
        try:
            # Capture the generated text (thought/answer)
            text = ""
            if response.generations and response.generations[0]:
                gen = response.generations[0][0]
                text = gen.text
                if not text and isinstance(gen.message, BaseMessage):
                    text = gen.message.content

            if not text:
                return

            self.step_counter += 1
            run_id = kwargs.get("run_id") or uuid.uuid4()
            
            with get_db_context() as db:
                trace = AgentTrace(
                    usecase_id=self.usecase_id,
                    turn_id=self.turn_id,
                    run_id=run_id,
                    step_number=self.step_counter,
                    step_type="thought",
                    content={"text": text},
                    metadata_={"response_metadata": response.llm_output},
                )
                db.add(trace)
                db.commit()
                
        except Exception as e:
            logger.warning(f"[DB-TRACE] Failed to log LLM end: {e}")

    def on_tool_start(
        self, serialized: Dict[str, Any], input_str: str, **kwargs: Any
    ) -> Any:
        """Run when tool starts running."""
        try:
            self.step_counter += 1
            run_id = kwargs.get("run_id") or uuid.uuid4()
            tool_name = serialized.get("name") if serialized else "unknown"
            
            with get_db_context() as db:
                trace = AgentTrace(
                    usecase_id=self.usecase_id,
                    turn_id=self.turn_id,
                    run_id=run_id,
                    step_number=self.step_counter,
                    step_type="tool_start",
                    content={"input": input_str, "tool": tool_name},
                    metadata_={"tool_name": tool_name},
                )
                db.add(trace)
                db.commit()
        except Exception as e:
            logger.warning(f"[DB-TRACE] Failed to log tool start: {e}")

    def on_tool_end(self, output: str, **kwargs: Any) -> Any:
        """Run when tool ends running."""
        try:
            self.step_counter += 1
            run_id = kwargs.get("run_id") or uuid.uuid4()
            tool_name = kwargs.get("name", "unknown")

            with get_db_context() as db:
                trace = AgentTrace(
                    usecase_id=self.usecase_id,
                    turn_id=self.turn_id,
                    run_id=run_id,
                    step_number=self.step_counter,
                    step_type="tool_end",
                    content={"output": str(output) if not isinstance(output, (dict, list, str, int, float, bool, type(None))) else output},
                    metadata_={"tool_name": tool_name},
                )
                db.add(trace)
                db.commit()
        except Exception as e:
            logger.warning(f"[DB-TRACE] Failed to log tool end: {e}")

    def on_tool_error(self, error: BaseException, **kwargs: Any) -> Any:
        """Run when tool errors."""
        try:
            self.step_counter += 1
            run_id = kwargs.get("run_id") or uuid.uuid4()
            
            with get_db_context() as db:
                trace = AgentTrace(
                    usecase_id=self.usecase_id,
                    turn_id=self.turn_id,
                    run_id=run_id,
                    step_number=self.step_counter,
                    step_type="error",
                    content={"error": str(error)},
                    metadata_={},
                )
                db.add(trace)
                db.commit()
        except Exception as e:
            logger.warning(f"[DB-TRACE] Failed to log tool error: {e}")
