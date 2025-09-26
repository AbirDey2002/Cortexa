from pydantic import BaseModel, ConfigDict
from uuid import UUID
from datetime import datetime
from typing import Optional


class FileMetadataSchema(BaseModel):
    file_id: UUID
    usecase_id: UUID
    file_name: str
    file_link: str
    user_id: UUID
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class FileWorkflowTrackerSchema(BaseModel):
    file_id: UUID
    text_extraction: str = "Not Started"
    requirement_generation: str = "Not Started"
    scenario_generation: str = "Not Started"
    test_case_generation: str = "Not Started"
    test_data_generation: str = "Not Started"
    test_script_generation: str = "Not Started"
    error_msg: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class OCRInfoSchema(BaseModel):
    id: UUID
    file_id: UUID
    total_pages: int
    completed_pages: int
    error_pages: int
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class OCROutputSchema(BaseModel):
    id: UUID
    file_id: UUID
    page_number: int
    page_text: str
    error_msg: Optional[str] = None
    is_completed: bool
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)
