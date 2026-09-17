import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

# bcrypt silently truncates anything past 72 bytes, so reject longer passwords
# outright instead of accepting a password that is not fully verified.
PASSWORD_FIELD = Field(..., min_length=8, max_length=72)


class UserCreate(BaseModel):
    email: EmailStr
    password: str = PASSWORD_FIELD


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=72)


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshTokenRequest(BaseModel):
    refresh_token: str
