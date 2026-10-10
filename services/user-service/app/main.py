import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, FastAPI, Header, HTTPException
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, EmailStr
from sqlalchemy import Column, Integer, String, create_engine, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker

# ---- Config (all from environment variables, nothing hardcoded) ----
DB_HOST = os.environ["DB_HOST"]
DB_USER = os.environ["DB_USER"]
DB_PASSWORD = os.environ["DB_PASSWORD"]
DB_NAME = os.getenv("DB_NAME", "users_db")
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))
ADMIN_EMAILS = {e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()}

engine = create_engine(
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:3306/{DB_NAME}",
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)


Base.metadata.create_all(engine)

app = FastAPI(title="user-service")
Instrumentator(excluded_handlers=["/metrics", ".*/health", ".*/ready"]).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class Credentials(BaseModel):
    email: EmailStr
    password: str


def make_token(user: User) -> str:
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "role": "admin" if user.email.lower() in ADMIN_EMAILS else "user",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


# ---- Health checks (Kubernetes probes will use these) ----
@app.get("/api/users/health")
def health():
    return {"status": "ok"}


@app.get("/api/users/ready")
def ready(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ready"}


# ---- Business endpoints ----
@app.post("/api/users/register", status_code=201)
def register(body: Credentials, db: Session = Depends(get_db)):
    if len(body.password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(409, "Email already registered")
    hashed = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt()).decode()
    user = User(email=body.email, password_hash=hashed)
    db.add(user)
    db.commit()
    return {"message": "registered"}


@app.post("/api/users/login")
def login(body: Credentials, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not bcrypt.checkpw(body.password.encode(), user.password_hash.encode()):
        raise HTTPException(401, "Invalid email or password")
    return {"access_token": make_token(user), "token_type": "bearer"}


@app.get("/api/users/me")
def me(authorization: str = Header(default="")):
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing token")
    try:
        data = jwt.decode(authorization[7:], JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid or expired token")
    return {"id": int(data["sub"]), "email": data["email"], "role": data.get("role", "user")}
# ci test
