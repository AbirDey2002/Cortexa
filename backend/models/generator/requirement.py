import uuid
from sqlalchemy import (
    Column,
    ForeignKey,
    DateTime,
    Boolean,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as pgUUID, JSON
from sqlalchemy.orm import relationship

from ..base import Base


class Requirement(Base):
    """
    Requirement model reflecting the requirements table in the database.
    Each requirement is linked to a specific use case.
    """

    __tablename__ = "requirements"

    id = Column(pgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    usecase_id = Column(
        pgUUID(as_uuid=True), ForeignKey("usecase_metadata.usecase_id"), nullable=False
    )
    requirement_text = Column(JSON, nullable=False)

    # Status field to track generation of child elements
    is_child_generated = Column(Boolean, default=False, nullable=False)

    # Timestamps
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, default=func.now(), onupdate=func.now(), nullable=False
    )

    # Soft delete flag
    is_deleted = Column(Boolean, default=False, nullable=False)

    # Relationships
    usecase = relationship("UsecaseMetadata", back_populates="requirements")
    scenarios = relationship("Scenario", back_populates="requirement")

    def __repr__(self):
        return f"<Requirement(id='{self.id}', usecase_id='{self.usecase_id}')>"