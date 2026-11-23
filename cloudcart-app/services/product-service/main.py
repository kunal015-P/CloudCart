
import os
from decimal import Decimal

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import create_engine, text

app = FastAPI(title="CloudCart Product Service", version="2.0.0")

DATABASE_URL = os.environ["DATABASE_URL"]

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True
)

PRODUCTS = [
    {
        "name": "Acer Predator Helios Neo 16",
        "description": "High-performance gaming laptop",
        "price": 129990,
        "stock": 8,
        "category": "Gaming Accessories",
        "image_url": "https://cloud-card-bucket-2211.s3.us-east-2.amazonaws.com/Gaming-+Accessories/ACER+PREDATOR+HELIOS+NEO+16.webp"
    },
    {
        "name": "GTPlayer Gaming Chair",
        "description": "Ergonomic gaming chair",
        "price": 14999,
        "stock": 15,
        "category": "Gaming Accessories",
        "image_url": "https://cloud-card-bucket-2211.s3.us-east-2.amazonaws.com/Gaming-+Accessories/GTPlayer+Gaming+Chair.jpeg"
    },
    {
        "name": "Impact Elite M193 Mouse",
        "description": "Gaming mouse",
        "price": 799,
        "stock": 40,
        "category": "Gaming Accessories",
        "image_url": "https://cloud-card-bucket-2211.s3.us-east-2.amazonaws.com/Gaming-+Accessories/Impact+Elite+M193+Mouse.jpeg"
    },
    {
        "name": "INTEX",
        "description": "INTEX computer accessory",
        "price": 1499,
        "stock": 25,
        "category": "Gaming Accessories",
        "image_url": "https://cloud-card-bucket-2211.s3.us-east-2.amazonaws.com/Gaming-+Accessories/INTEX.webp"
    },
    {
        "name": "US07 Speaker",
        "description": "Computer speaker",
        "price": 1999,
        "stock": 20,
        "category": "Gaming Accessories",
        "image_url": "https://cloud-card-bucket-2211.s3.us-east-2.amazonaws.com/Gaming-+Accessories/US07+Speaker.jpeg"
    },
    {
        "name": "Zebronics Curvv Screen",
        "description": "Computer display",
        "price": 12999,
        "stock": 12,
        "category": "Gaming Accessories",
        "image_url": "https://cloud-card-bucket-2211.s3.us-east-2.amazonaws.com/Gaming-+Accessories/Zebronics+Curvv+Screen.jpeg"
    },
    {
        "name": "Casual Sunglass",
        "description": "Casual sunglasses",
        "price": 999,
        "stock": 30,
        "category": "Goggles",
        "image_url": "https://cloud-card-bucket-2211.s3.us-east-2.amazonaws.com/Goggles/Casual+Sunglass.jpeg"
    },
    {
        "name": "Sunglasses",
        "description": "Everyday sunglasses",
        "price": 1499,
        "stock": 25,
        "category": "Goggles",
        "image_url": "https://cloud-card-bucket-2211.s3.us-east-2.amazonaws.com/Goggles/Sunglasses.jpeg"
    },
    {
        "name": "Casual Shoes",
        "description": "Casual footwear",
        "price": 1499,
        "stock": 25,
        "category": "Shoes",
        "image_url": "https://cloud-card-bucket-2211.s3.us-east-2.amazonaws.com/Shoes/Casual+Shoes.jpeg"
    },
    {
        "name": "Formal Shoes",
        "description": "Formal footwear",
        "price": 2499,
        "stock": 20,
        "category": "Shoes",
        "image_url": "https://cloud-card-bucket-2211.s3.us-east-2.amazonaws.com/Shoes/Formal+Shoes.jpeg"
    },
    {
        "name": "Sports Shoes",
        "description": "Sports footwear",
        "price": 1999,
        "stock": 30,
        "category": "Shoes",
        "image_url": "https://cloud-card-bucket-2211.s3.us-east-2.amazonaws.com/Shoes/Sports+Shoes.jpeg"
    },
    {
        "name": "Trekking Shoes",
        "description": "Trekking footwear",
        "price": 2999,
        "stock": 15,
        "category": "Shoes",
        "image_url": "https://cloud-card-bucket-2211.s3.us-east-2.amazonaws.com/Shoes/Tracking+Shoes.jpeg"
    },
    {
        "name": "Bulova Watch",
        "description": "Bulova wrist watch",
        "price": 24999,
        "stock": 5,
        "category": "Watches",
        "image_url": "https://cloud-card-bucket-2211.s3.us-east-2.amazonaws.com/Watches/Bulova+Watch.jpeg"
    },
    {
        "name": "Fastrack Watch",
        "description": "Fastrack wrist watch",
        "price": 2499,
        "stock": 20,
        "category": "Watches",
        "image_url": "https://cloud-card-bucket-2211.s3.us-east-2.amazonaws.com/Watches/Fastrack+Watch.jpeg"
    },
    {
        "name": "SAPPHERO Watch",
        "description": "SAPPHERO wrist watch",
        "price": 1499,
        "stock": 15,
        "category": "Watches",
        "image_url": "https://cloud-card-bucket-2211.s3.us-east-2.amazonaws.com/Watches/SAPPHERO+Watch.jpeg"
    },
    {
        "name": "TITAN Watch",
        "description": "TITAN wrist watch",
        "price": 4999,
        "stock": 15,
        "category": "Watches",
        "image_url": "https://cloud-card-bucket-2211.s3.us-east-2.amazonaws.com/Watches/TITAN+Watch.jpeg"
    }
]


class ProductCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str = ""
    price: Decimal = Field(gt=0)
    stock: int = Field(ge=0)
    category: str
    image_url: HttpUrl | None = None


def initialize_database():
    with engine.begin() as db:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS products (
                id SERIAL PRIMARY KEY,
                name VARCHAR(120) UNIQUE NOT NULL,
                description TEXT,
                price NUMERIC(12,2) NOT NULL,
                stock INTEGER NOT NULL DEFAULT 0,
                category VARCHAR(80) NOT NULL,
                image_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        for product in PRODUCTS:
            db.execute(
                text("""
                    INSERT INTO products
                    (name, description, price, stock, category, image_url)
                    VALUES
                    (:name, :description, :price, :stock, :category, :image_url)
                    ON CONFLICT (name) DO UPDATE SET
                        description = EXCLUDED.description,
                        category = EXCLUDED.category,
                        image_url = EXCLUDED.image_url
                """),
                product
            )


@app.on_event("startup")
def startup():
    initialize_database()


@app.get("/health")
def health():
    return {"status": "healthy", "service": "product-service"}


@app.get("/products")
def get_products(
    category: str = Query(default=""),
    search: str = Query(default="")
):
    with engine.connect() as db:
        rows = db.execute(
            text("""
                SELECT id, name, description, price, stock,
                       category, image_url
                FROM products
                WHERE (:category = '' OR category = :category)
                  AND name ILIKE :search
                ORDER BY id
            """),
            {
                "category": category,
                "search": f"%{search}%"
            }
        ).mappings().all()

    return [dict(row) for row in rows]


@app.get("/products/{product_id}")
def get_product(product_id: int):
    with engine.connect() as db:
        product = db.execute(
            text("SELECT * FROM products WHERE id = :id"),
            {"id": product_id}
        ).mappings().first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    return dict(product)


@app.post("/products", status_code=201)
def create_product(product: ProductCreate):
    with engine.begin() as db:
        result = db.execute(
            text("""
                INSERT INTO products
                (name, description, price, stock, category, image_url)
                VALUES
                (:name, :description, :price, :stock, :category, :image_url)
                RETURNING id
            """),
            {
                **product.model_dump(exclude={"image_url"}),
                "image_url": str(product.image_url) if product.image_url else None
            }
        )

        product_id = result.scalar_one()

    return get_product(product_id)
