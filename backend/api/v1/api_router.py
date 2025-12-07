from fastapi import APIRouter
from .endpoints.user_management import router as user_router
from .endpoints.usecase_management import router as usecase_router, frontend_router as usecase_frontend_router
from .endpoints.file_processing import router as file_router
from .endpoints.generator import router as generator_router
from .endpoints.gemini_chat import router as gemini_router, frontend_router as gemini_frontend_router
from .endpoints.requirements_extraction import router as requirements_router
from .endpoints.scenarios_extraction import router as scenarios_router
from .endpoints.model_management import router as model_router


api_router = APIRouter()

api_router.include_router(user_router, prefix="/users", tags=["users"])
api_router.include_router(usecase_router, prefix="/usecases", tags=["usecases"])
api_router.include_router(usecase_frontend_router, prefix="/frontend/usecases", tags=["frontend"])
api_router.include_router(file_router, prefix="/files", tags=["files"])
api_router.include_router(generator_router, prefix="/generator", tags=["generator"])
api_router.include_router(gemini_router, prefix="/usecases", tags=["gemini-chat"])
api_router.include_router(gemini_frontend_router, prefix="/frontend/usecases", tags=["gemini-frontend"])
api_router.include_router(requirements_router, prefix="/requirements", tags=["requirements"])
api_router.include_router(scenarios_router, prefix="/scenarios", tags=["scenarios"])
api_router.include_router(model_router, prefix="/api/v1", tags=["models"])


