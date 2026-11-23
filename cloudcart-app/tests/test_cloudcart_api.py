
import os
import uuid

import httpx
import pytest


BASE_URL = os.getenv("CLOUDCART_BASE_URL", "http://localhost").rstrip("/")
TIMEOUT = 20.0


@pytest.fixture
def client():
    with httpx.Client(
        base_url=BASE_URL,
        timeout=TIMEOUT,
        follow_redirects=True,
    ) as test_client:
        yield test_client


@pytest.fixture
def registered_user(client):
    unique_email = f"cloudcart-test-{uuid.uuid4().hex[:12]}@example.com"

    registration = client.post(
        "/api/users/register",
        json={
            "name": "CloudCart Test User",
            "email": unique_email,
            "password": "CloudCartTest123!",
        },
    )

    assert registration.status_code in (200, 201), (
        f"Registration failed: {registration.status_code} "
        f"{registration.text}"
    )

    login = client.post(
        "/api/users/login",
        json={
            "email": unique_email,
            "password": "CloudCartTest123!",
        },
    )

    assert login.status_code == 200, (
        f"Login failed: {login.status_code} {login.text}"
    )

    login_data = login.json()
    token = login_data["access_token"]
    user = login_data["user"]

    return {
        "id": user["id"],
        "email": unique_email,
        "token": token,
    }


@pytest.fixture
def authenticated_client(client, registered_user):
    client.headers.update(
        {"Authorization": f"Bearer {registered_user['token']}"}
    )
    return client


def get_products(client):
    response = client.get("/api/products/products")
    assert response.status_code == 200, response.text

    data = response.json()

    # Support either a plain array or an object containing "products".
    if isinstance(data, dict):
        data = data.get("products", [])

    assert isinstance(data, list)
    return data


@pytest.mark.integration
def test_product_catalogue_is_available(client):
    products = get_products(client)

    assert len(products) > 0

    first_product = products[0]
    assert "id" in first_product
    assert "name" in first_product
    assert "price" in first_product


@pytest.mark.integration
def test_user_registration_and_login(registered_user):
    assert registered_user["id"] is not None
    assert registered_user["token"]


@pytest.mark.integration
def test_authenticated_user_profile(authenticated_client):
    response = authenticated_client.get("/api/users/me")

    assert response.status_code == 200, response.text

    profile = response.json()
    assert "email" in profile


@pytest.mark.integration
def test_cart_add_read_and_remove(authenticated_client):
    products = get_products(authenticated_client)

    available_product = next(
        (
            product
            for product in products
            if int(product.get("stock", 0)) > 0
        ),
        None,
    )

    assert available_product is not None, "No in-stock products found"

    user_id = authenticated_client.get("/api/users/me").json()["id"]
    product_id = available_product["id"]

    add_response = authenticated_client.post(
        f"/api/cart/cart/{user_id}/items",
        json={
            "product_id": product_id,
            "quantity": 1,
        },
    )

    assert add_response.status_code in (200, 201), add_response.text

    cart_response = authenticated_client.get(
        f"/api/cart/cart/{user_id}"
    )

    assert cart_response.status_code == 200, cart_response.text

    cart = cart_response.json()
    assert any(
        str(item["product_id"]) == str(product_id)
        for item in cart["items"]
    )

    remove_response = authenticated_client.delete(
        f"/api/cart/cart/{user_id}/items/{product_id}"
    )

    assert remove_response.status_code in (200, 204), (
        remove_response.text
    )


@pytest.mark.integration
def test_recommendations_endpoint(client):
    response = client.get(
        "/api/ai/recommendations",
        params={"limit": 5},
    )

    assert response.status_code == 200, response.text

    data = response.json()
    assert isinstance(data, (list, dict))


@pytest.mark.integration
def test_orders_require_authentication(client):
    response = client.get("/api/orders/orders/me")

    assert response.status_code in (401, 403), response.text


@pytest.mark.e2e
def test_checkout_and_order_history(authenticated_client):
    products = get_products(authenticated_client)

    available_product = next(
        (
            product
            for product in products
            if int(product.get("stock", 0)) > 0
        ),
        None,
    )

    assert available_product is not None, "No in-stock products found"

    user_id = authenticated_client.get("/api/users/me").json()["id"]

    add_response = authenticated_client.post(
        f"/api/cart/cart/{user_id}/items",
        json={
            "product_id": available_product["id"],
            "quantity": 1,
        },
    )

    assert add_response.status_code in (200, 201), add_response.text

    checkout_response = authenticated_client.post(
        "/api/orders/orders/checkout",
        json={"checkout_id": str(uuid.uuid4())},
    )

    assert checkout_response.status_code in (200, 201), (
        checkout_response.text
    )

    order_history = authenticated_client.get(
        "/api/orders/orders/me"
    )

    assert order_history.status_code == 200, order_history.text
    assert len(order_history.json()) >= 1
