from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, text, desc
from datetime import datetime, timedelta
import logging
from typing import List, Dict, Any

from deps import get_db
from core.auth import verify_token
from models.user.user import User
from models.usecase.usecase import UsecaseMetadata
from models.generator.requirement import Requirement
from models.generator.scenario import Scenario
from models.generator.test_case import TestCase
from models.generator.test_script import TestScript

# Heuristic sizes in KB
SIZE_REQ_KB = 2
SIZE_SCENARIO_KB = 1
SIZE_TC_KB = 3
SIZE_TS_KB = 5

router = APIRouter()
logger = logging.getLogger(__name__)

def _get_user_from_token(db: Session, token_payload: Dict[str, Any]) -> User:
    email = token_payload.get("email") or token_payload.get("sub")
    if not email:
        raise HTTPException(status_code=401, detail="Could not identify user")
    user = db.query(User).filter(User.email == email, User.is_deleted == False).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

@router.get("/")
def get_user_metrics(
    token_payload: Dict[str, Any] = Depends(verify_token),
    db: Session = Depends(get_db)
):
    try:
        user = _get_user_from_token(db, token_payload)
        user_id = user.id

        # 1. Get all usecase IDs for this user
        usecases = db.query(UsecaseMetadata.usecase_id).filter(
            UsecaseMetadata.user_id == user_id, 
            UsecaseMetadata.is_deleted == False
        ).all()
        usecase_ids = [u[0] for u in usecases]

        if not usecase_ids:
            return {
                "counts": {"requirements": 0, "scenarios": 0, "test_cases": 0, "test_scripts": 0},
                "storage": {"used_kb": 0, "formatted": "0 KB"},
                "trends": [],
                "recent_activity": []
            }

        # 2. Counts
        req_count = db.query(func.count(Requirement.id)).filter(
            Requirement.usecase_id.in_(usecase_ids),
            Requirement.is_deleted == False
        ).scalar() or 0

        scenario_count = db.query(func.count(Scenario.id)).join(Requirement).filter(
            Requirement.usecase_id.in_(usecase_ids),
            Scenario.is_deleted == False
        ).scalar() or 0

        tc_count = db.query(func.count(TestCase.id)).join(Scenario).join(Requirement).filter(
            Requirement.usecase_id.in_(usecase_ids),
            TestCase.is_deleted == False
        ).scalar() or 0
        
        # TestScript parsing note: TestScript links to TestCase
        ts_count = db.query(func.count(TestScript.id)).join(TestCase).join(Scenario).join(Requirement).filter(
            Requirement.usecase_id.in_(usecase_ids),
            TestScript.is_deleted == False
        ).scalar() or 0

        # 3. Storage Calculation
        total_kb = (
            (req_count * SIZE_REQ_KB) +
            (scenario_count * SIZE_SCENARIO_KB) +
            (tc_count * SIZE_TC_KB) +
            (ts_count * SIZE_TS_KB)
        )
        storage_formatted = f"{total_kb} KB"
        if total_kb > 1024:
            storage_formatted = f"{total_kb / 1024:.2f} MB"

        # 4. Usage Trends (Last 30 Days)
        # This requires complex grouping. For simplicity/performance in Python:
        # Fetch detailed timestamps for last 30 days and aggregate in python.
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        
        # Helper to fetch dates
        def get_dates(model, filter_ids_col, filter_ids):
            return db.query(model.created_at).filter(
                filter_ids_col.in_(filter_ids),
                model.is_deleted == False,
                model.created_at >= thirty_days_ago
            ).all()

        # Needs joins for deep resources
        req_dates = get_dates(Requirement, Requirement.usecase_id, usecase_ids)
        
        scenario_dates = db.query(Scenario.created_at).join(Requirement).filter(
            Requirement.usecase_id.in_(usecase_ids),
            Scenario.is_deleted == False,
            Scenario.created_at >= thirty_days_ago
        ).all()
        
        tc_dates = db.query(TestCase.created_at).join(Scenario).join(Requirement).filter(
            Requirement.usecase_id.in_(usecase_ids),
            TestCase.is_deleted == False,
            TestCase.created_at >= thirty_days_ago
        ).all()
        
        ts_dates = db.query(TestScript.created_at).join(TestCase).join(Scenario).join(Requirement).filter(
            Requirement.usecase_id.in_(usecase_ids),
            TestScript.is_deleted == False,
            TestScript.created_at >= thirty_days_ago
        ).all()

        # Aggregate by day
        trends = {} # "YYYY-MM-DD": {req: 0, ts: 0, tc: 0}
        
        # Pre-fill last 30 days
        for i in range(30):
            d = (datetime.utcnow() - timedelta(days=i)).strftime("%Y-%m-%d")
            trends[d] = {"requirements": 0, "test_cases": 0, "test_scripts": 0}

        def aggregate(dates, key):
            for d in dates:
                date_str = d[0].strftime("%Y-%m-%d")
                if date_str in trends:
                    trends[date_str][key] += 1

        aggregate(req_dates, "requirements")
        aggregate(tc_dates, "test_cases")
        aggregate(ts_dates, "test_scripts")

        # Convert to list sorted by date
        trends_list = [
            {"date": k, **v} for k, v in sorted(trends.items())
        ]

        # 5. Recent Activity
        recent = []
        
        # Latest Test Case
        last_tc = db.query(TestCase.created_at).join(Scenario).join(Requirement).filter(
            Requirement.usecase_id.in_(usecase_ids),
            TestCase.is_deleted == False
        ).order_by(desc(TestCase.created_at)).first()
        if last_tc:
            recent.append(format_activity("Generated test cases", last_tc[0]))

        # Latest Requirement
        last_req = db.query(Requirement.created_at).filter(
            Requirement.usecase_id.in_(usecase_ids),
            Requirement.is_deleted == False
        ).order_by(desc(Requirement.created_at)).first()
        if last_req:
            recent.append(format_activity("Processed requirements", last_req[0]))

        # Latest Usecase (Chat)
        last_uc = db.query(UsecaseMetadata.created_at, UsecaseMetadata.usecase_name).filter(
            UsecaseMetadata.user_id == user_id,
            UsecaseMetadata.is_deleted == False
        ).order_by(desc(UsecaseMetadata.created_at)).first()
        if last_uc:
             recent.append(format_activity(f"Created chat '{last_uc.usecase_name}'", last_uc.created_at))

        # Sort recent by actual date (hidden in string? no, I need sorting logic. 
        # I'll just append and strictly take the top ones or sort if I kept the objects. 
        # User requested specific items: generate testcases, requirement, usecase.
        # I have one of each max.
        
        return {
            "counts": {
                "requirements": req_count,
                "scenarios": scenario_count,
                "test_cases": tc_count,
                "test_scripts": ts_count
            },
            "storage": {
                "used_kb": total_kb,
                "formatted": storage_formatted
            },
            "trends": trends_list,
            "recent_activity": recent
        }

    except Exception as e:
        logger.exception("Error calculating metrics")
        raise HTTPException(status_code=500, detail=str(e))

def format_activity(action, timestamp):
    now = datetime.utcnow()
    diff = now - timestamp
    hours = int(diff.total_seconds() / 3600)
    days = int(diff.total_seconds() / 86400)
    
    if days > 0:
        time_str = f"{days} days ago"
    elif hours > 0:
        time_str = f"{hours} hours ago"
    else:
        minutes = int(diff.total_seconds() / 60)
        time_str = f"{minutes} mins ago"

    return {
        "action": action,
        "date": time_str,
        "timestamp": timestamp.isoformat() # For potential sorting frontend side
    }
