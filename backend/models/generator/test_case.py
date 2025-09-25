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


class TestCase(Base):
    """
    TestCase model reflecting the test_cases table in the database.
    Each test case is linked to a specific scenario.
    """

    __tablename__ = "test_cases"

    id = Column(pgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scenario_id = Column(
        pgUUID(as_uuid=True), ForeignKey("scenarios.id"), nullable=False
    )
    test_case_text = Column(Text, nullable=False)

    # Timestamps
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, default=func.now(), onupdate=func.now(), nullable=False
    )

    # Soft delete flag
    is_deleted = Column(Boolean, default=False, nullable=False)

    # Relationships
    scenario = relationship("Scenario", back_populates="test_cases")
    # Disable test_script relationship to avoid circular dependency
    # test_script = relationship(
    #     "TestScript", back_populates="test_case", uselist=False,
    #     post_update=True
    # )

    def __repr__(self):
        return f"<TestCase(id='{self.id}', scenario_id='{self.scenario_id}')>"