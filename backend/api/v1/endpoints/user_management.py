from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
import uuid
import logging
import requests
from typing import Dict, Any
from datetime import datetime

from deps import get_db
from models.user.user import User
from core.auth import verify_token
from core.env_config import get_auth0_config

# Import additional models for cascading delete
from models.usecase.usecase import UsecaseMetadata
from models.generator.requirement import Requirement
from models.generator.scenario import Scenario
from models.generator.test_case import TestCase
from models.generator.test_script import TestScript
from models.file_processing.file_metadata import FileMetadata
from models.file_processing.file_workflow_tracker import FileWorkflowTracker
from models.file_processing.ocr_records import OCRInfo, OCROutputs

logger = logging.getLogger(__name__)
router = APIRouter()

router = APIRouter()


class UserUpdate(BaseModel):
    email: str | None = None
    name: str | None = None
    push_notification: bool | None = None


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    name: str | None = None
    push_notification: bool
    created_at: datetime

    class Config:
        from_attributes = True


class UserSyncResponse(BaseModel):
    user_id: str
    email: str
    name: str | None = None


@router.get("/{user_id}", response_model=UserResponse)
def get_user(user_id: uuid.UUID, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id, User.is_deleted == False).first()
    if not user:
        raise HTTPException(status_code=44, detail="User not found")
    
    response = UserResponse.model_validate(user)
    return response


@router.patch("/{user_id}", response_model=UserResponse)
def update_user(user_id: uuid.UUID, payload: UserUpdate, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id, User.is_deleted == False).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if payload.email is not None:
        user.email = payload.email
    if payload.name is not None:
        user.name = payload.name
    # Handle push_notification update
    if payload.push_notification is not None:
        user.push_notification = payload.push_notification
    db.commit()
    db.refresh(user)
    
    response = UserResponse.model_validate(user)
    return response


@router.delete("/{user_id}/data")
def delete_user_data(user_id: uuid.UUID, db: Session = Depends(get_db)):
    """
    Delete all data associated with the user (Usecases, Requirements, Scenarios, etc.)
    but keep the user account.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    try:
        # Get all usecase IDs for this user
        usecases = db.query(UsecaseMetadata).filter(UsecaseMetadata.user_id == user_id).all()
        usecase_ids = [u.usecase_id for u in usecases]
        
        if not usecase_ids:
            return {"status": "success", "message": "No data found to delete"}

        # --- File Processing Branch ---
        files = db.query(FileMetadata).filter(FileMetadata.usecase_id.in_(usecase_ids)).all()
        file_ids = [f.file_id for f in files]
        
        if file_ids:
            # Delete OCR Outputs & Info
            db.query(OCROutputs).filter(OCROutputs.file_id.in_(file_ids)).delete(synchronize_session=False)
            db.query(OCRInfo).filter(OCRInfo.file_id.in_(file_ids)).delete(synchronize_session=False)
            
            # Delete Workflow Trackers
            db.query(FileWorkflowTracker).filter(FileWorkflowTracker.file_id.in_(file_ids)).delete(synchronize_session=False)
            
            # Delete Files
            db.query(FileMetadata).filter(FileMetadata.file_id.in_(file_ids)).delete(synchronize_session=False)

        # --- Generator Branch ---
        # Get Requirement IDs
        requirements = db.query(Requirement).filter(Requirement.usecase_id.in_(usecase_ids)).all()
        req_ids = [r.id for r in requirements]
        
        if req_ids:
            # Get Scenario IDs
            scenarios = db.query(Scenario).filter(Scenario.requirement_id.in_(req_ids)).all()
            scenario_ids = [s.id for s in scenarios]
            
            if scenario_ids:
                # Get TestCase IDs
                test_cases = db.query(TestCase).filter(TestCase.scenario_id.in_(scenario_ids)).all()
                tc_ids = [tc.id for tc in test_cases]
                
                if tc_ids:
                    # 1. Delete TestScripts
                    db.query(TestScript).filter(TestScript.test_case_id.in_(tc_ids)).delete(synchronize_session=False)
                    
                    # 2. Delete TestScenes / TestCases
                    db.query(TestCase).filter(TestCase.id.in_(tc_ids)).delete(synchronize_session=False)
                
                # 3. Delete Scenarios
                db.query(Scenario).filter(Scenario.id.in_(scenario_ids)).delete(synchronize_session=False)
            
            # 4. Delete Requirements
            db.query(Requirement).filter(Requirement.id.in_(req_ids)).delete(synchronize_session=False)
            
        # 5. Delete Usecases
        db.query(UsecaseMetadata).filter(UsecaseMetadata.usecase_id.in_(usecase_ids)).delete(synchronize_session=False)
            
        db.commit()
        return {"status": "success", "message": "All user data deleted successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete user data: {str(e)}")



def _get_auth0_m2m_token(domain: str, client_id: str, client_secret: str) -> str:
    """
    Get Machine-to-Machine access token from Auth0 for Management API.
    """
    token_url = f"https://{domain}/oauth/token"
    token_data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "audience": f"https://{domain}/api/v2/",
        "grant_type": "client_credentials",
    }
    
    try:
        response = requests.post(token_url, json=token_data, timeout=10)
        
        if response.status_code == 401:
            error_data = response.json() if response.content else {}
            error_msg = error_data.get("error_description", error_data.get("error", "Unauthorized"))
            
            detailed_error = (
                "Auth0 Management API authentication failed (401 Unauthorized).\\n\\n"
                "This usually means:\\n"
                "1. The M2M application doesn't exist or credentials are wrong\\n"
                "2. The M2M application isn't authorized for 'Auth0 Management API'\\n"
                "3. The M2M application doesn't have 'create:users' scope\\n\\n"
                "SETUP INSTRUCTIONS:\\n"
                "1. Go to Auth0 Dashboard → Applications → Create Application\\n"
                "2. Choose 'Machine to Machine Applications'\\n"
                "3. Authorize it for 'Auth0 Management API'\\n"
                "4. Grant scopes: 'create:users', 'update:users', 'read:users'\\n"
                "5. Copy the Client ID and Client Secret\\n"
                "6. Add to backend/.env:\\n"
                "   AUTH0_M2M_CLIENT_ID=<your_m2m_client_id>\\n"
                "   AUTH0_M2M_CLIENT_SECRET=<your_m2m_client_secret>\\n"
                "7. Restart the backend server\\n\\n"
                f"Error details: {error_msg}"
            )
            # Log error but raise generic to avoid leaking too much info to frontend if not admin
            logger.error(detailed_error)
            raise HTTPException(status_code=500, detail="Auth0 Management API authentication failed")
        
        response.raise_for_status()
        token_result = response.json()
        access_token = token_result.get("access_token")
        if not access_token:
            raise HTTPException(status_code=500, detail="No access token in Auth0 response")
        return access_token
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get Auth0 Management API token: {str(e)}")


def _get_users_by_email_from_auth0(domain: str, m2m_token: str, email: str) -> list[dict]:
    """
    Get all users in Auth0 by email.
    Returns a list of user objects.
    """
    try:
        # Search for user by email in Auth0
        search_url = f"https://{domain}/api/v2/users-by-email"
        headers = {
            "Authorization": f"Bearer {m2m_token}",
            "Content-Type": "application/json",
        }
        params = {"email": email}
        
        response = requests.get(search_url, headers=headers, params=params, timeout=10)
        
        if response.status_code == 200:
            users = response.json()
            return users if isinstance(users, list) else []
        
        return []
    except Exception as e:
        logger.error(f"Failed to fetch users from Auth0: {e}")
        return []


@router.delete("/{user_id}")
def delete_account(user_id: uuid.UUID, db: Session = Depends(get_db)):
    """
    Delete user account and all associated data.
    """
    # 1. Delete all associated data
    try:
        delete_user_data(user_id, db)
    except HTTPException as e:
        if e.status_code != 404: 
            raise e
    except Exception as e:
         # Log but try to continue to account deletion if data deletion fails? 
         # No, if data delete fails (e.g. FK constraint), user delete will fail too.
         # So we must raise, but maybe data delete succeeded partially?
         # delete_user_data commits.
         raise HTTPException(status_code=500, detail=f"Failed to delete user data: {str(e)}")
    
    # 2. Get user to delete
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        # Might have been deleted conceptually?
        # If user is gone, we are good.
        return {"status": "success", "message": "Account already deleted"}
        
    # 3. Delete from Auth0 (Best Effort)
    try:
        auth0_config = get_auth0_config()
        domain = auth0_config.get("AUTH0_DOMAIN")
        m2m_client_id = auth0_config.get("AUTH0_M2M_CLIENT_ID") or auth0_config.get("AUTH0_CLIENT_ID")
        m2m_client_secret = auth0_config.get("AUTH0_M2M_CLIENT_SECRET") or auth0_config.get("AUTH0_CLIENT_SECRET")
        
        if domain and m2m_client_id and m2m_client_secret:
            m2m_token = _get_auth0_m2m_token(domain, m2m_client_id, m2m_client_secret)
            # Get ALL identities
            auth0_users = _get_users_by_email_from_auth0(domain, m2m_token, user.email)
            
            for auth0_u in auth0_users:
                try:
                    u_id = auth0_u.get("user_id")
                    if u_id:
                        requests.delete(
                            f"https://{domain}/api/v2/users/{u_id}",
                            headers={"Authorization": f"Bearer {m2m_token}"},
                            timeout=5
                        )
                        logger.info(f"Deleted Auth0 identity: {u_id}")
                except Exception as ex:
                    logger.error(f"Failed to delete Auth0 user {auth0_u.get('user_id')}: {ex}")
                    # Continue to next identity
    except Exception as e:
        logger.error(f"Auth0 deletion process failed: {e}")
        # Continue to DB deletion
        
    # 4. Delete from DB (Strict)
    try:
        # Re-fetch in case session issues, though 'user' is attached.
        db.delete(user)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete account from database: {str(e)}")
            
    return {"status": "success", "message": "Account deleted successfully"}


def _resolve_auth0_email(sub: str) -> str:
    """
    Resolve email from Auth0 using the subject (user_id) if missing from token.
    """
    try:
        auth0_config = get_auth0_config()
        domain = auth0_config.get("AUTH0_DOMAIN")
        m2m_client_id = auth0_config.get("AUTH0_M2M_CLIENT_ID") or auth0_config.get("AUTH0_CLIENT_ID")
        m2m_client_secret = auth0_config.get("AUTH0_M2M_CLIENT_SECRET") or auth0_config.get("AUTH0_CLIENT_SECRET")
        
        if not domain or not m2m_client_id or not m2m_client_secret:
            logger.error("Auth0 M2M credentials missing for email resolution")
            return None
            
        m2m_token = _get_auth0_m2m_token(domain, m2m_client_id, m2m_client_secret)
        
        # quote the sub just in case, though usually safe_url_string
        import urllib.parse
        safe_sub = urllib.parse.quote(sub)
        
        url = f"https://{domain}/api/v2/users/{safe_sub}"
        headers = {"Authorization": f"Bearer {m2m_token}"}
        
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return data.get("email")
            
        logger.error(f"Failed to fetch user {sub}: {response.text}")
        return None
    except Exception as e:
        logger.error(f"Error resolving email for {sub}: {e}")
        return None




@router.post("/sync", response_model=UserSyncResponse)
def sync_user(
    token_payload: Dict[str, Any] = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """
    Sync Auth0 user to database for SIGNUP flow.
    Creates user if doesn't exist, updates if exists.
    """
    # Extract user info from JWT token
    # Prefer email, but if not available, use sub (Auth0 user ID) as email
    email = token_payload.get("email")
    if not email and token_payload.get("sub"):
        email = _resolve_auth0_email(token_payload.get("sub"))
    
    name = token_payload.get("name") or token_payload.get("nickname")
    name = token_payload.get("name") or token_payload.get("nickname")
    
    if not email:
        raise HTTPException(
            status_code=400,
            detail="Email or sub not found in token"
        )
    
    # Check if user exists
    user = db.query(User).filter(User.email == email, User.is_deleted == False).first()
    
    if user:
        # Update existing user
        if name:
            user.name = name
        db.commit()
        db.refresh(user)
    else:
        # Check if email already exists (case-insensitive check for safety)
        existing_email = db.query(User).filter(
            func.lower(User.email) == email.lower(),
            User.is_deleted == False
        ).first()
        
        if existing_email:
            raise HTTPException(
                status_code=400,
                detail="An account with this email already exists. Please sign in instead."
            )
        
        # Create new user
        user = User(
            email=email,
            name=name
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    
    response = UserSyncResponse(
        user_id=str(user.id),
        email=user.email,
        name=user.name
    )
    
    return response


