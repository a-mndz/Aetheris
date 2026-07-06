# AETHERIS — Bug & Issues Audit

> Comprehensive read-only audit of the AETHERIS codebase (Python backend + frontend + configuration).
> Source files were NOT modified during this audit.

---

## P0 — Critical (fix immediately)

### Security

1. **`.env` contains 9 live API keys** (`OPENROUTER`, `NVIDIA_NIM`, `GROQ`, `GITHUB_TOKEN`, `MISTRAL`, `GOOGLE`, `OPENAI`, `KIE`, `UNLI_DEV`, plus `JWT_SECRET_KEY`). `core/config.py:41-56` refuses to start the app if these are present (`LEAKED_KEY_PREFIXES` check). Rotate all keys, remove `.env` from git history, add to `.gitignore`, ship `.env.example`.
2. **CSRF middleware accepts Origin-less requests** (`server.py:185-204`). State-changing POSTs without `Origin` or `Referer` are silently allowed. Reject with 403.
3. **JWT also stored in `localStorage`** (`aetheris-ui/src/utils/auth.js`, `aetheris_login.html`) — defeats the httpOnly cookie model and enables XSS-driven token theft.
4. **`reconstruct.py:1-28`** silently overwrites `api_gateway/rate_limiter.py` from `recovered_rate_limiter.txt` on any invocation. No backup, no confirmation, no dry-run. Quarantine or guard behind `if __name__ == "__main__"`.

### Correctness

5. **Streaming `fetch()` missing `credentials: 'include'`** (`aetheris-ui/src/api/client.js:98-117`) — auth cookie never sent on the SSE stream.
6. **`useSendQuery.js:65-104`** — aborted runs silently marked `done`, missing/null branch causes `assistant` turn to commit with no content.
7. **Provider status contract mismatch** — backend returns `{provider, status: "healthy"|"degraded"|"dead"}`, frontend (`App.jsx:196-209`) expects `{name, status: "online"|...}` → all providers render "unknown".
8. **`InputBox.jsx:13-26`** — `useEffect` deps include `onPreservedTextConsumed` (new closure each render), wiping preserved text early in an infinite loop.

## P1 — High

### Backend bugs

9. **`server.py:62,148-151`** — `StreamingManager()` instantiated at module import time; lifespan re-binds dict but not the manager → two coexisting managers.
10. **`server.py:176-214`** — Function-style middleware registered before `app.add_middleware(CORSMiddleware)` → CORS runs *before* CSRF (FastAPI stacks in reverse order).
11. **`server.py:124-137`** — `Base.metadata.create_all` runs on every boot, racing Alembic migrations. Drop it.
12. **`server.py:485-510`** — Wrong/missing error shapes: 504 timeout returns empty `agent_outputs`; 500 path leaves `confidence_score` unset. Frontend misreads as success.
13. **`server.py:514-608`** — SSE has no `wait_for` on the generator; misbehaving pipelines can hold connections open indefinitely (only `cleanup_stale_streams` catches it every 5 min).
14. **`api_gateway/client.py:107-123`** — Blocking `open(...).write(...)` inside async `post_request` blocks the event loop on every model call.
15. **`api_gateway/rate_limiter.py:286-291`** — Circuit-breaker race: OPEN→HALF_OPEN transition re-opens on first failure after cooldown, so HALF_OPEN is never exercised.
16. **`api_gateway/rate_limiter.py:632-678`** — `acquire_resources` uses `timeout=0.001` (1ms) → under any contention the rate-limit path is effectively dead. Path raises 500 instead of queueing.
17. **`api_gateway/rate_limiter.py:741-784`** — `get_resource_metrics` returns `0` whenever semaphore has `_value` (always); `maxlen` is reassigned every call.
18. **`orchestrator/checkpoints.py:358-392`** — `existing_q.scalar_one_or_none()` called on a `Result`, not the awaited value (line 370). Need `result = await session.execute(...); existing = result.scalar_one_or_none()`.
19. **`orchestrator/evaluation.py:24-114`** — `arbitrate_and_synthesize` bypasses `RuntimeEngine.execute_with_contracts` — judge synthesis has no rate-limiting, security validation, or streaming events.
20. **`orchestrator/decisions.py:520-544`** — `_execute_parallel` doesn't cancel underlying provider tasks on `TimeoutError`; semaphore permits held after pipeline returns.
21. **`orchestrator/streaming.py:177-251`** — `emit_event` `get_nowait`/`put_nowait` not atomic → two events can be dropped on overflow.
22. **`orchestrator/pipelines.py:911-923`** — `_mark_conversation_failed` silently keeps previous session's metadata on internal error → wrong session attributed to a failed run.
23. **`orchestrator/conversation.py:207-209`** — `add_turn` trims `history` but never decrements `total_tokens` → `remaining_capacity` grows over time, encouraging over-context.
24. **`orchestrator/decisions.py:269-274`** — `GENERATION_COMPLETED` fired even when both agents failed; frontend masks failure as success.
25. **`orchestrator/reasoning_graph.py:124-165`** — `record_failure_pattern` adds O(N) `FAILS` edges per failure → O(N²) edges after N failures, `expire_old_patterns` ignores edge count.
26. **`core/runtime.py:295-317`** — Fire-and-forget `asyncio.create_task(self.streaming_manager.emit_event(...))` with no exception handler.
27. **`core/passport.py:307-339`** — `log_final_state` uses blocking `time.sleep` inside `asyncio.run` → blocks loop up to 3s.
28. **`core/database.py:19`** — `ssl=True` enables TLS but does not verify server cert (no `sslrootcert`).
29. **`telemetry/observer.py:36-39`** — `MODEL_PRICING` substring match is order-dependent: `gpt-4o` matches `gpt-4o-mini` first → wrong billing.
30. **`server.py:378-380`** — Auth cookie `secure=False` hard-coded; even on HTTPS, will be sent over HTTP if user types `http://`.
31. **`server.py:417-423`** — `/auth/logout` doesn't invalidate JWT server-side; valid for up to 60 min after logout. Also lacks auth check.
32. **`server.py:426-441`** — `/auth/refresh` has no rate limit; stolen cookie allows unlimited refresh.
33. **`server.py:251-255`** — Password strength check `len(set(value)) < 3` accepts `"aaabbb"`, `"abcabc"`.
34. **`server.py:917-950`** — SPA catch-all serves any file under `WEB_DIR` (including `.map`, possible `.env`); no extension allowlist, no `..` guard.
35. **`server.py:237-243`** — Hand-rolled email validator accepts `"@"`, `"@example.com"` (no local part).
36. **`server.py:62`** — `_streaming_mgr` module-global leaks across lifespan restarts.
37. **`migrations/versions/001_initial_schema.py:38`** — Index declared `unique=False` while model declares `unique=True` → double-index cost on `users.email`.
38. **`migrations/env.py:48-52`** — Requires `JWT_SECRET_KEY` to be set before running alembic; brittle.

### Frontend bugs

39. **`public/login.html`** — calls `/api/auth/login`; backend exposes `/auth/login` → login form is broken.
40. **`MessageBubble` `memo`** — misses `partialData` dep → every streaming event re-renders every message.
41. **`ChatWindow`** — `FixedSizeList` for variable-height bubbles → overlap/overflow.
42. **`usePipelineStages.js:184`** — judge agent event dropped from `setPartialData`.
43. **`syntaxHighlight.js`** — uses `dangerouslySetInnerHTML`; currently safe but fragile.
44. **Hardcoded URLs** in `aetheris-os-app/` and `new ui/` directories (look for `localhost` / `127.0.0.1` references).

### Dependencies / config

45. **`aetheris-os-app/package.json`** — specifies **non-existent npm versions** (`vite ^8.1.0`, `typescript ~6.0.2`, `lucide-react ^1.22.0`, `@types/node ^24.13.2`) — `npm install` will fail.
46. **`requirements.txt`** — unpinned, outdated `passlib[bcrypt]`, `python-jose`; `passlib` not imported anywhere (dead weight).
47. **`pytest.ini:15-16`** — `event_loop` fixture deprecated in pytest-asyncio 0.21+.
48. **`.ruff.toml`** and `pytest.ini` lack coverage config despite `.coverage` artifact existing at root.

## P2 — Medium

- `orchestrator/conversation.py:373-422` — manual `expires_at` can purge ACTIVE sessions.
- `orchestrator/background_tasks.py:177-188` — `cancel_background_tasks` lacks timeout → can hang shutdown.
- `core/security.py:174-180` — `_LOGGED_KEY_PREFIXES` whitelist misses newer providers (Cohere `co-…`, Replicate `r8_…`).
- `core/security.py:325-337` — JWT has no `iss`/`aud`/`jti`.
- `core/schemas.py:128-194` — `overall_confidence` accepts numeric or string; Pydantic strict mode fails on mixed.
- `orchestrator/pipelines.py:599-635` — unbounded `agent_queue`, slow agent fills queue, no back-pressure; consumer `await agent_queue.get()` can block forever on cancel.
- `orchestrator/checkpoints.py:155-181` — JSON-serializes `agent_outputs` twice (size estimate + truncation check) → ~10MB of JSON per 5MB save.
- `orchestrator/reasoning_graph.py:215-220` — recomputes 26-dim placeholder embedding on every `find_similar_nodes`.
- `orchestrator/memory.py:39-54` — substring containment over full deque, O(N×M), false positives (`"what"` matches `"whatever"`).
- `orchestrator/memory_manager.py:90-101` — `int(words*1.3)` truncates → off-by-one per call.
- `api_gateway/client.py:152` — 500ms injected latency on every simulated call; no test bypass.
- `main.py:279-285` — `AllModelsExhaustedError` caught and loop continues without re-raising; `passport.log_final_state` skipped.

## P3 — Test gaps (zero coverage on critical paths)

- `tests/test_pipeline.py` (36 lines) — no actual `run_micro_mode` end-to-end test.
- No tests for: `orchestrator/streaming.py`, `api_gateway/client.py`, `orchestrator/reasoning_graph.py`, `core/runtime.py:execute_with_contracts`, `orchestrator/background_tasks.py`, `orchestrator/claims.py`, `core/passport.py:enforce_timeout`, SSE streaming pipeline, `/api/query` integration, password edge cases, `Secure` cookie flag.
- `tests/conftest.py:31` — `DATABASE_URL` default points to non-existent Postgres; tests importing `server.py` directly fail.

---

## Suggested fix order (top 10)

1. Rotate all `.env` secrets; remove from git history; ship `.env.example`; add to `.gitignore`.
2. Guard or delete `reconstruct.py`.
3. Fix CSRF middleware (reject Origin-less state-changing requests + reorder so CSRF runs outermost).
4. Remove `localStorage` JWT writes; rely on httpOnly cookie only.
5. Add `credentials: 'include'` to streaming `fetch`.
6. Fix `useSendQuery.js` run-result branching (B12 — aborted → not `done`).
7. Fix provider status field/enum mismatch in `App.jsx`.
8. Fix `InputBox.jsx` `useEffect` deps.
9. Repin `aetheris-os-app/package.json` to real npm versions.
10. Drop `Base.metadata.create_all` from `server.py` lifespan; rely on Alembic.