## Complexity Rules (YAGNI)

Always apply, to every diff. Scope is unnecessary complexity only; correctness,
security and performance belong to the other frames. The diff's best outcome is
getting shorter.

**Gotchas:**
- Never flag a single smoke test or `assert`-based self-check BECAUSE it is the
  minimum, not bloat.
- Always name the replacement, never just "simplify" BECAUSE a finding without a
  replacement is an opinion the author can't act on.
- Never flag an abstraction that already has two real callers or implementations,
  or whose second use the plan or kanban artifact names BECAUSE speculation is
  what makes it a finding.
- Only code added by this diff counts BECAUSE pre-existing complexity is not the
  author's to fix in this change.
- Never apply the fix, only list it BECAUSE deletion is a judgment for the author.

### Tags

| Tag       | What to cut                                          | Replacement                              |
|-----------|------------------------------------------------------|------------------------------------------|
| `delete:` | Dead code, unused flexibility, speculative feature   | Nothing — remove it                      |
| `stdlib:` | Hand-rolled thing the standard library ships         | Name the function/class                  |
| `native:` | Dependency or code doing what the platform already does | Name the native feature               |
| `yagni:`  | Abstraction with one implementation, config nobody sets, layer with one caller | Inline until a second use exists |
| `shrink:` | Same logic, fewer lines                              | Show the shorter form                    |

### Line format

One line per finding:

```
<file>:L<line>: <tag> <what>. <replacement>.
```

Examples:

```
email.py:L12-38: stdlib: 27-line email validator class. "@" check + confirmation email, 1 line.
date.js:L4: native: moment.js imported for one format call. Intl.DateTimeFormat, 0 deps.
repo.py:L88: yagni: AbstractRepository with one implementation. Inline it.
```

### Severity

Severity comes from mechanical facts the reviewer can verify in the diff, never
from taste. Yagni findings are never Critical BECAUSE Critical means a bug,
security hole or production failure.

<!-- deferred: 30-line and 25% thresholds are guesses, tune after a few real runs -->

| Severity      | Condition                                                              | How to verify                                |
|---------------|------------------------------------------------------------------------|----------------------------------------------|
| 🟡 Warning    | New third-party dependency where a `stdlib:` or `native:` replacement exists | Manifest diff plus a named replacement |
| 🟡 Warning    | Abstraction added in this diff with exactly one implementation or caller and ≥ 30 lines | Grep implementations and callers, count lines |
| 🟡 Warning    | Dead code added in this diff: unused function, parameter or flag       | Grep finds zero references                   |
| 🟡 Warning    | Total possible cut ≥ 25% of the diff's added lines                     | `net` divided by added lines                 |
| 🟢 Suggestion | Everything else: `shrink:`, `yagni:` under 30 lines                    | Low cost or taste                            |

### Placement

List findings in the `## ✂ Simplification` section of the report, one line each in
the format above, each prefixed with its severity emoji, no snippets. Put
`net: -<N> lines possible.` in the Summary. If there is nothing to cut, write
`Lean already.` in the Summary and omit the section.
