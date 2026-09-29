const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers: {
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...options.headers,
      },
    });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new Error("We couldn't reach the support service. Check that it's running and try again.");
  }

  if (!response.ok) {
    const detail = await response.text();
    let message = detail;
    try {
      const payload = JSON.parse(detail);
      message = payload?.detail || payload?.message || payload?.error || "";
    } catch {
      if (/failed to fetch/i.test(detail)) message = "";
    }
    throw new Error(message || `The support service couldn't complete that request (HTTP ${response.status}). Please try again.`);
  }

  if (response.status === 204) return null;
  return response.json();
}

export function sendChat({ customer_id, message }, { signal } = {}) {
  return request("/chat", {
    method: "POST",
    body: JSON.stringify({ customer_id, message }),
    signal,
  });
}

export function getCustomerMemories(customer_id, { signal } = {}) {
  return request(`/customers/${encodeURIComponent(customer_id)}/memories`, { signal });
}

export function createTicket({ customer_id, subject }) {
  return request("/tickets", {
    method: "POST",
    body: JSON.stringify({ customer_id, subject }),
  });
}

export function updateTicket(ticket_id, status) {
  return request(`/tickets/${encodeURIComponent(ticket_id)}`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
}