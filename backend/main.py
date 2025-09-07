from fastapi import FastAPI
from models.base import Base
from db.session import engine
from api.v1.api_router import api_router
from core.logging_config import setup_logging  # ensure logging is initialized


Base.metadata.create_all(bind=engine)

setup_logging()
app = FastAPI(title="cortexa backend")

app.include_router(api_router)