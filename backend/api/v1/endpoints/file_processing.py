import os
import asyncio
from fastapi import APIRouter, File, Form, UploadFile, HTTPException, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from services.file_processing.file_service import upload_file_to_blob
from services.file_processing.ocr_service import run_all_ocr_batches
from schemas.file_processing.file import FileMetadataSchema, FileWorkflowTrackerSchema
from models.file_processing.file_metadata import FileMetadata
from models.file_processing.file_workflow_tracker import FileWorkflowTracker
from models.file_processing.ocr_records import OCRInfo, OCROutputs
from models.user.user import User
from deps import get_db
from uuid import uuid4, UUID
from datetime import datetime
from core.config import OCRServiceConfigs, settings
from core.configs.pf_configs import PFImageToTextConfigs
import logging
from models.usecase.usecase import UsecaseMetadata


# Configure logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
# Prevent duplicate handlers
if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)
# Prevent propagation to avoid duplicate messages
logger.propagate = False

router = APIRouter()


async def check_ocr_completion(usecase_id: int, db_session, max_retries=20, retry_interval=5):
    """
    Check if OCR processing is complete for all files in a usecase.
    
    Args:
        usecase_id (int): The usecase ID
        db_session: Database session
        max_retries (int): Maximum number of retries
        retry_interval (int): Interval between retries in seconds
        
    Returns:
        bool: True if OCR is complete, False otherwise
    """
    for retry in range(max_retries):
        try:
            # Get all files for the usecase
            files = db_session.query(FileMetadata).filter(FileMetadata.usecase_id == usecase_id).all()
            
            if not files:
                logger.warning(f"No files found for usecase {usecase_id}")
                return False
            
            # Check if text extraction is complete for all files
            all_complete = True
            for file in files:
                # Get workflow tracker for the file
                workflow_tracker = db_session.query(FileWorkflowTracker).filter(
                    FileWorkflowTracker.file_id == file.file_id
                ).first()
                
                if not workflow_tracker:
                    logger.warning(f"No workflow tracker found for file {file.file_id}")
                    all_complete = False
                    break
                
                # Check if text extraction is completed
                if workflow_tracker.text_extraction != "Completed":
                    logger.info(f"Text extraction not complete for file {file.file_id}: Status is {workflow_tracker.text_extraction}")
                    all_complete = False
                    break
            
            if all_complete:
                logger.info(f"Text extraction complete for all files in usecase {usecase_id}")
                return True
            
            logger.info(f"Text extraction not yet complete for usecase {usecase_id}, retry {retry+1}/{max_retries}")
            await asyncio.sleep(retry_interval)
        except Exception as e:
            logger.error(f"Error checking text extraction completion: {e}", exc_info=True)
            await asyncio.sleep(retry_interval)
    
    logger.warning(f"Text extraction did not complete within the timeout for usecase {usecase_id}")
    return False


@router.post("/upload_file", response_model=list[FileMetadataSchema])
async def upload_file(background_tasks: BackgroundTasks,
                      files: list[UploadFile] = File(...),
                      email: str = Form(...),
                      usecase_id: UUID = Form(...),
                      db_session: Session = Depends(get_db)):
    """
    Upload multiple files and store their metadata in the database.
    
    Args:
        files (list[UploadFile]): List of files to upload
        email (str): Email of the user uploading the files
        usecase_id (int): ID of the usecase
        db_session (Session): Database session dependency
        background_tasks (BackgroundTasks): Background tasks handler
        
    Returns:
        list[FileMetadataSchema]: List of metadata for successfully uploaded files
        
    Raises:
        HTTPException: 500 error if file upload fails or database operation fails
        HTTPException: 404 error if user not found
    """
    logger.info(f"Starting file upload process for usecase_id: {usecase_id}")
    ocr_batch_size = OCRServiceConfigs.NUM_FILES_PER_BACKGROUND_TASK
    logger.info(f"OCR batch size set to: {ocr_batch_size}")


    with db_session as db:
        try:
            logger.info(f"Looking up user with email: {email}")
            # Get user by email
            user = db.query(User).filter(User.email == email).first()
            if not user:
                logger.error(f"User not found for email: {email}")
                raise HTTPException(status_code=404, detail="User not found")
            
            logger.info(f"User found. Using usecase ID: {usecase_id} for user: {email}")

            file_metadata_list = []
            for i, file in enumerate(files):
                logger.info(f"Processing file {i+1}/{len(files)}: {file.filename}")
                success, message, url = upload_file_to_blob(file)
                logger.info(f"Blob storage upload result for {file.filename}: Success={success}, Message={message}")
                logger.info(f"File URL: {url}")
                if success:
                    logger.info(f"Creating metadata entry for file: {file.filename}")
                    file_metadata = FileMetadata(
                        file_id=uuid4(),
                        file_name=file.filename,
                        file_link=url,
                        user_id=user.id,
                        usecase_id=usecase_id,
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    )
                    db.add(file_metadata)
                    file_metadata_list.append(file_metadata)
                else:
                    logger.error(f"Failed to upload file {file.filename}: {message}")
                    raise HTTPException(status_code=500, detail=message)
            
            logger.info("Committing metadata to database")
            db.commit()

            logger.info("Preparing OCR data for background processing")
            # Extract necessary data before session closes
            ocr_data = [(metadata.file_link, metadata.file_id) for metadata in file_metadata_list]
            
            logger.info("Adding OCR processing background task")
            # Add OCR processing background task
            background_tasks.add_task(
                run_all_ocr_batches, 
                usecase_id,
                ocr_data, 
                ocr_batch_size,
                PFImageToTextConfigs.api_key,
                PFImageToTextConfigs.username,
                PFImageToTextConfigs.password,
                PFImageToTextConfigs.asset_id,
                OCRServiceConfigs.NUM_WORKERS,
                OCRServiceConfigs.BATCH_SIZE,
                OCRServiceConfigs.MAX_RETRIES
            )

            # Refresh metadata objects
            for metadata in file_metadata_list:
                db.refresh(metadata)
            logger.info(f"File upload process completed successfully for {len(file_metadata_list)} files")
            return [FileMetadataSchema.from_orm(metadata) for metadata in file_metadata_list]
        except Exception as e:
            logger.error(f"Error occurred during file upload: {str(e)}", exc_info=True)
            db.rollback()
            logger.error(f"Error in upload_file: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))


@router.get("/files/{usecase_id}", response_model=list[FileMetadataSchema])
async def get_files_by_usecase(
    usecase_id: UUID,
    db_session: Session = Depends(get_db)
):
    """
    Get all files associated with a specific usecase ID.
    
    Args:
        usecase_id (UUID): ID of the usecase
        db_session (Session): Database session dependency
        
    Returns:
        list[FileMetadataSchema]: List of files metadata for the specified usecase
    """
    with db_session as db:
        try:
            files = db.query(FileMetadata).filter(
                FileMetadata.usecase_id == usecase_id
            ).all()
            
            return [FileMetadataSchema.from_orm(file) for file in files]
            
        except Exception as e:
            logger.error(f"Error fetching files for usecase {usecase_id}: {e}", exc_info=True)
            raise HTTPException(
                status_code=500, 
                detail=f"Error fetching files for usecase {usecase_id}: {str(e)}"
            )


@router.get("/files/{usecase_id}/status", response_model=list[FileWorkflowTrackerSchema])
async def get_usecase_file_status(
    usecase_id: UUID,
    db_session: Session = Depends(get_db)
):
    """
    Get workflow status for all files in a specific usecase.
    
    Args:
        usecase_id (UUID): ID of the usecase
        db_session (Session): Database session dependency
        
    Returns:
        list[FileWorkflowTrackerSchema]: List of workflow status for files in the usecase
    """
    with db_session as db:
        try:
            workflow_status = db.query(FileWorkflowTracker).join(
                FileMetadata, 
                FileWorkflowTracker.file_id == FileMetadata.file_id
            ).filter(
                FileMetadata.usecase_id == usecase_id
            ).all()
            
            # Initialize empty values if None to satisfy schema validation
            for status in workflow_status:
                status.text_extraction = status.text_extraction or ""
                status.requirement_generation = status.requirement_generation or ""
                status.scenario_generation = status.scenario_generation or ""
                status.test_case_generation = status.test_case_generation or ""
                status.test_data_generation = status.test_data_generation or ""
            
            return [FileWorkflowTrackerSchema.from_orm(status) for status in workflow_status]
            
        except Exception as e:
            logger.error(f"Error fetching workflow status for usecase {usecase_id}: {e}", exc_info=True)
            raise HTTPException(
                status_code=500, 
                detail=f"Error fetching workflow status for usecase {usecase_id}: {str(e)}"
            )


