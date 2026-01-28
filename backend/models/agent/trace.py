import uuid
from sqlalchemy import Column, String, Integer, DateTime, func, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

# This relative import goes up two levels to the 'models' directory
# to find the base.py file.
from ..base import Base

class AgentTrace(Base):
    """
    Model for storing agent execution traces (thoughts, tool calls, etc.) locally.
    """
    __tablename__ = 'agent_traces'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    usecase_id = Column(UUID(as_uuid=True), index=True, nullable=False)
    
    # LangChain/LangSmith Run ID for correlation
    run_id = Column(UUID(as_uuid=True), index=True, nullable=True)
    
    # Turn ID to link traces to specific chat messages
    turn_id = Column(UUID(as_uuid=True), index=True, nullable=True)
    
    # Ordering of steps
    step_number = Column(Integer, nullable=False, default=0)
    
    # Type of step: 'thought', 'tool_start', 'tool_end', 'observation', 'answer', 'error'
    step_type = Column(String(50), nullable=False)
    
    # The main content (thought text, tool output, etc.)
    content = Column(JSON, nullable=True)
    
    # Metadata (timestamps, tokens, tool names, etc.)
    metadata_ = Column("metadata", JSON, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=func.now(), nullable=False)

    def __repr__(self):
        return f"<AgentTrace(id='{self.id}', type='{self.step_type}', step={self.step_number})>"
