import uuid
from sqlalchemy import (
    Column,
    String,
    Boolean,
    ForeignKey,
    TIMESTAMP,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as pgUUID
from sqlalchemy.orm import relationship

# This relative import goes up two levels to the 'models' directory
# to find the base.py file.
from ..base import Base


class FileMetadata(Base):
    """
    FileMetadata model reflecting the file_metadata table in the database.
    This table stores metadata about files uploaded by users.
    """

    __tablename__ = "file_metadata"

    file_id = Column(pgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    usecase_id = Column(pgUUID(as_uuid=True), ForeignKey("usecase_metadata.usecase_id"), nullable=False)
    file_name = Column(String(255), nullable=False)
    file_link = Column(String(255), nullable=False)  # Online storage URL
    user_id = Column(pgUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    # Timestamps
    created_at = Column(TIMESTAMP, default=func.now(), nullable=False)
    updated_at = Column(
        TIMESTAMP, default=func.now(), onupdate=func.now(), nullable=False
    )

    # Soft delete flag
    is_deleted = Column(Boolean, default=False, nullable=False)

    # Relationships
    user = relationship("User")
    usecase = relationship("UsecaseMetadata")

    def __repr__(self):
        return f"<FileMetadata(file_id='{self.file_id}', file_name='{self.file_name}')>"

