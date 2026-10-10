"""SQLAlchemy models. Every row except a user belongs to exactly one user."""

from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, UTCDateTime, utcnow


class PaymentMethod(StrEnum):
    CASH = "cash"
    CARD = "card"
    UPI = "upi"
    BANK_TRANSFER = "bank_transfer"
    WALLET = "wallet"
    OTHER = "other"


_PAYMENT_METHODS_SQL = ", ".join(f"'{method.value}'" for method in PaymentMethod)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Stored lower-case, so the unique constraint is case-insensitive.
    email: Mapped[str] = mapped_column(String(254), unique=True)
    hashed_password: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("user_id", "name_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(50))
    # Case-folded name. The unique constraint is on this column, so "Food"
    # and "food" cannot both exist for one user.
    name_key: Mapped[str] = mapped_column(String(150))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Expense(Base):
    __tablename__ = "expenses"
    __table_args__ = (
        CheckConstraint("amount_minor > 0", name="amount_positive"),
        CheckConstraint(f"payment_method IN ({_PAYMENT_METHODS_SQL})", name="payment_method_known"),
        Index("ix_expenses_user_id_date", "user_id", "date"),
        Index("ix_expenses_user_id_category_id", "user_id", "category_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # No ON DELETE action: a category that still has expenses cannot be
    # deleted. RESTRICT is not used because it fires in the middle of the
    # cascade when a user is deleted, before that user's expenses are gone.
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    # Money is kept as whole minor units (amount x 100). SQLite has no decimal
    # type, and integer sums are exact.
    amount_minor: Mapped[int] = mapped_column(Integer)
    date: Mapped[date] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    payment_method: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    category: Mapped[Category] = relationship(lazy="joined", innerjoin=True)


class Budget(Base):
    __tablename__ = "budgets"
    __table_args__ = (
        UniqueConstraint("user_id", "category_id", "month"),
        CheckConstraint("amount_minor > 0", name="amount_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))
    # First day of the month the budget is for.
    month: Mapped[date] = mapped_column(Date)
    amount_minor: Mapped[int] = mapped_column(Integer)

    category: Mapped[Category] = relationship(lazy="joined", innerjoin=True)
