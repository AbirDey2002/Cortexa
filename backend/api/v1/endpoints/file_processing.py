import os
import asyncio
from fastapi import APIRouter, File, Form, UploadFile, HTTPException, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from services.file_processing.file_service import upload_file_to_blob
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
                      start_ocr: bool = Form(False),
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

            # Legacy OCR background processing removed
            logger.info("Files uploaded successfully; OCR/background processing not started")

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


@router.get("/ocr/{usecase_id}/document-markdown")
async def get_usecase_document_markdown(
    usecase_id: UUID,
    db_session: Session = Depends(get_db)
):
    """
    Return combined Markdown for all files in a usecase.
    Response shape:
    {
      usecase_id, 
      files: [{ file_id, file_name, markdown }],
      combined_markdown
    }
    """
    with db_session as db:
        try:
            files = db.query(FileMetadata).filter(
                FileMetadata.usecase_id == usecase_id
            ).order_by(FileMetadata.created_at.asc()).all()

            result_files = []
            combined_parts = []

            for f in files:
                outputs = db.query(OCROutputs).filter(
                    OCROutputs.file_id == f.file_id
                ).order_by(OCROutputs.page_number.asc()).all()

                md = "\n".join([o.page_text or "" for o in outputs])
                result_files.append({
                    "file_id": str(f.file_id),
                    "file_name": f.file_name,
                    "markdown": md,
                })
                if md.strip():
                    combined_parts.append(f"## {f.file_name}\n\n{md}\n")

            combined_markdown = "\n".join(combined_parts).strip()
            logger.info(
                f"document-markdown: usecase={usecase_id} files={len(result_files)} total_chars={len(combined_markdown)}"
            )
            return {
                "usecase_id": str(usecase_id),
                "files": result_files,
                "combined_markdown": combined_markdown,
            }
        except Exception as e:
            logger.error(f"Error building document markdown for usecase {usecase_id}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))


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


@router.get("/ocr/{usecase_id}/results")
async def get_ocr_results(
    usecase_id: UUID,
    db_session: Session = Depends(get_db)
):
    """
    Get OCR results for all files in a specific usecase.
    
    Args:
        usecase_id (UUID): ID of the usecase
        db_session (Session): Database session dependency
        
    Returns:
        dict: OCR results including progress and extracted text for each file
    """
    with db_session as db:
        try:
            # Get all files for the usecase
            files = db.query(FileMetadata).filter(FileMetadata.usecase_id == usecase_id).all()
            
            if not files:
                return {
                    "usecase_id": str(usecase_id),
                    "total_files": 0,
                    "files": [],
                    "overall_status": "no_files"
                }
            
            file_results = []
            total_pages = 0
            completed_pages = 0
            error_pages = 0
            
            for file_metadata in files:
                # Get OCR info for the file
                ocr_info = db.query(OCRInfo).filter(
                    OCRInfo.file_id == file_metadata.file_id
                ).first()
                
                # Get OCR outputs for the file
                ocr_outputs = db.query(OCROutputs).filter(
                    OCROutputs.file_id == file_metadata.file_id
                ).order_by(OCROutputs.page_number).all()
                
                # Get workflow tracker
                workflow_tracker = db.query(FileWorkflowTracker).filter(
                    FileWorkflowTracker.file_id == file_metadata.file_id
                ).first()
                
                file_total_pages = ocr_info.total_pages if ocr_info else 0
                file_completed_pages = ocr_info.completed_pages if ocr_info else 0
                file_error_pages = ocr_info.error_pages if ocr_info else 0
                
                total_pages += file_total_pages
                completed_pages += file_completed_pages
                error_pages += file_error_pages
                
                # Determine file status
                file_status = "not_started"
                if workflow_tracker:
                    if workflow_tracker.text_extraction == "Completed":
                        file_status = "completed"
                    elif workflow_tracker.text_extraction == "In Progress":
                        file_status = "in_progress"
                    elif workflow_tracker.text_extraction == "Failed":
                        file_status = "failed"
                
                # Format OCR outputs
                pages_data = []
                for output in ocr_outputs:
                    pages_data.append({
                        "page_number": output.page_number,
                        "text": output.page_text,
                        "is_completed": output.is_completed,
                        "error_msg": output.error_msg,
                        "created_at": output.created_at.isoformat() if output.created_at else None
                    })
                
                file_results.append({
                    "file_id": str(file_metadata.file_id),
                    "file_name": file_metadata.file_name,
                    "file_link": file_metadata.file_link,
                    "status": file_status,
                    "total_pages": file_total_pages,
                    "completed_pages": file_completed_pages,
                    "error_pages": file_error_pages,
                    "progress_percentage": (file_completed_pages / file_total_pages * 100) if file_total_pages > 0 else 0,
                    "pages": pages_data,
                    "created_at": file_metadata.created_at.isoformat() if file_metadata.created_at else None
                })
            
            # Determine overall status
            overall_status = "not_started"
            if total_pages > 0:
                if completed_pages == total_pages:
                    overall_status = "completed"
                elif completed_pages > 0:
                    overall_status = "in_progress"
                elif error_pages > 0:
                    overall_status = "partial_error"
            
            return {
                "usecase_id": str(usecase_id),
                "total_files": len(files),
                "total_pages": total_pages,
                "completed_pages": completed_pages,
                "error_pages": error_pages,
                "overall_progress_percentage": (completed_pages / total_pages * 100) if total_pages > 0 else 0,
                "overall_status": overall_status,
                "files": file_results,
                "last_updated": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error fetching OCR results for usecase {usecase_id}: {e}", exc_info=True)
            raise HTTPException(
                status_code=500, 
                detail=f"Error fetching OCR results for usecase {usecase_id}: {str(e)}"
            )


# Legacy OCR start endpoint removed


