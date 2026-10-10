from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.security import MAX_PASSWORD_BYTES


class UserCreate(BaseModel):
    email: EmailStr = Field(max_length=254, examples=["demo@example.com"])
    password: str = Field(min_length=8, examples=["a long passphrase"])

    @field_validator("password")
    @classmethod
    def password_fits_bcrypt(cls, value: str) -> str:
        # bcrypt reads only 72 bytes. A longer password is refused instead of
        # being cut short without the user knowing.
        if len(value.encode("utf-8")) > MAX_PASSWORD_BYTES:
            raise ValueError(f"Password must be at most {MAX_PASSWORD_BYTES} bytes long")
        return value


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str = Field(examples=["demo@example.com"])
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Seconds until the token expires", examples=[1800])
