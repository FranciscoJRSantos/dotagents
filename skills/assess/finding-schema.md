# Finding schema and interface sheet

Shared by `@assess`, `assess-surveyor`, `assess-verifier`, `rank.py` and
`findings.org`. Defined once here; every other file points at this one.

## Finding record (D6)

One finding is one Org heading with a property drawer. The surveyor writes the
heading as `** <title>` under `* Findings`; `findings.org` adds `TRIAGE` and
`OWNER` later.

```org
** <short title, imperative or noun phrase>
:PROPERTIES:
:ID: <repo>-<NN>
:REPO: <repo>
:PATH: <file path from the repo root>
:LINES: <start>-<end>
:KIND: debt | improvement | refactor | arch-gap
:TAGS: <one or more of: security phi data-correctness ml-lens contract reliability maintainability performance>
:RULE: <named anti-pattern from the surveyor frame, or "other">
:IMPACT: <1-5>
:INTEREST: <1-5>
:EFFORT: <1-5>
:CONFIDENCE: <0-100>
:END:
- Claim :: <one sentence a reader can falsify>
- Evidence :: =<path>:<line>= — <what the code shows, no raw log lines or payloads>
- Proposal :: <what to change, one sentence>
```

Rules:
- `IMPACT`, `INTEREST` and `EFFORT` are integers 1-5. `priority = IMPACT * INTEREST / EFFORT`.
- `PATH`, `LINES` and the Evidence citation must exist in the repo; a finding without a citation is dropped by `findings_org.py build`.
- Evidence quotes code or config, never data: no MRN, SSN, DOB, email, phone or log line.
- Write Org markup in prose: `=path=`, `~code~`, never backticks.

## Interface sheet (D3)

Appended to every `surveys/<repo>.org` under `* Interface sheet`. Each entry ends in a
citation `=<path>:<line>=`.

```org
* Interface sheet
** Exposes
- =GET /v1/patients= (HTTP) — =app/routes.py:42=
- =queue:intake-events= (SQS producer) — =app/publish.py:17=
** Consumes
- =PATIENT_API_URL= → patient-service (HTTP) — =app/client.py:9=
- =queue:billing-events= (SQS consumer) — =app/worker.py:31=
** Config
- =DATABASE_URL= (env, required) — =config/settings.py:5=
- =s3://<bucket>/models/= (data contract, read) — =app/model_store.py:12=
```

Rules:
- List what the code declares, not what it probably does. If a value is built at runtime, write the pattern and cite the builder.
- One line per endpoint, queue, topic, bucket prefix, table or env var that crosses the repo boundary.
