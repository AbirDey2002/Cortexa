import json
import logging
import time
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from uuid import UUID

from deps import get_db
from models.usecase.usecase import UsecaseMetadata
from services.testcases.testcases_service import (
    get_usecase_documents_markdown,
    extract_test_cases_from_scenario,
    persist_test_case,
)
from models.generator.requirement import Requirement
from models.generator.scenario import Scenario
from models.generator.test_case import TestCase
from db.session import get_db_context
from deps import get_db, get_current_user
from models.user.user import User
from typing import Dict, Any


router = APIRouter()

logger = logging.getLogger(__name__)

def _blue(text: str) -> str:
    try:
        return f"\033[34m{text}\033[0m"
    except Exception:
        return text


def _run_testcases_generation(usecase_id: UUID):
    """Background task to generate test cases for all scenarios."""
    logger.info("testcases_extraction: background generation started for usecase=%s", str(usecase_id))
    try:
        with get_db_context() as db:
            record = db.query(UsecaseMetadata).filter(
                UsecaseMetadata.usecase_id == usecase_id,
                
                UsecaseMetadata.is_deleted == False,
            ).first()
            if not record:
                logger.error("testcases_extraction: usecase not found %s", str(usecase_id))
                return
            
            # Check scenario_generation status
            scen_gen_status = record.scenario_generation or "Not Started"
            if scen_gen_status != "Completed":
                logger.error("testcases_extraction: scenario_generation not completed for usecase=%s status=%s", str(usecase_id), scen_gen_status)
                record.test_case_generation = "Failed"
                db.commit()
                return
            
            record.test_case_generation = "In Progress"
            db.commit()

            # Get the selected model from usecase, fallback to default
            from core.model_registry import get_default_model
            selected_model = record.selected_model or get_default_model()
            user_id = record.user_id
            logger.info(_blue(f"testcases_extraction: using model={selected_model} for usecase={usecase_id}, user_id={user_id}"))

            # Get extracted text once for all scenarios
            extracted_text = get_usecase_documents_markdown(db, usecase_id)

            # Fetch all scenarios for usecase (ordered by display_id)
            scenarios = db.query(Scenario).join(Requirement).filter(
                Requirement.usecase_id == usecase_id,
                Scenario.is_deleted == False,
                Requirement.is_deleted == False,
            ).order_by(Scenario.display_id.asc()).all()
            
            total_scenarios = len(scenarios)
            logger.info(_blue(f"testcases_extraction: processing {total_scenarios} scenarios"))

            inserted = 0
            for idx, scen in enumerate(scenarios, start=1):
                try:
                    scen_text = scen.scenario_text or {}
                    scen_name = scen_text.get("ScenarioName", f"Scenario {scen.display_id}")
                    
                    # Get requirement for context
                    requirement = db.query(Requirement).filter(
                        Requirement.id == scen.requirement_id,
                        Requirement.is_deleted == False,
                    ).first()
                    
                    if not requirement:
                        logger.warning(_blue(f"testcases_extraction: requirement not found for scenario {scen.id}"))
                        continue
                    
                    req_text = requirement.requirement_text or {}
                    
                    # Log polling status: starting scenario processing
                    logger.info(_blue(f"[TESTCASE-STATUS] usecase={usecase_id} | Processing scenario {idx}/{total_scenarios} | Name='{scen_name}' | Status=STARTING"))
                    
                    # Extract test cases
                    test_cases = extract_test_cases_from_scenario(
                        scen_text, 
                        req_text, 
                        extracted_text,
                        user_id=user_id,
                        model_name=selected_model
                    )
                    
                    # Log LLM test case payload (blue) before storing
                    try:
                        import json as _json
                        _preview = _json.dumps(test_cases)[:2000]
                        if len(_json.dumps(test_cases)) > 2000:
                            _preview += "... [TRUNCATED]"
                        logger.info(_blue(f"[TESTCASE-LLM] usecase={usecase_id} scenario='{scen_name}' test_cases_count={len(test_cases)} payload={_preview}"))
                    except Exception:
                        pass
                    
                    # Persist each test case
                    test_cases_inserted = 0
                    for tc_json in test_cases:
                        try:
                            persist_test_case(db, scen.id, tc_json)
                            test_cases_inserted += 1
                            inserted += 1
                        except Exception as e:
                            logger.error(_blue(f"[TESTCASE-STATUS] usecase={usecase_id} | Failed to persist test case for scenario '{scen_name}' | Error: {e}"), exc_info=True)
                            # Rollback the failed transaction before continuing
                            try:
                                db.rollback()
                            except Exception:
                                pass
                            continue
                    
                    # Log polling status: scenario completed
                    progress_pct = int((idx / total_scenarios) * 100) if total_scenarios > 0 else 0
                    logger.info(_blue(f"[TESTCASE-STATUS] usecase={usecase_id} | Completed scenario {idx}/{total_scenarios} ({progress_pct}%) | Name='{scen_name}' | Test cases inserted={test_cases_inserted} | Status=COMPLETED | Total inserted={inserted}"))
                    
                    # Log overall progress summary
                    if idx < total_scenarios:
                        remaining = total_scenarios - idx
                        next_scen = scenarios[idx] if idx < len(scenarios) else None
                        next_name = (next_scen.scenario_text or {}).get('ScenarioName', 'N/A') if next_scen else 'N/A'
                        logger.info(_blue(f"[TESTCASE-PROGRESS] usecase={usecase_id} | Progress: {idx}/{total_scenarios} completed ({progress_pct}%) | {remaining} remaining | Next: '{next_name}'"))
                    
                    # Wait 60 seconds between scenarios
                    if idx < total_scenarios:
                        logger.info(_blue(f"[TESTCASE-STATUS] usecase={usecase_id} | Waiting 60 seconds before processing next scenario..."))
                        time.sleep(60)
                except Exception as e:
                    scen_name = (scen.scenario_text or {}).get("ScenarioName", f"Scenario {scen.display_id}") if 'scen' in locals() else 'N/A'
                    logger.error(_blue(f"[TESTCASE-STATUS] usecase={usecase_id} | Failed scenario {idx}/{total_scenarios} | Name='{scen_name}' | Status=FAILED | Error: {e}"), exc_info=True)
                    # Rollback on error to prevent database session issues
                    try:
                        db.rollback()
                    except Exception:
                        pass
                    continue

            record = db.query(UsecaseMetadata).filter(UsecaseMetadata.usecase_id == usecase_id).first()
            record.test_case_generation = "Completed" if inserted > 0 else "Failed"
            db.commit()
            
            # Final summary log
            success_rate = int((inserted / (total_scenarios * 1.0)) * 100) if total_scenarios > 0 else 0
            logger.info(_blue(f"[TESTCASE-SUMMARY] usecase={usecase_id} | FINAL STATUS: {record.test_case_generation} | Total scenarios processed: {total_scenarios} | Total test cases inserted: {inserted} | Success rate: {success_rate}%"))
            logger.info(_blue(f"testcases_extraction: finished status={record.test_case_generation} test_cases_inserted={inserted}"))
    except Exception as e:
        logger.error("testcases_extraction: background generation error: %s", e, exc_info=True)
    finally:
        # Fail-safe: ensure status is not left hanging in 'In Progress'
        try:
            with get_db_context() as db:
                record = db.query(UsecaseMetadata).filter(
                    UsecaseMetadata.usecase_id == usecase_id,
                    
                    UsecaseMetadata.is_deleted == False,
                ).first()
                if record:
                    # If test cases exist and status still not Completed/Failed, mark Completed
                    total_inserted = db.query(TestCase).join(Scenario).join(Requirement).filter(
                        Requirement.usecase_id == usecase_id,
                        TestCase.is_deleted == False,
                    ).count()
                    current = (record.test_case_generation or "").strip()
                    if total_inserted > 0 and current not in ("Completed", "Failed"):
                        record.test_case_generation = "Completed"
                        db.commit()
                        logger.info(_blue(f"[TESTCASE-GEN FAIL-SAFE] set status=Completed usecase={usecase_id} total_inserted={total_inserted}"))
        except Exception:
            pass


@router.post("/{usecase_id}/generate")
def generate_testcases(
    usecase_id: UUID,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Start test case generation for a usecase."""
    try:
        record = db.query(UsecaseMetadata).filter(
            UsecaseMetadata.usecase_id == usecase_id,
            UsecaseMetadata.user_id == user.id,
            
            UsecaseMetadata.is_deleted == False,
        ).first()
        if not record:
            raise HTTPException(status_code=404, detail="Usecase not found")
        
        # Check scenario_generation status
        scen_gen_status = record.scenario_generation or "Not Started"
        if scen_gen_status != "Completed":
            raise HTTPException(
                status_code=400,
                detail=f"Scenario generation must be completed before generating test cases. Current status: {scen_gen_status}"
            )
        
        # Check test_case_generation status
        if record.test_case_generation == "In Progress":
            raise HTTPException(
                status_code=400,
                detail="Test case generation is already in progress"
            )
        
        # Set status to In Progress and schedule background task
        if record.test_case_generation in (None, "Not Started", "Failed"):
            record.test_case_generation = "In Progress"
        db.commit()
        background_tasks.add_task(_run_testcases_generation, usecase_id)
        logger.info("testcases_extraction: background task scheduled for %s", str(usecase_id))
        return {"status": "started", "usecase_id": str(usecase_id)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("generate_testcases error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Error starting test case generation")


@router.get("/{usecase_id}/status")
def testcases_status(
    usecase_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get test case generation status."""
    try:
        record = db.query(UsecaseMetadata).filter(
            UsecaseMetadata.usecase_id == usecase_id,
            UsecaseMetadata.user_id == user.id,
            
            UsecaseMetadata.is_deleted == False,
        ).first()
        if not record:
            raise HTTPException(status_code=404, detail="Usecase not found")

        # Count inserted test cases
        count = db.query(TestCase).join(Scenario).join(Requirement).filter(
            Requirement.usecase_id == usecase_id,
            TestCase.is_deleted == False,
        ).count()

        # Normalize status strictly to canonical values
        raw_status = (record.test_case_generation or "Not Started").strip().lower()
        canonical_map = {
            "not started": "Not Started",
            "in progress": "In Progress",
            "completed": "Completed",
            "failed": "Failed",
        }
        norm_status = canonical_map.get(raw_status, "Not Started")

        payload = {
            "usecase_id": str(usecase_id),
            "test_case_generation": norm_status,
            "total_inserted": count,
        }
        logger.info(_blue(f"testcases_status: usecase={usecase_id} status={norm_status} total_inserted={count}"))
        return payload
    except HTTPException:
        raise
    except Exception as e:
        logger.error("testcases_status error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Error getting test case status")


@router.get("/{usecase_id}/list")
def list_testcases(
    usecase_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get all test cases for a usecase.
    Returns test cases in a format suitable for frontend display.
    """
    try:
        record = db.query(UsecaseMetadata).filter(
            UsecaseMetadata.usecase_id == usecase_id,
            UsecaseMetadata.user_id == user.id,
            
            UsecaseMetadata.is_deleted == False,
        ).first()
        if not record:
            raise HTTPException(status_code=404, detail="Usecase not found")

        # Query all non-deleted test cases for the usecase (via Scenario -> Requirement join)
        test_cases = db.query(TestCase).join(Scenario).join(Requirement).filter(
            Requirement.usecase_id == usecase_id,
            TestCase.is_deleted == False,
            Scenario.is_deleted == False,
            Requirement.is_deleted == False,
        ).order_by(TestCase.created_at.asc()).all()

        # Transform test_case_text JSON to match frontend expected format
        testcases_list = []
        for tc in test_cases:
            try:
                tc_json = json.loads(tc.test_case_text) if tc.test_case_text else {}
            except Exception:
                tc_json = {}
            
            # Get scenario and requirement info
            scenario = db.query(Scenario).filter(Scenario.id == tc.scenario_id).first()
            scenario_display_id = scenario.display_id if scenario else None
            scenario_name = (scenario.scenario_text or {}).get("ScenarioName", "") if scenario else ""
            
            requirement = db.query(Requirement).filter(Requirement.id == scenario.requirement_id).first() if scenario else None
            requirement_display_id = requirement.display_id if requirement else None
            
            testcases_list.append({
                "id": str(tc.id),
                "display_id": tc.display_id,
                "test_case": tc_json.get("test case", ""),
                "description": tc_json.get("description", ""),
                "flow": tc_json.get("flow", ""),
                "requirementId": tc_json.get("requirementId", ""),
                "scenarioId": tc_json.get("scenarioId", ""),
                "preConditions": tc_json.get("preConditions", []),
                "testData": tc_json.get("testData", []),
                "testSteps": tc_json.get("testSteps", []),
                "expectedResults": tc_json.get("expectedResults", []),
                "postConditions": tc_json.get("postConditions", []),
                "risk_analysis": tc_json.get("risk_analysis", ""),
                "requirement_category": tc_json.get("requirement_category", ""),
                "lens": tc_json.get("lens", ""),
                "scenario_display_id": scenario_display_id,
                "scenario_name": scenario_name,
                "requirement_display_id": requirement_display_id,
                "created_at": tc.created_at.isoformat() if tc.created_at else None,
            })

        payload = {
            "test_cases": testcases_list,
            "count": len(testcases_list),
        }
        logger.info(_blue(f"list_testcases: usecase={usecase_id} count={len(testcases_list)}"))
        return payload
    except HTTPException:
        raise
    except Exception as e:
        logger.error("list_testcases error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Error getting test cases list")


@router.get("/{usecase_id}/read/{display_id}")
def read_testcase(
    usecase_id: UUID,
    display_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Read a specific test case by display_id for agent analysis.
    Returns test_case_text as formatted text (similar to OCR combined_markdown).
    """
    try:
        # Verify usecase exists
        record = db.query(UsecaseMetadata).filter(
            UsecaseMetadata.usecase_id == usecase_id,
            UsecaseMetadata.user_id == user.id,
            
            UsecaseMetadata.is_deleted == False,
        ).first()
        if not record:
            raise HTTPException(status_code=404, detail="Usecase not found")

        # Check test_case_generation status
        test_case_gen_status = record.test_case_generation or "Not Started"
        if test_case_gen_status not in ("In Progress", "Completed"):
            raise HTTPException(
                status_code=400,
                detail=f"Test case generation is '{test_case_gen_status}'. Test cases are not available yet."
            )

        # Find test case by usecase_id (via Scenario -> Requirement join) and display_id
        test_case = db.query(TestCase).join(Scenario).join(Requirement).filter(
            Requirement.usecase_id == usecase_id,
            TestCase.display_id == display_id,
            TestCase.is_deleted == False,
            Scenario.is_deleted == False,
            Requirement.is_deleted == False,
        ).first()

        if not test_case:
            raise HTTPException(
                status_code=404, 
                detail=f"Test case with display_id {display_id} not found for this usecase"
            )

        # Get test_case_text JSON
        try:
            tc_json = json.loads(test_case.test_case_text) if test_case.test_case_text else {}
        except Exception:
            tc_json = {}
        
        # Format as readable text (similar to OCR combined_markdown format)
        formatted_text_parts = []
        
        # Add test case ID
        tc_id = tc_json.get("id", "")
        if tc_id:
            formatted_text_parts.append(f"## Test Case: {tc_id}\n")
        
        # Add test case title
        tc_title = tc_json.get("test case", "")
        if tc_title:
            formatted_text_parts.append(f"### Title\n{tc_title}\n")
        
        # Add description
        description = tc_json.get("description", "")
        if description:
            formatted_text_parts.append(f"### Description\n{description}\n")
        
        # Add flow
        flow = tc_json.get("flow", "")
        if flow:
            formatted_text_parts.append(f"### Flow\n{flow}\n")
        
        # Add requirement and scenario IDs
        req_id = tc_json.get("requirementId", "")
        scen_id = tc_json.get("scenarioId", "")
        if req_id or scen_id:
            formatted_text_parts.append("### Mapping\n")
            if req_id:
                formatted_text_parts.append(f"**Requirement ID**: {req_id}\n")
            if scen_id:
                formatted_text_parts.append(f"**Scenario ID**: {scen_id}\n")
        
        # Add preconditions
        preconditions = tc_json.get("preConditions", [])
        if preconditions:
            formatted_text_parts.append("### Preconditions\n")
            for pc in preconditions:
                formatted_text_parts.append(f"- {pc}\n")
        
        # Add test data
        test_data = tc_json.get("testData", [])
        if test_data:
            formatted_text_parts.append("### Test Data\n")
            for td in test_data:
                formatted_text_parts.append(f"- {td}\n")
        
        # Add test steps
        test_steps = tc_json.get("testSteps", [])
        if test_steps:
            formatted_text_parts.append("### Test Steps\n")
            for step in test_steps:
                formatted_text_parts.append(f"{step}\n")
        
        # Add expected results
        expected_results = tc_json.get("expectedResults", [])
        if expected_results:
            formatted_text_parts.append("### Expected Results\n")
            for er in expected_results:
                formatted_text_parts.append(f"{er}\n")
        
        # Add post conditions
        post_conditions = tc_json.get("postConditions", [])
        if post_conditions:
            formatted_text_parts.append("### Post Conditions\n")
            for pc in post_conditions:
                formatted_text_parts.append(f"- {pc}\n")
        
        # Add risk analysis
        risk = tc_json.get("risk_analysis", "")
        if risk:
            formatted_text_parts.append(f"### Risk Analysis\n{risk}\n")
        
        # Add requirement category
        category = tc_json.get("requirement_category", "")
        if category:
            formatted_text_parts.append(f"### Requirement Category\n{category}\n")
        
        # Add lens
        lens = tc_json.get("lens", "")
        if lens:
            formatted_text_parts.append(f"### Lens\n{lens}\n")
        
        # Combine all parts
        formatted_text = "\n".join(formatted_text_parts)
        
        total_chars = len(formatted_text)
        
        logger.info(_blue(
            f"read_testcase: usecase={usecase_id} display_id={display_id} "
            f"test_case_id={test_case.id} total_chars={total_chars}"
        ))
        
        return {
            "usecase_id": str(usecase_id),
            "display_id": display_id,
            "test_case_id": str(test_case.id),
            "test_case_text": formatted_text,
            "test_case_json": tc_json,  # Also include raw JSON for reference
            "total_chars": total_chars,
            "message": f"Retrieved test case TC-{display_id}: {tc_title} ({total_chars} characters)."
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("read_testcase error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Error reading test case")

