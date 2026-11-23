
import os
from typing import Optional

import httpx

from fastapi import FastAPI, HTTPException, Query


# --------------------------------------------------
# Configuration
# --------------------------------------------------

PRODUCT_SERVICE_URL = os.getenv(
    "PRODUCT_SERVICE_URL",
    "http://product-service:8002"
)

app = FastAPI(
    title="CloudCart AI Recommendation Service",
    version="2.0.0"
)


# --------------------------------------------------
# Health endpoint
# --------------------------------------------------

@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "ai-recommendation-service",
        "engine": "rule-based"
    }


# --------------------------------------------------
# Retrieve products
# --------------------------------------------------

async def fetch_products():

    url = f"{PRODUCT_SERVICE_URL}/products"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()

            return response.json()

    except httpx.HTTPError:
        raise HTTPException(
            status_code=503,
            detail="Product Service is currently unavailable"
        )


# --------------------------------------------------
# Recommendation scoring
# --------------------------------------------------

def calculate_score(
    product: dict,
    category: Optional[str],
    keyword: Optional[str],
    budget: float
):
    score = 0
    reasons = []

    name = product.get("name", "").lower()
    description = product.get("description", "").lower()
    product_category = product.get("category", "").lower()

    search_text = f"{name} {description} {product_category}"

    price = float(product["price"])

    # Category matching
    if category:
        if product_category == category.lower():
            score += 50
            reasons.append("Matches your selected category")

    # Keyword matching
    if keyword:
        terms = keyword.lower().split()

        matched_terms = [
            term for term in terms
            if term in search_text
        ]

        score += len(matched_terms) * 15

        if matched_terms:
            reasons.append("Matches your search keywords")

    # Budget scoring
    if price <= budget:

        score += 30
        reasons.append("Within your budget")

        # Prefer products using a reasonable portion
        # of the customer's budget.
        if budget > 0:
            utilization = price / budget

            if utilization >= 0.70:
                score += 10
                reasons.append("Uses a good portion of your budget")

    return score, reasons


# --------------------------------------------------
# Recommendation endpoint
# --------------------------------------------------

@app.get("/recommendations")
async def recommendations(
    budget: float = Query(gt=0, le=10000000),
    category: Optional[str] = Query(default=None, max_length=80),
    keyword: Optional[str] = Query(default=None, max_length=100),
    limit: int = Query(default=6, ge=1, le=20)
):

    products = await fetch_products()

    results = []

    for product in products:

        try:
            price = float(product["price"])
            stock = int(product["stock"])

        except (KeyError, TypeError, ValueError):
            continue

        # Exclude unavailable products.
        if stock <= 0:
            continue

        # Exclude products outside the budget.
        if price > budget:
            continue

        score, reasons = calculate_score(
            product=product,
            category=category,
            keyword=keyword,
            budget=budget
        )

        # A selected category or keyword must match.
        if category and product.get("category", "").lower() != category.lower():
            continue

        if keyword:
            search_text = (
                product.get("name", "") + " " +
                product.get("description", "") + " " +
                product.get("category", "")
            ).lower()

            if not any(
                term in search_text
                for term in keyword.lower().split()
            ):
                continue

        results.append({
            "id": product["id"],
            "name": product["name"],
            "description": product.get("description"),
            "category": product.get("category"),
            "price": price,
            "stock": stock,
            "image_url": product.get("image_url"),
            "score": score,
            "reasons": reasons
        })

    # Highest score first.
    # Lower price breaks ties.
    results.sort(
        key=lambda item: (
            -item["score"],
            item["price"]
        )
    )

    selected = results[:limit]

    return {
        "message": (
            "Recommendations generated successfully"
            if selected
            else "No matching products found within your budget"
        ),
        "recommendation_engine": "rule-based",
        "budget": budget,
        "category": category,
        "keyword": keyword,
        "count": len(selected),
        "recommendations": selected
    }


# --------------------------------------------------
# Similar product recommendations
# --------------------------------------------------

@app.get("/recommendations/similar/{product_id}")
async def similar_products(
    product_id: int,
    limit: int = Query(default=4, ge=1, le=10)
):

    products = await fetch_products()

    selected_product = next(
        (
            p for p in products
            if int(p["id"]) == product_id
        ),
        None
    )

    if not selected_product:
        raise HTTPException(
            status_code=404,
            detail="Product not found"
        )

    category = selected_product.get("category", "")

    similar = []

    for product in products:

        if int(product["id"]) == product_id:
            continue

        if product.get("category", "").lower() != category.lower():
            continue

        if int(product.get("stock", 0)) <= 0:
            continue

        similar.append({
            "id": product["id"],
            "name": product["name"],
            "category": product["category"],
            "price": float(product["price"]),
            "image_url": product.get("image_url"),
            "stock": product["stock"]
        })

    return {
        "product": selected_product["name"],
        "category": category,
        "count": min(len(similar), limit),
        "similar_products": similar[:limit]
    }
