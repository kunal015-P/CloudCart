
import React, { useEffect, useMemo, useState } from "react";
import {
  ShoppingCart, Search, User, LogOut, Package,
  Sparkles, Plus, Minus, Trash2, X, Menu,
  ArrowRight, RefreshCw
} from "lucide-react";

import {
  api,
  getToken,
  getSavedUser,
  saveSession,
  clearSession
} from "./api.js";

const CATEGORIES = [
  "Gaming Accessories",
  "Goggles",
  "Watches",
  "Shoes"
];

const money = (amount) =>
  new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0
  }).format(Number(amount || 0));

function App() {
  const [user, setUser] = useState(getSavedUser());
  const [products, setProducts] = useState([]);
  const [cart, setCart] = useState({
    items: [],
    total_items: 0,
    total_amount: 0
  });

  const [orders, setOrders] = useState([]);
  const [activeCategory, setActiveCategory] = useState("All");
  const [search, setSearch] = useState("");
  const [budget, setBudget] = useState("5000");
  const [recommendations, setRecommendations] = useState([]);

  const [authOpen, setAuthOpen] = useState(false);
  const [authMode, setAuthMode] = useState("login");
  const [cartOpen, setCartOpen] = useState(false);
  const [ordersOpen, setOrdersOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const [authForm, setAuthForm] = useState({
    name: "",
    email: "",
    password: ""
  });

  const [checkoutBusy, setCheckoutBusy] = useState(false);

  const authenticated = Boolean(getToken() && user?.id);

  // -----------------------------------------------
  // Load products
  // -----------------------------------------------

  async function loadProducts() {
    try {
      const result = await api.products(search);
      setProducts(result);
    } catch (err) {
      setError(err.message);
    }
  }

  // -----------------------------------------------
  // Load customer cart
  // -----------------------------------------------

  async function loadCart() {
    if (!authenticated) return;

    try {
      const result = await api.getCart(user.id);
      setCart(result);
    } catch (err) {
      setError(err.message);
    }
  }

  // -----------------------------------------------
  // Load order history
  // -----------------------------------------------

  async function loadOrders() {
    if (!authenticated) return;

    try {
      const result = await api.orders();
      setOrders(result);
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    loadProducts();
  }, [search]);

  useEffect(() => {
    loadCart();
  }, [user?.id]);

  // -----------------------------------------------
  // Authentication
  // -----------------------------------------------

  async function handleAuth(event) {
    event.preventDefault();
    setError("");
    setMessage("");
    setLoading(true);

    try {
      if (authMode === "register") {
        await api.register(authForm);

        setMessage("Registration successful. Please log in.");
        setAuthMode("login");
        setAuthForm({
          name: "",
          email: authForm.email,
          password: ""
        });
      } else {
        const result = await api.login({
          email: authForm.email,
          password: authForm.password
        });

        saveSession(result);
        setUser(result.user);
        setAuthOpen(false);
        setAuthForm({
          name: "",
          email: "",
          password: ""
        });

        setMessage(`Welcome to CloudCart, ${result.user.name}!`);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function logout() {
    clearSession();
    setUser(null);
    setCart({
      items: [],
      total_items: 0,
      total_amount: 0
    });
    setOrders([]);
    setCartOpen(false);
    setOrdersOpen(false);
    setMessage("You have been logged out.");
  }

  // -----------------------------------------------
  // Add to cart
  // -----------------------------------------------

  async function addToCart(product) {
    if (!authenticated) {
      setAuthOpen(true);
      setAuthMode("login");
      setMessage("Please log in to add products to your cart.");
      return;
    }

    setError("");

    try {
      await api.addToCart(user.id, product.id, 1);
      await loadCart();
      setMessage(`${product.name} added to cart.`);
    } catch (err) {
      setError(err.message);
    }
  }

  // -----------------------------------------------
  // Update cart quantity
  // -----------------------------------------------

  async function updateQuantity(item, quantity) {
    if (quantity < 1) return;

    try {
      await api.updateCart(
        user.id,
        item.product_id,
        quantity
      );

      await loadCart();
    } catch (err) {
      setError(err.message);
    }
  }

  // -----------------------------------------------
  // Remove cart item
  // -----------------------------------------------

  async function removeItem(item) {
    try {
      await api.removeCartItem(
        user.id,
        item.product_id
      );

      await loadCart();
      setMessage("Product removed from cart.");
    } catch (err) {
      setError(err.message);
    }
  }

  // -----------------------------------------------
  // Checkout
  // -----------------------------------------------

  async function checkout() {
    if (!authenticated || !cart.items.length) return;

    setCheckoutBusy(true);
    setError("");

    try {
      const checkoutId = crypto.randomUUID();

      const result = await api.checkout(checkoutId);

      setMessage(
        `Order #${result.order.id} placed successfully! Payment was simulated.`
      );

      await Promise.all([
        loadCart(),
        loadOrders(),
        loadProducts()
      ]);

      setCartOpen(false);
      setOrdersOpen(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setCheckoutBusy(false);
    }
  }

  // -----------------------------------------------
  // AI recommendations
  // -----------------------------------------------

  async function getRecommendations() {
    setLoading(true);
    setError("");

    try {
      const result = await api.recommendations(
        budget,
        activeCategory === "All" ? "" : activeCategory,
        search
      );

      setRecommendations(result.recommendations || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  // -----------------------------------------------
  // Product filtering
  // -----------------------------------------------

  const visibleProducts = useMemo(() => {
    return products.filter(product => {
      return activeCategory === "All" ||
        product.category === activeCategory;
    });
  }, [products, activeCategory]);

  const groupedProducts = useMemo(() => {
    return CATEGORIES.map(category => ({
      category,
      items: visibleProducts.filter(
        product => product.category === category
      )
    })).filter(group => group.items.length > 0);
  }, [visibleProducts]);

  // -----------------------------------------------
  // Reusable product card
  // -----------------------------------------------

  function ProductCard({ product }) {
    const [imageError, setImageError] = useState(false);

    const outOfStock = Number(product.stock) <= 0;

    return (
      <article className="product-card">
        <div className="product-image-box">
          {product.image_url && !imageError ? (
            <img
              src={product.image_url}
              alt={product.name}
              loading="lazy"
              onError={() => setImageError(true)}
            />
          ) : (
            <div className="image-fallback">
              <Package size={36} />
              <span>Image unavailable</span>
            </div>
          )}

          <span className="category-label">
            {product.category}
          </span>
        </div>

        <div className="product-details">
          <h3>{product.name}</h3>

          <p className="product-description">
            {product.description}
          </p>

          <div className="price-row">
            <strong>{money(product.price)}</strong>

            <span className={outOfStock ? "out-stock" : "in-stock"}>
              {outOfStock ? "Out of stock" : `${product.stock} available`}
            </span>
          </div>

          <button
            className="primary-button full-button"
            disabled={outOfStock}
            onClick={() => addToCart(product)}
          >
            <ShoppingCart size={17} />
            Add to Cart
          </button>
        </div>
      </article>
    );
  }

  // -----------------------------------------------
  // Main UI
  // -----------------------------------------------

  return (
    <div className="app">

      {/* Header */}

      <header className="site-header">
        <a href="#" className="brand">
          <span className="brand-icon">C</span>
          <span>CloudCart</span>
        </a>

        <nav className={menuOpen ? "nav-links open" : "nav-links"}>
          <a href="#home" onClick={() => setMenuOpen(false)}>Home</a>
          <a href="#catalogue" onClick={() => setMenuOpen(false)}>Shop</a>
          <a href="#ai" onClick={() => setMenuOpen(false)}>AI Assistant</a>
        </nav>

        <div className="header-actions">
          {authenticated ? (
            <>
              <button
                className="icon-button"
                title="Order history"
                onClick={() => {
                  loadOrders();
                  setOrdersOpen(true);
                }}
              >
                <Package />
              </button>

              <button
                className="icon-button cart-button"
                title="Shopping cart"
                onClick={() => setCartOpen(true)}
              >
                <ShoppingCart />
                <span className="cart-count">
                  {cart.total_items || 0}
                </span>
              </button>

              <span className="welcome-user">
                Hi, {user.name}
              </span>

              <button
                className="icon-button"
                title="Logout"
                onClick={logout}
              >
                <LogOut />
              </button>
            </>
          ) : (
            <button
              className="primary-button"
              onClick={() => {
                setAuthMode("login");
                setAuthOpen(true);
              }}
            >
              <User size={17} /> Login
            </button>
          )}

          <button
            className="icon-button mobile-menu"
            onClick={() => setMenuOpen(!menuOpen)}
            aria-label="Toggle navigation"
          >
            <Menu />
          </button>
        </div>
      </header>

      {/* Notifications */}

      {(message || error) && (
        <div className={error ? "notice error" : "notice success"}>
          <span>{error || message}</span>
          <button
            onClick={() => {
              setMessage("");
              setError("");
            }}
          >
            <X size={17} />
          </button>
        </div>
      )}

      {/* Hero */}

      <section className="hero" id="home">
        <div className="hero-content">
          <span className="hero-tag">
            YOUR SMART SHOPPING DESTINATION
          </span>

          <h1>
            Shop Better.<br />
            <span>Live Smarter.</span>
          </h1>

          <p>
            Explore gaming accessories, stylish watches,
            shoes and eyewear — all in one place.
          </p>

          <a href="#catalogue" className="hero-button">
            Explore Products <ArrowRight size={18} />
          </a>
        </div>

        <div className="hero-art">
          <div className="hero-circle">
            <ShoppingCart size={110} />
          </div>
          <span className="hero-floating">Smart shopping</span>
        </div>
      </section>

      {/* Category navigation */}

      <section className="category-section">
        <div className="section-heading">
          <div>
            <span className="eyebrow">EXPLORE COLLECTIONS</span>
            <h2>Shop by Category</h2>
          </div>
        </div>

        <div className="category-list">
          {[
            { name: "All", emoji: "🛍️" },
            { name: "Gaming Accessories", emoji: "🎮" },
            { name: "Goggles", emoji: "🕶️" },
            { name: "Watches", emoji: "⌚" },
            { name: "Shoes", emoji: "👟" }
          ].map(category => (
            <button
              key={category.name}
              className={
                activeCategory === category.name
                  ? "category-chip active"
                  : "category-chip"
              }
              onClick={() => {
                setActiveCategory(category.name);
                setRecommendations([]);
              }}
            >
              <span>{category.emoji}</span>
              {category.name}
            </button>
          ))}
        </div>
      </section>

      {/* Product catalogue */}

      <main id="catalogue" className="catalogue">
        <div className="section-heading">
          <div>
            <span className="eyebrow">OUR COLLECTION</span>
            <h2>
              {activeCategory === "All"
                ? "Discover Products"
                : activeCategory}
            </h2>
          </div>

          <div className="search-box">
            <Search size={18} />
            <input
              type="search"
              placeholder="Search products..."
              value={search}
              onChange={event => setSearch(event.target.value)}
            />
          </div>
        </div>

        {groupedProducts.map(group => (
          <section className="product-section" key={group.category}>
            <div className="product-section-title">
              <h3>{group.category}</h3>
              <span>{group.items.length} products</span>
            </div>

            <div className="product-grid">
              {group.items.map(product => (
                <ProductCard
                  key={product.id}
                  product={product}
                />
              ))}
            </div>
          </section>
        ))}

        {visibleProducts.length === 0 && (
          <div className="empty-state">
            <Package size={42} />
            <h3>No products found</h3>
            <p>Try another search or category.</p>
          </div>
        )}
      </main>

      {/* AI recommendations */}

      <section className="ai-section" id="ai">
        <div className="ai-heading">
          <span className="ai-icon">
            <Sparkles />
          </span>

          <div>
            <span className="eyebrow">CLOUDCART SMART ASSISTANT</span>
            <h2>Find Products Within Your Budget</h2>
            <p>
              Tell us your budget and we'll suggest suitable products.
            </p>
          </div>
        </div>

        <div className="ai-controls">
          <label>
            Your budget (₹)
            <input
              type="number"
              min="1"
              value={budget}
              onChange={event => setBudget(event.target.value)}
            />
          </label>

          <button
            className="primary-button"
            disabled={loading || !Number(budget) || Number(budget) <= 0}
            onClick={getRecommendations}
          >
            <Sparkles size={17} />
            {loading ? "Finding products..." : "Get Recommendations"}
          </button>
        </div>

        {recommendations.length > 0 && (
          <div className="recommendation-grid">
            {recommendations.map(product => (
              <div className="recommendation-card" key={product.id}>
                <img
                  src={product.image_url}
                  alt={product.name}
                  loading="lazy"
                />

                <div>
                  <h3>{product.name}</h3>
                  <strong>{money(product.price)}</strong>
                  <p>{product.reasons?.join(" · ")}</p>
                  <button
                    className="primary-button"
                    onClick={() => addToCart(product)}
                  >
                    Add to Cart
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Cart drawer */}

      {cartOpen && (
        <div className="overlay" onClick={() => setCartOpen(false)}>
          <aside className="drawer" onClick={e => e.stopPropagation()}>
            <div className="drawer-heading">
              <h2>Your Shopping Cart</h2>
              <button className="icon-button" onClick={() => setCartOpen(false)}>
                <X />
              </button>
            </div>

            {cart.items.length === 0 ? (
              <div className="empty-state">
                <ShoppingCart size={42} />
                <h3>Your cart is empty</h3>
                <p>Explore products and add your favourites.</p>
              </div>
            ) : (
              <>
                <div className="cart-items">
                  {cart.items.map(item => (
                    <div className="cart-item" key={item.product_id}>
                      <img src={item.image_url} alt={item.name} />

                      <div className="cart-item-details">
                        <h3>{item.name}</h3>
                        <strong>{money(item.price)}</strong>

                        <div className="quantity-controls">
                          <button
                            onClick={() => updateQuantity(
                              item,
                              item.quantity - 1
                            )}
                            disabled={item.quantity <= 1}
                          >
                            <Minus size={14} />
                          </button>

                          <span>{item.quantity}</span>

                          <button
                            onClick={() => updateQuantity(
                              item,
                              item.quantity + 1
                            )}
                            disabled={item.quantity >= item.stock}
                          >
                            <Plus size={14} />
                          </button>

                          <button
                            className="remove-button"
                            onClick={() => removeItem(item)}
                          >
                            <Trash2 size={15} />
                          </button>
                        </div>
                      </div>

                      <strong>{money(item.subtotal)}</strong>
                    </div>
                  ))}
                </div>

                <div className="cart-total">
                  <span>Subtotal</span>
                  <strong>{money(cart.total_amount)}</strong>
                </div>

                <p className="payment-note">
                  Demo checkout only. No real payment is collected.
                </p>

                <button
                  className="primary-button full-button"
                  disabled={checkoutBusy}
                  onClick={checkout}
                >
                  {checkoutBusy ? "Processing..." : "Place Order"}
                </button>
              </>
            )}
          </aside>
        </div>
      )}

      {/* Order history */}

      {ordersOpen && (
        <div className="overlay" onClick={() => setOrdersOpen(false)}>
          <aside className="drawer" onClick={e => e.stopPropagation()}>
            <div className="drawer-heading">
              <h2>My Orders</h2>
              <button className="icon-button" onClick={() => setOrdersOpen(false)}>
                <X />
              </button>
            </div>

            {orders.length === 0 ? (
              <div className="empty-state">
                <Package size={42} />
                <h3>No orders yet</h3>
                <p>Your placed orders will appear here.</p>
              </div>
            ) : (
              orders.map(order => (
                <div className="order-card" key={order.id}>
                  <div className="order-header">
                    <strong>Order #{order.id}</strong>
                    <span className="order-status">
                      {order.order_status}
                    </span>
                  </div>

                  <p>{new Date(order.created_at).toLocaleString("en-IN")}</p>

                  {order.items.map(item => (
                    <div key={item.product_id} className="order-line">
                      <span>
                        {item.product_name} × {item.quantity}
                      </span>
                      <strong>{money(item.subtotal)}</strong>
                    </div>
                  ))}

                  <div className="order-total">
                    Total: {money(order.total_amount)}
                  </div>

                  <p className="payment-note">
                    Payment: {order.payment_status}
                  </p>
                </div>
              ))
            )}
          </aside>
        </div>
      )}

      {/* Authentication modal */}

      {authOpen && (
        <div className="overlay" onClick={() => setAuthOpen(false)}>
          <div className="auth-modal" onClick={e => e.stopPropagation()}>
            <div className="drawer-heading">
              <h2>
                {authMode === "login" ? "Welcome Back" : "Create Account"}
              </h2>
              <button className="icon-button" onClick={() => setAuthOpen(false)}>
                <X />
              </button>
            </div>

            <p className="auth-description">
              {authMode === "login"
                ? "Log in to continue shopping."
                : "Create your CloudCart customer account."}
            </p>

            <form onSubmit={handleAuth}>
              {authMode === "register" && (
                <label>
                  Full Name
                  <input
                    required
                    minLength="2"
                    value={authForm.name}
                    onChange={e => setAuthForm({
                      ...authForm,
                      name: e.target.value
                    })}
                    placeholder="Your name"
                  />
                </label>
              )}

              <label>
                Email Address
                <input
                  type="email"
                  required
                  value={authForm.email}
                  onChange={e => setAuthForm({
                    ...authForm,
                    email: e.target.value
                  })}
                  placeholder="you@example.com"
                />
              </label>

              <label>
                Password
                <input
                  type="password"
                  required
                  minLength="8"
                  maxLength="72"
                  value={authForm.password}
                  onChange={e => setAuthForm({
                    ...authForm,
                    password: e.target.value
                  })}
                  placeholder="At least 8 characters"
                />
              </label>

              <button
                className="primary-button full-button"
                type="submit"
                disabled={loading}
              >
                {loading
                  ? "Please wait..."
                  : authMode === "login"
                    ? "Login"
                    : "Create Account"}
              </button>
            </form>

            <p className="auth-switch">
              {authMode === "login"
                ? "Don't have an account?"
                : "Already have an account?"}

              <button
                onClick={() => setAuthMode(
                  authMode === "login" ? "register" : "login"
                )}
              >
                {authMode === "login" ? "Register" : "Login"}
              </button>
            </p>
          </div>
        </div>
      )}

      {/* Footer */}

      <footer className="site-footer">
        <div className="brand">
          <span className="brand-icon">C</span>
          <span>CloudCart</span>
        </div>

        <p>
          Your smart shopping destination.
        </p>

        <small>
          CloudCart portfolio project · Demo payment only
        </small>
      </footer>
    </div>
  );
}

export default App;
