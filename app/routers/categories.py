from fastapi import APIRouter, Response

from app.deps import CurrentUser, DbSession
from app.schemas.category import CategoryCreate, CategoryOut, CategoryUpdate
from app.schemas.common import ResourceId, error_responses
from app.services import categories as category_service

router = APIRouter(prefix="/categories", tags=["categories"], responses=error_responses(401))


@router.get("", response_model=list[CategoryOut], summary="List your categories")
def list_categories(db: DbSession, user: CurrentUser):
    return category_service.list_categories(db, user.id)


@router.post(
    "",
    response_model=CategoryOut,
    status_code=201,
    summary="Create a category",
    responses=error_responses(409, 422),
)
def create_category(data: CategoryCreate, db: DbSession, user: CurrentUser):
    """Names are unique per user, ignoring case."""
    return category_service.create_category(db, user.id, data.name)


@router.get(
    "/{category_id}",
    response_model=CategoryOut,
    summary="Get one category",
    responses=error_responses(404, 422),
)
def get_category(category_id: ResourceId, db: DbSession, user: CurrentUser):
    return category_service.get_category(db, user.id, category_id)


@router.patch(
    "/{category_id}",
    response_model=CategoryOut,
    summary="Rename a category",
    responses=error_responses(404, 409, 422),
)
def rename_category(category_id: ResourceId, data: CategoryUpdate, db: DbSession, user: CurrentUser):
    return category_service.rename_category(db, user.id, category_id, data.name)


@router.delete(
    "/{category_id}",
    status_code=204,
    summary="Delete a category",
    responses=error_responses(404, 409, 422),
)
def delete_category(category_id: ResourceId, db: DbSession, user: CurrentUser):
    """Refused while expenses use the category. Its budgets are deleted with it."""
    category_service.delete_category(db, user.id, category_id)
    return Response(status_code=204)
