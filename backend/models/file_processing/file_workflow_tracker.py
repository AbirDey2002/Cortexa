from sqlalchemy import Column, ForeignKey, String, Boolean, Text
from sqlalchemy.dialects.postgresql import UUID as pgUUID
from ..base import Base


class FileWorkflowTracker(Base):
    __tablename__ = "file_workflow_tracker"
    file_id = Column(pgUUID(as_uuid=True), ForeignKey('file_metadata.file_id'), primary_key=True)
    text_extraction = Column(String(50), default="Not Started")
    requirement_generation = Column(String(50), default="Not Started")
    scenario_generation = Column(String(50), default="Not Started")
    test_case_generation = Column(String(50), default="Not Started")
    test_data_generation = Column(String(50), default="Not Started")
    test_script_generation = Column(String(50), default="Not Started")
    error_msg = Column(Text, nullable=True)
    is_deleted = Column(Boolean, default=False)
