"""The database rules that do not depend on the API: constraints and foreign keys."""

from datetime import date, timezone

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.database import Base, make_engine, make_session_factory
from app.models import Budget, Category, Expense, User


@pytest.fixture
def db(tmp_path):
    engine = make_engine(f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    Base.metadata.create_all(engine)
    session = make_session_factory(engine)()
    yield session
    session.close()
    engine.dispose()


def add_user(db, email="a@example.com"):
    user = User(email=email, hashed_password="x")
    db.add(user)
    db.flush()
    return user


def add_category(db, user, name="Food"):
    category = Category(user_id=user.id, name=name, name_key=name.casefold())
    db.add(category)
    db.flush()
    return category


def add_expense(db, user, category, **overrides):
    values = {"amount_minor": 1250, "date": date(2026, 6, 1), "payment_method": "cash"}
    values.update(overrides)
    expense = Expense(user_id=user.id, category_id=category.id, **values)
    db.add(expense)
    db.flush()
    return expense


def test_foreign_keys_are_switched_on(db):
    assert db.execute(text("PRAGMA foreign_keys")).scalar() == 1


def test_timestamps_are_read_back_as_utc(db):
    user = add_user(db)
    db.commit()
    db.expire_all()

    assert db.get(User, user.id).created_at.tzinfo == timezone.utc


def test_email_is_unique(db):
    add_user(db, "a@example.com")
    with pytest.raises(IntegrityError):
        add_user(db, "a@example.com")


def test_category_name_is_unique_per_user_ignoring_case(db):
    user = add_user(db)
    add_category(db, user, "Food")
    with pytest.raises(IntegrityError):
        add_category(db, user, "FOOD")


def test_two_users_may_have_the_same_category_name(db):
    add_category(db, add_user(db, "a@example.com"), "Food")
    add_category(db, add_user(db, "b@example.com"), "Food")
    db.commit()


@pytest.mark.parametrize("amount_minor", [0, -100])
def test_expense_amount_must_be_positive(db, amount_minor):
    user = add_user(db)
    category = add_category(db, user)
    with pytest.raises(IntegrityError):
        add_expense(db, user, category, amount_minor=amount_minor)


def test_expense_payment_method_must_be_known(db):
    user = add_user(db)
    category = add_category(db, user)
    with pytest.raises(IntegrityError):
        add_expense(db, user, category, payment_method="cheque")


def test_expense_needs_an_existing_category(db):
    user = add_user(db)
    db.add(Expense(user_id=user.id, category_id=999, amount_minor=100, date=date(2026, 6, 1), payment_method="cash"))
    with pytest.raises(IntegrityError):
        db.flush()


def test_category_in_use_cannot_be_deleted(db):
    user = add_user(db)
    category = add_category(db, user)
    add_expense(db, user, category)
    db.commit()

    db.delete(category)
    with pytest.raises(IntegrityError):
        db.flush()


def test_deleting_a_category_deletes_its_budgets(db):
    user = add_user(db)
    category = add_category(db, user)
    db.add(Budget(user_id=user.id, category_id=category.id, month=date(2026, 6, 1), amount_minor=50000))
    db.commit()

    db.delete(category)
    db.commit()

    assert db.scalars(select(Budget)).all() == []


def test_one_budget_per_category_and_month(db):
    user = add_user(db)
    category = add_category(db, user)
    db.add(Budget(user_id=user.id, category_id=category.id, month=date(2026, 6, 1), amount_minor=50000))
    db.flush()
    db.add(Budget(user_id=user.id, category_id=category.id, month=date(2026, 6, 1), amount_minor=70000))
    with pytest.raises(IntegrityError):
        db.flush()


def test_deleting_a_user_deletes_everything_they_own(db):
    user = add_user(db)
    category = add_category(db, user)
    add_expense(db, user, category)
    db.add(Budget(user_id=user.id, category_id=category.id, month=date(2026, 6, 1), amount_minor=50000))
    db.commit()

    db.delete(user)
    db.commit()

    assert db.scalars(select(Expense)).all() == []
    assert db.scalars(select(Category)).all() == []
    assert db.scalars(select(Budget)).all() == []
