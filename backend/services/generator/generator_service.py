from sqlalchemy.orm import Session
from models.generator.requirement import Requirement
from models.generator.scenario import Scenario
from models.generator.test_case import TestCase
from models.usecase.usecase import UsecaseMetadata


def extract_requirement_headers(ocr_text: str) -> list[str]:
    # Very basic splitter by lines into headers
    return [h.strip() for h in ocr_text.splitlines() if h.strip()]


def run_generator_workflow(db: Session, usecase_id) -> dict:
    usecase = db.query(UsecaseMetadata).filter(UsecaseMetadata.usecase_id == usecase_id, UsecaseMetadata.is_deleted == False).first()
    if not usecase:
        raise ValueError("Usecase not found")

    # For this basic version, assume OCR text is aggregate of all pages in chat_history or placeholder
    ocr_text = "\n".join([m.get("content", "") for m in (usecase.chat_history or [])]) or "Sample requirement A\nSample requirement B"
    headers = extract_requirement_headers(ocr_text)

    created_requirements = []
    for header in headers:
        req = Requirement(usecase_id=usecase_id, requirement_text={"header": header})
        db.add(req)
        db.flush()
        created_requirements.append(req)

        scen_texts = [f"Scenario for: {header} #{i+1}" for i in range(2)]
        for s in scen_texts:
            scen = Scenario(requirement_id=req.id, scenario_text=s)
            db.add(scen)
            db.flush()

            for j in range(2):
                tc = TestCase(scenario_id=scen.id, test_case_text=f"Test case {j+1} for {s}")
                db.add(tc)

    usecase.requirement_generation = "Completed"
    usecase.scenario_generation = "Completed"
    usecase.test_case_generation = "Completed"

    return {
        "requirements": [str(r.id) for r in created_requirements]
    }


