---
description: >
  Review code changes on the current branch against main with risk-based routing.
  Accepts a slug (work folder name) or a scope (commit/branch/MR).
---
Load the `review` skill and follow it. The argument $ARGUMENTS is a slug when
`.agents/{artifacts,archive}/<arg>` exists, otherwise it is a scope (commit,
branch, or MR). When no argument is given, review the whole branch.
