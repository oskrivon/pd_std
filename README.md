# Ptero Dactyl Studio

An AI-driven game-dev studio: **you supply the idea, AI agents build the prototype** —
autonomously and continuously. An orchestrator decomposes a one-line game concept into
tasks, specialised workers write the code and generate the art, and a vision-based
validator checks that the result actually runs and plays before the loop moves on.

## Concept

```
YOU: "Tower defense with mages, isometric, LÖVE 2D"
                    │
                    ▼
        ┌───────────────────────┐
        │     ORCHESTRATOR      │  ← Claude Opus decomposes the idea
        │     (decomposition)   │
        └───────────┬───────────┘
                    │
    ┌───────────────┼───────────────┐
    ▼               ▼               ▼
┌───────┐      ┌───────┐      ┌───────┐
│ CODE  │      │  ART  │      │ TEST  │
│WORKER │      │WORKER │      │WORKER │
└───┬───┘      └───┬───┘      └───┬───┘
    │              │              │
    └──────────────┼──────────────┘
                   ▼
        ┌───────────────────────┐
        │      VALIDATOR        │  ← Vision checks the result
        │   (smoke + gameplay)  │
        └───────────────────────┘
                   │
                   ▼
             PLAYABLE PROTOTYPE
```

The orchestrator uses a stronger model (Claude Opus) for decomposition and cheaper models
for routine code, picking each task by ROI (value / tokens). Every meaningful change is
smoke-tested immediately, so failures surface fast.

## Quick start

```bash
# 1. Install (Python 3.11+)
pip install -e ".[full]"          # 'full' adds screen-capture / process helpers

# 2. Configure API keys
cp config/.env.example config/.env
# edit config/.env: ANTHROPIC_API_KEY, and optionally AIMLAPI_KEY / PIXELLAB_API_KEY

# 3. Create a project and let the studio work on it
ptero-studio new tower_defense --engine love
ptero-studio add tower_defense "Grid-based map with mage towers and a wave spawner"
ptero-studio run                  # execute the task queue (--once for a single task)
```

Other commands: `ptero-studio projects` (list projects), `ptero-studio tasks [project]`
(inspect the queue), `ptero-studio status` (overall status).

## Supported engines

| Engine | Status | Notes |
|--------|--------|-------|
| **LÖVE 2D** | Ready | 2D games in Lua |
| **Unreal Engine** | Ready | 3D / complex projects (via an MCP integration) |
| **Blender** | WIP | 3D models → 2D sprites |

## Asset generation

| Method | When to use |
|--------|-------------|
| **Diffusion / DALL·E** | Unique characters, illustrations |
| **PixelLab** | Sprites, rotations, animations |
| **Procedural** | Tiles, patterns, gradients |
| **Placeholder** | WIP, fast prototypes |

## Run modes

- **Single task** — `ptero-studio run --once` executes the next queued task and stops.
- **Continuous** — `ptero-studio run` keeps pulling tasks until the queue (or budget) is
  empty.
- **Idea-driven** — start from a one-line concept with `ptero-studio new … --engine …`,
  then let the orchestrator decompose it into the queue.

## Structure

```
cli.py             # entry point (installed as `ptero-studio`)
core/              # orchestrator, task queue, project model, daemon loop, budget/model choice
adapters/          # engine adapters (LÖVE 2D, Unreal via MCP, Blender)
assets/            # asset generation (diffusion, procedural)
validation/        # vision + gameplay smoke tests
config/            # settings and system prompts
tools/             # supporting CLI utilities (`ptero-tool`)
docs/              # ARCHITECTURE / PLAN / PROGRESS / RUNBOOK
```

## Documentation

- [ARCHITECTURE.md](docs/ARCHITECTURE.md) — full system architecture
- [PLAN.md](docs/PLAN.md) — phased implementation plan
- [RUNBOOK.md](docs/RUNBOOK.md) — how to run and operate the studio
- [PROGRESS.md](docs/PROGRESS.md) — change log

## Design principles

1. **Autonomy** — minimal human intervention once an idea is queued.
2. **Continuity** — the runner keeps working while tasks and budget remain.
3. **Token economy** — always pick the task with the best value-per-token.
4. **Fail fast** — validate after every change.
5. **Reuse** — share integrations (e.g. the Unreal/MCP layer) instead of duplicating them.

## Related projects

Prototypes this studio was built to drive: a LÖVE 2D roguelike (its main test bed), a
LÖVE 2D mini-game, and an Unreal collectible-card game that is the source of the
engine's MCP integration.

---

*Ptero Dactyl Studio — let AI build your games.*
