import * as React from "react";
import { useEffect, useRef, useState } from "react";
import {
  Activity,
  ArrowDownLeft,
  ArrowUpRight,
  BrainCircuit,
  Check,
  ChevronDown,
  CircleAlert,
  Clock3,
  Headphones,
  LifeBuoy,
  LoaderCircle,
  Mail,
  MessageCircleMore,
  Plus,
  Send,
  ShieldCheck,
  Sparkles,
  TicketCheck,
  TicketPlus,
  UserRound,
  X,
} from "lucide-react";
import { createTicket, getCustomerMemories, sendChat, updateTicket } from "./api";

const STATUSES = ["open", "in_progress", "resolved", "escalated"];
const MEMORY_DEMO_STEPS = [
  { title: "A new issue arrives", detail: "A customer reports that a payment failed again." },
  { title: "The issue is resolved", detail: "Clearing the payment session fixes the illustrative issue." },
  { title: "Useful context is retained", detail: "The successful troubleshooting becomes persistent customer memory." },
  { title: "The customer returns", detail: "Later, the customer reports another payment failure." },
  { title: "Hindsight recalls the context", detail: "The prior issue and fix are brought back into the support response." },
  { title: "Support starts with what worked", detail: "The agent gives a personalized next step instead of starting over." },
];

function getMemoryItems(payload) {
  const items = Array.isArray(payload) ? payload : payload?.memories;
  if (!Array.isArray(items)) return [];

  return items.filter((item) => {
    if (!item || typeof item !== "object") return false;
    const kind = `${item.type || ""} ${item.kind || ""} ${item.source || ""}`.toLowerCase();
    return !kind.includes("transcript") && !kind.includes("conversation");
  });
}

function memoryText(memory) {
  return memory.content || memory.memory || memory.summary || memory.description || memory.text || "";
}

function memoryOutcome(memory) {
  return memory?.successful_solution || memory?.solution || memory?.resolution || memory?.outcome || "";
}

function memoryRelevanceReason(memory) {
  return typeof memory?.relevance_reason === "string" ? memory.relevance_reason.trim() : "";
}

function formatDate(value) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? String(value)
    : new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date);
}

function statusLabel(status) {
  return (status || "open").replaceAll("_", " ");
}

function App() {
  const [appStage, setAppStage] = useState("splash");
  const [authMode, setAuthMode] = useState("login");
  const [authForm, setAuthForm] = useState({ name: "", email: "", password: "" });
  const [authError, setAuthError] = useState("");
  const [demoAccounts, setDemoAccounts] = useState([]);
  const [authUser, setAuthUser] = useState(null);
  const [showProfileMenu, setShowProfileMenu] = useState(false);
  const [showAccountProfile, setShowAccountProfile] = useState(false);
  const [editingAccountProfile, setEditingAccountProfile] = useState(false);
  const [accountProfileForm, setAccountProfileForm] = useState({ name: "", email: "" });
  const [accountProfileError, setAccountProfileError] = useState("");
  const [customers, setCustomers] = useState([]);
  const [customerId, setCustomerId] = useState("");
  const [customerInput, setCustomerInput] = useState("");
  const [memories, setMemories] = useState([]);
  const [memoryLoading, setMemoryLoading] = useState(false);
  const [memoryError, setMemoryError] = useState("");
  const [memoryRetry, setMemoryRetry] = useState(0);
  const [messages, setMessages] = useState([]);
  const [messageInput, setMessageInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [chatError, setChatError] = useState("");
  const [tickets, setTickets] = useState([]);
  const [ticketSubject, setTicketSubject] = useState("");
  const [ticketLoading, setTicketLoading] = useState(false);
  const [ticketError, setTicketError] = useState("");
  const [updatingTicketId, setUpdatingTicketId] = useState("");
  const [demoMode, setDemoMode] = useState("hindsight");
  const [demoExpanded, setDemoExpanded] = useState(true);
  const [demoRunning, setDemoRunning] = useState(false);
  const [demoStep, setDemoStep] = useState(-1);
  const [showEscalation, setShowEscalation] = useState(false);
  const messageEndRef = useRef(null);

  useEffect(() => {
    const splashTimer = window.setTimeout(() => setAppStage("auth"), 2500);
    return () => window.clearTimeout(splashTimer);
  }, []);

  useEffect(() => {
    if (!customerId) {
      setMemories([]);
      setMemoryError("");
      setMemoryLoading(false);
      return undefined;
    }

    const controller = new AbortController();
    setMemoryLoading(true);
    setMemoryError("");
    setMemories([]);

    getCustomerMemories(customerId, { signal: controller.signal })
      .then((payload) => setMemories(getMemoryItems(payload)))
      .catch((error) => {
        if (error.name !== "AbortError") setMemoryError(error.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setMemoryLoading(false);
      });

    return () => controller.abort();
  }, [customerId, memoryRetry]);

  useEffect(() => {
    messageEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, chatLoading]);

  useEffect(() => {
    if (!demoRunning) return undefined;
    const timer = window.setTimeout(() => {
      if (demoStep >= MEMORY_DEMO_STEPS.length - 1) {
        setDemoRunning(false);
      } else {
        setDemoStep((current) => current + 1);
      }
    }, 900);
    return () => window.clearTimeout(timer);
  }, [demoRunning, demoStep]);

  const activeTicket = tickets.find((ticket) => ["open", "in_progress"].includes(ticket.status));
  const latestCustomerMessage = [...messages].reverse().find((message) => message.role === "customer");
  const latestAgentMessage = [...messages].reverse().find((message) => message.role === "agent");
  const summaryMemory = latestAgentMessage?.memories?.[0] || memories[0];
  const previousSolution = memoryOutcome(summaryMemory);
  const previousContext = summaryMemory
    ? summaryMemory.previous_issue || summaryMemory.issue || memoryText(summaryMemory)
    : "No prior memory returned for this customer.";
  const timelineMemories = [...memories].sort((left, right) => {
    const leftDate = Date.parse(left.created_at || "");
    const rightDate = Date.parse(right.created_at || "");
    if (!Number.isFinite(leftDate)) return Number.isFinite(rightDate) ? 1 : 0;
    if (!Number.isFinite(rightDate)) return -1;
    return leftDate - rightDate;
  });
  const suggestedNextAction = latestAgentMessage?.suggested_next_action || "Not provided by the current API response.";
  const selectedCustomer = customers.find((customer) => customer.customer_id === customerId);
  const displayName = selectedCustomer?.name || (customerId ? "Profile unavailable" : "No customer selected");
  const conversationStatus = !customerId
    ? "SELECT A CUSTOMER"
    : chatLoading
    ? "AI RESPONDING"
    : chatError
      ? "NEEDS ATTENTION"
      : messages.length > 0
        ? "IN CONVERSATION"
        : "READY TO START";

  function registerDemoAccount(event) {
    event.preventDefault();
    const account = {
      name: authForm.name.trim(),
      email: authForm.email.trim().toLowerCase(),
      password: authForm.password,
    };

    if (!account.name || !account.email || !account.password) {
      setAuthError("Enter your name, email, and password to continue.");
      return;
    }
    if (demoAccounts.some((item) => item.email === account.email)) {
      setAuthError("An account with this email already exists in this demo session. Sign in instead.");
      return;
    }

    const customer_id = `SESSION-${globalThis.crypto?.randomUUID?.() || Date.now().toString(36)}`.toUpperCase();
    const profile = { name: account.name, email: account.email, customer_id };
    setDemoAccounts((current) => [...current, { ...account, customer: profile }]);
    setCustomers((current) => [...current, profile]);
    setAuthUser(profile);
    setCustomerId(customer_id);
    setCustomerInput(customer_id);
    setAuthForm({ name: "", email: "", password: "" });
    setAuthError("");
    setMessages([]);
    setTickets([]);
    setAppStage("hub");
  }

  function loginDemoAccount(event) {
    event.preventDefault();
    const email = authForm.email.trim().toLowerCase();
    const account = demoAccounts.find((item) => item.email === email && item.password === authForm.password);
    if (!account) {
      setAuthError("No matching account exists in this demo session. Register first; demo accounts are cleared when the page reloads.");
      return;
    }

    setAuthUser(account.customer);
    setCustomerId(account.customer.customer_id);
    setCustomerInput(account.customer.customer_id);
    setAuthForm({ name: "", email: "", password: "" });
    setAuthError("");
    setMessages([]);
    setTickets([]);
    setAppStage("hub");
  }

  function signOutDemoAccount() {
    setShowProfileMenu(false);
    setShowAccountProfile(false);
    setEditingAccountProfile(false);
    setAuthUser(null);
    setAuthMode("login");
    setAuthForm({ name: "", email: "", password: "" });
    setAuthError("");
    setAppStage("auth");
  }

  function openAccountProfile(edit = false) {
    setAccountProfileForm({ name: authUser.name, email: authUser.email });
    setAccountProfileError("");
    setEditingAccountProfile(edit);
    setShowProfileMenu(false);
    setShowAccountProfile(true);
  }

  function saveAccountProfile(event) {
    event.preventDefault();
    const updatedUser = {
      ...authUser,
      name: accountProfileForm.name.trim(),
      email: accountProfileForm.email.trim().toLowerCase(),
    };

    if (!updatedUser.name || !updatedUser.email) {
      setAccountProfileError("Enter both a name and a valid email address.");
      return;
    }

    const emailInUse = demoAccounts.some((account) =>
      account.email === updatedUser.email && account.customer.customer_id !== authUser.customer_id,
    );
    if (emailInUse) {
      setAccountProfileError("That email is already used by another demo account.");
      return;
    }

    setAuthUser(updatedUser);
    setCustomers((current) => current.map((customer) =>
      customer.customer_id === updatedUser.customer_id ? updatedUser : customer,
    ));
    setDemoAccounts((current) => current.map((account) =>
      account.customer.customer_id === updatedUser.customer_id
        ? { ...account, name: updatedUser.name, email: updatedUser.email, customer: updatedUser }
        : account,
    ));
    setAccountProfileError("");
    setEditingAccountProfile(false);
  }

  function loadCustomer(event) {
    event.preventDefault();
    const nextId = customerInput.trim();
    if (!nextId || nextId === customerId) return;
    setCustomerId(nextId);
    setMessages([]);
    setTickets([]);
    setChatError("");
    setTicketError("");
  }

  function runMemoryDemo() {
    setDemoExpanded(true);
    setDemoStep(0);
    setDemoRunning(true);
  }

  async function submitMessage(event) {
    event.preventDefault();
    const message = messageInput.trim();
    if (!customerId || !message || chatLoading) return;

    setMessages((current) => [...current, { role: "customer", content: message }]);
    setMessageInput("");
    setChatError("");
    setChatLoading(true);

    try {
      const result = await sendChat({ customer_id: customerId, message });
      const response = typeof result?.response === "string" ? result.response : "The agent returned no response.";
      setMessages((current) => [
        ...current,
        {
          role: "agent",
          content: response,
          conversation_id: result?.conversation_id,
          memories: getMemoryItems(result?.memories),
          status: result?.status,
          created_at: result?.created_at,
          suggested_next_action: typeof result?.suggested_next_action === "string" ? result.suggested_next_action : "",
        },
      ]);
    } catch (error) {
      setChatError(error.message);
    } finally {
      setChatLoading(false);
    }
  }

  async function submitTicket(event) {
    event.preventDefault();
    const subject = ticketSubject.trim();
    if (!customerId || !subject || ticketLoading) return;

    setTicketLoading(true);
    setTicketError("");
    try {
      const result = await createTicket({ customer_id: customerId, subject });
      const ticket = result?.ticket || result;
      setTickets((current) => [
        {
          ticket_id: ticket?.ticket_id || "",
          customer_id: ticket?.customer_id || customerId,
          subject: ticket?.subject || subject,
          status: ticket?.status || "open",
          created_at: ticket?.created_at || "",
        },
        ...current,
      ]);
      setTicketSubject("");
    } catch (error) {
      setTicketError(error.message);
    } finally {
      setTicketLoading(false);
    }
  }

  async function changeTicketStatus(ticket, status) {
    if (!ticket.ticket_id || updatingTicketId) return;
    setUpdatingTicketId(ticket.ticket_id);
    setTicketError("");
    try {
      const result = await updateTicket(ticket.ticket_id, status);
      const updated = result?.ticket || result;
      setTickets((current) =>
        current.map((item) =>
          item.ticket_id === ticket.ticket_id
            ? { ...item, status: updated?.status || status, created_at: updated?.created_at || item.created_at }
            : item,
        ),
      );
    } catch (error) {
      setTicketError(error.message);
    } finally {
      setUpdatingTicketId("");
    }
  }

  function renderMemory(memory, index) {
    const text = memoryText(memory);
    if (!text) return null;
    const relevanceReason = memoryRelevanceReason(memory);
    const outcome = memoryOutcome(memory);
    return (
      <article className="memory-item memory-timeline-item" key={memory.id || memory.memory_id || `${text}-${index}`}>
        <span className="memory-timeline-marker"><BrainCircuit size={14} /></span>
        <div className="memory-copy">
          <p>{text}</p>
          <div className="memory-meta">
            {memory.category && <span>{memory.category}</span>}
            {memory.created_at && <time>{formatDate(memory.created_at)}</time>}
          </div>
          {relevanceReason && <p className="memory-relevance"><strong>Relevant because</strong> {relevanceReason}</p>}
          {outcome && <p className="memory-outcome"><strong>Recorded outcome</strong> {outcome}</p>}
        </div>
      </article>
    );
  }

  if (appStage === "splash") {
    return (
      <main className="splash-screen" aria-label="Standford Support Hub loading">
        <div className="splash-brand-mark"><Headphones size={29} strokeWidth={2} /></div>
        <div className="splash-wordmark"><strong>standford</strong><span>SUPPORT HUB</span></div>
        <p>SUPPORT THAT REMEMBERS</p>
        <div className="splash-memory-line"><span /><BrainCircuit size={15} /><span /></div>
      </main>
    );
  }

  if (appStage === "auth") {
    return (
      <div className="entry-shell">
        <header className="entry-header">
          <a className="brand" href="#entry" aria-label="Standford Support Hub">
            <span className="brand-mark"><Headphones size={20} strokeWidth={2.2} /></span>
            <span className="brand-words"><strong>standford</strong><small>SUPPORT HUB</small></span>
          </a>
          <span className="demo-session-badge"><span /> HACKATHON DEMO</span>
        </header>
        <main id="entry" className="entry-layout">
          <section className="entry-story">
            <span className="entry-eyebrow"><BrainCircuit size={15} /> MEMORY-DRIVEN CUSTOMER SUPPORT</span>
            <h1>Not just a chatbot.<br />Support that remembers.</h1>
            <p>Hindsight carries useful customer context across conversations, so support can pick up where it left off.</p>
            <div className="entry-memory-proof">
              <span className="entry-proof-icon"><BrainCircuit size={20} /></span>
              <div><strong>Context that stays useful</strong><span>Previous issues · helpful solutions · customer preferences</span></div>
            </div>
          </section>
          <section className="auth-panel" aria-labelledby="auth-title">
            <div className="auth-tabs" role="group" aria-label="Account access">
              <button type="button" className={authMode === "login" ? "active" : ""} aria-pressed={authMode === "login"} onClick={() => { setAuthMode("login"); setAuthError(""); }}>Sign in</button>
              <button type="button" className={authMode === "register" ? "active" : ""} aria-pressed={authMode === "register"} onClick={() => { setAuthMode("register"); setAuthError(""); }}>Register</button>
            </div>
            <div className="auth-heading">
              <span className="section-overline">STANDFORD SUPPORT HUB</span>
              <h2 id="auth-title">{authMode === "register" ? "Create your profile" : "Welcome back"}</h2>
              <p>{authMode === "register" ? "Start a personalized support session." : "Sign in to continue to customer support."}</p>
            </div>
            <div className="auth-demo-notice"><ShieldCheck size={15} /><p>Demo access only. No authentication service is connected; accounts exist only until this page reloads.</p></div>
            <form className="auth-form" onSubmit={authMode === "register" ? registerDemoAccount : loginDemoAccount}>
              {authMode === "register" && <>
                <label htmlFor="auth-name">Name</label>
                <input id="auth-name" name="name" autoComplete="name" required value={authForm.name} onChange={(event) => setAuthForm((current) => ({ ...current, name: event.target.value }))} placeholder="Your full name" />
              </>}
              <label htmlFor="auth-email">Email</label>
              <input id="auth-email" name="email" type="email" autoComplete="email" required value={authForm.email} onChange={(event) => setAuthForm((current) => ({ ...current, email: event.target.value }))} placeholder="you@example.com" />
              <label htmlFor="auth-password">Password</label>
              <input id="auth-password" name="password" type="password" autoComplete={authMode === "register" ? "new-password" : "current-password"} required minLength="8" value={authForm.password} onChange={(event) => setAuthForm((current) => ({ ...current, password: event.target.value }))} placeholder="At least 8 characters" />
              {authError && <p className="auth-error" role="alert">{authError}</p>}
              <button className="auth-submit" type="submit">{authMode === "register" ? "Create demo account" : "Sign in to demo"}<ArrowUpRight size={16} /></button>
            </form>
            <p className="auth-mode-prompt">{authMode === "register" ? "Already have a demo account?" : "New to Standford Support Hub?"} <button type="button" onClick={() => { setAuthMode(authMode === "register" ? "login" : "register"); setAuthError(""); }}>{authMode === "register" ? "Sign in" : "Create an account"}</button></p>
          </section>
        </main>
        <footer className="entry-footer"><span>HINDSIGHT PERSISTENT MEMORY</span><span>Memory-driven customer support · Hack With Hyderabad 3.0</span></footer>
      </div>
    );
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="Standford Support Hub home">
          <span className="brand-mark"><Headphones size={20} strokeWidth={2.2} /></span>
          <span className="brand-words"><strong>standford</strong><small>SUPPORT HUB</small></span>
        </a>
        <div className="topbar-center"><span className="workspace-dot" /> Customer care workspace</div>
        <div className="topbar-right">
          <span className="topbar-date">Memory-driven support</span>
          {authUser && <div className="profile-menu-wrap">
            <span className="account-context-label">MY ACCOUNT</span>
            <button className="profile-trigger" type="button" aria-label={`Open profile menu for ${authUser.name}`} aria-expanded={showProfileMenu} onClick={() => setShowProfileMenu((open) => !open)}>
              <span className="agent-avatar" aria-hidden="true">{authUser.name.split(/\s+/).map((part) => part[0]).join("").slice(0, 2).toUpperCase()}</span>
              <span className="profile-trigger-name">{authUser.name}</span>
              <ChevronDown size={14} />
            </button>
            {showProfileMenu && <div className="profile-menu" role="menu" aria-label="Account menu">
              <div className="profile-menu-identity"><strong>{authUser.name}</strong><span>{authUser.email}</span></div>
              <button type="button" role="menuitem" onClick={() => openAccountProfile(false)}><UserRound size={15} /> View profile</button>
              <button type="button" role="menuitem" onClick={() => openAccountProfile(true)}><Activity size={15} /> Edit profile</button>
              <button type="button" role="menuitem" onClick={signOutDemoAccount}><ArrowDownLeft size={15} /> Log out</button>
            </div>}
          </div>}
        </div>
      </header>

      <main id="top" className="dashboard">
        <section className="page-heading">
          <div>
            <div className="eyebrow"><span className="eyebrow-line" /> AI CUSTOMER SUPPORT <span className="eyebrow-separator">/</span> HINDSIGHT MEMORY</div>
            <h1>Support that remembers<span>.</span></h1>
            <p>An AI support agent that carries relevant customer context from one conversation to the next.</p>
          </div>
          <div className="customer-actions">
            <form className="customer-switcher" onSubmit={loadCustomer}>
              <label htmlFor="customer-id"><UserRound size={16} /> SUPPORT CUSTOMER</label>
              <div className="customer-switcher-control">
                <input
                  id="customer-id"
                  list="registered-customers"
                  value={customerInput}
                  onChange={(event) => setCustomerInput(event.target.value)}
                  aria-label="Select or enter support customer ID"
                  placeholder="Search or enter customer ID"
                />
                <datalist id="registered-customers">
                  {customers.map((customer) => <option key={customer.customer_id} value={customer.customer_id} label={`${customer.name} · ${customer.email}`} />)}
                </datalist>
                <button type="submit" disabled={!customerInput.trim() || customerInput.trim() === customerId}>
                  Load <ChevronDown size={14} />
                </button>
              </div>
            </form>
          </div>
        </section>

        <section className={`demo-strip ${demoExpanded ? "" : "demo-collapsed"}`} aria-label="Before and after demonstration">
          <div className="demo-intro">
            <div className="demo-icon"><Sparkles size={17} /></div>
            <div><span className="demo-kicker">THE DIFFERENCE</span><strong>Same question. Better context.</strong></div>
          </div>
          {demoExpanded && (
            <div className="demo-content">
              <div className="demo-quote"><span>CUSTOMER</span><p>“My payment failed again.”</p></div>
              <div className={`demo-answer standard-answer ${demoMode === "standard" ? "demo-highlight" : ""}`}>
                <span>BEFORE · NO PERSISTENT MEMORY</span>
                <p>“Can you explain the issue?”</p>
              </div>
              <div className={`demo-answer memory-answer ${demoMode === "hindsight" ? "demo-highlight" : ""}`}>
                <span>AFTER · HINDSIGHT RECALL</span>
                <p>“Last time, clearing the payment session helped. Is the same issue happening again?”</p>
              </div>
            </div>
          )}
          {demoExpanded && <ol className="journey-flow" aria-label="Illustrative persistent-memory support journey">
            {MEMORY_DEMO_STEPS.map((step, index) => <li className={`journey-step ${demoStep === index ? "is-current" : demoStep > index ? "is-complete" : ""}`} aria-current={demoStep === index ? "step" : undefined} key={step.title}>
              <span>{demoStep > index ? <Check size={12} /> : String(index + 1).padStart(2, "0")}</span>
              <div><strong>{step.title}</strong>{demoRunning && demoStep === index && <small>{step.detail}</small>}</div>
            </li>)}
          </ol>}
          <div className="demo-actions">
            {demoExpanded && <button className="demo-run-button" type="button" onClick={runMemoryDemo} disabled={demoRunning} aria-label="Run illustrative memory demo">
              {demoRunning ? `Step ${demoStep + 1} of ${MEMORY_DEMO_STEPS.length}` : <><Activity size={14} /> Run memory demo</>}
            </button>}
            {demoExpanded && <div className="segmented-control" role="group" aria-label="Demo response">
              <button className={demoMode === "standard" ? "selected" : ""} aria-pressed={demoMode === "standard"} onClick={() => setDemoMode("standard")} type="button">Standard</button>
              <button className={demoMode === "hindsight" ? "selected" : ""} aria-pressed={demoMode === "hindsight"} onClick={() => setDemoMode("hindsight")} type="button">With memory</button>
            </div>}
            <button className="demo-toggle" type="button" onClick={() => setDemoExpanded((expanded) => !expanded)} aria-label={demoExpanded ? "Collapse demonstration" : "Expand demonstration"} aria-expanded={demoExpanded}>
              {demoExpanded ? <X size={16} /> : <Sparkles size={16} />}
            </button>
          </div>
          <p className="demo-note">Illustrative replies and flow · returned memories are shown separately</p>
        </section>

        <section className="profile-band" aria-label="Customer profile">
          <div className="profile-identity">
            <span className="profile-avatar"><UserRound size={21} /></span>
            <div><span className="section-overline">CURRENT SUPPORT CUSTOMER</span><h2>{displayName}</h2><small className="profile-origin">{selectedCustomer ? "Session-only profile · not saved to backend" : customerId ? "Profile details unavailable for this customer ID" : "Create a customer or enter an ID to begin"}</small></div>
          </div>
          <div className="profile-detail"><span>customer_id</span><strong>{customerId || "—"}</strong></div>
          <div className="profile-detail profile-email"><span>Email</span><strong><Mail size={14} /> {selectedCustomer?.email || "Not available"}</strong></div>
          <div className="profile-metrics" title="Historical counts are unavailable without a customer ticket-list endpoint">
            <div><strong>—</strong><span>Previous tickets</span><small>Not available</small></div>
            <div><strong>—</strong><span>Resolved</span><small>Not available</small></div>
            <div><strong>—</strong><span>Open</span><small>Not available</small></div>
          </div>
        </section>

        <div className="workspace-grid">
          <section className="primary-column">
            <section className="panel chat-panel">
              <div className="panel-heading chat-heading">
                <div className="panel-title-wrap">
                  <span className="panel-icon chat-icon"><MessageCircleMore size={18} /></span>
                  <div><h2>Live support</h2><p>Conversation with {displayName}</p></div>
                </div>
                <span className={`session-label ${chatError ? "session-error" : chatLoading ? "session-working" : ""}`} aria-live="polite"><span /> {conversationStatus}</span>
              </div>

              <div className="chat-messages" aria-live="polite">
                {messages.length === 0 && (
                  <div className="chat-empty">
                    <div className="empty-orbit"><MessageCircleMore size={23} /></div>
                    <strong>Start with what they need.</strong>
                    <p>{customerId ? "Send a message to begin a support conversation. Relevant customer memories are available alongside the chat." : "Select a customer or create a session profile before starting support."}</p>
                    {customerId && <div className="suggestion-row">
                      <button type="button" onClick={() => setMessageInput("I need help with a recent issue.")}>I need help with a recent issue <ArrowUpRight size={13} /></button>
                      <button type="button" onClick={() => setMessageInput("Can you help me with my account?")}>Help with my account <ArrowUpRight size={13} /></button>
                    </div>}
                  </div>
                )}
                {messages.map((message, index) => (
                  <article className={`chat-message ${message.role === "customer" ? "from-customer" : "from-agent"}`} key={`${message.role}-${index}`}>
                    <span className={`message-avatar ${message.role === "customer" ? "customer-message-avatar" : "agent-message-avatar"}`}>
                      {message.role === "customer" ? <UserRound size={15} /> : <Sparkles size={15} />}
                    </span>
                    <div className="message-body">
                      <div className="message-author"><strong>{message.role === "customer" ? displayName : "Standford agent"}</strong>
                        {message.created_at && <time>{formatDate(message.created_at)}</time>}
                        {message.status && <span className={`message-status status-${message.status}`}>{statusLabel(message.status)}</span>}
                      </div>
                      <div className="message-bubble">{message.content}</div>
                      {message.conversation_id && <span className="conversation-reference">conversation_id · {message.conversation_id}</span>}
                      {message.memories?.length > 0 && <div className="message-memory-context" aria-label="Memory context returned with this response"><div className="message-memory-note"><BrainCircuit size={13} /> Memory used: {message.memories.map((memory) => memory.category).filter(Boolean).slice(0, 2).join(", ") || "Hindsight context"}</div>{message.memories.map((memory, memoryIndex) => {
                        const text = memoryText(memory);
                        return text ? <article className="message-memory-item" key={memory.id || memory.memory_id || `${text}-${memoryIndex}`}><p>{text}</p><div className="memory-meta">{memory.category && <span>{memory.category}</span>}{memory.created_at && <time>{formatDate(memory.created_at)}</time>}</div></article> : null;
                      })}</div>}
                    </div>
                  </article>
                ))}
                {chatLoading && <div className="typing-state"><span className="typing-avatar"><Sparkles size={14} /></span><span className="typing-dots"><i /><i /><i /></span><span>Finding the right context</span><LoaderCircle size={13} className="spin" /></div>}
                <div ref={messageEndRef} />
              </div>

              {chatError && <div className="inline-error" role="alert"><CircleAlert size={15} /><span>{chatError}</span><button type="button" onClick={() => setChatError("")} aria-label="Dismiss error"><X size={14} /></button></div>}
              <form className="composer" onSubmit={submitMessage}>
                <label className="sr-only" htmlFor="message-input">Message the support agent</label>
                <textarea id="message-input" rows="1" placeholder={customerId ? "Write a message..." : "Select a customer to start chatting"} value={messageInput} onChange={(event) => setMessageInput(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); event.currentTarget.form.requestSubmit(); } }} disabled={!customerId || chatLoading} />
                <div className="composer-footer"><span><ShieldCheck size={13} /> {customerId ? "Customer context attached" : "Customer required to start"}</span>
                  <button className="send-button" type="submit" disabled={!customerId || !messageInput.trim() || chatLoading} aria-label="Send message">{chatLoading ? <LoaderCircle size={16} className="spin" /> : <Send size={16} />}</button>
                </div>
              </form>
              <section className="support-summary" aria-labelledby="support-summary-title">
                <div className="support-summary-heading"><BrainCircuit size={15} /><h3 id="support-summary-title">AI support brief</h3></div>
                <dl>
                  <div><dt>Current issue</dt><dd>{activeTicket?.subject || latestCustomerMessage?.content || "No issue reported yet."}</dd></div>
                  <div><dt>Relevant previous context</dt><dd>{previousContext}</dd></div>
                  <div><dt>Previous successful solution</dt><dd>{summaryMemory?.successful_solution || "Not included in the returned memory data."}</dd></div>
                  <div><dt>Suggested next action</dt><dd>{suggestedNextAction}</dd></div>
                </dl>
              </section>
            </section>

            <section className={`panel escalation-panel ${showEscalation ? "escalation-expanded" : ""}`}>
              <div className="panel-heading escalation-heading">
                <div className="panel-title-wrap"><span className="panel-icon escalation-icon"><LifeBuoy size={18} /></span><div><h2>Human handoff</h2><p>Bring a person into the loop</p></div></div>
                <button className="icon-button" type="button" onClick={() => setShowEscalation((visible) => !visible)} aria-label={showEscalation ? "Close escalation details" : "Show escalation details"} aria-expanded={showEscalation}>{showEscalation ? <X size={16} /> : <ArrowUpRight size={16} />}</button>
              </div>
              {showEscalation && <div className="escalation-context">
                <div className="context-row"><span>Customer</span><strong>{displayName} · {customerId}</strong></div>
                <div className="context-row"><span>Ticket ID</span><strong>{activeTicket?.ticket_id || "No open ticket"}</strong></div>
                <div className="context-row"><span>Current issue</span><strong>{activeTicket?.subject || latestCustomerMessage?.content || "No issue captured yet"}</strong></div>
                <div className="context-row"><span>Previous relevant context</span><strong>{previousContext}</strong></div>
                <div className="context-row"><span>Previous outcome</span><strong>{previousSolution || "Not returned by the available memory data"}</strong></div>
                <div className="context-row"><span>Relevant memories</span><strong>{memoryLoading ? "Loading" : `${memories.length} returned`}</strong></div>
                <div className="context-row"><span>Previous troubleshooting</span><strong>{messages.filter((message) => message.role === "agent").length} agent replies in this session</strong></div>
                <div className="context-row"><span>Status</span><strong>{activeTicket ? statusLabel(activeTicket.status) : "No open ticket"}</strong></div>
                <button className="escalate-button" type="button" disabled={!activeTicket?.ticket_id || !!updatingTicketId} onClick={() => changeTicketStatus(activeTicket, "escalated")}>
                  {updatingTicketId === activeTicket?.ticket_id ? <LoaderCircle size={15} className="spin" /> : <Headphones size={15} />}
                  {activeTicket?.ticket_id ? "Escalate to a human agent" : "Create an identified ticket to escalate"}
                  {activeTicket?.ticket_id && <ArrowUpRight size={14} />}
                </button>
                <p className="escalation-footnote">Escalation updates the ticket status to <code>escalated</code>.</p>
              </div>}
              {!showEscalation && <button className="handoff-prompt" type="button" onClick={() => setShowEscalation(true)}><span><ArrowDownLeft size={14} /> Review handoff context</span><ArrowUpRight size={14} /></button>}
            </section>

            <section className="panel tickets-panel">
              <div className="panel-heading">
                <div className="panel-title-wrap"><span className="panel-icon ticket-icon"><TicketCheck size={18} /></span><div><h2>Previous tickets</h2><p>Customer support history</p></div></div>
                <span className="history-unavailable"><CircleAlert size={13} /> History endpoint unavailable</span>
              </div>
              <div className="ticket-history-note">The API contract does not include a ticket-list endpoint. Tickets created in this session appear below.</div>
              {ticketError && <div className="inline-error ticket-error" role="alert"><CircleAlert size={15} /><span>{ticketError}</span><button type="button" onClick={() => setTicketError("")} aria-label="Dismiss error"><X size={14} /></button></div>}
              {tickets.length === 0 ? (
                <div className="ticket-empty"><span><TicketPlus size={18} /></span><div><strong>Ready for the first support ticket</strong><p>Tickets created for this customer will appear here.</p></div></div>
              ) : (
                <div className="ticket-list">
                  {tickets.map((ticket, index) => (
                    <article className="ticket-row" key={ticket.ticket_id || `${ticket.subject}-${index}`}>
                      <span className="ticket-row-icon"><TicketCheck size={16} /></span>
                      <div className="ticket-main"><div className="ticket-subject">{ticket.subject}</div><div className="ticket-meta"><span>ticket_id · {ticket.ticket_id || "Awaiting backend ID"}</span><span>customer_id · {ticket.customer_id}</span>{ticket.created_at && <time>{formatDate(ticket.created_at)}</time>}</div></div>
                      <span className={`status-badge status-${ticket.status}`}>{statusLabel(ticket.status)}</span>
                      {ticket.ticket_id && ticket.status !== "resolved" && ticket.status !== "escalated" && <div className="ticket-actions">
                        <button type="button" title="Escalate to a human" aria-label="Escalate to a human" disabled={!!updatingTicketId} onClick={() => changeTicketStatus(ticket, "escalated")}><ArrowUpRight size={15} /></button>
                        <button type="button" title="Resolve ticket" aria-label="Resolve ticket" disabled={!!updatingTicketId} onClick={() => changeTicketStatus(ticket, "resolved")}><Check size={15} /></button>
                      </div>}
                    </article>
                  ))}
                </div>
              )}
              <form className="new-ticket-form" onSubmit={submitTicket}>
                <label htmlFor="ticket-subject"><Plus size={15} /> Create a ticket</label>
                <div><input id="ticket-subject" value={ticketSubject} onChange={(event) => setTicketSubject(event.target.value)} placeholder="Briefly describe the issue" disabled={!customerId} /><button type="submit" disabled={!customerId || !ticketSubject.trim() || ticketLoading}>{ticketLoading ? <LoaderCircle size={15} className="spin" /> : "Create ticket"}</button></div>
              </form>
            </section>
          </section>

          <aside className="secondary-column">
            <section className="panel memory-panel">
              <div className="memory-panel-heading">
                <div className="memory-heading-icon"><BrainCircuit size={19} /></div>
                <div><span className="section-overline">HINDSIGHT · PRIOR SUPPORT CONTEXT</span><h2>Customer memory timeline</h2></div>
                <span className="memory-count">{memoryLoading ? "..." : memories.length.toString().padStart(2, "0")}</span>
              </div>
              <p className="memory-intro"><span className="memory-recall-label">PERSISTENT CONTEXT · RECALLED FROM PRIOR SUPPORT</span> Actual memory records returned for this customer. Dates and categories appear where provided.</p>
              <div className="memory-list" aria-live="polite">
                {memoryLoading && <div className="memory-state"><LoaderCircle size={17} className="spin" /><span>Retrieving customer memories</span></div>}
                {!memoryLoading && memoryError && <div className="memory-error"><CircleAlert size={16} /><div><strong>Memories couldn’t load</strong><p>{memoryError}</p><button type="button" onClick={() => setMemoryRetry((attempt) => attempt + 1)}>Try again</button></div></div>}
                {!memoryLoading && !customerId && <div className="memory-empty"><span className="memory-empty-mark"><BrainCircuit size={19} /></span><strong>Select a customer to view memory</strong><p>Hindsight context will load when a customer ID is selected.</p></div>}
                {!memoryLoading && customerId && !memoryError && memories.length === 0 && <div className="memory-empty"><span className="memory-empty-mark"><BrainCircuit size={19} /></span><strong>No prior context recalled yet</strong><p>Relevant memories from earlier support interactions will appear here when returned by Hindsight.</p></div>}
                {!memoryLoading && !memoryError && timelineMemories.map(renderMemory)}
              </div>
              <div className="memory-source"><span><Activity size={13} /> HINDSIGHT MEMORY</span><span>customer_id · {customerId}</span></div>
            </section>

            <div className="privacy-note"><ShieldCheck size={15} /><p>{customerId ? <>Customer memories are fetched for <code>{customerId}</code>. Conversation transcripts are not shown as memories.</> : "Select a customer to load Hindsight memories."}</p></div>
          </aside>
        </div>

        <footer className="dashboard-footer"><span>STANDFORD SUPPORT HUB</span><span>Support with continuity <span className="footer-dot">·</span> Customer context stays in view</span><span className="footer-build"><Clock3 size={12} /> READY FOR THE NEXT CONVERSATION</span></footer>
        </main>
        {showAccountProfile && authUser && <div className="dialog-backdrop">
          <section className="customer-dialog account-profile-dialog" role="dialog" aria-modal="true" aria-labelledby="account-profile-title">
            <div className="customer-dialog-header">
              <div><span className="section-overline">DEMO SESSION PROFILE</span><h2 id="account-profile-title">{editingAccountProfile ? "Edit your profile" : "Your profile"}</h2></div>
              <button className="icon-button" type="button" aria-label="Close profile" onClick={() => { setShowAccountProfile(false); setEditingAccountProfile(false); }}><X size={17} /></button>
            </div>
            {editingAccountProfile ? <form className="account-profile-form" onSubmit={saveAccountProfile}>
              <label htmlFor="account-profile-name">Name</label>
              <input id="account-profile-name" autoComplete="name" required value={accountProfileForm.name} onChange={(event) => setAccountProfileForm((current) => ({ ...current, name: event.target.value }))} />
              <label htmlFor="account-profile-email">Email</label>
              <input id="account-profile-email" type="email" autoComplete="email" required value={accountProfileForm.email} onChange={(event) => setAccountProfileForm((current) => ({ ...current, email: event.target.value }))} />
              {accountProfileError && <p className="auth-error" role="alert">{accountProfileError}</p>}
              <div className="account-profile-form-actions">
                <button type="button" onClick={() => { setEditingAccountProfile(false); setAccountProfileError(""); }}>Cancel</button>
                <button className="auth-submit" type="submit">Save profile</button>
              </div>
            </form> : <>
              <div className="account-profile-avatar"><UserRound size={22} /><strong>{authUser.name}</strong></div>
              <dl className="account-profile-details">
                <div><dt>Name</dt><dd>{authUser.name}</dd></div>
                <div><dt>Email</dt><dd>{authUser.email}</dd></div>
                <div><dt>customer_id</dt><dd>{authUser.customer_id}</dd></div>
              </dl>
              <p className="customer-dialog-note">This demo profile is held in page memory only. No authentication or profile data is sent to a registration service.</p>
            </>}
          </section>
        </div>}
    </div>
  );
}

export default App;