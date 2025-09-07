import asyncio
from fastapi import APIRouter, File, Form, UploadFile, HTTPException, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from services.file_processing.file_service import upload_file_to_blob
from services.file_processing.ocr_service import run_all_ocr_batches
from models.file_processing.file_metadata import FileMetadata
from models.file_processing.file_workflow_tracker import FileWorkflowTracker
from deps import get_db
from uuid import uuid4, UUID
from datetime import datetime
from core.config import OCRServiceConfigs, settings
from models.usecase.usecase import UsecaseMetadata


router = APIRouter()


@router.post("/upload_file")
async def upload_file(background_tasks: BackgroundTasks,
                      files: list[UploadFile] = File(...),
                      email: str = Form(...),
                      usecase_id: str = Form(...),
                      db_session: Session = Depends(get_db)):
    ocr_batch_size = OCRServiceConfigs.NUM_FILES_PER_BACKGROUND_TASK
    with db_session as db:
        try:
            try:
                usecase_uuid = UUID(usecase_id)
            except Exception:
                raise HTTPException(status_code=400, detail="usecase_id must be a UUID")
            usecase = db.query(UsecaseMetadata).filter(UsecaseMetadata.usecase_id == usecase_uuid).first()
            if not usecase:
                raise HTTPException(status_code=404, detail="Usecase not found")
            file_metadata_list = []
            for file in files:
                if not file.filename.lower().endswith('.pdf'):
                    raise HTTPException(status_code=400, detail="Only PDF files are supported")
                success, message, url = upload_file_to_blob(file)
                if success:
                    file_metadata = FileMetadata(
                        file_id=uuid4(),
                        file_name=file.filename,
                        file_link=url,
                        user_id=usecase.user_id,
                        usecase_id=usecase.usecase_id,
                    )
                    db.add(file_metadata)
                    # Initialize tracker row
                    tracker = FileWorkflowTracker(file_id=file_metadata.file_id)
                    db.add(tracker)
                    file_metadata_list.append(file_metadata)
                else:
                    raise HTTPException(status_code=500, detail=message)
            db.commit()
            ocr_data = [(metadata.file_link, metadata.file_id) for metadata in file_metadata_list]
            from core.configs.pf_configs import PFImageToTextConfigs
            background_tasks.add_task(
                run_all_ocr_batches,
                usecase.usecase_id,
                ocr_data,
                ocr_batch_size,
                PFImageToTextConfigs.api_key,
                PFImageToTextConfigs.username,
                PFImageToTextConfigs.password,
                PFImageToTextConfigs.asset_id,
                OCRServiceConfigs.NUM_WORKERS,
                OCRServiceConfigs.BATCH_SIZE,
                OCRServiceConfigs.MAX_RETRIES,
            )
            for metadata in file_metadata_list:
                db.refresh(metadata)
            return [{"file_id": str(m.file_id), "file_name": m.file_name, "file_link": m.file_link} for m in file_metadata_list]
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=str(e))


