from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import ConflictError, NotFoundError
from app.models import Category
from app.repositories import categories

# Copied to every new user. They are ordinary rows: the user can rename or delete them.
DEFAULT_CATEGORIES = (
    "Food",
    "Transport",
    "Housing",
    "Utilities",
    "Health",
    "Entertainment",
    "Shopping",
    "Education",
    "Other",
)


def create_defaults(db: Session, user_id: int) -> None:
    """Add the default categories. The caller commits, so this is part of registration."""
    for name in DEFAULT_CATEGORIES:
        categories.add(db, user_id, name, is_default=True)


def list_categories(db: Session, user_id: int) -> list[Category]:
    return categories.list_for_user(db, user_id)


def get_category(db: Session, user_id: int, category_id: int) -> Category:
    """The user's own category. Another user's category is reported as not found."""
    category = categories.get(db, user_id, category_id)
    if category is None:
        raise NotFoundError("Category not found")
    return category


def _duplicate(name: str) -> ConflictError:
    return ConflictError(f"You already have a category named '{name}'")


def create_category(db: Session, user_id: int, name: str) -> Category:
    existing = categories.get_by_name(db, user_id, name)
    if existing is not None:
        raise _duplicate(existing.name)

    category = categories.add(db, user_id, name)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _duplicate(name) from None
    return category


def rename_category(db: Session, user_id: int, category_id: int, name: str) -> Category:
    category = get_category(db, user_id, category_id)
    existing = categories.get_by_name(db, user_id, name)
    if existing is not None and existing.id != category.id:
        raise _duplicate(existing.name)

    categories.rename(db, category, name)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _duplicate(name) from None
    return category


def delete_category(db: Session, user_id: int, category_id: int) -> None:
    category = get_category(db, user_id, category_id)
    in_use = categories.count_expenses(db, user_id, category.id)
    if in_use:
        raise ConflictError(
            f"Category '{category.name}' is used by {in_use} expense(s). Move or delete them first."
        )
    categories.delete(db, category)
    db.commit()
