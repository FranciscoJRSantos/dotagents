# Risk Classifier

Risk classification for `@review`. Auto-detects escalation patterns from diff + codebase
structure. Progressive learning from review outcomes.

---

## Escalation Classes

Classify each file change into one of these classes. A change escalates if it touches
any of these patterns:

| Class | Patterns | Escalate? |
|-------|----------|-----------|
| **Auth** | Authentication, authorization, session handling, token validation, password hashing, JWT, OAuth | ✅ Always |
| **Billing** | Payment processing, subscription logic, pricing, invoicing, refund calculations | ✅ Always |
| **Schema** | Database migrations, schema changes, column drops/renames, index changes | ✅ Always |
| **Security** | Input sanitization, SQL injection prevention, XSS prevention, CSRF tokens, CORS config | ✅ Always |
| **Migrations** | Data migrations, backfill scripts, ETL pipelines | ✅ Always |
| **Crypto** | Encryption, hashing, key management, certificate handling | ✅ Always |
| **External APIs** | Changes to third-party API integrations, webhook handlers | ⚠️ If contract changes |
| **Config** | Environment variables, feature flags, deployment config | ⚠️ If production-affecting |
| **Tests** | Test-only changes, test infrastructure | ❌ Never |
| **Docs** | Documentation, comments, README updates | ❌ Never |
| **Refactor** | Code reorganization, naming changes, no behavioral change | ❌ Never |

---

## Auto-Detect Patterns (First Run)

On first `@review` invocation for a codebase, scan for sensitive areas and write
patterns to `.agents/review.md`:

```bash
# Scan for auth modules
find . -type f \( -name '*auth*' -o -name '*session*' -o -name '*token*' \) \
  -not -path '*/node_modules/*' -not -path '*/.git/*' | head -20

# Scan for billing/payment modules
find . -type f \( -name '*payment*' -o -name '*billing*' -o -name '*subscription*' \) \
  -not -path '*/node_modules/*' -not -path '*/.git/*' | head -20

# Scan for migration files
find . -type f -name '*migration*' -o -name '*migrate*' \
  -not -path '*/node_modules/*' -not -path '*/.git/*' | head -20
```

Write detected patterns to `.agents/review.md`:

```markdown
## Auto-Detected Patterns

### Auth modules
- src/auth/**
- src/middleware/session.py
- lib/token_validation.rb

### Billing modules
- src/payments/**
- src/billing/invoices.py

### Schema changes
- db/migrations/**
- alembic/versions/**
```

Subsequent `@review` invocations load these patterns and check the diff against them.

---

## Progressive Learning

When the user overrides a risk classification (e.g. says "this didn't need review"),
update `.agents/review.md` with the learned pattern:

```markdown
## Learned Patterns

### False positives (don't escalate)
- src/auth/utils.py — helper functions, no security impact (learned 2026-11-08)

### False negatives (escalate)
- src/config/features.py — feature flag changes affect production (learned 2026-11-08)
```

Load learned patterns on every `@review` invocation and apply them before static classes.

---

## Evidence Format

When risk is escalated, show the user a one-liner in conversation:

```
Files: <N> | Risk: <reason> | Checks: ✅/<span style="color:red">❌</span>
```

Examples:

```
Files: 3 | Risk: auth module changed (session.py) | Checks: ✅
Files: 1 | Risk: schema migration (add_column) | Checks: ✅
Files: 5 | Risk: billing logic + external API | Checks: ❌ (test failures)
```

The full review report goes to the artifact. Conversation is routing only.

---

## Classification Logic

After the reviewer runs, classify the diff:

1. **Check learned patterns** — if any file matches a learned false positive, skip escalation
2. **Check escalation classes** — if any file matches an escalation class, escalate
3. **Check heuristics** — if file count > 10 or changes span > 3 directories, escalate
4. **Otherwise** — auto-pass

Output the evidence format when escalating. Auto-pass when clear.

---

## Integration with @review

The `@review` skill loads this partial and applies the classification after the reviewer
returns findings. The reviewer always runs; the classifier decides whether to show the
user the full report or just the evidence format.
