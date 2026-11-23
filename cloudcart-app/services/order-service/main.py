
import os
from decimal import Decimal
from datetime import datetime, timezone
from uuid import UUID

import redis

from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from jose import jwt, JWTError
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError


# --------------------------------------------------
# Configuration
# --------------------------------------------------

DATABASE_URL = os.environ["DATABASE_URL"]
REDIS_URL = os.environ["REDIS_URL"]

JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True
)

redis_client = redis.Redis.from_url(
    REDIS_URL,
    decode_responses=True
)

app = FastAPI(
    title="CloudCart Order Service",
    version="2.0.0"
)

security = HTTPBearer()


# --------------------------------------------------
# Request models
# --------------------------------------------------

class CheckoutRequest(BaseModel):
    checkout_id: UUID


# --------------------------------------------------
# Authentication
# --------------------------------------------------

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

    return user_id


# --------------------------------------------------
# Database initialization
# --------------------------------------------------

def initialize_database():

    with engine.begin() as db:

        db.execute(text("""
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                checkout_id UUID UNIQUE NOT NULL,
                total_amount NUMERIC(12,2) NOT NULL,
                order_status VARCHAR(30) NOT NULL,
                payment_status VARCHAR(30) NOT NULL,
                payment_method VARCHAR(50) NOT NULL,
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            )
        """))

        db.execute(text("""
            CREATE TABLE IF NOT EXISTS order_items (
                id SERIAL PRIMARY KEY,
                order_id INTEGER NOT NULL
                    REFERENCES orders(id) ON DELETE CASCADE,
                product_id INTEGER NOT NULL,
                product_name VARCHAR(120) NOT NULL,
                unit_price NUMERIC(12,2) NOT NULL,
                quantity INTEGER NOT NULL,
                subtotal NUMERIC(12,2) NOT NULL
            )
        """))

        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_orders_user_id
            ON orders(user_id)
        """))

        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_order_items_order_id
            ON order_items(order_id)
        """))


@app.on_event("startup")
def startup():
    initialize_database()


# --------------------------------------------------
# Health endpoint
# --------------------------------------------------

@app.get("/health")
def health():

    try:
        redis_client.ping()

        with engine.connect() as db:
            db.execute(text("SELECT 1"))

        return {
            "status": "healthy",
            "service": "order-service",
            "postgres": "connected",
            "redis": "connected"
        }

    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Order Service dependency unavailable"
        )


# --------------------------------------------------
# Order serialization
# --------------------------------------------------

def get_order_details(db, order_id: int):

    order = db.execute(
        text("""
            SELECT id, user_id, checkout_id, total_amount,
                   order_status, payment_status, payment_method,
                   created_at
            FROM orders
            WHERE id = :order_id
        """),
        {"order_id": order_id}
    ).mappings().first()

    if not order:
        return None

    items = db.execute(
        text("""
            SELECT product_id, product_name, unit_price,
                   quantity, subtotal
            FROM order_items
            WHERE order_id = :order_id
            ORDER BY id
        """),
        {"order_id": order_id}
    ).mappings().all()

    return {
        "id": order["id"],
        "user_id": order["user_id"],
        "checkout_id": str(order["checkout_id"]),
        "total_amount": float(order["total_amount"]),
        "order_status": order["order_status"],
        "payment_status": order["payment_status"],
        "payment_method": order["payment_method"],
        "created_at": order["created_at"],
        "items": [
            {
                "product_id": item["product_id"],
                "product_name": item["product_name"],
                "unit_price": float(item["unit_price"]),
                "quantity": item["quantity"],
                "subtotal": float(item["subtotal"])
            }
            for item in items
        ]
    }


# --------------------------------------------------
# Checkout
# --------------------------------------------------

@app.post("/orders/checkout", status_code=201)
def checkout(
    request: CheckoutRequest,
    user_id: int = Depends(get_current_user)
):

    cart_key = f"cloudcart:cart:{user_id}"

    # --------------------------------------------------
    # Check if this checkout was already processed
    # --------------------------------------------------

    with engine.connect() as db:

        existing = db.execute(
            text("""
                SELECT id
                FROM orders
                WHERE checkout_id = :checkout_id
                  AND user_id = :user_id
            """),
            {
                "checkout_id": request.checkout_id,
                "user_id": user_id
            }
        ).scalar_one_or_none()

        if existing:
            return {
                "message": "Checkout already processed",
                "order": get_order_details(db, existing)
            }

    # --------------------------------------------------
    # Read cart from Redis
    # --------------------------------------------------

    try:
        cart_items = redis_client.hgetall(cart_key)

    except redis.RedisError:
        raise HTTPException(
            status_code=503,
            detail="Shopping cart service unavailable"
        )

    if not cart_items:
        raise HTTPException(
            status_code=400,
            detail="Your shopping cart is empty"
        )

    requested_items = []

    for product_id, quantity in cart_items.items():

        try:
            pid = int(product_id)
            qty = int(quantity)

        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid shopping cart data"
            )

        if pid <= 0 or qty <= 0 or qty > 20:
            raise HTTPException(
                status_code=400,
                detail="Invalid product or quantity in cart"
            )

        requested_items.append((pid, qty))

    requested_items.sort(key=lambda item: item[0])

    # --------------------------------------------------
    # Validate inventory and create order atomically
    # --------------------------------------------------

    try:

        with engine.begin() as db:

            # Recheck idempotency inside the transaction.
            existing = db.execute(
                text("""
                    SELECT id
                    FROM orders
                    WHERE checkout_id = :checkout_id
                      AND user_id = :user_id
                """),
                {
                    "checkout_id": request.checkout_id,
                    "user_id": user_id
                }
            ).scalar_one_or_none()

            if existing:
                order_id = existing

            else:

                validated_items = []
                total = Decimal("0.00")

                # Lock each product row in a stable order.
                for product_id, quantity in requested_items:

                    product = db.execute(
                        text("""
                            SELECT id, name, price, stock
                            FROM products
                            WHERE id = :product_id
                            FOR UPDATE
                        """),
                        {"product_id": product_id}
                    ).mappings().first()

                    if not product:
                        raise HTTPException(
                            status_code=404,
                            detail=f"Product {product_id} not found"
                        )

                    price = Decimal(str(product["price"]))
                    stock = int(product["stock"])

                    if price <= 0:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Price not configured for {product['name']}"
                        )

                    if stock < quantity:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Insufficient stock for {product['name']}. Available: {stock}"
                        )

                    subtotal = price * quantity
                    total += subtotal

                    validated_items.append({
                        "id": product["id"],
                        "name": product["name"],
                        "price": price,
                        "quantity": quantity,
                        "subtotal": subtotal
                    })

                # Simulated payment.
                # No real payment provider or card information is used.

                result = db.execute(
                    text("""
                        INSERT INTO orders (
                            user_id,
                            checkout_id,
                            total_amount,
                            order_status,
                            payment_status,
                            payment_method
                        )
                        VALUES (
                            :user_id,
                            :checkout_id,
                            :total_amount,
                            'CONFIRMED',
                            'SIMULATED_PAID',
                            'DEMO'
                        )
                        RETURNING id
                    """),
                    {
                        "user_id": user_id,
                        "checkout_id": request.checkout_id,
                        "total_amount": total
                    }
                )

                order_id = result.scalar_one()

                for item in validated_items:

                    # Deduct inventory within the same transaction.
                    db.execute(
                        text("""
                            UPDATE products
                            SET stock = stock - :quantity
                            WHERE id = :product_id
                        """),
                        {
                            "quantity": item["quantity"],
                            "product_id": item["id"]
                        }
                    )

                    db.execute(
                        text("""
                            INSERT INTO order_items (
                                order_id,
                                product_id,
                                product_name,
                                unit_price,
                                quantity,
                                subtotal
                            )
                            VALUES (
                                :order_id,
                                :product_id,
                                :product_name,
                                :unit_price,
                                :quantity,
                                :subtotal
                            )
                        """),
                        {
                            "order_id": order_id,
                            "product_id": item["id"],
                            "product_name": item["name"],
                            "unit_price": item["price"],
                            "quantity": item["quantity"],
                            "subtotal": item["subtotal"]
                        }
                    )

        # The database transaction has committed.
        # Clear the cart only after successful checkout.

        try:
            redis_client.delete(cart_key)

        except redis.RedisError:
            # The order is committed; do not report checkout failure.
            # A later cart cleanup/reconciliation can handle this case.
            pass

        with engine.connect() as db:
            order = get_order_details(db, order_id)

        return {
            "message": "Order placed successfully",
            "payment_note": "Payment is simulated for this demo",
            "order": order
        }

    except HTTPException:
        raise

    except IntegrityError:
        # A concurrent request may have used the same checkout ID.
        with engine.connect() as db:

            existing = db.execute(
                text("""
                    SELECT id
                    FROM orders
                    WHERE checkout_id = :checkout_id
                      AND user_id = :user_id
                """),
                {
                    "checkout_id": request.checkout_id,
                    "user_id": user_id
                }
            ).scalar_one_or_none()

            if existing:
                return {
                    "message": "Checkout already processed",
                    "order": get_order_details(db, existing)
                }

        raise HTTPException(
            status_code=409,
            detail="Checkout conflict. Please retry with a new checkout ID."
        )


# --------------------------------------------------
# Get customer's order history
# --------------------------------------------------

@app.get("/orders/me")
def get_my_orders(
    user_id: int = Depends(get_current_user)
):

    with engine.connect() as db:

        order_ids = db.execute(
            text("""
                SELECT id
                FROM orders
                WHERE user_id = :user_id
                ORDER BY created_at DESC
            """),
            {"user_id": user_id}
        ).scalars().all()

        return [
            get_order_details(db, order_id)
            for order_id in order_ids
        ]


# --------------------------------------------------
# Get individual order
# --------------------------------------------------

@app.get("/orders/{order_id}")
def get_order(
    order_id: int,
    user_id: int = Depends(get_current_user)
):

    with engine.connect() as db:

        order = db.execute(
            text("""
                SELECT id
                FROM orders
                WHERE id = :order_id
                  AND user_id = :user_id
            """),
            {
                "order_id": order_id,
                "user_id": user_id
            }
        ).scalar_one_or_none()

        if not order:
            raise HTTPException(
                status_code=404,
                detail="Order not found"
            )

        return get_order_details(db, order)
