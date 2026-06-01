# Project Handoff: Slimming & Modular Refactor (May 2026)

## Context
**Project**: Ravenswood Bluff (Blood on the Clocktower AI Engine)  
**Objective**: Project maintenance, technical debt reduction, and architectural modularization.

---

## 1. Project Slimming Summary
We have performed a cleanup of redundant logs and temporary data to maintain a lean environment.
- **Deleted**:
    - `orchestrator_run.log`, `storyteller_run.log` (Large log files).
    - `.debug_game_logs/`, `tmp/`, `scratch/`, `storyteller_eval_samples/`.
    - `data/*.corrupt_*` (Damaged DB backups).
    - `data/_probe*`, `data/_pytest*` (Temporary test/exploration files).
- **Preserved Assets**:
    - `data/games.db` (Primary game records).
    - `data/sessions/*.jsonl` (AI trace assets for quality audit).

---

## 2. In-depth Code Audit Findings
The core logic was previously concentrated in two "God Objects":
- **`src/agents/ai_agent.py`**: Massive class handling persona, memory tiers, LLM calls, and deception logic.
- **`src/orchestrator/game_loop.py`**: Monolithic state machine handling all game phases.

**Strategic Goal**: Decompose these into service-oriented components with clear responsibility boundaries.

---

## 3. Modular Refactor Preview (Non-destructive)
We have implemented a **Preview Architecture** in separate backup directories. The original code remains untouched.

### 3.1 AI Agent Refactor (`src/agents/refactor_preview/`)
- **`prompt_factory.py`**: Logic for building system and action prompts.
- **`memory_controller.py`**: High-level manager for tiered memory retrieval.
- **`action_executor.py`**: Orchestrates LLM requests, timeouts, and fallbacks.
- **`agent_facade.py`**: A lightweight agent entry point that composes the above services.

### 3.2 Orchestrator Refactor (`src/orchestrator/refactor_preview/`)
- **`orchestrator_core.py`**: A dispatcher that uses a registry of phase handlers.
- **`phases/base.py`**: `IPhaseHandler` interface definition.
- **`phases/night.py`, `day.py`, `nomination.py`**: Specific logic for game phases.

---

## 4. Next Steps for Claude
1. **Validate Logic Parity**: Compare the output of the new `PromptFactory` with the legacy `AIAgent._build_persona_prompt_block` to ensure zero regression in prompt quality.
2. **Phased Migration**:
    - Start by having `AIAgent` delegate its prompt building to `PromptFactory`.
    - Then migrate memory management to `MemoryController`.
    - Finally, swap the `GameOrchestrator` logic to use the `PhaseHandlers`.
3. **Automated Testing**: Implement unit tests for the new modular components (which are now much easier to test than the monolithic originals).

---

## 5. Technical Environment
- **Python**: 3.12
- **Key Modules**: `src.state.game_state`, `src.content.trouble_brewing_terms`.
- **Patterns**: Facade, Strategy, Phase-based Dispatching.
