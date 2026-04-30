# docs/golfball/ — the architectural lineage

This folder holds the design-time conversations that produced Hornelore's
core architecture, separate from the engineering specs that codify it.

The engineering specs (in `docs/specs/` and at the repo root as `WO-*.md`)
say *what* to build and *how*. The golfball folder says *why* — the
reasoning, the metaphor, the back-and-forth between the three voices
(Chris, Claude, ChatGPT) that shaped the system before it became code.

## Why "golfball"

In *golfball.docx* (Chris, 2026-04-30, Chapter 1), an eight-year-old in
Grand Forks cuts open a golf ball with his father's utility knife and
discovers the architectural pattern that every Lorevox-shaped system
inherits:

```
COVER     — outer behavior, identity
WINDINGS  — memory, discipline, accumulated truth
CORE      — stable capacity at the center
```

Lori and Corkybot are siblings of this pattern. Same architecture,
different windings, different covers, different purposes. The design
rule that flows from this:

> **The core gives capacity. The windings give memory and discipline.
> The cover gives identity.**
> — Chris, 2026-04-30

This folder preserves the dialogue that turned that insight into the
formal architecture now codified in `WO-LORI-STORY-CAPTURE-01_Spec.md`
(§0.5 *Origin & ground truth*).

## What lives here

| File | Purpose |
|---|---|
| `README.md` | This file. Folder index + "why golfball" framing. |
| `dialogue-2026-04-30.md` | Three-voice record — Chris, Claude, ChatGPT — of the conversation that produced the four-classification LAW system, the sibling-golfball pattern, and the caddie metaphor for outside design partners. |

## What is NOT here (and why)

- `golfball.docx` itself — Chris's literary source material, kept outside
  the repo by design. The book is its own artifact; this folder cites
  it but doesn't copy it.
- Engineering specs — those live at the repo root (`WO-*.md`) or under
  `docs/specs/`. Spec changes go through the spec; this folder records
  the reasoning behind spec changes, not the spec itself.
- Code — never. Code traces back to specs; specs trace back to here.
  One direction.

## Future additions

When `docs/specs/LOREVOX-PHILOSOPHY.md` is authored (parked, not started),
its top will quote the locked design rule and reference this folder for
the dialogue that produced it. The philosophy doc is the formal output;
this folder is the studio where it was made.
