import { useEffect, useState } from "react";

async function api(path, { method = "GET", body, token } = {}) {
  const res = await fetch(path, {
    method,
    headers: {
      ...(body ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(typeof data.detail === "string" ? data.detail : "Invalid input");
  }
  return data;
}

function roleFromToken(t) {
  try {
    const b64 = t.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(atob(b64)).role || "user";
  } catch {
    return "user";
  }
}

export default function App() {
  const [token, setToken] = useState(sessionStorage.getItem("token") || "");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [books, setBooks] = useState([]);
  const [orders, setOrders] = useState([]);
  const [qty, setQty] = useState({});
  const [newBook, setNewBook] = useState({ title: "", author: "", price: "" });
  const [msg, setMsg] = useState({ text: "", error: false });

  const say = (text, error = false) => setMsg({ text, error });
  const isAdmin = Boolean(token) && roleFromToken(token) === "admin";

  const loadBooks = () =>
    api("/api/books").then(setBooks).catch((e) => say(e.message, true));

  const loadOrders = () =>
    token
      ? api("/api/orders", { token }).then(setOrders).catch((e) => say(e.message, true))
      : setOrders([]);

  useEffect(() => { loadBooks(); }, []);
  useEffect(() => { loadOrders(); }, [token]);

  const register = async () => {
    try {
      await api("/api/users/register", { method: "POST", body: { email, password } });
      say("Registered. Now click Login.");
    } catch (e) { say(e.message, true); }
  };

  const login = async () => {
    try {
      const data = await api("/api/users/login", { method: "POST", body: { email, password } });
      sessionStorage.setItem("token", data.access_token);
      setToken(data.access_token);
      setPassword("");
      say("Logged in.");
    } catch (e) { say(e.message, true); }
  };

  const logout = () => {
    sessionStorage.removeItem("token");
    setToken("");
    say("Logged out.");
  };

  const order = async (book) => {
    try {
      const quantity = Number(qty[book.id] || 1);
      const o = await api("/api/orders", { method: "POST", token, body: { book_id: book.id, quantity } });
      say(`Ordered ${o.quantity} x ${o.book_title}. Total: Rs ${o.total_price}`);
      loadOrders();
    } catch (e) { say(e.message, true); }
  };

  const addBook = async () => {
    try {
      await api("/api/books", {
        method: "POST", token,
        body: { title: newBook.title, author: newBook.author, price: Number(newBook.price) },
      });
      setNewBook({ title: "", author: "", price: "" });
      say("Book added.");
      loadBooks();
    } catch (e) { say(e.message, true); }
  };

  const deleteBook = async (id) => {
    try {
      await api(`/api/books/${id}`, { method: "DELETE", token });
      say("Book deleted.");
      loadBooks();
    } catch (e) { say(e.message, true); }
  };

  return (
    <div>
      <h1>Mini Bookstore</h1>
      {msg.text && <div className={`msg ${msg.error ? "err" : ""}`}>{msg.text}</div>}

      <section>
        {token ? (
          <button onClick={logout}>Logout</button>
        ) : (
          <>
            <input placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} />
            <input type="password" placeholder="Password (min 8)" value={password}
                   onChange={(e) => setPassword(e.target.value)} />
            <button onClick={login}>Login</button>
            <button onClick={register}>Register</button>
          </>
        )}
      </section>

      <section>
        <h2>Books</h2>
        <table>
          <thead>
            <tr><th>Title</th><th>Author</th><th>Price</th><th></th></tr>
          </thead>
          <tbody>
            {books.map((b) => (
              <tr key={b.id}>
                <td>{b.title}</td>
                <td>{b.author}</td>
                <td>Rs {b.price}</td>
                <td>
                  {token ? (
                    <>
                      <input type="number" min="1" max="100" style={{ width: 50 }}
                             value={qty[b.id] || 1}
                             onChange={(e) => setQty({ ...qty, [b.id]: e.target.value })} />
                      <button onClick={() => order(b)}>Order</button>
                      {isAdmin && <button onClick={() => deleteBook(b.id)}>Delete</button>}
                    </>
                  ) : (
                    "Login to order"
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {isAdmin && (
          <div style={{ marginTop: 12 }}>
            <input placeholder="Title" value={newBook.title}
                   onChange={(e) => setNewBook({ ...newBook, title: e.target.value })} />
            <input placeholder="Author" value={newBook.author}
                   onChange={(e) => setNewBook({ ...newBook, author: e.target.value })} />
            <input placeholder="Price" type="number" style={{ width: 80 }} value={newBook.price}
                   onChange={(e) => setNewBook({ ...newBook, price: e.target.value })} />
            <button onClick={addBook}>Add book</button>
          </div>
        )}
      </section>

      {token && (
        <section>
          <h2>My orders</h2>
          {orders.length === 0 ? (
            <p>No orders yet.</p>
          ) : (
            <table>
              <thead>
                <tr><th>#</th><th>Book</th><th>Qty</th><th>Total</th><th>Time (UTC)</th></tr>
              </thead>
              <tbody>
                {orders.map((o) => (
                  <tr key={o.id}>
                    <td>{o.id}</td><td>{o.book_title}</td><td>{o.quantity}</td>
                    <td>Rs {o.total_price}</td><td>{o.created_at}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      )}
    </div>
  );
}
