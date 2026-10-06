import os
from datetime import datetime
from decimal import Decimal

import httpx
import jwt
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Integer, Numeric, String, create_engine, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker

# ---- Config (all from environment variables) ----
DB_HOST = os.environ["DB_HOST"]
DB_USER = os.environ["DB_USER"]
DB_PASSWORD = os.environ["DB_PASSWORD"]
DB_NAME = os.getenv("DB_NAME", "orders_db")
JWT_SECRET = os.environ["JWT_SECRET"]
BOOK_SERVICE_URL = os.getenv("BOOK_SERVICE_URL", "http://book-service:8000")

engine = create_engine(
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:3306/{DB_NAME}",
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    book_id = Column(Integer, nullable=False)
    book_title = Column(String(255), nullable=False)
    quantity = Column(Integer, nullable=False)
    total_price = Column(Numeric(10, 2), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


Base.metadata.create_all(engine)

app = FastAPI(title="order-service")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class OrderIn(BaseModel):
    book_id: int = Field(gt=0)
    quantity: int = Field(gt=0, le=100)


def order_dict(o: Order) -> dict:
    return {
        "id": o.id,
        "book_id": o.book_id,
        "book_title": o.book_title,
        "quantity": o.quantity,
        "total_price": float(o.total_price),
        "created_at": o.created_at.isoformat(),
    }


def require_login(authorization: str = Header(default="")) -> dict:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing token")
    try:
        return jwt.decode(authorization[7:], JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid or expired token")


# ---- Health checks (Kubernetes probes) ----
@app.get("/api/orders/health")
def health():
    return {"status": "ok"}


@app.get("/api/orders/ready")
def ready(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ready"}


# ---- Business endpoints ----
@app.post("/api/orders", status_code=201)
def create_order(
    body: OrderIn,
    db: Session = Depends(get_db),
    user: dict = Depends(require_login),
):
    # Ask book-service for the book (price comes from here, never from the client)
    try:
        resp = httpx.get(f"{BOOK_SERVICE_URL}/api/books/{body.book_id}", timeout=5.0)
    except httpx.RequestError:
        raise HTTPException(503, "book-service not reachable")

    if resp.status_code == 404:
        raise HTTPException(404, "Book not found")
    if resp.status_code != 200:
        raise HTTPException(502, "book-service error")

    book = resp.json()
    total = Decimal(str(book["price"])) * body.quantity

    order = Order(
        user_id=int(user["sub"]),
        book_id=book["id"],
        book_title=book["title"],
        quantity=body.quantity,
        total_price=total,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order_dict(order)


@app.get("/api/orders")
def my_orders(db: Session = Depends(get_db), user: dict = Depends(require_login)):
    rows = (
        db.query(Order)
        .filter(Order.user_id == int(user["sub"]))
        .order_by(Order.id.desc())
        .all()
    )
    return [order_dict(o) for o in rows]
