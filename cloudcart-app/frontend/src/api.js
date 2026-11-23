
const BASE = "/api";

export function getToken() {
  return localStorage.getItem("cloudcart_token");
}

export function saveSession(data) {
  localStorage.setItem("cloudcart_token", data.access_token);
  localStorage.setItem("cloudcart_user", JSON.stringify(data.user));
}

export function clearSession() {
  localStorage.removeItem("cloudcart_token");
  localStorage.removeItem("cloudcart_user");
}

export function getSavedUser() {
  try {
    return JSON.parse(localStorage.getItem("cloudcart_user"));
  } catch {
    return null;
  }
}

export async function apiRequest(path, options = {}) {
  const token = getToken();

  const headers = {
    ...(options.body ? { "Content-Type": "application/json" } : {}),
    ...options.headers
  };

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${BASE}${path}`, {
    ...options,
    headers
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    if (response.status === 401) {
      clearSession();
    }

    throw new Error(
      data.detail || data.message || "Something went wrong"
    );
  }

  return data;
}

export const api = {
  register: (payload) =>
    apiRequest("/users/register", {
      method: "POST",
      body: JSON.stringify(payload)
    }),

  login: (payload) =>
    apiRequest("/users/login", {
      method: "POST",
      body: JSON.stringify(payload)
    }),

  products: (search = "") =>
    apiRequest(`/products/products?search=${encodeURIComponent(search)}`),

  addToCart: (userId, productId, quantity = 1) =>
    apiRequest(`/cart/cart/${userId}/items`, {
      method: "POST",
      body: JSON.stringify({
        product_id: productId,
        quantity
      })
    }),

  getCart: (userId) =>
    apiRequest(`/cart/cart/${userId}`),

  updateCart: (userId, productId, quantity) =>
    apiRequest(`/cart/cart/${userId}/items/${productId}`, {
      method: "PATCH",
      body: JSON.stringify({ quantity })
    }),

  removeCartItem: (userId, productId) =>
    apiRequest(`/cart/cart/${userId}/items/${productId}`, {
      method: "DELETE"
    }),

  checkout: (checkoutId) =>
    apiRequest("/orders/orders/checkout", {
      method: "POST",
      body: JSON.stringify({ checkout_id: checkoutId })
    }),

  orders: () =>
    apiRequest("/orders/orders/me"),

  recommendations: (budget, category, keyword) => {
    const params = new URLSearchParams({
      budget: String(budget)
    });

    if (category) params.set("category", category);
    if (keyword) params.set("keyword", keyword);

    return apiRequest(`/ai/recommendations?${params}`);
  }
};
