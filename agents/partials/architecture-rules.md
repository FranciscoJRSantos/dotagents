## Architecture Rules

Apply when the diff adds, moves or reshapes modules, public interfaces, data flow
or cross-boundary calls. Skip pure internal edits (bodies of functions, renames
inside one module, formatting).

**Gotchas:**
- Always judge against the project's own patterns (`.agents/review.md`,
  `.agents/conventions.md`, neighbouring code) before generic principles BECAUSE a
  consistent "wrong" pattern is cheaper than two competing "right" ones.
- Never recommend a new layer, pattern or abstraction without naming the concrete
  change pressure it relieves BECAUSE the owner prefers good-enough on time over
  speculative structure.
- Always cite the file and the import or call that proves a finding BECAUSE
  structural claims without evidence are opinions.
- Never report bugs, security or style issues from this frame BECAUSE the other
  frames own them.

### Context to load

Read structure before code: directory placement predicts where change will land.

```bash
cat .agents/codemap/codemap.md 2>/dev/null
```

If no codemap exists, infer the layout from `git ls-files` and say so in the
Summary. Then read the siblings of each new or moved file, and use Grep to find the
callers and importers of anything new, moved or whose signature changed.

### Architecture specialist frame

**Vocabulary:** dependency direction, layering, module boundary, cohesion,
coupling (afferent/efferent), public interface, seam, dependency inversion, single
source of truth, anti-corruption layer, change amplification, shotgun surgery,
leaky abstraction, pattern consistency, blast radius.

**Named anti-patterns to detect:**
1. **Inverted dependency** — a lower layer or core module imports from a higher
   layer or edge (domain importing controller, HTTP or ORM types) → Critical
2. **Cycle introduced** — new circular import or mutual dependency between
   modules → Critical
3. **Declared boundary violated** — code breaks a boundary or pattern rule stated
   in `.agents/review.md` or `.agents/conventions.md` → Warning
4. **Boundary bypass** — reaches around a module's public interface into its
   internals or tables, with no declared rule → Suggestion
5. **Pattern drift** — a second way of doing something the codebase already solves
   (error handling, data access, config loading) → Suggestion
6. **Misplaced responsibility** — business rules in a controller, route handler,
   task or migration; I/O inside pure logic → Suggestion
7. **Leaky abstraction** — an interface exposing its implementation (ORM models,
   vendor SDK types, raw dicts) across a boundary → Suggestion
8. **Shotgun surgery** — one conceptual change forces edits in 4+ unrelated
   places, or the same knowledge is duplicated across modules → Suggestion
9. **Hidden coupling** — shared mutable state, import-time side effects, or
   modules coupled through a schema or string constant neither owns → Suggestion
10. **Unowned cross-cutting concern** — auth, logging, retries or validation
    re-implemented per call site instead of at one seam → Suggestion

### Severity calibration

Only objective violations (1, 2) and rules the project declared itself (3) reach
Critical or Warning. Everything else is a judgment call and stays Suggestion BECAUSE
`/review` blocks `/ship` on any Critical or Warning, and a debatable design opinion
must not stop a ship.

A boundary becomes enforced when the project writes it down: one line in
`.agents/review.md` promotes "noticed" (Suggestion) to "violated" (Warning).

Report findings in the `## 🏛 Architecture` section of the report, each tagged
with its severity.
