"""
Authorization helpers for validating user ownership of resources.
Prevents users from accessing other users' data.
"""
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from typing import Any, Dict
import uuid
import logging

logger = logging.getLogger(__name__)


def verify_usecase_owner(
    db: Session,
    usecase_id: str,
    token_payload: Dict[str, Any]
) -> bool:
    """
    Verify that the authenticated user owns the specified usecase.
    
    Args:
        db: Database session
        usecase_id: UUID of the usecase to check
        token_payload: Decoded JWT token payload
    
    Returns:
        True if user owns the usecase
        
    Raises:
        HTTPException: 404 if usecase not found, 403 if user doesn't own it
    """
    from models.usecase.usecase import UsecaseMetadata
    from models.user.user import User
    
    # Get user from token
    email = token_payload.get("email")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email not found in token"
        )
    
    # Fetch user
    user = db.query(User).filter(User.email == email, User.is_deleted == False).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Fetch usecase and verify ownership
    usecase = db.query(UsecaseMetadata).filter(
        UsecaseMetadata.usecase_id == usecase_id,
        UsecaseMetadata.is_deleted == False
    ).first()
    
    if not usecase:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usecase not found"
        )
    
    if str(usecase.user_id) != str(user.id):
        logger.warning(
            f"Authorization failed: User {user.id} attempted to access usecase {usecase_id} "
            f"owned by {usecase.user_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this usecase"
        )
    
    return True


def verify_file_owner(
    db: Session,
    file_id: str,
    token_payload: Dict[str, Any]
) -> bool:
    """
    Verify that the authenticated user owns the specified file (via usecase ownership).
    
    Args:
        db: Database session
        file_id: UUID of the file to check
        token_payload: Decoded JWT token payload
    
    Returns:
        True if user owns the file
        
    Raises:
        HTTPException: 404 if file not found, 403 if user doesn't own it
    """
    from models.file_processing.file_metadata import FileMetadata
    from models.user.user import User
    
    # Get user from token
    email = token_payload.get("email")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email not found in token"
        )
    
    # Fetch user
    user = db.query(User).filter(User.email == email, User.is_deleted == False).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Fetch file
    file = db.query(FileMetadata).filter(
        FileMetadata.file_id == file_id,
        FileMetadata.is_deleted == False
    ).first()
    
    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )
    
    # Verify usecase ownership
    if file.usecase_id:
        verify_usecase_owner(db, str(file.usecase_id), token_payload)
    
    return True


def get_user_from_token(
    db: Session,
    token_payload: Dict[str, Any]
):
    """
    Get user object from token payload.
    
    Args:
        db: Database session
        token_payload: Decoded JWT token payload
    
    Returns:
        User object
        
    Raises:
        HTTPException: 401 if email not in token, 404 if user not found
    """
    from models.user.user import User
    
    email = token_payload.get("email")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email not found in token"
        )
    
    user = db.query(User).filter(User.email == email, User.is_deleted == False).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return user
