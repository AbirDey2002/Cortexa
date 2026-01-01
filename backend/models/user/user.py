import uuid
from sqlalchemy import Column, String, Boolean, DateTime, func
from sqlalchemy.dialects.postgresql import UUID

# This relative import goes up one level to the 'models' directory
# to find the base.py file.
from ..base import Base

class User(Base):
    """
    User model reflecting the users table in the database.
    """
    __tablename__ = 'users'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, nullable=False)
    # The length of the string is passed directly to the String type
    name = Column(String(50), nullable=True)
    password = Column(String, nullable=True)
    profile_image_url = Column(String, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    
    # Soft delete flag
    is_deleted = Column(Boolean, default=False, nullable=False)

    def __repr__(self):
        return f"<User(id='{self.id}', email='{self.email}', name='{self.name}')>"