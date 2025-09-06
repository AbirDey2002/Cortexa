import uuid
from sqlalchemy import (
    Column,
    ForeignKey,
    TIMESTAMP,
    Integer,
    Boolean,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as pgUUID
from sqlalchemy.orm import relationship
from ..base import Base


class OCRInfo(Base):
    __tablename__ = "ocr_info"
    id = Column(pgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    file_id = Column(pgUUID(as_uuid=True), ForeignKey("file_metadata.file_id"))
    total_pages = Column(Integer, nullable=False)
    completed_pages = Column(Integer, nullable=False)
    error_pages = Column(Integer, nullable=False)
    is_deleted = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP, default=func.now())
    updated_at = Column(TIMESTAMP, default=func.now(), onupdate=func.now())

    file = relationship("FileMetadata", back_populates="ocr_info")

    def __repr__(self):
        return f"<OCRInfo(id='{self.id}', file_id='{self.file_id}')>"


class OCROutputs(Base):
    __tablename__ = "ocr_outputs"
    id = Column(pgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    file_id = Column(pgUUID(as_uuid=True), ForeignKey("file_metadata.file_id"))
    page_number = Column(Integer, nullable=False)
    page_text = Column(Text, nullable=False)
    error_msg = Column(Text, nullable=True)
    is_completed = Column(Boolean, default=False)
    is_deleted = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP, default=func.now())
    updated_at = Column(TIMESTAMP, default=func.now(), onupdate=func.now())

    file = relationship("FileMetadata", back_populates="ocr_outputs")

    def __repr__(self):
        return f"<OCROutputs(id='{self.id}', page_number='{self.page_number}')>"

