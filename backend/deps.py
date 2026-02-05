import logging
from typing import Dict, Any
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session
from db.session import get_db
from models.user.user import User
from core.auth import verify_token

logger = logging.getLogger(__name__)

def get_current_user(
    request: Request,
    token_payload: Dict[str, Any] = Depends(verify_token),
    db: Session = Depends(get_db)
) -> User:
    """
    Dependency to resolve the current user from the JWT token payload.
    Auto-creates the user in the database if they don't exist yet but have a valid token.
    """
    email = token_payload.get("email")
    if not email:
        email = token_payload.get("sub")
    
    if not email:
        raise HTTPException(status_code=401, detail="Could not identify user from token")
        
    user = db.query(User).filter(User.email == email, User.is_deleted == False).first()
    
    if not user:
        logger.info(f"User {email} not found in DB. Auto-creating from token.")
        name = token_payload.get("name") or token_payload.get("nickname")
        user = User(email=email, name=name)
        db.add(user)
        db.commit()
        db.refresh(user)
         
    request.state.user_id = user.id
    return user


