from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Category, Expense


def name_key(name: str) -> str:
    """The form of a name that is compared for uniqueness."""
    return name.casefold()


def list_for_user(db: Session, user_id: int) -> list[Category]:
    query = select(Category).where(Category.user_id == user_id).order_by(Category.name_key, Category.id)
    return list(db.scalars(query))


def get(db: Session, user_id: int, category_id: int) -> Category | None:
    return db.scalar(select(Category).where(Category.user_id == user_id, Category.id == category_id))


def get_by_name(db: Session, user_id: int, name: str) -> Category | None:
    return db.scalar(
        select(Category).where(Category.user_id == user_id, Category.name_key == name_key(name))
    )


def add(db: Session, user_id: int, name: str, *, is_default: bool = False) -> Category:
    category = Category(user_id=user_id, name=name, name_key=name_key(name), is_default=is_default)
    db.add(category)
    db.flush()
    return category


def rename(db: Session, category: Category, name: str) -> None:
    category.name = name
    category.name_key = name_key(name)
    db.flush()


def delete(db: Session, category: Category) -> None:
    db.delete(category)
    db.flush()


def count_expenses(db: Session, user_id: int, category_id: int) -> int:
    query = (
        select(func.count())
        .select_from(Expense)
        .where(Expense.user_id == user_id, Expense.category_id == category_id)
    )
    return db.scalar(query) or 0
