from sqlalchemy import Column, ForeignKey, DateTime, JSON, String, Integer, Boolean, Text
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from ..base import Base

class UsecaseMetadata(Base):
    """
    UseCaseMetadata table to check the status of the usecase
    """

    __tablename__ = "usecase_metadata"

    usecase_id = Column(UUID(as_uuid=True), primary_key = True, default = uuid.uuid4)
    user_id = Column(UUID(as_uuid = True), ForeignKey("users.id"), nullable = False)
    chat_history = Column(JSON, nullable = True)
    chat_summary = Column(Text, nullable = True)  # New column for chat summary
    usecase_name = Column(String, nullable=False)
    text_extraction = Column(String(50), default="Not Started")
    requirement_generation = Column(String(50), default="Not Started")
    scenario_generation = Column(String(50), default="Not Started")
    test_case_generation = Column(String(50), default="Not Started")
    test_script_generation = Column(String(50), default="Not Started")
    requirement_generation_confirmed = Column(Boolean, default=False, nullable=False)
    scenario_generation_confirmed = Column(Boolean, default=False, nullable=False)
    selected_model = Column(String, nullable=True, default="gemini-2.5-flash-lite")
    status = Column(String(20), default="Completed", nullable=False)
    is_deleted = Column(Boolean, default = False, nullable = False)
    created_at = Column(DateTime, default = func.now(), nullable = False)
    updated_at = Column(DateTime, default = func.now(), onupdate = func.now(), nullable = False)
    email = Column(String, nullable = False)

    # Relationships
    user = relationship("User")
    # Use string literal for relationship to avoid circular import
    requirements = relationship("Requirement", back_populates="usecase", lazy="noload")