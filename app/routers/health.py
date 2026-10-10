from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class Health(BaseModel):
    status: str


@router.get("/health", response_model=Health, summary="Liveness check")
def health() -> Health:
    return Health(status="ok")
