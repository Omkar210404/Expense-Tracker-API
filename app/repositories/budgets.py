from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Budget, Category


def add(db: Session, user_id: int, *, category: Category, month: date, amount_minor: int) -> Budget:
    budget = Budget(user_id=user_id, category=category, month=month, amount_minor=amount_minor)
    db.add(budget)
    db.flush()
    return budget


def get(db: Session, user_id: int, budget_id: int) -> Budget | None:
    return db.scalar(select(Budget).where(Budget.user_id == user_id, Budget.id == budget_id))


def get_for_category_and_month(db: Session, user_id: int, category_id: int, month: date) -> Budget | None:
    return db.scalar(
        select(Budget).where(
            Budget.user_id == user_id, Budget.category_id == category_id, Budget.month == month
        )
    )


def list_for_user(db: Session, user_id: int, *, month: date | None = None) -> list[Budget]:
    """The user's budgets, newest month first, then by category name."""
    query = select(Budget).join(Category, Budget.category_id == Category.id).where(Budget.user_id == user_id)
    if month is not None:
        query = query.where(Budget.month == month)
    query = query.order_by(Budget.month.desc(), Category.name_key, Budget.id)
    return list(db.scalars(query))


def delete(db: Session, budget: Budget) -> None:
    db.delete(budget)
    db.flush()
