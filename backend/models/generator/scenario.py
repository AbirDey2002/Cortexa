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


class Scenario(Base):
    """
    Scenario model reflecting the scenarios table in the database.
    Each scenario is linked to a specific requirement.
    """

    __tablename__ = "scenarios"

    id = Column(pgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    requirement_id = Column(
        pgUUID(as_uuid=True), ForeignKey("requirements.id"), nullable=False
    )
    scenario_text = Column(Text, nullable=False)

    # Timestamps
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, default=func.now(), onupdate=func.now(), nullable=False
    )

    # Soft delete flag
    is_deleted = Column(Boolean, default=False, nullable=False)

    # Relationships
    requirement = relationship("Requirement", back_populates="scenarios")
    test_cases = relationship("TestCase", back_populates="scenario")

    def __repr__(self):
        return f"<Scenario(id='{self.id}', requirement_id='{self.requirement_id}')>"