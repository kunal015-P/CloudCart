
import os

import httpx
import redis

from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from jose import jwt, JWTError


# --------------------------------------------------
# Configuration
# --------------------------------------------------

REDIS_URL = os.environ["REDIS_URL"]
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

PRODUCT_SERVICE_URL = os.getenv(
    "PRODUCT_SERVICE_URL",
    "http://product-service:8002"
)

app = FastAPI(
    title="CloudCart Cart Service",
    version="2.0.0"
)

redis_client = redis.Redis.from_url(
    REDIS_URL,
    decode_responses=True
)

security = HTTPBearer()


# --------------------------------------------------
# Request models
# --------------------------------------------------

class CartItemInput(BaseModel):
    product_id: int = Field(gt=0)
    quantity: int = Field(gt=0, le=20)


class QuantityUpdate(BaseModel):
    quantity: int = Field(gt=0, le=20)


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


def verify_cart_owner(user_id: int, current_user: int):
    if user_id != current_user:
        raise HTTPException(
            status_code=403,
            detail="You cannot access another customer's cart"
        )


# --------------------------------------------------
# Redis helpers
# --------------------------------------------------

def cart_key(user_id: int) -> str:
    return f"cloudcart:cart:{user_id}"


def get_redis_client():
    return redis_client


# --------------------------------------------------
# Product Service integration
# --------------------------------------------------

def get_product(product_id: int):

    url = f"{PRODUCT_SERVICE_URL}/products/{product_id}"

    try:
        response = httpx.get(url, timeout=5.0)

        if response.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail="Product not found"
            )

        response.raise_for_status()

        return response.json()

    except HTTPException:
        raise

    except httpx.HTTPError:
        raise HTTPException(
            status_code=503,
            detail="Product Service is currently unavailable"
        )


# --------------------------------------------------
# Health endpoint
# --------------------------------------------------

@app.get("/health")
def health():

    try:
        redis_client.ping()

        return {
            "status": "healthy",
            "service": "cart-service",
            "redis": "connected"
        }

    except redis.RedisError:
        raise HTTPException(
            status_code=503,
            detail="Redis connection failed"
        )


# --------------------------------------------------
# Get customer cart
# --------------------------------------------------

@app.get("/cart/{user_id}")
def get_cart(
    user_id: int,
    current_user: int = Depends(get_current_user)
):

    verify_cart_owner(user_id, current_user)

    items = redis_client.hgetall(cart_key(user_id))

    cart_items = []
    total = 0.0

    for product_id, quantity in items.items():

        product = get_product(int(product_id))

        quantity = int(quantity)
        price = float(product["price"])

        subtotal = price * quantity
        total += subtotal

        cart_items.append({
            "product_id": int(product_id),
            "name": product["name"],
            "image_url": product.get("image_url"),
            "category": product.get("category"),
            "price": price,
            "quantity": quantity,
            "stock": product["stock"],
            "subtotal": round(subtotal, 2)
        })

    return {
        "user_id": user_id,
        "items": cart_items,
        "total_items": sum(item["quantity"] for item in cart_items),
        "total_amount": round(total, 2)
    }


# --------------------------------------------------
# Add product to cart
# --------------------------------------------------

@app.post("/cart/{user_id}/items")
def add_to_cart(
    user_id: int,
    item: CartItemInput,
    current_user: int = Depends(get_current_user)
):

    verify_cart_owner(user_id, current_user)

    product = get_product(item.product_id)

    available_stock = int(product["stock"])

    if available_stock <= 0:
        raise HTTPException(
            status_code=400,
            detail="Product is currently out of stock"
        )

    key = cart_key(user_id)

    existing_quantity = int(
        redis_client.hget(key, str(item.product_id)) or 0
    )

    new_quantity = existing_quantity + item.quantity

    if new_quantity > available_stock:
        raise HTTPException(
            status_code=400,
            detail=f"Only {available_stock} units are available"
        )

    if new_quantity > 20:
        raise HTTPException(
            status_code=400,
            detail="Maximum 20 units per product are allowed"
        )

    redis_client.hset(
        key,
        str(item.product_id),
        new_quantity
    )

    return {
        "message": "Product added to cart",
        "product_id": item.product_id,
        "quantity": new_quantity
    }


# --------------------------------------------------
# Update product quantity
# --------------------------------------------------

@app.patch("/cart/{user_id}/items/{product_id}")
def update_cart_item(
    user_id: int,
    product_id: int,
    update: QuantityUpdate,
    current_user: int = Depends(get_current_user)
):

    verify_cart_owner(user_id, current_user)

    key = cart_key(user_id)

    existing = redis_client.hget(key, str(product_id))

    if existing is None:
        raise HTTPException(
            status_code=404,
            detail="Product is not in your cart"
        )

    product = get_product(product_id)

    if update.quantity > int(product["stock"]):
        raise HTTPException(
            status_code=400,
            detail="Requested quantity exceeds available stock"
        )

    redis_client.hset(
        key,
        str(product_id),
        update.quantity
    )

    return {
        "message": "Cart quantity updated",
        "product_id": product_id,
        "quantity": update.quantity
    }


# --------------------------------------------------
# Remove product from cart
# --------------------------------------------------

@app.delete("/cart/{user_id}/items/{product_id}")
def remove_cart_item(
    user_id: int,
    product_id: int,
    current_user: int = Depends(get_current_user)
):

    verify_cart_owner(user_id, current_user)

    removed = redis_client.hdel(
        cart_key(user_id),
        str(product_id)
    )

    if removed == 0:
        raise HTTPException(
            status_code=404,
            detail="Product is not in your cart"
        )

    return {
        "message": "Product removed from cart",
        "product_id": product_id
    }


# --------------------------------------------------
# Clear entire cart
# --------------------------------------------------

@app.delete("/cart/{user_id}")
def clear_cart(
    user_id: int,
    current_user: int = Depends(get_current_user)
):

    verify_cart_owner(user_id, current_user)

    redis_client.delete(cart_key(user_id))

    return {
        "message": "Shopping cart cleared"
    }
