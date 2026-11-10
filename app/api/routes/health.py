from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import SessionDep

router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness and database connectivity check")
async def health(session: SessionDep) -> JSONResponse:
    try:
        await session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse(
            {"status": "unavailable"}, status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )
    return JSONResponse({"status": "ok"})
