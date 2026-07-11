import { useState, useEffect, useRef, useCallback } from "react";
import "./dashboard.css";

import { AGENTS } from "./constants/agents.js";
import { INIT_MODELS } from "./constants/models.js";
import { SEED_CONVERSATIONS } from "./constants/conversations.js";
import { RESPONSES } from "./constants/homeContent.js";
import { LOADING_DELAY, PANEL_LOAD_DELAY, TOAST_DISMISS_DELAY } from "./constants/timing.js";
import { randId } from "./utils/id.js";
import { truncate } from "./utils/format.js";
import { useKeyboardShortcut } from "./hooks/useKeyboardShortcut.js";
import { useEscapeKey } from "./hooks/useEscapeKey.js";

import Header from "./components/Header.jsx";
import Sidebar from "./components/Sidebar.jsx";
import HomeHero from "./components/HomeHero.jsx";
import ChatThread from "./components/ChatThread.jsx";
import PlaceholderView from "./components/PlaceholderView.jsx";
import ChatInputBar from "./components/ChatInputBar.jsx";
import RightPanel from "./components/RightPanel.jsx";
import ErrorBoundary from "./components/ErrorBoundary.jsx";
import ToastStack from "./components/ToastStack.jsx";
import ModelApiStudioModal from "./components/ModelApiStudioModal.jsx";

/**
 * Three tiers, not two. The previous version only distinguished "<900px:
 * overlay drawers" from ">=900px: full desktop, both panels open by default."
 * That's wrong for the 900\u20131199px band \u2014 landscape tablets and small
 * laptops \u2014 where "both panels open" reserves 272+312=584px for chrome and
 * leaves as little as ~316px for actual content. That's not broken the way
 * "both" is broken below 900px (no backdrop trap here, both panels can
 * genuinely coexist), it's just a bad default. Pick a better one.
 */
function computeInitialLayoutMode() {
  if (typeof window === "undefined") return "both";
  const w = window.innerWidth;
  if (w < 900) return "hidden";
  if (w < 1200) return "left";
  return "both";
}

export default function AetherisDashboard({ onExitLanding = null }) {
  const [isNarrow, setIsNarrow] = useState(() =>
    typeof window !== "undefined" && window.matchMedia("(max-width: 900px)").matches
  );
  // Below 900px both rails become position:fixed overlays with a full-viewport
  // backdrop (see .backdrop in CSS). "both" at that width means two overlays
  // stacked on top of the chat input with no way to reach it underneath \u2014
  // that combination is simply not a legal state, not just an unlikely one.
  const [layoutMode, setLayoutModeRaw] = useState(computeInitialLayoutMode); // left | right | both | hidden

  useEffect(() => {
    if (typeof window === "undefined") return;
    const mq = window.matchMedia("(max-width: 900px)");
    function handle(e) {
      setIsNarrow(e.matches);
      // Crossing into narrow while sitting on "both" would otherwise strand the
      // user behind an opaque backdrop with no visible control to dismiss it.
      if (e.matches) setLayoutModeRaw((prev) => (prev === "both" ? "hidden" : prev));
    }
    mq.addEventListener("change", handle);
    return () => mq.removeEventListener("change", handle);
  }, []);

  const changeLayoutMode = useCallback((mode) => {
    setLayoutModeRaw(isNarrow && mode === "both" ? "hidden" : mode);
  }, [isNarrow]);

  const sidebarOpen = layoutMode === "both" || layoutMode === "left";
  const rightOpen = layoutMode === "both" || layoutMode === "right";

  const [view, setView] = useState("home");
  const [search, setSearch] = useState("");
  const searchRef = useRef(null);
  const [loadingConversations, setLoadingConversations] = useState(true);

  useEffect(() => {
    const t = setTimeout(() => setLoadingConversations(false), LOADING_DELAY);
    return () => clearTimeout(t);
  }, []);

  const [conversations, setConversations] = useState(() => {
    if (typeof window === "undefined") return SEED_CONVERSATIONS;
    try {
      const saved = localStorage.getItem("aetheris_saved_conversations");
      if (saved) {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed) && parsed.length > 0) return parsed;
      }
    } catch (e) {}
    return SEED_CONVERSATIONS;
  });
  const [activeId, setActiveId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [typingAgent, setTypingAgent] = useState(null);
  const [streaming, setStreaming] = useState(false);
  const sendingRef = useRef(false);
  const abortRef = useRef(null);
  const dbLoadedRef = useRef(false);

  const [authVerified, setAuthVerified] = useState(false);

  useEffect(() => {
    if (typeof window !== "undefined") {
      try {
        localStorage.setItem("aetheris_saved_conversations", JSON.stringify(conversations));
      } catch (e) {}
    }
    const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
    if (token && conversations.length > 0 && authVerified) {
      const active = conversations.find((c) => c.id === activeId) || conversations[0];
      if (active && active.id) {
        fetch("/api/conversations", {
          method: "POST",
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
          credentials: "include",
          body: JSON.stringify({
            id: String(active.id),
            title: active.title || "Conversation",
            mode: active.mode || "HYBRID",
            transcript: active.transcript || [],
          }),
        }).catch(() => {});
      }
    }
  }, [conversations, activeId, authVerified]);

  useEffect(() => {
    if (!activeId) return;
    setConversations((prev) =>
      prev.map((c) => (c.id === activeId ? { ...c, transcript: messages } : c))
    );
  }, [activeId, messages]);

  const fetchStatus = useCallback(async () => {
    try {
      const token = localStorage.getItem("access_token");
      if (!token) {
        window.location.href = "/login";
        return;
      }
      const headers = { Authorization: `Bearer ${token}` };
      const res = await fetch("/api/status", { headers, credentials: "include" });
      if (res.status === 401 || !res.ok) {
        localStorage.removeItem("access_token");
        localStorage.removeItem("user_email");
        localStorage.removeItem("refresh_token");
        window.location.href = "/login";
        return;
      }
      setAuthVerified(true);
      if (!dbLoadedRef.current) {
        dbLoadedRef.current = true;
        fetch("/api/conversations", { headers, credentials: "include" })
          .then((r) => (r.ok ? r.json() : null))
          .then((convData) => {
            if (convData && convData.conversations && Array.isArray(convData.conversations) && convData.conversations.length > 0) {
              setConversations(convData.conversations);
            }
          })
          .catch(() => {});
      }
      const data = await res.json();
      if (data) {
        if (data.providers && Array.isArray(data.providers)) {
          const onlineCount = data.providers.filter((p) => p.status === "online" || p.status === "available").length;
          setStats((prev) => ({
            ...prev,
            agentsOnline: `${onlineCount}/${data.providers.length || 6}`,
            tokens: data.telemetry?.total_tokens ?? prev.tokens,
            avgResponse: data.telemetry?.avg_response_s ?? prev.avgResponse,
            successRate: data.telemetry?.success_rate ?? prev.successRate,
            sparkline: data.telemetry?.sparkline ?? prev.sparkline,
          }));
        }
        if (data.models && Array.isArray(data.models) && data.models.length > 0) {
          setModels((prevModels) => {
            const activeMap = new Map(prevModels.map((m) => [m.id, m.active]));
            return data.models.map((m) => ({
              ...m,
              active: activeMap.has(m.id) ? activeMap.get(m.id) : (m.active !== undefined ? m.active : true),
            }));
          });
        }
      }
    } catch (e) {
      localStorage.removeItem("access_token");
      window.location.href = "/login";
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    const iv = setInterval(fetchStatus, 5000);
    return () => clearInterval(iv);
  }, [fetchStatus]);

  const [models, setModels] = useState(INIT_MODELS);
  const [agentState, setAgentState] = useState({ breaker: true, logician: true, creative: true, judge: true });

  const [inputValue, setInputValue] = useState("");
  const inputRef = useRef(null);
  const [mode, setMode] = useState("Balanced");
  const [modelSelect, setModelSelect] = useState("Auto");
  const [webSearch, setWebSearch] = useState(false);
  const [autoExpand, setAutoExpand] = useState(true);
  const [attached, setAttached] = useState(null);

  const [stats, setStats] = useState({ agentsOnline: "6/6", tokens: 0, avgResponse: "1.2", successRate: "99.4", sparkline: [] });
  const [rightPanelLoaded, setRightPanelLoaded] = useState(false);
  const [studioOpen, setStudioOpen] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setRightPanelLoaded(true), PANEL_LOAD_DELAY);
    return () => clearTimeout(t);
  }, []);

  const [notifications, setNotifications] = useState([
    { id: "n1", text: "Judge flagged confirmation bias in 2 responses", time: "12m ago", read: false },
    { id: "n2", text: "mistral-large deactivated \u2014 rate limit", time: "1h ago", read: false },
    { id: "n3", text: "Weekly telemetry report is ready", time: "Yesterday", read: true },
  ]);

  const [toasts, setToasts] = useState([]);
  // Stable across renders (empty dep array, closes over nothing but setState
  // setters, which React itself guarantees are stable). Every handler below
  // that calls pushToast can safely depend on it without that dependency
  // forcing the handler to be recreated on every render.
  const pushToast = useCallback((text, kind = "success", action = null) => {
    const id = randId();
    setToasts((t) => [...t, { id, text, kind, action }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), TOAST_DISMISS_DELAY);
  }, []);

  const toggleModel = useCallback((id) => {
    setModels((prev) => {
      const target = prev.find((m) => m.id === id);
      if (!target) return prev;
      const activeCount = prev.filter((m) => m.active).length;
      if (target.active && activeCount === 1) {
        pushToast("At least one model must stay active");
        return prev;
      }
      const newActive = !target.active;
      const token = localStorage.getItem("access_token");
      if (token) {
        fetch("/api/models/toggle", {
          method: "POST",
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
          credentials: "include",
          body: JSON.stringify({ id, active: newActive }),
        }).catch(() => {});
      }
      return prev.map((m) => (m.id === id ? { ...m, active: newActive } : m));
    });
  }, [pushToast]);

  const addModel = useCallback((name) => {
    const exists = models.some((m) => m.name.toLowerCase() === name.toLowerCase());
    if (exists) {
      pushToast(`${name} is already active`);
      return false;
    }
    const cleanId = name.split("/").pop().replace(/\./g, "").replace(/-/g, "");
    const newModel = { id: cleanId || randId(), name: name.split("/").pop(), latency: "1.1s", active: true };
    setModels((prev) => [...prev, newModel]);
    const token = localStorage.getItem("access_token");
    if (token) {
      fetch("/api/models/add", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        credentials: "include",
        body: JSON.stringify({ model: name, role: "generation" }),
      }).then(() => fetchStatus()).catch(() => {});
    }
    pushToast(`${name} added to orchestrator`);
    return true;
  }, [models, pushToast, fetchStatus]);

  const toggleAgent = useCallback((id) => {
    setAgentState((prev) => {
      const activeCount = Object.values(prev).filter(Boolean).length;
      if (prev[id] && activeCount === 1) { pushToast("At least one agent must stay included"); return prev; }
      return { ...prev, [id]: !prev[id] };
    });
  }, [pushToast]);

  const openConversation = useCallback((conv) => {
    setActiveId(conv.id);
    setMessages((conv.transcript || []).map((m) => ({ ...m, id: randId() })));
    setView("home");
  }, []);

  const newConversation = useCallback(() => {
    setActiveId(null);
    setMessages([]);
    setView("home");
    setInputValue("");
  }, []);

  const deleteConversation = useCallback((convId) => {
    setConversations((prev) => prev.filter((c) => c.id !== convId));
    if (activeId === convId) {
      pendingTimeouts.current.forEach(clearTimeout);
      pendingTimeouts.current = [];
      sendingRef.current = false;
      setActiveId(null);
      setMessages([]);
      setTypingAgent(null);
      setStreaming(false);
    }
    pushToast("Conversation deleted");
  }, [activeId, pushToast]);

  const pendingTimeouts = useRef([]);
  useEffect(() => () => pendingTimeouts.current.forEach(clearTimeout), []);

  const handleSend = useCallback((text) => {
    const finalText = (text ?? inputValue).trim();
    if (!finalText || streaming || sendingRef.current) return;
    sendingRef.current = true;
    const included = AGENTS.filter((a) => agentState[a.id]);

    let convId = activeId;
    if (!convId) {
      convId = randId();
      const conv = { id: convId, title: truncate(finalText, 48), time: "Just now", mode, agentsCount: included.length, score: null, transcript: [] };
      setConversations((prev) => [conv, ...prev]);
      setActiveId(convId);
    }

    setMessages((m) => [...m, { id: randId(), role: "user", text: finalText }]);
    setInputValue("");
    setAttached(null);
    setStreaming(true);
    setView("home");
    setTimeout(() => inputRef.current?.focus(), 0);

    const abortController = new AbortController();
    abortRef.current = abortController;

    (async () => {
      try {
        const token = localStorage.getItem("access_token");
        const headers = { "Content-Type": "application/json" };
        if (token) headers.Authorization = `Bearer ${token}`;

        const response = await fetch("/api/query/stream", {
          method: "POST",
          headers,
          credentials: "include",
          body: JSON.stringify({ query: finalText }),
          signal: abortController.signal,
        });

        if (!response.ok) {
          if (response.status === 401) {
            pushToast("Authentication required. Redirecting to login...");
            setTimeout(() => { window.location.href = "/login"; }, 1500);
            return;
          }
          const errText = await response.text().catch(() => "");
          throw new Error(`Server error (${response.status}): ${errText || response.statusText}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed.startsWith("data: ")) continue;

            try {
              const envelope = JSON.parse(trimmed.slice(6));
              const eventType = envelope.event;
              const payload = envelope.data || {};

              if (eventType === "agent_started" || eventType === "progress") {
                const agentName = payload.agent || payload.agent_name;
                if (agentName) setTypingAgent(agentName);
              } else if (eventType === "agent_completed" || eventType === "draft_answer") {
                const agentName = payload.agent || payload.agent_name || "Agent";
                const content = payload.final_answer || payload.content || payload.answer;
                if (content && typeof content === "string") {
                  setMessages((prev) => {
                    let lastUserIdx = -1;
                    for (let i = prev.length - 1; i >= 0; i--) {
                      if (prev[i].role === "user") { lastUserIdx = i; break; }
                    }
                    const existingIdx = prev.findIndex((msg, i) => i > lastUserIdx && msg.role === "agent" && (msg.agentId || "").toLowerCase() === agentName.toLowerCase());
                    if (existingIdx !== -1) {
                      const updated = [...prev];
                      updated[existingIdx] = { ...updated[existingIdx], text: content };
                      return updated;
                    }
                    return [...prev, { id: randId(), role: "agent", agentId: agentName, text: content }];
                  });
                }
              } else if (eventType === "result") {
                const resData = payload.payload || payload;
                if (resData.final_answer) {
                  setMessages((prev) => {
                    let lastUserIdx = -1;
                    for (let i = prev.length - 1; i >= 0; i--) {
                      if (prev[i].role === "user") { lastUserIdx = i; break; }
                    }
                    const existingIdx = prev.findIndex((msg, i) => i > lastUserIdx && msg.role === "agent" && (msg.agentId || "").toLowerCase() === "synthesis");
                    if (existingIdx !== -1) {
                      const updated = [...prev];
                      updated[existingIdx] = { ...updated[existingIdx], text: resData.final_answer };
                      return updated;
                    }
                    return [...prev, { id: randId(), role: "agent", agentId: "Synthesis", text: resData.final_answer }];
                  });
                }
              } else if (eventType === "error") {
                pushToast(`Pipeline Error: ${payload.message || "Unknown error"}`);
              }
            } catch (e) {
              // Ignore partial or unparseable JSON line
            }
          }
        }
      } catch (err) {
        if (err.name !== "AbortError") {
          pushToast(`Backend error: ${err.message}`);
          setMessages((m) => [...m, { id: randId(), role: "agent", agentId: "System", text: `Could not reach backend: ${err.message}` }]);
        }
      } finally {
        sendingRef.current = false;
        setStreaming(false);
        setTypingAgent(null);
        abortRef.current = null;
        fetchStatus();
      }
    })();
  }, [inputValue, streaming, activeId, pushToast]);

  const stopGeneration = useCallback(() => {
    if (abortRef.current) abortRef.current.abort();
    pendingTimeouts.current.forEach(clearTimeout);
    pendingTimeouts.current = [];
    sendingRef.current = false;
    setStreaming(false);
    setTypingAgent(null);
    pushToast("Generation stopped");
  }, [pushToast]);

  const markAllRead = useCallback(() => {
    setNotifications((n) => n.map((x) => ({ ...x, read: true })));
  }, []);

  const onLogout = useCallback(() => {
    localStorage.removeItem("access_token");
    localStorage.removeItem("user_email");
    localStorage.removeItem("refresh_token");
    window.location.href = "/login";
  }, []);

  const ensurePanels = useCallback((which) => {
    if (which === "sidebar" && (layoutMode === "right" || layoutMode === "hidden")) {
      changeLayoutMode(isNarrow ? "left" : "both");
    }
    if (which === "right" && (layoutMode === "left" || layoutMode === "hidden")) {
      changeLayoutMode(isNarrow ? "right" : "both");
    }
  }, [layoutMode, isNarrow, changeLayoutMode]);

  const openSettingsView = useCallback(() => setView("settings"), []);
  const openBothPanels = useCallback(() => changeLayoutMode("both"), [changeLayoutMode]);
  const openTelemetryPanel = useCallback(() => ensurePanels("right"), [ensurePanels]);
  const goBackToConversationList = useCallback(() => {
    if (isNarrow) changeLayoutMode("left");
  }, [changeLayoutMode, isNarrow]);
  const toggleSidebarMobile = useCallback(
    () => changeLayoutMode(sidebarOpen ? "hidden" : "left"),
    [changeLayoutMode, sidebarOpen]
  );
  const closeMobilePanels = useCallback(() => {
    if (isNarrow && (sidebarOpen || rightOpen)) {
      changeLayoutMode("hidden");
    }
  }, [changeLayoutMode, isNarrow, rightOpen, sidebarOpen]);

  useEscapeKey(closeMobilePanels);

  useKeyboardShortcut("k", useCallback(() => {
    if (!sidebarOpen) changeLayoutMode(isNarrow ? "left" : "both");
    setTimeout(() => searchRef.current?.focus(), 50);
  }, [sidebarOpen, changeLayoutMode, isNarrow]));
  useKeyboardShortcut("n", useCallback(() => newConversation(), [newConversation]));
  useKeyboardShortcut("/", useCallback(() => {
    inputRef.current?.focus();
  }, []), { meta: false, allowInInput: false });

  const activeConv = conversations.find((c) => c.id === activeId);

  if (!authVerified) {
    return (
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100vh',
        backgroundColor: '#0a0a0a',
        color: '#8f8f8f',
        fontFamily: 'system-ui, sans-serif'
      }}>
        <span>Verifying secure session...</span>
      </div>
    );
  }

  return (
    <div className="aetheris-app">
      <div className="fx-scanlines" aria-hidden="true" />
      <div className="fx-noise" aria-hidden="true" />

      <Header
        models={models} toggleModel={toggleModel} addModel={addModel}
        onOpenSettings={openSettingsView}
        onOpenStudio={() => setStudioOpen(true)}
        layoutMode={layoutMode} setLayoutMode={changeLayoutMode} isNarrow={isNarrow}
        notifications={notifications} markAllRead={markAllRead}
        onMissionControl={openBothPanels}
        onTelemetry={openTelemetryPanel}
        onLogout={onLogout}
        onOpenSidebarMobile={toggleSidebarMobile}
        onExitLanding={onExitLanding}
      />

      <div className="body">
        <Sidebar
          open={sidebarOpen} conversations={conversations} activeId={activeId}
          onSelect={openConversation} onDelete={deleteConversation} onNew={newConversation}
          search={search} setSearch={setSearch} view={view} setView={setView}
          searchRef={searchRef} loading={loadingConversations} isNarrow={isNarrow} streaming={streaming}
          onClose={closeMobilePanels}
        />

        <main className="center">
          <ErrorBoundary>
            {view === "home" ? (
              activeId ? (
                <div key={activeId} className="thread-enter">
                <ChatThread
                  messages={messages}
                  typingAgent={typingAgent}
                  title={activeConv?.title || ""}
                  mode={activeConv?.mode || mode}
                  agentsCount={activeConv?.agentsCount ?? AGENTS.filter((a) => agentState[a.id]).length}
                  pushToast={pushToast}
                  onBack={goBackToConversationList}
                  isNarrow={isNarrow}
                />
                </div>
              ) : (
                <HomeHero
                  agentState={agentState}
                  toggleAgent={toggleAgent}
                  onQuickPrompt={(t) => handleSend(t)}
                  onFocusInput={() => inputRef.current?.focus()}
                  onOpenSettings={openSettingsView}
                  onOpenTelemetry={openTelemetryPanel}
                />
              )
            ) : (
              <PlaceholderView view={view} />
            )}
          </ErrorBoundary>

          <ChatInputBar
            value={inputValue} onChange={setInputValue} onSend={() => handleSend()} onStop={stopGeneration}
            streaming={streaming} mode={mode} setMode={setMode}
            modelSelect={modelSelect} setModelSelect={setModelSelect}
            webSearch={webSearch} setWebSearch={setWebSearch}
            autoExpand={autoExpand} setAutoExpand={setAutoExpand}
            attached={attached} setAttached={setAttached} pushToast={pushToast} inputRef={inputRef}
          />
        </main>

        <ErrorBoundary>
          <RightPanel
            open={rightOpen} stats={stats} models={models}
            conversations={conversations} activeId={activeId} onSelect={openConversation}
            isNarrow={isNarrow} isLoaded={rightPanelLoaded} onClose={closeMobilePanels}
          />
        </ErrorBoundary>
      </div>

      {(sidebarOpen || rightOpen) && <div className="backdrop" onClick={closeMobilePanels} aria-hidden="true" />}
      <ModelApiStudioModal
        isOpen={studioOpen}
        onClose={() => setStudioOpen(false)}
        models={models}
        onToggleModel={toggleModel}
        onRefresh={fetchStatus}
      />
      <ToastStack toasts={toasts} />
    </div>
  );
}
