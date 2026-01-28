# Import all models to ensure they are registered with SQLAlchemy

from .base import Base
from .user.user import User
from .user.api_key import UserAPIKey
from .usecase.usecase import UsecaseMetadata
from .file_processing.file_metadata import FileMetadata
from .file_processing.file_workflow_tracker import FileWorkflowTracker
from .file_processing.ocr_records import OCRInfo, OCROutputs
from .generator.requirement import Requirement
from .generator.scenario import Scenario
from .generator.test_case import TestCase
from .generator.test_script import TestScript
from .agent.trace import AgentTrace
