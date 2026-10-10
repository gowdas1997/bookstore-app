import os

import jwt
from fastapi import Depends, FastAPI, Header, HTTPException
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, Field
from sqlalchemy import Column, Integer, Numeric, String, create_engine, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker

# ---- Config (all from environment variables) ----
DB_HOST = os.environ["DB_HOST"]
DB_USER = os.environ["DB_USER"]
DB_PASSWORD = os.environ["DB_PASSWORD"]
DB_NAME = os.getenv("DB_NAME", "books_db")
JWT_SECRET = os.environ["JWT_SECRET"]

engine = create_engine(
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:3306/{DB_NAME}",
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class Book(Base):
    __tablename__ = "books"
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    author = Column(String(255), nullable=False)
    price = Column(Numeric(10, 2), nullable=False)


Base.metadata.create_all(engine)

# Seed 3 sample books on first start (only if table is empty)
with SessionLocal() as s:
    if s.query(Book).count() == 0:
        s.add_all([
            Book(title="Python Basics", author="A. Kumar", price=299),
            Book(title="Docker in Practice", author="R. Sharma", price=499),
            Book(title="Kubernetes Up and Running", author="S. Rao", price=699),
        ])
        s.commit()

app = FastAPI(title="book-service")
Instrumentator(excluded_handlers=["/metrics", ".*/health", ".*/ready"]).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class BookIn(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    author: str = Field(min_length=1, max_length=255)
    price: float = Field(gt=0)


def book_dict(b: Book) -> dict:
    return {"id": b.id, "title": b.title, "author": b.author, "price": float(b.price)}


def require_login(authorization: str = Header(default="")) -> dict:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing token")
    try:
        return jwt.decode(authorization[7:], JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid or expired token")


def require_admin(user: dict = Depends(require_login)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(403, "Admin only")
    return user


# ---- Health checks (Kubernetes probes) ----
@app.get("/api/books/health")
def health():
    return {"status": "ok"}


@app.get("/api/books/ready")
def ready(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ready"}


# ---- Business endpoints ----
@app.get("/api/books")
def list_books(db: Session = Depends(get_db)):
    return [book_dict(b) for b in db.query(Book).order_by(Book.id).all()]


@app.get("/api/books/{book_id}")
def get_book(book_id: int, db: Session = Depends(get_db)):
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    return book_dict(book)


@app.post("/api/books", status_code=201)
def add_book(body: BookIn, db: Session = Depends(get_db), user: dict = Depends(require_admin)):
    book = Book(title=body.title, author=body.author, price=body.price)
    db.add(book)
    db.commit()
    db.refresh(book)
    return book_dict(book)


@app.delete("/api/books/{book_id}")
def delete_book(book_id: int, db: Session = Depends(get_db), user: dict = Depends(require_admin)):
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    db.delete(book)
    db.commit()
    return {"message": "deleted"}
