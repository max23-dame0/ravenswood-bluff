# CLAUDE.md — Programming Agent Guide for Ravenswood Bluff

> **Purpose**: This document is the single entry point for any programming agent (Claude, Codex, Gemini, etc.) to understand, navigate, and contribute to this project. It is designed to be reusable, traceable, and kept up-to-date.
>
> **Last updated**: 2026-05-08 | **Current phase**: Alpha 1.1 M5 Done, M4 human playtest pending, Phase 7 refactor complete
>
> **Update rule**: When you make a change that affects architecture, conventions, or phase status, update the relevant section of this file and commit it with your work.

---

## 1. Project Identity

**鸦木布拉夫小镇 (Ravenswood Bluff)** — A multi-agent AI-driven social deduction game engine for *Blood on the Clocktower* (Trouble Brewing script). LLM-powered AI players and an AI storyteller play alongside human players via a browser-based WebSocket UI.

- **Language**: Python 3.11+
- **Framework**: FastAPI + WebSocket + Pydantic v2
- **License**: MIT
- **Package name**: `ravenswood-bluff` (version `0.1.0`)

---

## 2. How to Run

```powershell
# Activate venv
.\.venv\Scripts\activate

# Install in dev mode
pip install -e "."

# Start server (mock mode — no LLM API key needed)
$env:BOTC_BACKEND = "mock"
.\.venv\Scripts\python.exe -m src.api.server
# -> http://127.0.0.1:8000

# Start server (live mode — needs OPENAI_API_KEY in .env)
.\.venv\Scripts\python.exe -m src.api.server

# CLI simulation (headless)
.\.venv\Scripts\python.exe simulate_game.py --backend mock --player-count 5

# Run all tests
.\.venv\Scripts\python.exe -m pytest tests -q

# Run Alpha 1.1 aggregate acceptance (8 gates)
.\.venv\Scripts\python.exe scripts\alpha1.1_acceptance.py
```

---

## 3. Architecture Overview

### 3.1 Connection Map

```
server.py (FastAPI + WebSocket)
  |
  +--> GameOrchestrator (game_loop.py) — top-level coordinator
         |
         +--> GameState (immutable Pydantic snapshots)
         +--> PhaseManager (state machine: SETUP→FIRST_NIGHT→DAY→NOMINATION→VOTING→EXECUTION→NIGHT→GAME_OVER)
         +--> EventBus (async pub/sub) → all event routing
         +--> InformationBroker → visibility filtering → agent.observe_event()
         +--> StorytellerAgent → night info adjudication, balance, narration
         +--> RuleEngine → validation (can_nominate, can_vote, votes_required)
         +--> NominationManager → nominate/vote/execute mechanics
         +--> VictoryChecker → win conditions (demon dead=good, ≤2 alive=evil, mayor special)
         +--> SnapshotManager → replay snapshots
         +--> GameRecordStore → SQLite persistence
         +--> GameDataCollector → metrics and AI action traces
         |
         +--> AIAgent(s) → LLMBackend (OpenAI-compatible or Mock)
         |     +--> WorkingMemory, EpisodicMemory, VectorMemory, SocialGraph
         |     +--> Persona, DeceptionTracker, DecisionNoise, DifficultyPreset
         |
         +--> HumanAgent(s) → WebSocket to browser client
```

### 3.2 Data Flow: Setup to Game End

1. **Setup** (`POST /api/game/setup`): Distributes roles from Trouble Brewing script. Creates `PlayerState` per seat. Assigns archetype-based `Persona` to each AI agent. Registers all agents with `InformationBroker`.

2. **First Night**: Evil team gets teammate reveal + 3 bluff roles. Storyteller presets initial info (washerwoman/investigator/librarian/chef data, fortune teller red herring). Night actions execute in canonical order. Night info distributed (may be distorted if poisoned/drunk).

3. **Day Discussion** (N rounds): Each AI agent receives its `AgentVisibleState` (restricted view), constructs prompt with persona + memory + social graph, calls LLM, returns a speak action. Human players wait for WebSocket input. **Sequential processing** ensures later AI see earlier speakers' events.

4. **Nomination Phase**: Collects nomination intents. First legal intent triggers nomination → defense speech → all players vote → votes tallied → highest-voted candidate executed (if threshold met).

5. **Night** (subsequent): Transient statuses cleared. Misregistration decided. Night actions execute. Night info distributed. Death triggers resolved.

6. **Victory Check**: After each phase. All demons dead → GOOD wins. Only 2 alive with demon → EVIL wins. Mayor special: 3 alive, no execution today → GOOD wins.

7. **Game Over**: Settlement report built. Persisted to SQLite. Published as `game_settlement` event.

### 3.3 Key Design Principles

- **Immutable state**: `GameState` is a frozen Pydantic model. All transitions use `.with_update()`, `.with_player_update()`, `.with_event()`, `.with_message()`.
- **Information isolation**: Each agent only sees what their role should see. `InformationBroker` filters events by `Visibility` enum (PUBLIC, TEAM_EVIL, TEAM_GOOD, PRIVATE, STORYTELLER_ONLY).
- **Event-driven**: All game state changes go through `EventBus.publish()`. The orchestrator subscribes `"*"` to forward events to the log and broker.
- **Persona-driven AI**: Each AI has a `Persona` (archetype, speaking style, decision style) that affects prompt construction and behavior.
- **Difficulty as multi-axis config**: `DifficultyPreset` controls competence, deception, volatility, expressiveness, and information_openness — not just temperature.

---

## 4. Directory Structure

```
d:\鸦木布拉夫小镇\
├── src/                          # Main Python package
│   ├── agents/                   # AI agents (players + storyteller)
│   │   ├── ai_agent.py           # LLM-driven player agent facade (~1100 lines)
│   │   ├── storyteller_agent.py  # AI game master (58KB)
│   │   ├── base_agent.py         # Abstract base class
│   │   ├── human_agent.py        # WebSocket proxy for human players
│   │   ├── persona_registry.py   # 9 archetype definitions
│   │   ├── difficulty_presets.py # CASUAL/STANDARD/MASTER/CHAOS presets
│   │   ├── decision_noise.py     # Controlled randomness per difficulty
│   │   ├── deception/            # DeceptionTracker (extracted from ai_agent)
│   │   ├── persona/              # Persona model (extracted from ai_agent)
│   │   ├── prompt/               # PromptFactory (extracted from ai_agent)
│   │   ├── speech/               # SpeechSanitizer (extracted from ai_agent)
│   │   ├── decision/             # DecisionEngine + FallbackDispatcher
│   │   ├── observation/          # EventObserver (extracted from ai_agent)
│   │   ├── strategy/             # EvilStrategy (extracted from ai_agent)
│   │   ├── memory/               # 4-layer memory system
│   │   │   ├── working_memory.py # Short-term observations + facts + claims
│   │   │   ├── episodic_memory.py# Key event memories
│   │   │   ├── vector_memory.py  # RAG-based semantic retrieval
│   │   │   ├── social_graph.py   # Trust/suspicion scores per player
│   │   │   └── memory_controller.py # Unified memory management
│   │   ├── reasoning/            # Logic deduction
│   │   └── dialogue/             # Conversation flow management
│   │
│   ├── api/                      # FastAPI + WebSocket server
│   │   └── server.py             # All REST endpoints + WS handlers (40KB)
│   │
│   ├── engine/                   # Game rules engine
│   │   ├── phase_manager.py      # State machine for game phases
│   │   ├── rule_engine.py        # Validation (can_nominate, can_vote, etc.)
│   │   ├── nomination.py         # Nomination/voting/execution mechanics
│   │   ├── victory_checker.py    # Win/loss conditions
│   │   ├── scripts.py            # Trouble Brewing script + role distribution
│   │   ├── data_collector.py     # Game snapshot capture for analysis
│   │   └── roles/                # Role implementations
│   │       ├── base_role.py      # Abstract role with _ROLE_REGISTRY
│   │       ├── townsfolk.py      # 13 good team roles (34KB)
│   │       ├── outsiders.py      # 4 outsider roles
│   │       ├── minions.py        # 4 evil minion roles
│   │       └── demons.py         # 1 demon role (Imp, with star-pass)
│   │
│   ├── orchestrator/             # Game orchestration
│   │   ├── game_loop.py          # GameOrchestrator facade (~766 lines)
│   │   ├── agents/               # AgentManager (extracted from game_loop)
│   │   ├── claims/               # ClaimExtractor (extracted from game_loop)
│   │   ├── grimoire/             # GrimoireManager (extracted from game_loop)
│   │   ├── info/                 # PrivateInfoNormalizer (extracted from game_loop)
│   │   ├── metrics/              # MetricsCollector (extracted from game_loop)
│   │   ├── phases/               # Phase handlers (extracted from game_loop)
│   │   │   ├── night_phase.py    # NightPhaseHandler (~574 lines)
│   │   │   ├── day_discussion.py # DayDiscussionHandler (~274 lines)
│   │   │   └── nomination_voting.py # NominationVotingHandler (~756 lines)
│   │   ├── settlement/           # SettlementBuilder (extracted from game_loop)
│   │   ├── event_bus.py          # Async pub/sub event system
│   │   ├── information_broker.py # Visibility filtering + agent registry
│   │   ├── storyteller_balance.py# Strategic balancing logic
│   │   └── replay_parser.py      # Log replay for debugging
│   │
│   ├── state/                    # State management
│   │   ├── game_state.py         # Core Pydantic models (GameState, PlayerState, etc.)
│   │   ├── game_record.py        # SQLite persistence (GameRecordStore)
│   │   ├── event_log.py          # In-memory event container
│   │   └── snapshot.py           # Game state snapshots
│   │
│   ├── llm/                      # LLM backend abstraction
│   │   ├── base_backend.py       # Abstract interface (generate, get_embeddings)
│   │   ├── openai_backend.py     # OpenAI-compatible API client
│   │   └── mock_backend.py       # Pattern-matching test backend
│   │
│   └── content/                  # Game content definitions
│       ├── trouble_brewing_night_order.py
│       └── trouble_brewing_terms.py
│
├── tests/                        # pytest test suite (~50+ files)
│   ├── test_agents/              # Agent reasoning, persona, memory tests
│   ├── test_engine/              # Role abilities, rules, edge cases
│   ├── test_orchestrator/        # Game loop, API, integration (27 files)
│   ├── test_state/               # State models, persistence
│   └── test_runs/                # Test-generated artifacts (not committed)
│
├── scripts/                      # 42 acceptance/benchmark/utility scripts
│   ├── alpha1.1_acceptance.py    # Current aggregate gate (8 sub-gates)
│   ├── ai_speed_acceptance.py    # Latency P50/P95 + timeout fallback
│   ├── ai_conversation_quality_acceptance.py  # Speech quality gates
│   ├── difficulty_acceptance.py  # Difficulty config validation
│   ├── difficulty_behavior_acceptance.py      # Behavioral-level difficulty
│   └── ...                       # (see Section 6 for full list)
│
├── docs/                         # Documentation by milestone
│   ├── alpha-1.1-plan.md         # Current active plan
│   ├── alpha-1.1-plan/           # Task boards (M5, M5-R, M6, M7)
│   ├── alpha-1.1-evidence/       # 22 evidence files + README + template
│   └── ...                       # Historical plans (alpha-0.1 through 1.0)
│
├── public/                       # Frontend (served by FastAPI)
│   ├── index.html                # Player/storyteller UI (141KB single-page app)
│   └── storyteller.html          # Dedicated storyteller interface (35KB)
│
├── data/                         # Runtime data (SQLite, exports, sessions)
├── ref_docs/                     # Official BOTC rulebook PDFs
├── pyproject.toml                # Project metadata + dependencies
├── .env                          # LLM endpoints + API keys (not committed)
└── CLAUDE.md                     # This file
```

---

## 5. Key Source Files (by importance)

| File | Lines | Role |
|------|------:|------|
| `src/agents/ai_agent.py` | ~1100 | AI player facade — delegates to 9 extracted modules |
| `src/orchestrator/game_loop.py` | ~766 | GameOrchestrator facade — delegates to 9 extracted modules |
| `src/agents/storyteller_agent.py` | ~1500 | AI storyteller — night info adjudication, balance, narration, misregistration |
| `src/agents/decision/decision_engine.py` | ~1050 | DecisionEngine — target scoring, nomination, voting logic |
| `src/orchestrator/phases/nomination_voting.py` | ~756 | NominationVotingHandler — nomination, voting, execution mechanics |
| `src/orchestrator/phases/night_phase.py` | ~574 | NightPhaseHandler — night actions, death triggers, slayer shots |
| `src/agents/observation/event_observer.py` | ~670 | EventObserver — event processing, social graph updates, memory storage |
| `src/orchestrator/metrics/__init__.py` | ~450 | MetricsCollector — latency tracking, action metrics, data snapshots |
| `src/orchestrator/phases/day_discussion.py` | ~274 | DayDiscussionHandler — discussion rounds, speech dedup, chat |
| `src/api/server.py` | ~1000 | FastAPI endpoints + WebSocket + game session management |
| `src/state/game_state.py` | ~400 | Core Pydantic models (GameState, PlayerState, GamePhase, GameConfig, etc.) |
| `src/engine/roles/townsfolk.py` | ~900 | 13 townsfolk role implementations |
| `src/agents/difficulty_presets.py` | ~250 | 4 difficulty presets with multi-axis config |
| `src/engine/nomination.py` | ~300 | Nomination, voting, execution mechanics |
| `src/orchestrator/information_broker.py` | ~250 | Visibility filtering, agent registry, legal context |

---

## 6. Testing & Acceptance Infrastructure

### 6.1 Test Execution

```powershell
# Full test suite
.\.venv\Scripts\python.exe -m pytest tests -q

# Specific test file
.\.venv\Scripts\python.exe -m pytest tests/test_agents/test_agent_reasoning.py -q

# Low-memory mode (for constrained environments)
.\.venv\Scripts\python.exe scripts\run_full_tests_low_memory.py
```

### 6.2 Alpha 1.1 Aggregate Acceptance (8 gates)

```powershell
.\.venv\Scripts\python.exe scripts\alpha1.1_acceptance.py
```

| Gate | Script | What it validates |
|------|--------|-------------------|
| 1 | pytest (multiple dirs) | No regressions in existing tests |
| 2 | `test_agent_reasoning.py` | Agent decision-making logic |
| 3 | `difficulty_acceptance.py` | Difficulty config validation (54 checks) |
| 4 | `difficulty_comparison.py` | Cross-difficulty behavioral comparison (62 checks) |
| 5 | `difficulty_behavior_acceptance.py` | Behavioral-level difficulty validation |
| 6 | `ai_speed_acceptance.py` | Latency P50/P95, timeout fallback, event ordering |
| 7 | `ai_conversation_quality_acceptance.py` | Speech quality: low-info rate, duplicates, context response |
| 8 | `alpha1_rules_acceptance.py` | Alpha 1.0 backward compatibility |

### 6.3 Adding a New Acceptance Gate

1. Create `scripts/your_acceptance.py` with a `main() -> int` function (0=pass, 1=fail).
2. Add a `Gate(...)` entry in `scripts/alpha1.1_acceptance.py`.
3. Use `_script_exists()` for optional gates that may not be implemented yet.
4. Run `.\.venv\Scripts\python.exe scripts\alpha1.1_acceptance.py` to verify integration.

---

## 7. Development History & Current Phase

### 7.1 Version Timeline

| Phase | Key Achievement |
|-------|----------------|
| Phase 0 | Core data model, event bus, LLM adapter |
| Alpha 0.1 | Core game loop and ruleset foundation |
| Alpha 0.2 | Waves 1-4: full game flow, roles, AI players, storyteller |
| Alpha 0.3 | Observability, strategic intelligence, data collection |
| Alpha 1.0 | Stable playable game: UI, persistence, live backend, settlement |
| **Alpha 1.1** | **Current**: Difficulty system + speed work completed in mock, live speech quality regression under repair |

### 7.2 Alpha 1.1 Milestone Status

| Milestone | Status | Summary |
|-----------|--------|---------|
| M1: Difficulty Skeleton + Casual | **Done** | DifficultyPreset model, GameConfig integration, casual mode |
| M2: Master + Deception | **Done** | Evil AI fabrication, info-release pacing, deception budget |
| M3: Chaos + Decision Noise | **Done** | High-randomness mode with bounded guardrails |
| M4: Experience Validation | **Blocked / Required** | Human playtesting exposed live speech regression; mock evidence is not enough for release |
| M5: AI Speed | **Done** | All speed, quality, and live speech tasks complete; live-like 5p+8p gate 0% fallback, 100% LLM success |
| M5-R: Speech Quality Fix | **Done** | Sequential finalization, fallback diversity, minimum effective speech |
| M5-L: Live Speech Recovery | **Done** | SpeechPreGenCache, backend-aware budgets, release_blocker circuit breaker, async claim extraction, evidence files |
| M6: Difficulty Calibration | **Done** | Multi-axis preset, faction boundary, Standard baseline |
| M7: Verification | **Done** | Evidence system, aggregate acceptance, behavior/speed scripts |

### 7.3 Current Branch

- **Branch**: `alpha1.1`
- **Base**: `main`
- **Status**: M5-L live-like recovery is implemented, but do not treat Alpha 1.1 as release-ready until a real live backend human playtest confirms public speech fallback is no longer common.

---

## 8. Coding Conventions & Patterns

### 8.1 State Management

- `GameState` is **immutable** (Pydantic `frozen=True`). Never mutate it directly.
- Use `.with_update()`, `.with_player_update()`, `.with_event()`, `.with_message()` for state transitions.
- The orchestrator holds the authoritative `self.state` reference and updates it after each transition.

### 8.2 Agent Interface

All agents implement `BaseAgent`:
```python
async def act(self, visible_state, action_type, legal_context) -> dict
async def observe_event(self, event, visible_state) -> None
async def archive_phase_memory(self, visible_state) -> None
def synchronize_role(self, player_state) -> None
```

### 8.3 Information Isolation

- Agents only see `AgentVisibleState` — a filtered view based on `Visibility` enum.
- Never pass `GameState` directly to agents. Use `InformationBroker.get_visible_state()`.
- Evil team private channel uses `ChatMessage(recipient_ids=[...])`.

### 8.4 Difficulty System

- `DifficultyLevel` enum: `CASUAL`, `STANDARD`, `MASTER`, `CHAOS`
- `DifficultyPreset` has 5 axes: `competence`, `deception`, `volatility`, `expressiveness`, `information_openness`
- Difficulty affects: prompt modifiers, temperature, persona overrides, strategy prompts, speech style prompts
- **Important**: Good AI must never receive evil strategy prompts. Check `player.team` before injecting strategy.

### 8.5 AI Fallback Pattern

- Each action type has a latency budget in `_action_latency_budgets` (vote=1200ms, speak=3500ms, etc.)
- `_timed_act()` wraps `agent.act()` with hard timeout → returns legal fallback on timeout
- Agent-level fallback (`_persona_fallback_speech`) fires before orchestrator timeout
- Fallback reason distinguishes `orchestrator_hard_timeout:{type}` from `latency_budget_exceeded`
- Public `speak` and `defense_speech` are high-value social actions. A fallback speech is an emergency protection path, not an acceptable normal path.
- In live backend runs, track `speak_fallback_rate`, `orchestrator_timeout_rate`, and `llm_successful_speech_rate`. Any live game where public speech fallback exceeds 20% is a release blocker.
- Difficulty `latency_budget` values must be wired into the agent timeout path; static `ACTION_BUDGET` values alone are not sufficient.

### 8.6 Testing Patterns

- Tests use `MockBackend` (pattern-matching, no LLM calls) by default.
- `BOTC_BACKEND=mock` env var selects mock mode.
- Acceptance scripts use `_check(label, condition)` for pass/fail tracking.
- Game loop tests use `_StopGame` exception + event capture to stop early.

---

## 9. Known Gotchas

1. **`ai_agent.py` is a facade (~1100 lines)** — delegates to 9 extracted modules (DecisionEngine, PromptFactory, SpeechSanitizer, EventObserver, EvilStrategy, MemoryController, DeceptionTracker, Persona, FallbackDispatcher). When editing agent behavior, check the relevant module under `src/agents/`.

2. **`game_loop.py` is a facade (~766 lines)** — delegates to 9 extracted modules (MetricsCollector, AgentManager, GrimoireManager, ClaimExtractor, PrivateInfoNormalizer, SettlementBuilder, NightPhaseHandler, DayDiscussionHandler, NominationVotingHandler). When editing orchestrator behavior, check the relevant module under `src/orchestrator/`.

3. **Sequential speech, not parallel** — Day discussion processes AI speeches sequentially (FIX-037). Do not use `asyncio.gather` for final speech generation; it breaks context for later speakers.

3. **Dual timeout budgets** — Orchestrator budget must be larger than agent budget. If you change `_action_latency_budgets`, ensure the orchestrator's `_timed_act` timeout exceeds the agent's internal `latency_budget_ms`.

4. **Trust coefficient affects persona diversity** — Changing `min(0.20, abs(profile.trust_score) * 0.25)` in `_fallback_decision` can collapse archetype behavioral differences. Use targeted fallback overrides instead.

5. **MockBackend collision** — With 20 speak options, birthday-paradox collisions become likely above ~12 players. Expand the option pool if adding larger game support.

6. **GameState immutability** — Never `state.players[idx].field = value`. Always use `state.with_player_update(player_id, field=value)`.

7. **Event visibility** — When publishing events, always set the correct `visibility`. Leaking TEAM_EVIL info to PUBLIC breaks the game.

8. **SQLite concurrency** — `GameRecordStore` uses `aiosqlite`. The test suite creates per-test databases to avoid lock contention. Don't share a single DB across parallel test runs.

9. **Live speech can fail while mock gates pass** — MockBackend returns in milliseconds, so speed and conversation gates can show excellent P95 values even when the configured live model times out on most public speeches. Always verify live or slow-recorded speech before claiming UX completion.

10. **Claim extraction must not block discussion quality** — `_extract_claims_via_llm()` is useful for memory and replay, but failures such as empty/non-JSON responses should be asynchronous, rate-limited, and non-blocking. It must not add visible waiting or repeated warning noise during live discussions.

---

## 10. Common Tasks

### Add a new role

1. Create class in `src/engine/roles/{category}.py` inheriting `BaseRole`.
2. Decorate with `@register_role("role_id")`.
3. Implement `get_definition()`, `execute_ability()`, `can_act_at_phase()`, `needs_night_target()`.
4. Add to distribution table in `src/engine/scripts.py`.
5. Add tests in `tests/test_engine/`.

### Add a new difficulty axis

1. Add field to `DifficultyPreset` in `src/agents/difficulty_presets.py`.
2. Set values for all 4 presets (CASUAL, STANDARD, MASTER, CHAOS).
3. Use the axis in `ai_agent.py` prompt construction or decision logic.
4. Update `scripts/difficulty_behavior_acceptance.py` to verify the axis produces behavioral differences.

### Add a new acceptance gate

1. Create `scripts/your_acceptance.py` with `main() -> int`.
2. Add `Gate("name", ["scripts/your_acceptance.py"], timeout)` in `scripts/alpha1.1_acceptance.py`.
3. Run aggregate to verify integration.

### Debug an AI decision

1. Check `scripts/dump_ai_prompt.py` to extract the exact prompt sent to LLM.
2. Check `data/exports/` for AI trace files after a game.
3. Use `GET /api/game/metrics` during a live game for real-time action metrics.

---

## 11. Documentation Map

| Document | Location | Purpose |
|----------|----------|---------|
| This file | `CLAUDE.md` | Agent onboarding guide |
| Architecture | `architecture.md` | Detailed architecture (33KB) |
| Current plan | `docs/alpha-1.1-plan.md` | Active development plan |
| Task boards | `docs/alpha-1.1-plan/task_*.md` | Per-milestone task tracking |
| Evidence | `docs/alpha-1.1-evidence/` | Verification evidence files |
| Verification policy | `docs/alpha-1.1-plan/verification_policy.md` | Evidence levels and Done criteria |
| Rule matrix | `docs/rule_matrix.md` | Role ability matrix |
| Changelog | `CHANGELOG.md` | Version history |
| Release notes | `VERSION_NOTES.md` | Alpha 1.0 release notes |
| Known issues | `docs/alpha-1.0-known-issues.md` | Known issues tracker |

---

## 12. Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `BOTC_BACKEND` | `auto` | `mock` / `openai` / `auto` (auto = openai if key exists, else mock) |
| `OPENAI_API_KEY` | — | LLM API key |
| `OPENAI_BASE_URL` | `http://127.0.0.1:8045/v1` | LLM endpoint |
| `DEFAULT_MODEL` | `gemini-3-flash` | LLM model name |
| `EMBEDDING_API_KEY` | — | Embedding API key (falls back to OPENAI_API_KEY) |
| `EMBEDDING_BASE_URL` | — | Embedding endpoint |
| `EMBEDDING_MODEL` | `Pro/BAAI/bge-m3` | Embedding model |
| `EMBEDDING_DIMENSION` | `1536` | Embedding vector dimension |

---

## 13. How to Update This Document

This document is **versioned with the project**. When you make changes that affect it:

1. **Architecture changes**: Update Section 3 and 4.
2. **New conventions**: Add to Section 8.
3. **New gotchas**: Add to Section 9.
4. **Phase transitions**: Update Section 1 and 7.
5. **New tasks/dependencies**: Update the relevant section.
6. **Always update** the "Last updated" date at the top.

Commit this file alongside your changes: `docs: update CLAUDE.md for <what changed>`.
