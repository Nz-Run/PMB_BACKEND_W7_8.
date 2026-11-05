
from datetime import date
from pydantic import BaseModel, EmailStr, ConfigDict, Field


class RegisterRequest(BaseModel):
    name: str = Field(min_length=3, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8)
    tanggal_lahir: date
    alamat: str = Field(min_length=5, max_length=255)
    program_studi: str = Field(min_length=2, max_length=100)


class RegisterResponse(BaseModel):
    message: str
    user_id: int
    applicant_id: int
    registration_id: int
    email: EmailStr
    status_pendaftaran: str


class UserResponse(BaseModel):
    id: int
    name: str
    email: EmailStr

    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    message: str
    user_id: int
    name: str
    email: EmailStr
    access_token: str
    token_type: str