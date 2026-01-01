from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from passlib.context import CryptContext
import uuid
import logging
import requests
from typing import Dict, Any

from deps import get_db
from models.user.user import User
from core.auth import verify_token
from core.env_config import get_auth0_config

logger = logging.getLogger(__name__)
router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class UserCreate(BaseModel):
    email: str
    name: str | None = None
    password: str


class UserUpdate(BaseModel):
    email: str | None = None
    name: str | None = None
    password: str | None = None


class UserLogin(BaseModel):
    email: str
    password: str


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    name: str | None = None
    profile_image_url: str | None = None

    class Config:
        from_attributes = True


class UserSyncResponse(BaseModel):
    user_id: str
    email: str
    name: str | None = None
    profile_image_url: str | None = None


@router.post("/", response_model=UserResponse)
def create_user(payload: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed_password = pwd_context.hash(payload.password)
    user = User(email=payload.email, name=payload.name, password=hashed_password)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/check")
def check_user_exists(email: str, db: Session = Depends(get_db)):
    """
    Check if a user exists with the given email in database.
    Used by frontend to validate before signup/login.
    """
    user = db.query(User).filter(User.email == email, User.is_deleted == False).first()
    return {"exists": user is not None}


class Auth0SignupRequest(BaseModel):
    email: str
    password: str
    name: str | None = None


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
        logger.error(f"\033[91m[AUTH0-M2M] Requesting M2M token from: {token_url}\033[0m")
        logger.error(f"\033[91m[AUTH0-M2M] Using client_id: {client_id[:10]}...\033[0m")
        response = requests.post(token_url, json=token_data, timeout=10)
        
        if response.status_code == 401:
            error_data = response.json() if response.content else {}
            error_msg = error_data.get("error_description", error_data.get("error", "Unauthorized"))
            logger.error(f"\033[91m[AUTH0-M2M] 401 Unauthorized: {error_msg}\033[0m")
            logger.error(f"\033[91m[AUTH0-M2M] Full error response: {error_data}\033[0m")
            
            detailed_error = (
                "Auth0 Management API authentication failed (401 Unauthorized).\n\n"
                "This usually means:\n"
                "1. The M2M application doesn't exist or credentials are wrong\n"
                "2. The M2M application isn't authorized for 'Auth0 Management API'\n"
                "3. The M2M application doesn't have 'create:users' scope\n\n"
                "SETUP INSTRUCTIONS:\n"
                "1. Go to Auth0 Dashboard → Applications → Create Application\n"
                "2. Choose 'Machine to Machine Applications'\n"
                "3. Authorize it for 'Auth0 Management API'\n"
                "4. Grant scopes: 'create:users', 'update:users', 'read:users'\n"
                "5. Copy the Client ID and Client Secret\n"
                "6. Add to backend/.env:\n"
                "   AUTH0_M2M_CLIENT_ID=<your_m2m_client_id>\n"
                "   AUTH0_M2M_CLIENT_SECRET=<your_m2m_client_secret>\n"
                "7. Restart the backend server\n\n"
                f"Error details: {error_msg}"
            )
            raise HTTPException(status_code=500, detail=detailed_error)
        
        response.raise_for_status()
        token_result = response.json()
        access_token = token_result.get("access_token")
        if not access_token:
            raise HTTPException(status_code=500, detail="No access token in Auth0 response")
        logger.error(f"\033[91m[AUTH0-M2M] Successfully obtained M2M token\033[0m")
        return access_token
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"\033[91m[AUTH0-M2M] Failed to get M2M token: {str(e)}\033[0m")
        raise HTTPException(status_code=500, detail=f"Failed to get Auth0 Management API token: {str(e)}")


def _check_user_exists_in_auth0(domain: str, m2m_token: str, email: str) -> dict | None:
    """
    Check if a user exists in Auth0 by email.
    Returns the user object if found, None otherwise.
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
            if users and len(users) > 0:
                # Return the first matching user
                logger.error(f"\033[91m[AUTH0-CHECK] User found in Auth0: {email}\033[0m")
                return users[0]
        
        logger.error(f"\033[91m[AUTH0-CHECK] User not found in Auth0: {email}\033[0m")
        return None
    except Exception as e:
        logger.error(f"\033[91m[AUTH0-CHECK] Error checking user in Auth0: {str(e)}\033[0m")
        # Don't fail the signup if we can't check - let Auth0 handle it
        return None


@router.post("/auth0-signup")
def auth0_signup(payload: Auth0SignupRequest, db: Session = Depends(get_db)):
    """
    Create a new user in Auth0 and database using Management API.
    Handles case where user exists in Auth0 but not in database (syncs them).
    """
    # Check if user already exists in database
    existing_user_db = db.query(User).filter(func.lower(User.email) == payload.email.lower(), User.is_deleted == False).first()
    if existing_user_db:
        raise HTTPException(status_code=400, detail="An account with this email already exists. Please sign in instead.")
    
    # Get Auth0 config
    auth0_config = get_auth0_config()
    domain = auth0_config.get("AUTH0_DOMAIN")
    # Use M2M credentials if available, otherwise fall back to regular credentials
    m2m_client_id = auth0_config.get("AUTH0_M2M_CLIENT_ID") or auth0_config.get("AUTH0_CLIENT_ID")
    m2m_client_secret = auth0_config.get("AUTH0_M2M_CLIENT_SECRET") or auth0_config.get("AUTH0_CLIENT_SECRET")
    has_m2m_creds = bool(auth0_config.get("AUTH0_M2M_CLIENT_ID") and auth0_config.get("AUTH0_M2M_CLIENT_SECRET"))
    
    logger.error(f"\033[91m[AUTH0-SIGNUP] M2M credentials check:\033[0m")
    logger.error(f"\033[91m[AUTH0-SIGNUP] - AUTH0_M2M_CLIENT_ID set: {bool(auth0_config.get('AUTH0_M2M_CLIENT_ID'))}\033[0m")
    logger.error(f"\033[91m[AUTH0-SIGNUP] - AUTH0_M2M_CLIENT_SECRET set: {bool(auth0_config.get('AUTH0_M2M_CLIENT_SECRET'))}\033[0m")
    logger.error(f"\033[91m[AUTH0-SIGNUP] - Using M2M credentials: {has_m2m_creds}\033[0m")
    logger.error(f"\033[91m[AUTH0-SIGNUP] - Fallback to SPA credentials: {not has_m2m_creds}\033[0m")
    
    if not domain or not m2m_client_id or not m2m_client_secret:
        error_msg = (
            "Auth0 configuration missing. Please set the following in your backend/.env file:\n"
            "1. AUTH0_DOMAIN (required)\n"
            "2. AUTH0_M2M_CLIENT_ID (from Machine-to-Machine application)\n"
            "3. AUTH0_M2M_CLIENT_SECRET (from Machine-to-Machine application)\n\n"
            "NOTE: You CANNOT use your SPA application credentials for Management API.\n"
            "You MUST create a separate Machine-to-Machine application in Auth0 Dashboard."
        )
        raise HTTPException(status_code=500, detail=error_msg)
    
    if not has_m2m_creds:
        logger.error(f"\033[91m[AUTH0-SIGNUP] WARNING: Using SPA credentials for M2M - this will likely fail!\033[0m")
        logger.error(f"\033[91m[AUTH0-SIGNUP] Please create a Machine-to-Machine application and set AUTH0_M2M_CLIENT_ID and AUTH0_M2M_CLIENT_SECRET\033[0m")
    
    try:
        # Get M2M token for Management API
        logger.error(f"\033[91m[AUTH0-SIGNUP] Attempting to get M2M token with client_id: {m2m_client_id[:10]}...\033[0m")
        m2m_token = _get_auth0_m2m_token(domain, m2m_client_id, m2m_client_secret)
        
        # Check if user already exists in Auth0
        logger.error(f"\033[91m[AUTH0-SIGNUP] Checking if user exists in Auth0: {payload.email}\033[0m")
        auth0_user = _check_user_exists_in_auth0(domain, m2m_token, payload.email)
        
        if auth0_user:
            # User exists in Auth0 but not in our database
            logger.error(f"\033[91m[AUTH0-SIGNUP] User exists in Auth0 but not in DB. Syncing to database...\033[0m")
            
            # Check the connection type - if it's Google, they should sign in with Google
            connections = auth0_user.get("identities", [])
            is_google_user = any(conn.get("provider") == "google-oauth2" for conn in connections)
            
            if is_google_user:
                raise HTTPException(
                    status_code=400,
                    detail="An account with this email already exists (created via Google). Please sign in with Google instead."
                )
            
            # User exists in Auth0 (likely created via another method or previous signup)
            # Create them in our database
            user = User(
                email=payload.email,
                name=payload.name or auth0_user.get("name"),
                password=None,  # Auth0 handles password
                profile_image_url=auth0_user.get("picture")
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            
            logger.error(f"\033[91m[AUTH0-SIGNUP] User synced to database successfully: {user.email}\033[0m")
            
            return {
                "success": True,
                "user_id": str(user.id),
                "email": user.email,
                "message": "Account synced successfully. Please sign in to continue."
            }
        
        # User doesn't exist in Auth0, create new user
        logger.error(f"\033[91m[AUTH0-SIGNUP] User doesn't exist in Auth0. Creating new user...\033[0m")
        
        # Create user in Auth0 using Management API
        management_url = f"https://{domain}/api/v2/users"
        user_data = {
            "email": payload.email,
            "password": payload.password,
            "connection": "Username-Password-Authentication",
            "email_verified": False,
        }
        if payload.name:
            user_data["name"] = payload.name
        
        headers = {
            "Authorization": f"Bearer {m2m_token}",
            "Content-Type": "application/json",
        }
        
        response = requests.post(management_url, json=user_data, headers=headers, timeout=10)
        
        if response.status_code == 409:  # Conflict - user already exists (race condition)
            # This shouldn't happen since we checked, but handle it anyway
            logger.error(f"\033[91m[AUTH0-SIGNUP] 409 Conflict - User was created between check and create. Syncing...\033[0m")
            auth0_user = _check_user_exists_in_auth0(domain, m2m_token, payload.email)
            if auth0_user:
                # Sync to database
                user = User(
                    email=payload.email,
                    name=payload.name or auth0_user.get("name"),
                    password=None,
                    profile_image_url=auth0_user.get("picture")
                )
                db.add(user)
                db.commit()
                db.refresh(user)
                
                return {
                    "success": True,
                    "user_id": str(user.id),
                    "email": user.email,
                    "message": "Account synced successfully. Please sign in to continue."
                }
            else:
                raise HTTPException(
                    status_code=400,
                    detail="An account with this email already exists. Please sign in instead."
                )
        
        response.raise_for_status()
        auth0_user = response.json()
        
        # User created successfully in Auth0
        # Now create user in our database
        user = User(
            email=payload.email,
            name=payload.name,
            password=None,  # Auth0 handles password
            profile_image_url=auth0_user.get("picture")
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        
        logger.error(f"\033[91m[AUTH0-SIGNUP] User created successfully in Auth0 and DB: {user.email}\033[0m")
        
        return {
            "success": True,
            "user_id": str(user.id),
            "email": user.email,
            "message": "Account created successfully"
        }
        
    except HTTPException:
        raise
    except requests.exceptions.HTTPError as e:
        logger.error(f"\033[91m[AUTH0-SIGNUP] HTTP error: {str(e)}\033[0m")
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_data = e.response.json()
                error_msg = error_data.get("message", error_data.get("error", "Failed to create user in Auth0"))
                if "already exists" in error_msg.lower() or "user already exists" in error_msg.lower() or "already in use" in error_msg.lower():
                    raise HTTPException(
                        status_code=400,
                        detail="An account with this email already exists (possibly created via Google). Please sign in instead."
                    )
                raise HTTPException(status_code=400, detail=f"Auth0 signup failed: {error_msg}")
            except HTTPException:
                raise
            except:
                raise HTTPException(status_code=400, detail=f"Failed to create user in Auth0: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to communicate with Auth0: {str(e)}")
    except requests.exceptions.RequestException as e:
        logger.error(f"\033[91m[AUTH0-SIGNUP] Request error: {str(e)}\033[0m")
        raise HTTPException(status_code=500, detail=f"Failed to communicate with Auth0: {str(e)}")
    except Exception as e:
        logger.error(f"\033[91m[AUTH0-SIGNUP] Unexpected error: {str(e)}\033[0m", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Unexpected error during signup: {str(e)}")


@router.get("/{user_id}", response_model=UserResponse)
def get_user(user_id: uuid.UUID, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id, User.is_deleted == False).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.post("/verify")
def verify_user(payload: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email, User.is_deleted == False).first()
    if not user or not user.password:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not pwd_context.verify(payload.password, user.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"status": "verified", "user_id": str(user.id)}


class Auth0LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/auth0-login")
def auth0_login(payload: Auth0LoginRequest, db: Session = Depends(get_db)):
    """
    Authenticate user with Auth0 using password grant (Resource Owner Password Credentials).
    Returns access token and user info. No popup/redirect needed.
    """
    # Check if user exists in database first
    user = db.query(User).filter(User.email == payload.email, User.is_deleted == False).first()
    if not user:
        raise HTTPException(status_code=404, detail="No account found with this email. Please sign up first.")
    
    # Get Auth0 config
    auth0_config = get_auth0_config()
    domain = auth0_config.get("AUTH0_DOMAIN")
    client_id = auth0_config.get("AUTH0_CLIENT_ID")
    client_secret = auth0_config.get("AUTH0_CLIENT_SECRET")
    audience = auth0_config.get("AUTH0_AUDIENCE")
    
    if not domain or not client_id or not client_secret:
        raise HTTPException(status_code=500, detail="Auth0 configuration missing")
    
    # Authenticate with Auth0 using password grant
    token_url = f"https://{domain}/oauth/token"
    token_data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "audience": audience,
        "grant_type": "password",
        "username": payload.email,
        "password": payload.password,
        "connection": "Username-Password-Authentication",
        "scope": "openid profile email",
    }
    
    try:
        response = requests.post(token_url, json=token_data, timeout=10)
        response.raise_for_status()
        auth0_tokens = response.json()
        
        access_token = auth0_tokens.get("access_token")
        id_token = auth0_tokens.get("id_token")
        
        if not access_token:
            raise HTTPException(status_code=401, detail="Failed to get access token from Auth0")
        
        # Decode ID token to get user info (we can use python-jose for this)
        from jose import jwt
        try:
            # For password grant, we don't verify the token signature since we got it from Auth0
            # But we should at least decode it to get user info
            id_token_payload = jwt.get_unverified_claims(id_token) if id_token else {}
        except:
            id_token_payload = {}
        
        return {
            "access_token": access_token,
            "id_token": id_token,
            "user_id": str(user.id),
            "email": user.email,
            "name": user.name,
        }
        
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            raise HTTPException(status_code=401, detail="Invalid email or password")
        elif e.response.status_code == 403:
            raise HTTPException(status_code=403, detail="Access denied. Please check your credentials.")
        else:
            error_data = e.response.json() if e.response else {}
            error_msg = error_data.get("error_description", error_data.get("error", "Authentication failed"))
            raise HTTPException(status_code=401, detail=error_msg)
    except requests.exceptions.RequestException as e:
        logger.error(f"\033[91m[AUTH0-LOGIN] Request error: {str(e)}\033[0m")
        raise HTTPException(status_code=500, detail=f"Failed to communicate with Auth0: {str(e)}")
    except Exception as e:
        logger.error(f"\033[91m[AUTH0-LOGIN] Unexpected error: {str(e)}\033[0m", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Unexpected error during login: {str(e)}")


@router.patch("/{user_id}", response_model=UserResponse)
def update_user(user_id: uuid.UUID, payload: UserUpdate, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id, User.is_deleted == False).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if payload.email is not None:
        user.email = payload.email
    if payload.name is not None:
        user.name = payload.name
    if payload.password is not None:
        user.password = pwd_context.hash(payload.password)
    db.commit()
    db.refresh(user)
    return user


@router.post("/sync-login", response_model=UserSyncResponse)
def sync_user_login(
    token_payload: Dict[str, Any] = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """
    Sync Auth0 user to database for LOGIN flow.
    Only updates existing users, does NOT create new users.
    Returns error if user doesn't exist.
    """
    logger.error("\033[91m[USER-SYNC-LOGIN] Endpoint called - Starting user sync for login\033[0m")
    
    # Extract user info from JWT token
    email = token_payload.get("email")
    if not email:
        email = token_payload.get("sub")
    
    if not email:
        logger.error("\033[91m[USER-SYNC-LOGIN] ERROR: Neither email nor sub found in token\033[0m")
        raise HTTPException(
            status_code=400,
            detail="Email or sub not found in token"
        )
    
    name = token_payload.get("name") or token_payload.get("nickname")
    picture = token_payload.get("picture")
    
    logger.error(f"\033[91m[USER-SYNC-LOGIN] Checking if user exists with email: {email}\033[0m")
    user = db.query(User).filter(User.email == email, User.is_deleted == False).first()
    
    if not user:
        logger.error(f"\033[91m[USER-SYNC-LOGIN] User does not exist! Email: {email}\033[0m")
        raise HTTPException(
            status_code=404,
            detail="No account found with this email. Please sign up first."
        )
    
    logger.error(f"\033[91m[USER-SYNC-LOGIN] User exists! User ID: {user.id}\033[0m")
    # Update existing user
    if name:
        user.name = name
    if picture:
        user.profile_image_url = picture
    db.commit()
    db.refresh(user)
    
    response = UserSyncResponse(
        user_id=str(user.id),
        email=user.email,
        name=user.name,
        profile_image_url=user.profile_image_url
    )
    
    logger.error(f"\033[91m[USER-SYNC-LOGIN] Returning response: {response}\033[0m")
    return response


@router.post("/sync", response_model=UserSyncResponse)
def sync_user(
    token_payload: Dict[str, Any] = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """
    Sync Auth0 user to database for SIGNUP flow.
    Creates user if doesn't exist, updates if exists.
    """
    logger.error("\033[91m[USER-SYNC] Starting user sync\033[0m")
    logger.error(f"\033[91m[USER-SYNC] Token payload keys: {list(token_payload.keys())}\033[0m")
    logger.error(f"\033[91m[USER-SYNC] Full token payload: {token_payload}\033[0m")
    
    # Extract user info from JWT token
    # Prefer email, but if not available, use sub (Auth0 user ID) as email
    email = token_payload.get("email")
    if not email:
        logger.error("\033[91m[USER-SYNC] WARNING: No email in token, using sub as email\033[0m")
        email = token_payload.get("sub")
        if email:
            logger.error(f"\033[91m[USER-SYNC] Using sub as email: {email}\033[0m")
    
    name = token_payload.get("name") or token_payload.get("nickname")
    picture = token_payload.get("picture")
    
    logger.error(f"\033[91m[USER-SYNC] Extracted email: {email}\033[0m")
    logger.error(f"\033[91m[USER-SYNC] Extracted name: {name}\033[0m")
    logger.error(f"\033[91m[USER-SYNC] Extracted picture: {picture}\033[0m")
    logger.error(f"\033[91m[USER-SYNC] Token sub: {token_payload.get('sub')}\033[0m")
    
    if not email:
        logger.error("\033[91m[USER-SYNC] ERROR: Neither email nor sub found in token\033[0m")
        raise HTTPException(
            status_code=400,
            detail="Email or sub not found in token"
        )
    
    # Check if user exists
    logger.error(f"\033[91m[USER-SYNC] Checking if user exists with email: {email}\033[0m")
    user = db.query(User).filter(User.email == email, User.is_deleted == False).first()
    
    if user:
        logger.error(f"\033[91m[USER-SYNC] User exists! User ID: {user.id}\033[0m")
        # Update existing user
        if name:
            logger.error(f"\033[91m[USER-SYNC] Updating name: {user.name} -> {name}\033[0m")
            user.name = name
        if picture:
            logger.error(f"\033[91m[USER-SYNC] Updating profile_image_url: {user.profile_image_url} -> {picture}\033[0m")
            user.profile_image_url = picture
        db.commit()
        db.refresh(user)
        logger.error(f"\033[91m[USER-SYNC] User updated successfully\033[0m")
    else:
        logger.error("\033[91m[USER-SYNC] User does not exist, creating new user...\033[0m")
        # Check if email already exists (case-insensitive check for safety)
        existing_email = db.query(User).filter(
            func.lower(User.email) == email.lower(),
            User.is_deleted == False
        ).first()
        
        if existing_email:
            logger.error(f"\033[91m[USER-SYNC] Email conflict detected: {email} already exists with different case\033[0m")
            raise HTTPException(
                status_code=400,
                detail="An account with this email already exists. Please sign in instead."
            )
        
        # Create new user
        user = User(
            email=email,
            name=name,
            password=None,  # Auth0 handles authentication
            profile_image_url=picture
        )
        logger.error(f"\033[91m[USER-SYNC] New user object created: email={user.email}, name={user.name}\033[0m")
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.error(f"\033[91m[USER-SYNC] New user created successfully! User ID: {user.id}\033[0m")
    
    response = UserSyncResponse(
        user_id=str(user.id),
        email=user.email,
        name=user.name,
        profile_image_url=user.profile_image_url
    )
    
    logger.error(f"\033[91m[USER-SYNC] Returning response: {response}\033[0m")
    return response


