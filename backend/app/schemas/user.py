from pydantic import BaseModel, EmailStr

class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    avatar: str | None
    soul_coin_balance: int
    is_admin: bool = False

class AuthResponse(BaseModel):
    access_token: str
    user: UserResponse
