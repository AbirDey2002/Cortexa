import uuid
from sqlalchemy import (
    Column,
    ForeignKey,
    DateTime,
    String,
    Boolean,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as pgUUID
from sqlalchemy.orm import relationship

from ..base import Base


class TestScript(Base):
    """
    TestScript model reflecting the test_scripts table in the database.
    Each test script is linked to a specific test case.
    """

    __tablename__ = "test_scripts"

    id = Column(pgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    test_case_id = Column(
        pgUUID(as_uuid=True), ForeignKey("test_cases.id"), nullable=False, unique=True
    )
    script_text = Column(Text, nullable=False)

    # Timestamps
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, default=func.now(), onupdate=func.now(), nullable=False
    )

    # Soft delete flag
    is_deleted = Column(Boolean, default=False, nullable=False)

    # Relationships
    test_case = relationship("TestCase", back_populates="test_script")

    def __repr__(self):
        return f"<TestScript(id='{self.id}', test_case_id='{self.test_case_id}')>"