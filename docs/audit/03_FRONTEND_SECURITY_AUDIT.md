# AETHERIS Frontend & Security Audit

**Audit Date:** 2026-06-27
**Auditor:** Principal Frontend Architect & Security Engineer
**Scope:** Complete static analysis of the React frontend, authentication system, token management, CORS configuration, XSS/CSRF protections, session handling, and credential storage.

---

## Table of Contents

1. [Frontend Architecture Overview](#1-frontend-architecture-overview)
2. [React Components](#2-react-components)
3. [State Management](#3-state-management)
4. [Authentication & JWT](#4-authentication--jwt)
5. [CORS Configuration](#5-cors-configuration)
6. [XSS & CSRF](#6-xss--csrf)
7. [Credential & Secret Storage](#7-credential--secret-storage)
8. [Session Management](#8-session-management)
9. [Accessibility](#9-accessibility)
10. [Responsive Design](#10-responsive-design)
11. [Loading & Error States](#11-loading--error-states)
12. [Streaming & WebSocket Synchronization](#12-streaming--websocket-synchronization)
13. [Animation System](#13-animation-system)
14. [Privilege Escalation](#14-privilege-escalation)
15. [Issue Register](#15-issue-register)

---

## 1. Frontend Architecture Overview

| Layer | Technology | Assessment |
|-------|-----------|------------|
| Build | Vite 5 + React 18.3 | ✅ Modern, fast |
| Styling | Tailwind CSS 3 + PostCSS | ✅ Utility-first, maintainable |
| State | Zustand 4 (4 stores) | ✅ Lightweight, performant |
| Animation | Framer Motion 11 | ✅ Declarative, accessible |
| Routing | None (SPA with auth gate) | ⚠️ No route-based code splitting |
| HTTP | Axios + native fetch (SSE) | ⚠️ Mixed API patterns |
| Testing | Vitest + @testing-library/react | ✅ 14 test files, good coverage |
| Auth | localStorage-based JWT | 🔴 XSS-vulnerable storage |

### Frontend File Inventory (28 source, 14 test, 2 HTML, 1 CSS)

```
src/
  App.jsx                    (387 lines)  Main app, auth gate, layout
  main.jsx                   (10 lines)   Entry point
  index.css                  (449 lines)  Tailwind + custom classes + keyframes
  api/
    client.js                (163 lines)  Axios + fetch SSE client
  components/
    AgentCard.jsx            (341 lines)  Collapsible agent card
    AgentStreamCard.jsx      (216 lines)  Live streaming agent card
    AgentThinkingCard.jsx    (111 lines)  Simpler thinking card
    BiasRiskBadge.jsx        (15 lines)   Risk label badge
    ChatWindow.jsx           (176 lines)  Virtualized message list
    ConfidenceBadge.jsx      (22 lines)   Confidence score badge
    EmptyState.jsx           (127 lines)  Welcome/onboarding page
    InputBox.jsx             (90 lines)   Auto-resize textarea
    JudgePanel.jsx           (155 lines)  Post-execution judge analysis
    MessageBubble.jsx        (336 lines)  Memoized message renderer
    MissionControlPanel.jsx  (401 lines)  Slide-in dashboard (5 tabs)
    NotificationStack.jsx    (88 lines)   Toast notification stack
    PipelineStatus.jsx       (258 lines)  7-stage pipeline visualization
    ProviderStatusBar.jsx    (98 lines)   Top bar with health dots
    ReasoningGraph.jsx       (338 lines)  Interactive SVG graph
    ReasoningPanel.jsx       (256 lines)  Post-execution reasoning detail
    ReasoningTimeline.jsx    (176 lines)  Chronological event list
    SettingsPanel.jsx        (201 lines)  Modal with FocusTrap
    Sidebar.jsx              (343 lines)  Sidebar with search + virtualization
    TelemetryDrawer.jsx      (463 lines)  Analytics dashboard (4 tabs)
    TriadMark.jsx            (23 lines)   SVG signature visual
  hooks/
    useAnimations.js         (22 lines)   Animation preference hook
    usePipelineStages.js     (273 lines)  Core pipeline state hook
    useSendQuery.js          (109 lines)  Glue hook: store + pipeline
  store/
    useChatStore.js          (131 lines)  Conversations w/ localStorage
    useNotificationStore.js  (52 lines)   Toast notifications
    usePipelineStore.js      (110 lines)  Pipeline execution state
    useSettingsStore.js      (88 lines)   Preferences w/ localStorage
  utils/
    animations.js            (283 lines)  Framer Motion variants
    auth.js                  (55 lines)   JWT localStorage management
    retry.js                 (72 lines)   Retry with backoff
    syntaxHighlight.js       (157 lines)  Custom regex-based highlighter
```

---

## 2. React Components

### 2.1 Mission Control Panel (MissionControlPanel.jsx)

**Lines:** 401
**Assessment:** ⚠️ Heavy — loads 5 tabs with substantial content

| Tab | Content | Assessment |
|-----|---------|------------|
| Pipeline | PipelineStatus + stage duration bars | ✅ Lightweight |
| Agents | Grid of AgentCard components | ⚠️ Can be heavy with many agents |
| Timeline | ReasoningTimeline with filter | ✅ Virtualized |
| Graph | Lazy-loaded ReasoningGraph (Suspense) | ⚠️ Interactive SVG, can be CPU-intensive |
| Metrics | Stats display | ✅ Lightweight |

**Issues:**
- The Graph tab (ReasoningGraph) is Suspense-lazy-loaded but rendered unconditionally in the DOM when the panel is open (App.jsx:355-368). All tabs are rendered simultaneously, not just the active one. The graph creation (`buildGraphData`) is called in App.jsx on every render.
- Resize logic uses mouse events without `pointer-events` fallback for touch devices (MissionControlPanel.jsx drag handle).

### 2.2 Chat Interface (ChatWindow.jsx + MessageBubble.jsx + InputBox.jsx)

**Lines:** 176 + 336 + 90
**Assessment:** ✅ Well-structured with virtualization

**ChatWindow.jsx:**
- Uses `react-window` FixedSizeList for virtualization (threshold: 50 messages)
- ResizeObserver for container height tracking
- Auto-scroll to bottom on new messages (scrollIntoView)
- Ctrl+Home/End keyboard shortcuts for scroll
- Respects messageDensity setting (compact/comfortable)

**MessageBubble.jsx:**
- `React.memo` with custom comparator (17 fields checked)
- Three states: `pending` (streaming), `error`, `done`
- User messages: right-aligned gradient background
- Assistant messages: glass-panel styling with markdown rendering
- Code blocks use `dangerouslySetInnerHTML` for syntax highlighting (`syntaxHighlight.js`)
- Copy to clipboard with `navigator.clipboard.writeText` + textarea fallback
- Expandable reasoning panel with `AnimatePresence`

**InputBox.jsx:**
- Auto-resizing textarea (max 160px, ~3 rows)
- 4000 character limit with live counter at 80% threshold
- Enter to send, Shift+Enter for newline
- Preserved text on failure

### 2.3 Streaming Components

**AgentStreamCard.jsx (216 lines):**
- Shows live status (spinner/checkmark/X icon)
- Confidence chip, percentage progress bar
- Live progress message with ping dot animation
- Expanded view: progress timeline, reasoning summary, draft/final answer
- Proper aria attributes (`aria-live="polite"`, `role="status"`)

**AgentCard.jsx (341 lines):**
- Collapsible with Framer Motion animation
- Normalizes data from both `usePipelineStore` and `usePipelineStages` formats
- Shows duration, summary, claims with validation badges, warnings
- Left-accent colored border per agent type

### 2.4 Reasoning Timeline (ReasoningTimeline.jsx)

**Lines:** 176
**Assessment:** ✅ Good UX, clear chronological visualization

- Color-coded by agent, icon per event type
- Agent filter dropdown
- Auto-highlights most recent event
- Relative timestamps (Just now, Xs ago, Xm ago, Xh ago)
- Hover/click to highlight

### 2.5 Login Pages

Two separate login pages exist:

1. **`aetheris_login.html`** (788 lines, root-level, served by `/login` route)
   - Sign In / Sign Up toggle
   - POST to `/auth/login` or `/auth/register`
   - Stores access_token, refresh_token, user_email in localStorage
   - Inline CSS, inline JS

2. **`aetheris-ui/public/login.html`** (432 lines, within frontend)
   - Similar functionality, POST to `/api/auth/login`
   - Stores tokens in localStorage
   - Static file only (not served by backend)

**Issue:** Two duplicate login pages with different API paths — maintenance burden and inconsistency risk.

### 2.6 Authentication (App.jsx)

```javascript
const [authed, setAuthed] = useState(() => isAuthenticated());
// ...
useEffect(() => {
  if (!authed) {
    redirectToLogin();
  }
}, [authed]);
```

- Auth is checked once on mount via `isAuthenticated()` (checks `!!localStorage.getItem('access_token')`)
- Redirect happens via `window.location.href = '/login'`
- If not authenticated, `return null` (renders nothing)

**Issue:** Auth state is never verified with the server on mount. A stale/expired token passes the client-side check and is only caught when a 401 response arrives.

### 2.7 Settings Panel (SettingsPanel.jsx)

**Lines:** 201
**Assessment:** ✅ Well-structured modal with FocusTrap

- 6 settings: message density, font size, animations, auto-expand reasoning, mission control
- Radio groups with icons, toggle switches
- Reset to defaults button
- Escape to close, auto-focus first element
- `focus-trap-react` for focus isolation

### 2.8 Notification Stack (NotificationStack.jsx)

**Lines:** 88
**Assessment:** ✅ Clean implementation

- Fixed top-right corner, stacked vertically
- `AnimatePresence` with spring animations
- 4 types: success (emerald), warning (amber), error (rose), info (blue)
- Auto-dismiss after 5s (non-error) or manual dismiss
- Respects animation preferences

---

## 3. State Management

### 3.1 Zustand Stores

| Store | File | State | Persistence |
|-------|------|-------|-------------|
| `useChatStore` | `useChatStore.js` | conversations, activeId, telemetry, providerHealth | localStorage (`aetheris.conversations.{email}.v1`) |
| `useSettingsStore` | `useSettingsStore.js` | messageDensity, fontSize, animationsEnabled, autoExpandReasoning, missionControlOpen, missionControlPinned | localStorage (`aetheris.settings.{email}.v1`) |
| `usePipelineStore` | `usePipelineStore.js` | stage, progress, startTime, elapsedMs, agentStates, partialData | None (ephemeral) |
| `useNotificationStore` | `useNotificationStore.js` | notifications array | None (ephemeral) |

### 3.2 Chat Store Architecture (useChatStore.js)

**Lines:** 131
**Assessment:** ⚠️ Well-structured but localStorage persistence creates XSS risk

```javascript
const storageKey = email
  ? `aetheris.conversations.${email}.v1`
  : `aetheris.conversations.anonymous.v1`;
```

- Conversations persisted per-user by email
- 100-entry cap on telemetry history
- Auto-title from first user message (truncated to 48 chars)
- `getActiveConversation()` via Zustand's `get()` for external access

**Issue:** Conversation data stored in localStorage is structured JSON that can be parsed, but no size limits exist on individual conversations. A conversation with very long messages could grow localStorage indefinitely.

### 3.3 Settings Store (useSettingsStore.js)

**Lines:** 88
**Assessment:** ✅ Clean, well-tested

- 6 settings with sensible defaults
- Per-user persistence via email key
- `resetToDefaults()` restores initial state

### 3.4 Pipeline Store (usePipelineStore.js)

**Lines:** 110
**Assessment:** ⚠️ Overlaps with `usePipelineStages.js` hook

- Tracks stage, progress, elapsed time, agent states, partial data
- `updateAgentState` creates or merges per-agent state
- `reset` clears all state

**Issue:** The store and the `usePipelineStages` hook maintain separate copies of pipeline state. `usePipelineStages` is the primary source of truth (driven by SSE events), while `usePipelineStore` appears to be a legacy store that may diverge.

### 3.5 Validation Script (`__validation.js`)

**Lines:** 93
**Assessment:** 🔴 Legacy manual test script

- Manually exercises all three stores
- No assertions, no test framework integration
- Would throw on reference errors at runtime

---

## 4. Authentication & JWT

### 4.1 Token Lifecycle

| Step | Component | Location | Assessment |
|------|-----------|----------|------------|
| Login | Login page → POST `/auth/login` | `aetheris_login.html` | ✅ |
| Token receipt | Server returns `{"access_token": "...", "token_type": "bearer"}` | `server.py:300-303` | ✅ |
| Token storage | `localStorage.setItem('access_token', token)` | `utils/auth.js:10-12` | 🔴 XSS-vulnerable |
| Token attachment | Axios interceptor adds `Authorization: Bearer <token>` | `api/client.js:13-22` | ✅ |
| Token validation | `get_current_user` decodes JWT, queries DB | `core/security.py:340-367` | ✅ |
| 401 handling | Clear auth + redirect to `/login` | `api/client.js:26-31` | ✅ |
| Token refresh | `refresh_token` stored but **never used** | `utils/auth.js:22-28` | 🔴 Dead code |

### 4.2 JWT Configuration

```python
# core/config.py:73-89
JWT_SECRET_KEY: str = Field(default="09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7")
JWT_ALGORITHM: str = Field(default="HS256")
JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60)
```

**Issues:**

1. **Hardcoded default JWT secret** (HIGH): The default value `09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7` is a static string in the source code. If not overridden via `aetheris_JWT_SECRET_KEY` env var, every Aetheris instance uses the same key. This is a well-known security issue — any attacker who obtains the source can forge JWTs.

2. **No refresh token mechanism**: The `refresh_token` is stored in localStorage but never used to obtain new access tokens. The `access_token` expires after 60 minutes with no way to refresh. The user must log in again.

3. **No token revocation**: There is no blacklist or revocation mechanism. A leaked token remains valid for its full 60-minute lifespan.

### 4.3 Authentication Flow

```
Login Page → POST /auth/login
  → Server validates credentials
  → Server creates JWT with {"sub": email}
  → Returns {"access_token": token}
  → Login page stores in localStorage
  → Redirects to /
  → App.jsx checks isAuthenticated() [localStorage check]
  → Every API call: Axios interceptor attaches Bearer token
  → Server validates: get_current_user dependency
```

**Client-side auth check bypass:** `isAuthenticated()` only checks `!!localStorage.getItem('access_token')`. It does not verify:
- Token expiration
- Token signature
- Token belongs to the current user
- Token hasn't been revoked

A malformed or expired token passes the client-side check. Only the first API call with a 401 response reveals the issue.

### 4.4 Server-Side Auth Protection

All `/api/*` routes use `Depends(get_current_user)`:
```python
async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], db: ...) -> User:
    payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    email = payload.get("sub")
    stmt = select(User).where(User.email == email)
    user = result.scalars().first()
    return user
```

**Issue:** The `get_current_user` function queries the database on every API request. For SSE streaming endpoints, this adds database overhead to each connection. For high-traffic deployments, this could be a bottleneck.

---

## 5. CORS Configuration

### 5.1 Current Configuration

```python
# server.py:148-154
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 5.2 Vulnerability: Wildcard + Credentials (CRITICAL)

`allow_origins=["*"]` with `allow_credentials=True` is a **known insecure combination**. The CORS specification states that when credentials are allowed, the `Access-Control-Allow-Origin` header must be a specific origin, not `*`. 

**Behavior:** FastAPI's CORSMiddleware will send `Access-Control-Allow-Origin: *` along with `Access-Control-Allow-Credentials: true`.

**Impact:** Any website can make credentialed requests to the Aetheris API. If a user is logged in and visits a malicious site, that site can read responses from the Aetheris API, including pipeline outputs and potentially sensitive data.

**Evidence:** The `fetchProviderStatus` function and all API calls include the Authorization header (Bearer token from localStorage). With wildcard CORS + credentials, a malicious site can:
1. Make authenticated requests to the Aetheris API
2. Read the responses (including pipeline responses, telemetry data)
3. Access provider health information

---

## 6. XSS & CSRF

### 6.1 XSS Attack Surface

| Vector | Location | Protection | Risk |
|--------|----------|------------|------|
| `dangerouslySetInnerHTML` | `MessageBubble.jsx:102` | Custom highlighter escapes HTML | ⚠️ Depends on highlighter correctness |
| `localStorage` token read | Multiple | Token is string, not rendered as HTML | ✅ |
| User query input | `InputBox.jsx` | Text content, not rendered as HTML | ✅ |
| Markdown rendering | `MessageBubble.jsx:264-271` | `react-markdown` escapes HTML by default | ✅ |
| SSE event data | `client.js:119-134` | `JSON.parse` into object, rendered via React | ✅ |
| Provider names | `App.jsx:192-194` | String, rendered as JSX text | ✅ |

### 6.2 `dangerouslySetInnerHTML` Analysis

```javascript
// MessageBubble.jsx:102
<code dangerouslySetInnerHTML={{ __html: html }} />
```

The `highlight` function in `syntaxHighlight.js` is a custom regex-based tokenizer that produces safe HTML. Key observations:
- The function escapes HTML entities (`&`, `<`, `>`, `"`, `'`) before tokenization (line 24-28)
- It only wraps tokens in `<span>` tags with class names
- No raw user input is included in the output
- Language names are matched against a known list

**Verdict:** The `dangerouslySetInnerHTML` usage is acceptably safe because the highlighter properly escapes HTML before processing. However, any bug in the highlighter could introduce an XSS vulnerability.

### 6.3 CSRF Protection

**Status: 🔴 NONE**

There is no CSRF protection anywhere in the codebase:
- No CSRF tokens
- No `SameSite` cookie attributes (tokens are in localStorage, not cookies)
- No `Origin`/`Referer` header validation
- No custom request headers requirement

**Mitigation:** Because JWTs are stored in `localStorage` (not cookies), CSRF attacks that rely on automatic cookie attachment are not applicable. However, XSS attacks can read localStorage tokens.

### 6.4 XSS via localStorage

**Risk: HIGH** — localStorage is accessible to any JavaScript running on the same origin. An XSS vulnerability in any part of the application would allow an attacker to:
1. Read `access_token`, `refresh_token`, `user_email`
2. Read all conversation history from localStorage
3. Read all settings
4. Impersonate the user by exfiltrating the JWT

---

## 7. Credential & Secret Storage

### 7.1 Frontend: localStorage Tokens

```javascript
// utils/auth.js
const TOKEN_KEY = 'access_token';
const EMAIL_KEY = 'user_email';
const REFRESH_KEY = 'refresh_token';
```

All three values are stored in plaintext in `localStorage`:
- `access_token`: JWT containing user email, valid for 60 minutes
- `refresh_token`: Never used (dead code), but stored
- `user_email`: Plaintext email address

### 7.2 Backend: .env File with Live API Keys

**File:** `.env` (12 lines, root of project)

**9 live API keys committed to the repository:**
| Provider | Key (prefix) | Line |
|----------|-------------|------|
| OpenRouter | `sk-or-v1-...` | 1 |
| NVIDIA NIM | `nvapi-...` | 2 |
| Groq | `gsk_p3...` | 4 |
| GitHub | `github_pat_...` | 5 |
| Mistral | `PohdLX...` | 6 |
| Google | `AQ.Ab8...` | 7 |
| OpenAI | `sk-proj-...` | 8 |
| Kie | `d08787...` | 9 |
| UNLI.dev | `sk-ZOIl...` | 10 |

**Impact:** Each key provides access to paid LLM API services. Total potential cost exposure: thousands of USD per day if abused.

### 7.3 Environment Variable Configuration

`core/config.py` uses `pydantic-settings` with `env_prefix="aetheris_"`:
- API keys: `aetheris_OPENROUTER_API_KEY`, etc.
- JWT secret: `aetheris_JWT_SECRET_KEY`
- Database URL: `DATABASE_URL` (note: no prefix — uses explicit `validation_alias`)

**Issue:** The `JWT_SECRET_KEY` field uses `validation_alias="aetheris_JWT_SECRET_KEY"` (line 75), not the default `AETHERIS_JWT_SECRET_KEY`. Since the model config has `case_sensitive=True`, the env var must be exactly `aetheris_JWT_SECRET_KEY` (lowercase 'a'). If a developer sets `AETHERIS_JWT_SECRET_KEY` (uppercase 'A'), it won't be read and the hardcoded default is used.

---

## 8. Session Management

### 8.1 Backend Session State (ConversationDirector)

`orchestrator/conversation.py`:
- Sessions stored in `self._sessions: dict[str, ConversationSession]` (in-memory only)
- No database persistence
- Lost on server restart

### 8.2 Frontend Conversation State

`useChatStore.js` persists conversations to localStorage:
```javascript
const storageKey = `aetheris.conversations.${email}.v1`;
```

**Issues:**
1. **Divergence from backend (HIGH-008):** The frontend manages conversation history entirely in localStorage. Backend session endpoints exist but are never called from the frontend for history retrieval.
2. **Storage limits:** localStorage is limited to ~5-10MB per origin. Long conversations with many messages could exceed this limit.
3. **No server-side backup:** All conversation history is client-only. Clearing browser data or switching devices loses all conversation history.

### 8.3 Session ID Generation

```python
# server.py:319
session_id = str(uuid.uuid4())
```

A new UUID is generated for every `/api/query` request. These sessions are created but:
- Never persisted to database
- Never associated with the authenticated user
- Frontend never receives the session_id
- No mechanism to retrieve past sessions

---

## 9. Accessibility

### 9.1 Assessment: GOOD

| Feature | Location | Assessment |
|---------|----------|------------|
| Skip link | `index.html:15` | ✅ Hidden skip-to-content link |
| ARIA labels | `AgentStreamCard.jsx`, `MessageBubble.jsx`, `Sidebar.jsx` | ✅ Properly applied |
| Focus trap | `Sidebar.jsx`, `SettingsPanel.jsx`, `TelemetryDrawer.jsx`, `MissionControlPanel.jsx` | ✅ `focus-trap-react` |
| Keyboard navigation | `ChatWindow.jsx` (Ctrl+Home/End), `Sidebar.jsx` | ✅ |
| `role="alert"` | `App.jsx:326`, `MessageBubble.jsx:240` | ✅ Live region for errors |
| `aria-live` | `AgentStreamCard.jsx` | ✅ Polite announcements |
| `prefers-reduced-motion` | `index.css`, `animations.js` | ✅ Global media query |
| `aria-expanded` | `MessageBubble.jsx:285` | ✅ Expand/collapse state |
| Focus visible | `index.css` (cyan outline) | ✅ Custom focus-visible styles |
| Color contrast | Dark theme with high-contrast colors | ✅ |
| Touch targets | `index.css: .touch-target` (min 44px) | ✅ Mobile-friendly |

### 9.2 Issues

1. **No keyboard navigation in Mission Control tabs:** The tab panel uses click handlers without corresponding keyboard event handlers. Users cannot use arrow keys to navigate between tabs.

2. **No `aria-live` region for SSE stream updates:** The streaming pipeline updates agent states but there's no polite announcement region for screen readers to announce new events without interrupting.

3. **No heading hierarchy:** The page structure lacks a clear `<h1>`-`<h6>` hierarchy. The main content area has no `<h1>` landmark. The app title in `Sidebar.jsx` is a `<span>` or `<div>`, not an `<h1>`.

4. **ReasoningGraph SVG lacks `role="img"`:** The interactive SVG graph (ReasoningGraph.jsx) has an `aria-label` on the container but no `role="img"` to identify it as an image for screen readers.

---

## 10. Responsive Design

### 10.1 Assessment: GOOD

| Breakpoint | Behavior | Assessment |
|------------|----------|------------|
| Mobile (< 768px) | Sidebar overlay, full-width content, hamburger menu, mobile labels in PipelineStatus | ✅ |
| Tablet (768-1024px) | Desktop layout, slight padding adjustments | ✅ |
| Desktop (> 1024px) | Full layout with sidebar | ✅ |

### 10.2 Responsive Features

- `Sidebar.jsx`: Mobile overlay with FocusTrap + backdrop, desktop always-visible 280px
- `PipelineStatus.jsx`: Mobile labels, wraps after stage 3
- `MissionControlPanel.jsx`: Full-screen overlay on mobile
- `InputBox.jsx`: Full-width with responsive max-width
- `ChatWindow.jsx`: Adapts message widths (`max-w-[75%]` user, `max-w-[85%]` assistant)

### 10.3 Issues

1. **Mission Control Panel resize not touch-compatible:** The drag-to-resize handle uses `mousedown`/`mousemove`/`mouseup` events without `touchstart`/`touchmove`/`touchend` equivalents. Touch users cannot resize the panel.

2. **Agent card grid collapses at small widths:** The 2-column grid (`grid-cols-1 sm:grid-cols-2`) in MessageBubble.jsx works on mobile but on very narrow screens (320px), agent stream cards become too narrow.

---

## 11. Loading & Error States

### 11.1 Loading States

| Component | Loading State | Assessment |
|-----------|--------------|------------|
| App.jsx | `LoadingFallback` (spinner) for Suspense panels | ✅ |
| ChatWindow.jsx | EmptyState when no messages | ✅ |
| InputBox.jsx | Disabled with spinner when pending | ✅ |
| MissionControlPanel.jsx | Suspense fallback for Graph tab | ✅ |
| Sidebar.jsx | Debounced search, no-results state | ✅ |

### 11.2 Error States

| Component | Error State | Assessment |
|-----------|-------------|------------|
| MessageBubble.jsx | Red border with message + Retry button | ✅ |
| App.jsx | Connection-lost banner (amber) | ✅ |
| App.jsx | Notifications for stage errors | ✅ |
| NotificationStack.jsx | Toast notifications for warnings | ✅ |

### 11.3 Issues

1. **Global error boundary missing:** There is no `ErrorBoundary` wrapping the application. A React rendering crash in any component will unmount the entire app and show a white screen. The `Suspense` boundaries only catch lazy-loaded components.

2. **Network error recovery limited:** The connection-lost banner is purely cosmetic. If the backend is down, the frontend shows the banner but has no automatic reconnection mechanism beyond the 30s health poll.

---

## 12. Streaming & WebSocket Synchronization

### 12.1 SSE Implementation

```javascript
// api/client.js:66-154
const response = await fetch(`${API_BASE_URL}/api/query/stream`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
  body: JSON.stringify(payload),
  signal,
});

const reader = response.body.getReader();
// Read stream chunks, parse SSE data: lines
```

### 12.2 Event Flow

```
Backend emits SSE events:
  agent_started → progress → reasoning_summary → draft_answer → agent_completed → result
                                                                    ↓
Frontend parses via ReadableStream:
  onEvent callback → usePipelineStages hook → agentStates update → React re-render
```

### 12.3 Issues

1. **No WebSocket fallback:** SSE is the only streaming mechanism. If the HTTP connection is interrupted, the entire stream is lost with no recovery mechanism. WebSocket support would provide bidirectional communication and reconnection.

2. **No reconnection logic:** If the stream connection drops mid-response, the frontend treats it as a failure. There is no partial response recovery or automatic reconnection.

3. **Buffer accumulation:** The SSE parser (`client.js:102-138`) reads chunks into a buffer and splits on newlines. If a large payload (e.g., a long reasoning summary) arrives in a single chunk, the buffer could grow large. There is no upper bound on buffer size.

4. **Event ordering assumptions:** The frontend assumes events arrive in order (`agent_started` before `agent_completed`). Out-of-order events could cause incorrect agent state transitions.

---

## 13. Animation System

### 13.1 Assessment: ✅ Well-designed, accessibility-aware

**Animation Library:** Framer Motion 11

**Configuration file:** `utils/animations.js` (283 lines, 52 tests)

**Key features:**
- `prefersReducedMotion()` media query check
- `getTransitionDuration()` — uses 0.01s for reduced motion, normal durations otherwise
- 15 animation variants for different component types
- All animation durations under 300ms (verified by tests)

**Animation Variants:**
| Variant | Duration | Usage |
|---------|----------|-------|
| `panelVariants` | 300ms | Expand/collapse panels |
| `messageVariants` | 350ms | Message fade-in-up |
| `cardExpandVariants` | 250ms | Agent card expand |
| `modalOverlayVariants` | 200ms | Modal backdrop fade |
| `modalContentVariants` | 250ms | Modal scale+fade |
| `slideInRightVariants` | 300ms | Telemetry drawer |
| `slideInLeftVariants` | 300ms | Sidebar |

### 13.2 Issues

1. **CSS animations not respecting reduced motion:** Custom CSS keyframes in `index.css` (`@keyframes shimmer`, `step-reveal`, `thinking-pulse`) are not wrapped in `@media (prefers-reduced-motion: reduce)`. The `prefers-reduced-motion` media query in `index.css` only sets `* { animation-duration: 0.01s !important; }`, but some CSS keyframes use `infinite` which may not be properly overridden by duration alone.

2. **Framer Motion animations bypass CSS reduced-motion:** Framer Motion uses JavaScript-driven animations that respect the `prefersReducedMotion()` hook, but the `useAnimations` hook checks both the user setting and system preference. However, `useAnimations` is only used by `EmptyState.jsx` and `NotificationStack.jsx`. Many components use Framer Motion directly without consulting the animation preference.

---

## 14. Privilege Escalation

### 14.1 User Roles

**Status: 🔴 NONE**

There is no role-based access control (RBAC) in the application:
- No admin/regular user distinction
- No permission system
- No scope or role in JWT claims
- All authenticated users have full access to all endpoints

### 14.2 API Protection

All API endpoints use `Depends(get_current_user)` for authentication but no additional authorization checks. Any authenticated user can:
- Access any session (sessions are in-memory and not user-scoped)
- Access any checkpoint
- View provider health
- View telemetry
- Trigger provider recovery

### 14.3 Session Isolation

**Status: 🔴 NONE**

Sessions in `ConversationDirector` are not associated with any user. Any authenticated user could potentially access another user's session if they knew the session ID. However, the frontend never exposes session IDs to other users.

---

## 15. Issue Register

### SEC-001: CORS Wildcard with Credentials

| Field | Value |
|-------|-------|
| **Severity** | Critical |
| **File** | `server.py` |
| **Lines** | 148-154 |
| **Function** | `app.add_middleware(CORSMiddleware)` |
| **Description** | CORS middleware configured with `allow_origins=["*"]` AND `allow_credentials=True`. This violates the CORS specification — credentialed requests cannot use wildcard origins. FastAPI's implementation sends both headers, allowing any site to make authenticated requests and read responses. |
| **Evidence** | `allow_origins=["*"]` at line 150, `allow_credentials=True` at line 151. All API calls include Bearer token from localStorage. |
| **Impact** | Any website can make cross-origin authenticated requests to the Aetheris API. A malicious site visited while a user is logged into Aetheris can exfiltrate pipeline results, telemetry, and provider health data. |
| **Root Cause** | Developer used permissive CORS settings for local development without restricting for production. |
| **Suggested Resolution** | Set `allow_origins` to the specific frontend origin(s) in production. Remove `allow_credentials=True` when using wildcard. Use environment variable for origins list. |
| **Verification** | Send a cross-origin fetch with `credentials: "include"` from a different origin; observe the response headers `Access-Control-Allow-Origin: *` and `Access-Control-Allow-Credentials: true`. |

---

### SEC-002: Hardcoded Default JWT Secret Key

| Field | Value |
|-------|-------|
| **Severity** | Critical |
| **File** | `core/config.py` |
| **Lines** | 73-77 |
| **Function** | `aetherisConfig` class |
| **Description** | The `JWT_SECRET_KEY` field has a hardcoded default value: `"09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7"`. This value is used if the environment variable `aetheris_JWT_SECRET_KEY` is not set. Since the key is in the source code, anyone with access to the repository can forge valid JWTs. |
| **Evidence** | `core/config.py:73-77`: `JWT_SECRET_KEY: str = Field(default="09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7")`. The `.env` file does not set `aetheris_JWT_SECRET_KEY`. |
| **Impact** | Any developer who can read the source code (or anyone who obtains it) can forge JWTs with arbitrary `sub` claims, gaining access to any user account. Since all API endpoints require `get_current_user`, an attacker with a forged token can access all data. |
| **Root Cause** | Default value included for development convenience; no production configuration validation enforces a custom secret. |
| **Suggested Resolution** | Remove the default value; use `Field(default="")` or `Field(default=None)`. Add startup validation that raises if `JWT_SECRET_KEY` is the default or empty. Enforce via environment variable. |
| **Verification** | Run the server without setting `aetheris_JWT_SECRET_KEY`. Check logs for warnings. Decode a generated JWT using the default secret. |

---

### SEC-003: API Keys Committed to Repository

| Field | Value |
|-------|-------|
| **Severity** | Critical |
| **File** | `.env` |
| **Lines** | 1-12 |
| **Description** | 9 live API keys for paid LLM services (OpenRouter, NVIDIA NIM, Groq, GitHub, Mistral, Google, OpenAI, Kie, UNLI.dev) are stored in the `.env` file in the repository root. While `.env` is gitignored, the file exists on disk and could be accidentally committed, shared, or exposed. |
| **Evidence** | Full keys visible in `.env` (see section 7.2). Each key is a valid, live credential. |
| **Impact** | Potential financial loss from unauthorized API usage. Each key provides access to paid LLM services with usage-based billing. Combined cost exposure could exceed thousands of USD per day. |
| **Root Cause** | Development convenience — keys placed in `.env` for local testing. |
| **Suggested Resolution** | Immediately rotate all 9 API keys at their respective providers. Remove real keys from `.env` and replace with empty strings. Use `.env.example` with placeholder values. |
| **Verification** | Check if any keys have been committed to git history. Verify key rotation at each provider. Confirm `.env` is in `.gitignore`. |

---

### SEC-004: JWT Stored in localStorage (XSS-Vulnerable)

| Field | Value |
|-------|-------|
| **Severity** | High |
| **File** | `aetheris-ui/src/utils/auth.js` |
| **Lines** | 1-55 |
| **Description** | JWT access token, refresh token, and user email are stored in `localStorage` in plaintext. localStorage is accessible to any JavaScript executing on the same origin. If any XSS vulnerability exists in the application, tokens can be exfiltrated. |
| **Evidence** | `setToken(token)` at line 11 writes to `localStorage.setItem(TOKEN_KEY, token)`. `getToken()` at line 7 reads from localStorage. All Axios requests attach this token via interceptor (api/client.js:13-22). |
| **Impact** | XSS + localStorage JWT exfiltration allows complete account takeover. The attacker can impersonate the user for the full 60-minute token lifespan. |
| **Root Cause** | SPA pattern where `httpOnly` cookies cannot be used because the frontend is served from a different origin than the API (different ports in dev). |
| **Suggested Resolution** | Use `httpOnly` secure cookies with `SameSite=Strict` for JWT storage. Serve frontend and API from the same origin in production. If cross-origin is required, use a BFF (Backend for Frontend) pattern. As a mitigation, implement short-lived tokens (5-15 min) with refresh token rotation. |
| **Verification** | Check that JWT is accessible via `document.cookie` after switching to httpOnly cookies. Verify that XSS via console no longer exposes the token. |

---

### SEC-005: No CSRF Protection

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **File** | (project-wide) |
| **Lines** | — |
| **Description** | No CSRF protection exists anywhere in the project. There are no CSRF tokens, no SameSite cookie attributes, no Origin/Referer validation, and no custom headers requirement. |
| **Evidence** | Search for "csrf", "xsrf", "sameSite", "SameSite" across all files — zero results. CORS middleware allows all origins (`["*"]`). |
| **Impact** | While localStorage-based JWTs are not automatically sent by browsers (mitigating standard CSRF), if a token is moved to cookies (as recommended by SEC-004), CSRF protection becomes essential. Any `GET` endpoint could be exploited via `<img>` tags. |
| **Root Cause** | CSRF protection was never implemented because the current localStorage-based auth is not vulnerable to traditional CSRF. |
| **Suggested Resolution** | If moving to cookie-based auth: (1) Set `SameSite=Strict` or `SameSite=Lax` on auth cookies. (2) Implement CSRF tokens for state-changing endpoints. (3) Validate `Origin` or `Referer` headers for all POST/PUT/DELETE requests. |
| **Verification** | After implementing cookie auth, confirm that a cross-origin form submission fails to authenticate. |

---

### SEC-006: Token Refresh Mechanism Dead Code

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **File** | `aetheris-ui/src/utils/auth.js` |
| **Lines** | 22-28 |
| **Description** | `getRefreshToken()` and `setRefreshToken()` functions exist but are never called anywhere in the codebase. The login page stores a `refresh_token` from the login response, but no code ever uses it to refresh an expired access token. |
| **Evidence** | `setRefreshToken` is only called in `aetheris_login.html` and `aetheris-ui/public/login.html`. No code calls `getRefreshToken()`. The `refresh_token` is stored but never consumed. |
| **Impact** | When the access token expires (after 60 minutes), the user is logged out with no way to automatically refresh. This causes an abrupt interruption during long pipeline runs or extended usage sessions. |
| **Root Cause** | Refresh token infrastructure was started but never completed. |
| **Suggested Resolution** | Implement token refresh flow: (1) Backend: add `/auth/refresh` endpoint that validates refresh tokens. (2) Frontend: Axios response interceptor catches 401, silently refreshes via refresh token, retries original request. (3) Rotate refresh tokens on each use. |
| **Verification** | After implementation, verify that a 401 response triggers an automatic refresh and retry without user interruption. |

---

### SEC-007: No Input Validation on Login (Server-Side Only)

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **File** | `server.py`, `aetheris_login.html` |
| **Lines** | 265-303 |
| **Function** | `register_user`, `login_user` |
| **Description** | The registration endpoint stores whatever `req.email` and `req.password` are provided. There is no validation for password strength, email format (beyond database string length), or rate-limiting on login attempts. The login page does client-side validation only. |
| **Evidence** | `server.py:277-279`: `hashed = hash_password(req.password); new_user = User(email=req.email, password_hash=hashed)`. No strength requirements or format checks. |
| **Impact** | Weak passwords (e.g., "password", "123456") can be used. Brute-force attacks are not rate-limited. Account enumeration is possible via the registration endpoint (returns "Email already registered"). |
| **Root Cause** | Authentication was implemented as a basic MVP without security hardening. |
| **Suggested Resolution** | (1) Add password strength requirements (min length, complexity). (2) Add email format validation. (3) Implement rate limiting on login/register endpoints. (4) Return generic error messages to prevent account enumeration. |
| **Verification** | Attempt to register with password "a" — verify it's rejected. Attempt to brute-force with 100 requests in 60 seconds — verify rate limiting. |

---

### SEC-008: No HTTPS/TLS Configuration

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **File** | `server.py`, `aetheris-ui/vite.config.js` |
| **Lines** | — |
| **Description** | The server runs on plain HTTP (uvicorn) with no TLS/SSL configuration. The Vite dev server also runs on plain HTTP (port 5173). Passwords and tokens are transmitted in cleartext over the network. |
| **Evidence** | `server.py` uses `uvicorn.run(app, ...)` without SSL context. `vite.config.js` has no `server.https` option. The API base URL defaults to `http://localhost:8000`. |
| **Impact** | On any network path (Wi-Fi, VPN, corporate network), credentials and tokens can be intercepted via packet capture. This is especially critical in development environments on untrusted networks. |
| **Root Cause** | TLS was never configured — assumed for local development only. |
| **Suggested Resolution** | (1) Add support for TLS certificates via environment variables. (2) Use self-signed certificates for development with `mkcert`. (3) Document TLS configuration for production. |
| **Verification** | Use Wireshark or browser dev tools to verify that login credentials are transmitted in cleartext over HTTP. |

---

### SEC-009: No Rate Limiting on Auth Endpoints

| Field | Value |
|-------|-------|
| **Severity** | High |
| **File** | `server.py` |
| **Lines** | 265-303 |
| **Function** | `register_user`, `login_user` |
| **Description** | There is no rate limiting on authentication endpoints. The `ResourceManager` rate-limits provider API calls, but the auth routes have no protection against brute-force attacks. |
| **Evidence** | No middleware or decorator on `/auth/register` or `/auth/login`. The `ResourceManager` (rate_limiter.py) only controls provider API concurrency, not HTTP route rate limiting. |
| **Impact** | An attacker can perform unlimited brute-force password guessing against user accounts. Account enumeration is possible via the registration endpoint. |
| **Root Cause** | Auth rate limiting was overlooked during implementation. |
| **Suggested Resolution** | (1) Add FastAPI middleware for rate limiting on auth routes (e.g., `slowapi`). (2) Implement IP-based rate limiting: 5 attempts per minute per IP. (3) Add account lockout after 10 failed attempts. |
| **Verification** | Send 20 rapid login requests with invalid credentials — verify that requests after the 5th are rate-limited. |

---

### SEC-010: No Session/User Isolation

| Field | Value |
|-------|-------|
| **Severity** | High |
| **File** | `orchestrator/conversation.py`, `server.py` |
| **Lines** | `conversation.py:92`, `server.py:319-332` |
| **Description** | Conversation sessions are not associated with any user. The `ConversationDirector` stores sessions in a flat dictionary with no user ownership. Any authenticated user with a session_id can access any session. Additionally, the `session_id` is a plain UUID v4 with no HMAC signing. |
| **Evidence** | `conversation.py:92`: `self._sessions: dict[str, ConversationSession]` — no user_id field in the lookup. `server.py:319`: `session_id = str(uuid.uuid4())` — no user context attached. |
| **Impact** | If an attacker obtains another user's session_id (via XSS, log leakage, or brute-force), they can access that user's conversation history, checkpoints, and pipeline state. |
| **Root Cause** | Session isolation was not implemented because sessions are in-memory and considered ephemeral. |
| **Suggested Resolution** | (1) Attach `user_id` to every session upon creation. (2) Add authorization check in every session-related endpoint: `session.user_id == current_user.id`. (3) Sign session IDs with HMAC to prevent tampering. |
| **Verification** | Create a session as user A, then attempt to access it as user B (by manipulating the session_id) — verify it's rejected. |

---

### SEC-011: No Role-Based Access Control

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **File** | `core/security.py`, `server.py` |
| **Lines** | `security.py:340-367`, `server.py:308+` |
| **Description** | There is no role system in the application. All authenticated users have access to all endpoints, including provider recovery (`POST /api/providers/{name}/recovery`) and telemetry (`GET /api/telemetry`). The JWT token contains only a `sub` claim with the email. |
| **Evidence** | JWT payload (security.py:335): `to_encode.update({"exp": expire})` — only `sub` and `exp` claims. No `role`, `scope`, or `permissions` claim. All API routes use only `Depends(get_current_user)` with no additional authorization. |
| **Impact** | Any authenticated user can trigger provider recovery (a potentially disruptive operation), view telemetry for all users, and access any checkpoint. |
| **Root Cause** | RBAC was deferred as a Phase 2 feature. |
| **Suggested Resolution** | (1) Add a `role` column to the User model (e.g., "admin", "user", "viewer"). (2) Add role to JWT claims. (3) Create a `require_role()` dependency for sensitive endpoints. (4) Restrict provider recovery and telemetry to admin role. |
| **Verification** | After implementation, verify that a regular user receives 403 on `/api/providers/{name}/recovery` while an admin succeeds. |

---

### FNT-001: No React Error Boundary

| Field | Value |
|-------|-------|
| **Severity** | High |
| **File** | `aetheris-ui/src/App.jsx` |
| **Lines** | 117-387 |
| **Description** | The entire application is wrapped in a single React root with no error boundary. If any component throws during rendering (e.g., a null reference in agent state processing), the entire React tree unmounts and the user sees a white screen. Only `Suspense` boundaries exist for lazy-loaded components, but these only catch loading errors, not render errors. |
| **Evidence** | No `ErrorBoundary` class component or `react-error-boundary` import is present. Only `Suspense` is used for lazy-loaded components (App.jsx:355, 370, 380). |
| **Impact** | A single unhandled rendering error in any of the 23+ components causes a complete UI failure with no recovery mechanism. The user must refresh the page. |
| **Root Cause** | Error boundaries require class components; functional components cannot implement `componentDidCatch`. This was likely overlooked. |
| **Suggested Resolution** | Create a React error boundary class component with: (1) Fallback UI with error details (safe to display). (2) "Reload" button. (3) Error logging to console/telemetry. Wrap the entire app tree in this boundary. |
| **Verification** | Temporarily throw an error in a component's render — verify the error boundary catches it and shows a fallback UI instead of a white screen. |

---

### FNT-002: Auth Check Not Server-Verified on Mount

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **File** | `aetheris-ui/src/App.jsx` |
| **Lines** | 118, 152-156 |
| **Description** | The authentication check on application mount (`useState(() => isAuthenticated())`) only checks for the presence of a token string in localStorage. It does not verify token validity with the server. An expired, malformed, or forged token passes the client-side check, and the UI renders fully before failing on the first API call. |
| **Evidence** | `App.jsx:118`: `const [authed, setAuthed] = useState(() => isAuthenticated());` — only checks `!!getToken()`. No API call to validate the token. `client.js:26-31`: 401 is only caught on actual API responses. |
| **Impact** | Users with expired tokens see a brief flash of the full UI before redirecting to login. The app makes at least one API call (health poll) before detecting token invalidity. |
| **Root Cause** | Client-only auth check for UX speed, without server validation. |
| **Suggested Resolution** | (1) On mount, make a lightweight authenticated API call (e.g., `GET /api/me` or the health endpoint) to validate the token. (2) While validating, show a loading state. (3) If validation fails, redirect to login immediately without rendering the full UI. |
| **Verification** | Set an expired token in localStorage and refresh the page — verify that the app detects invalidity before rendering the main UI. |

---

### FNT-003: ReasonGraph Built on Every Render

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **File** | `aetheris-ui/src/App.jsx` |
| **Lines** | 78-107, 297 |
| **Description** | `buildGraphData` is called on every render of App.jsx via `useMemo` with `agentStates` as dependency. This function iterates all agent states and constructs graph node/edge objects. While `useMemo` prevents re-computation when agentStates doesn't change, the function is relatively expensive and runs whenever agentStates updates (which can be multiple times per second during streaming). |
| **Evidence** | `App.jsx:78-107`: `buildGraphData` creates node/edge arrays with nested loops. `App.jsx:297`: `const graphData = useMemo(() => buildGraphData(agentStates), [agentStates])`. |
| **Impact** | During active streaming (agent states updating frequently), `buildGraphData` runs on every agent state update, consuming CPU cycles unnecessarily. The graph data is only consumed by `ReasoningGraph` inside `MissionControlPanel`. |
| **Root Cause** | The graph data is derived eagerly instead of being computed lazily when the graph tab is opened. |
| **Suggested Resolution** | (1) Move graph data computation into `MissionControlPanel` and compute it only when the Graph tab is active. (2) Or wrap in a `useMemo` with deeper equality check. (3) Or compute lazily via `useRef` that only recomputes when explicitly requested. |
| **Verification** | Add console.log inside `buildGraphData` and observe it running during streaming when the Mission Control Panel is closed. |

---

### FNT-004: Two Duplicate Login Pages

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **File** | `aetheris_login.html`, `aetheris-ui/public/login.html` |
| **Lines** | 788, 432 |
| **Description** | There are two separate login page implementations: one at the repository root (`aetheris_login.html`, 788 lines) served by the backend at `/login`, and one inside the frontend static directory (`aetheris-ui/public/login.html`, 432 lines). Both implement similar functionality but with different API endpoints and different code. |
| **Evidence** | `server.py:256-262`: serves `aetheris_login.html` at `/login`. `aetheris-ui/public/login.html`: static file, not served by backend. The root-level login has Sign In/Sign Up toggle; the frontend one has separate forms. |
| **Impact** | Duplicate code must be maintained in parallel. Bug fixes must be applied to both. Different API paths (`/auth/login` vs `/api/auth/login`) create confusion. The `/login` route path differs from the `/api/auth/login` API path. |
| **Root Cause** | Login page was created outside the frontend build pipeline before the Vite app was complete. |
| **Suggested Resolution** | (1) Integrate login into the Vite React app as a proper React component. (2) Serve the Vite-built login page from the backend. (3) Remove the root-level `aetheris_login.html` file. (4) Remove the static `public/login.html` file. |
| **Verification** | After migration, verify that `/login` returns the Vite-built React login page. Verify login, registration, and token storage all work. |

---

### FNT-005: Pipeline Stage Notification Race

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **File** | `aetheris-ui/src/App.jsx` |
| **Lines** | 236-245 |
| **Description** | The error notification effect checks `prevStage.current !== 'error' && stage === 'error'` to trigger a notification. However, during rapid state transitions (e.g., error → idle → error), the comparison may miss state changes because the `prevStage` ref is updated synchronously but state updates are async. |
| **Evidence** | `App.jsx:236-245`: useEffect with `stage` dependency. The `prevStage.current = stage` update at line 244 runs inside the effect, which may execute after React has already queued the next state change. |
| **Impact** | Some pipeline error notifications may be missed during rapid state transitions. The "Connection restored" notification may fire when the connection was never claimed lost. |
| **Root Cause** | Race between React state updates and the ref-based comparison. |
| **Suggested Resolution** | Use a reducer for state machine transitions instead of effect-based derivation. Or debounce the stage-derived notifications with a short delay. |
| **Verification** | Simulate rapid pipeline failures (error → idle → error) and verify both error notifications appear. |

---

### FNT-006: SSE Buffer No Size Limit

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **File** | `aetheris-ui/src/api/client.js` |
| **Lines** | 102-138 |
| **Function** | `streamQuery` |
| **Description** | The SSE parser accumulates data in a `buffer` string with no upper bound. If the server sends a very large message (e.g., a multi-megabyte response), the buffer could consume excessive memory. The backend has a 64KB payload limit (`PAYLOAD_LIMIT_BYTES = 65536`), but the frontend does not enforce a corresponding limit. |
| **Evidence** | `client.js:104`: `let buffer = '';` — unbounded string. `client.js:110`: `buffer += decoder.decode(value, { stream: true })` — accumulates without size check. |
| **Impact** | A misconfigured or malicious backend could cause the frontend to accumulate a large buffer, consuming memory and potentially causing performance degradation. |
| **Root Cause** | No frontend-side validation of incoming data size. |
| **Suggested Resolution** | Add a maximum buffer size (e.g., 1MB) to the SSE parser. If exceeded, close the connection and reject with an error. |
| **Verification** | Send a response larger than 1MB from the backend — verify the frontend closes the connection and shows an error. |

---

### FNT-007: No Keyboard Navigation in Mission Control Tabs

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **File** | `aetheris-ui/src/components/MissionControlPanel.jsx` |
| **Lines** | — |
| **Description** | The tab panel in MissionControlPanel uses click handlers without arrow key navigation. Keyboard users cannot navigate between tabs using Left/Right arrow keys, violating WAI-ARIA tabs pattern. |
| **Evidence** | The tab implementation uses `onClick` for tab switching but has no `onKeyDown` handler for arrow keys. No `role="tab"`, `role="tablist"`, or `role="tabpanel"` attributes. |
| **Impact** | Keyboard-only users cannot navigate between Pipeline, Agents, Timeline, Graph, and Metrics tabs without using focus order to reach each tab button. |
| **Root Cause** | ARIA tabs pattern not implemented. |
| **Suggested Resolution** | (1) Add `role="tablist"` to the tab container with Left/Right arrow key handlers. (2) Add `role="tab"` with `aria-selected` to each tab button. (3) Add `role="tabpanel"` with `aria-labelledby` to each panel. (4) Implement roving tabindex for focus management. |
| **Verification** | Navigate to the tab bar using keyboard, press Left/Right arrow keys — verify tabs switch without mouse interaction. |

---

### FNT-008: No Heading Hierarchy

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **File** | `aetheris-ui/src/App.jsx`, `aetheris-ui/src/components/Sidebar.jsx` |
| **Lines** | — |
| **Description** | The application lacks a clear heading hierarchy. The "Aetheris" branding in the sidebar is likely a `<div>` or `<span>`, not an `<h1>`. The main content area has no heading. Screen reader users navigating by headings will find no structure to orient themselves. |
| **Evidence** | Sidebar.jsx renders the Aetheris logo and text. No `<h1>` through `<h6>` tags are used in the main page layout. Chat messages and panel titles are typically `<div>` or `<button>` elements. |
| **Impact** | Screen reader users cannot quickly navigate between sections of the application. The page has no landmark headings to identify the main content, sidebar, or panels. |
| **Root Cause** | Heading hierarchy was not considered during component design. |
| **Suggested Resolution** | (1) Add `<h1>Aetheris</h1>` to the sidebar branding. (2) Add `<h2>` headings for each panel/section. (3) Ensure heading levels are sequential and properly nested. |
| **Verification** | Use a screen reader's heading navigation (e.g., NVDA's H key) to traverse the page — verify all major sections are reachable via headings. |

---

### FNT-009: CSS Animations Not Fully Respecting Reduced Motion

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **File** | `aetheris-ui/src/index.css` |
| **Lines** | ~430-440 |
| **Description** | While the `@media (prefers-reduced-motion: reduce)` media query sets `* { animation-duration: 0.01s !important; }`, this may not properly override CSS keyframe animations that use `infinite` duration. Some browsers handle this differently, and the shimmer/thinking-pulse animations may continue animating. The `useAnimations` hook correctly checks preferences, but many components don't use it. |
| **Evidence** | `index.css` has `@keyframes shimmer`, `@keyframes thinking-pulse` with `animation: shimmer 2.2s infinite linear` and `animation: thinking-pulse 2s ease-in-out infinite`. The reduced-motion override uses `animation-duration` only, not `animation-play-state: paused` or removing the animation entirely. |
| **Impact** | Users who prefer reduced motion may still see pulsing/spinning animations in some components during streaming. This can cause vestibular discomfort. |
| **Root Cause** | Incomplete CSS reduced-motion implementation. The Framer Motion hook handles JS animations correctly, but CSS animations have a different override path. |
| **Suggested Resolution** | In the `prefers-reduced-motion` media query, add: (1) `animation-iteration-count: 1` for infinite animations. (2) `animation-fill-mode: forwards` to keep the final state. (3) Or set `animation: none !important` and provide static fallback classes. |
| **Verification** | Enable `prefers-reduced-motion: reduce` in browser dev tools — verify all CSS animations stop completely, not just slow down. |

---

## Summary Statistics

| Category | Issues | Critical | High | Medium | Low |
|----------|--------|----------|------|--------|-----|
| Authentication & JWT | 3 | 1 | 1 | 1 | 0 |
| CORS | 1 | 1 | 0 | 0 | 0 |
| Secrets & Credentials | 1 | 1 | 0 | 0 | 0 |
| CSRF & XSS | 2 | 0 | 1 | 1 | 0 |
| Session Management | 2 | 0 | 1 | 1 | 0 |
| Access Control | 2 | 0 | 1 | 1 | 0 |
| TLS/Rate Limiting | 2 | 0 | 1 | 1 | 0 |
| Frontend Resilience | 2 | 0 | 1 | 1 | 0 |
| Performance | 1 | 0 | 0 | 0 | 1 |
| UX/Responsive | 3 | 0 | 0 | 1 | 2 |
| Accessibility | 3 | 0 | 0 | 0 | 3 |
| **Total** | **22** | **3** | **6** | **6** | **7** |
