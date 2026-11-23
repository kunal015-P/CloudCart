
import os
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import create_engine, text
from jose import jwt, JWTError
from passlib.context import CryptContext

# --------------------------------------------------
# Configuration
# --------------------------------------------------

DATABASE_URL = os.environ["DATABASE_URL"]
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True
)

app = FastAPI(
    title="CloudCart User Service",
    version="2.0.0"
)

password_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)

security = HTTPBearer()


# --------------------------------------------------
# Request models
# --------------------------------------------------

class UserRegister(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)


# --------------------------------------------------
# Database initialization
# --------------------------------------------------

def initialize_database():
    with engine.begin() as db:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                email VARCHAR(255) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            )
        """))


@app.on_event("startup")
def startup():
    initialize_database()


# --------------------------------------------------
# Password utilities
# --------------------------------------------------

def hash_password(password: str) -> str:
    return password_context.hash(password)


def verify_password(
    password: str,
    hashed_password: str
) -> bool:
    return password_context.verify(
        password,
        hashed_password
    )


# --------------------------------------------------
# JWT utilities
# --------------------------------------------------

def create_access_token(user_id: int, email: str):
    expires = datetime.now(timezone.utc) + timedelta(
        minutes=JWT_EXPIRE_MINUTES
    )

    payload = {
        "sub": str(user_id),
        "email": email,
        "exp": expires
    }

    token = jwt.encode(
        payload,
        JWT_SECRET,
        algorithm=JWT_ALGORITHM
    )

    return token


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    token = credentials.credentials

    try:
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM]
        )

        user_id = int(payload["sub"])

    except (JWTError, KeyError, ValueError):
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired access token"
        )

    with engine.connect() as db:
        user = db.execute(
            text("""
                SELECT id, name, email, created_at
                FROM users
                WHERE id = :id
            """),
            {"id": user_id}
        ).mappings().first()

    if not user:
        raise HTTPException(
            status_code=401,
            detail="User no longer exists"
        )

    return dict(user)


# --------------------------------------------------
# Health endpoint
# --------------------------------------------------

@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "user-service"
    }


# --------------------------------------------------
# Registration
# --------------------------------------------------

@app.post("/register", status_code=201)
def register(user: UserRegister):

    hashed_password = hash_password(user.password)

    try:
        with engine.begin() as db:
            result = db.execute(
                text("""
                    INSERT INTO users
                    (name, email, password_hash)
                    VALUES
                    (:name, :email, :password_hash)
                    RETURNING id, name, email, created_at
                """),
                {
                    "name": user.name,
                    "email": user.email.lower(),
                    "password_hash": hashed_password
                }
            )

            new_user = result.mappings().one()

    except Exception as exc:
        # A production implementation should catch the specific
        # unique-constraint violation rather than all exceptions.
        from sqlalchemy.exc import IntegrityError

        if isinstance(exc, IntegrityError):
            raise HTTPException(
                status_code=409,
                detail="Email already registered"
            )

        raise

    return {
        "message": "Registration successful",
        "user": dict(new_user)
    }


# --------------------------------------------------
# Login
# --------------------------------------------------

@app.post("/login")
def login(credentials: UserLogin):

    with engine.connect() as db:
        user = db.execute(
            text("""
                SELECT id, name, email, password_hash
                FROM users
                WHERE email = :email
            """),
            {"email": credentials.email.lower()}
        ).mappings().first()

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

    if not verify_password(
        credentials.password,
        user["password_hash"]
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

    access_token = create_access_token(
        user["id"],
        user["email"]
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": JWT_EXPIRE_MINUTES * 60,
        "user": {
            "id": user["id"],
            "name": user["name"],
            "email": user["email"]
        }
    }


# --------------------------------------------------
# Current authenticated user
# --------------------------------------------------

@app.get("/me")
def get_me(current_user=Depends(get_current_user)):
    return current_user
