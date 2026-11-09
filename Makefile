GLOBAL_SKILLS      := skills

AGENTS_SRC         := agents
AGENTS_DIR         ?= $(HOME)/.agents

## Shared scripts skills call (artifact-dir, md2org, org-check, slug) → ~/.agents/bin/.
## They share ~/.agents/ with agents/partials, and manifest-sync keeps one manifest
## per target, so both MUST be synced in one call (deploy and drift) — separate calls
## would delete each other's manifest entries.
BIN_SRC            := bin
AGENTS_DIR_ITEMS   := $(AGENTS_SRC)/partials $(BIN_SRC)

## Files that resolve the active work folder: each must call ~/.agents/bin/artifact-dir
## (checked by lint-agents). The rest of the chain joins as it moves to Org folders;
## until then it stays under the artifact-label identity check.
ARTIFACT_DIR_CALLERS := $(GLOBAL_SKILLS)/arch/SKILL.md $(GLOBAL_SKILLS)/build/SKILL.md $(GLOBAL_SKILLS)/review/SKILL.md

OPENCODE_SKILLS_DIR ?= $(HOME)/.config/opencode/skills
OPENCODE_AGENTS_DIR  ?= $(HOME)/.config/opencode/agents

## OpenCode V2 slash commands. In this repo only `review` (overriding the built-in)
## and `log-hours` live here: skills are invoked with `@<skill-id>` and need no
## command shim.
COMMANDS_SRC         := commands
OPENCODE_COMMANDS_DIR ?= $(HOME)/.config/opencode/commands

CLAUDE_SKILLS_DIR  ?= $(HOME)/.claude/skills
CLAUDE_AGENTS_DIR  ?= $(HOME)/.claude/agents

## Local global rules (gitignored). Template: global/AGENTS.md.example
GLOBAL_AGENTS_SRC   := global/AGENTS.md
GLOBAL_AGENTS_DEST  ?= $(HOME)/.config/opencode/AGENTS.md

## Set DRY_RUN=1 to preview what deploy/drift would change (rsync --dry-run).
DRY_RUN ?=
ifeq ($(DRY_RUN),1)
RSYNC_DRY := --dry-run
else
RSYNC_DRY :=
endif

.PHONY: check-pandoc deploy deploy-skills deploy-agents deploy-commands deploy-global drift lint lint-skills lint-agents lint-docs test list-skills list-agents

## Deploy everything to OpenCode and Claude Code (skills, agents, commands, global rules).
## Each target dir keeps a .personal-agents-manifest; only listed items are touched.
deploy: check-pandoc deploy-skills deploy-agents deploy-commands deploy-global

## bin/md2org needs pandoc; fail before anything is deployed or linted without it.
check-pandoc:
	@command -v pandoc >/dev/null 2>&1 || { echo "FAIL  pandoc not found — install it (dnf install pandoc); bin/md2org needs it"; exit 1; }

## Skills → ~/.config/opencode/skills/ and ~/.claude/skills/ (agents untouched).
## Use this to ship skill changes without clobbering live agents with a stale repo.
deploy-skills:
	@echo "Deploying skills to $(OPENCODE_SKILLS_DIR)..."
	@DRY_RUN=$(DRY_RUN) scripts/manifest-sync.sh "$(OPENCODE_SKILLS_DIR)" $(GLOBAL_SKILLS)/*/
	@echo "Deploying skills to $(CLAUDE_SKILLS_DIR)..."
	@DRY_RUN=$(DRY_RUN) scripts/manifest-sync.sh "$(CLAUDE_SKILLS_DIR)" $(GLOBAL_SKILLS)/*/

## OpenCode slash commands → ~/.config/opencode/commands/. Only the overriding
## `/review` and `log-hours` live here; skills are invoked with `@<skill-id>`.
deploy-commands:
	@echo "Deploying commands to $(OPENCODE_COMMANDS_DIR)..."
	@DRY_RUN=$(DRY_RUN) scripts/manifest-sync.sh "$(OPENCODE_COMMANDS_DIR)" $(COMMANDS_SRC)/*

## Agents → ~/.config/opencode/agents/ (source md), ~/.claude/agents/ (generated
## Claude variants) and ~/.agents/ (partials and the shared bin/ scripts).
deploy-agents: check-pandoc
	@echo "Deploying agents to $(OPENCODE_AGENTS_DIR)..."
	@DRY_RUN=$(DRY_RUN) scripts/deploy-agents.sh "$(AGENTS_SRC)" "$(OPENCODE_AGENTS_DIR)" --md-only
	@if [ -L "$(CLAUDE_AGENTS_DIR)" ]; then \
		if [ "$(DRY_RUN)" = "1" ]; then \
			echo "MIGRATE $(CLAUDE_AGENTS_DIR): would replace the symlink with a real dir (target left intact)"; \
		else \
			echo "MIGRATE $(CLAUDE_AGENTS_DIR): replacing the symlink with a real dir (target left intact)"; \
			rm "$(CLAUDE_AGENTS_DIR)"; \
		fi; \
	fi
	@echo "Deploying generated Claude agent variants to $(CLAUDE_AGENTS_DIR)..."
	@DRY_RUN=$(DRY_RUN) scripts/deploy-agents.sh "$(AGENTS_SRC)" "$(CLAUDE_AGENTS_DIR)" --claude
	@echo "Deploying agent partials and bin/ scripts to $(AGENTS_DIR)..."
	@DRY_RUN=$(DRY_RUN) scripts/manifest-sync.sh "$(AGENTS_DIR)" $(AGENTS_DIR_ITEMS)

## Global rules → ~/.config/opencode/AGENTS.md
## The source file is gitignored; skips with a warning when it is absent.
deploy-global:
	@if [ ! -f "$(GLOBAL_AGENTS_SRC)" ]; then \
		echo "WARN  $(GLOBAL_AGENTS_SRC) not found — skipping (create it from global/AGENTS.md.example)"; \
	else \
		echo "Deploying global rules to $(GLOBAL_AGENTS_DEST)..."; \
		mkdir -p "$$(dirname "$(GLOBAL_AGENTS_DEST)")"; \
		rsync -av $(RSYNC_DRY) "$(GLOBAL_AGENTS_SRC)" "$(GLOBAL_AGENTS_DEST)"; \
	fi

## Read-only check: diff the repo against every deployed location. Never copies.
drift:
	@status=0; \
	DRY_RUN=$(DRY_RUN) scripts/manifest-sync.sh --drift "$(OPENCODE_SKILLS_DIR)" $(GLOBAL_SKILLS)/*/ || status=1; \
	DRY_RUN=$(DRY_RUN) scripts/manifest-sync.sh --drift "$(CLAUDE_SKILLS_DIR)" $(GLOBAL_SKILLS)/*/ || status=1; \
	DRY_RUN=$(DRY_RUN) scripts/manifest-sync.sh --drift "$(OPENCODE_COMMANDS_DIR)" $(COMMANDS_SRC)/* || status=1; \
	DRY_RUN=$(DRY_RUN) scripts/deploy-agents.sh --drift "$(AGENTS_SRC)" "$(OPENCODE_AGENTS_DIR)" --md-only || status=1; \
	DRY_RUN=$(DRY_RUN) scripts/deploy-agents.sh --drift "$(AGENTS_SRC)" "$(CLAUDE_AGENTS_DIR)" --claude || status=1; \
	DRY_RUN=$(DRY_RUN) scripts/manifest-sync.sh --drift "$(AGENTS_DIR)" $(AGENTS_DIR_ITEMS) || status=1; \
	if [ ! -f "$(GLOBAL_AGENTS_SRC)" ]; then \
		echo "INFO  $(GLOBAL_AGENTS_SRC) not found — skipping global rules drift"; \
	elif [ ! -f "$(GLOBAL_AGENTS_DEST)" ]; then \
		echo "DIFF  global rules: $(GLOBAL_AGENTS_DEST) not found"; \
		status=1; \
	elif diff -q "$(GLOBAL_AGENTS_SRC)" "$(GLOBAL_AGENTS_DEST)" >/dev/null; then \
		echo "OK    global rules"; \
	else \
		echo "DIFF  global rules"; \
		status=1; \
	fi; \
	exit $$status

## List all skills
list-skills:
	@echo "Custom ($(shell ls $(GLOBAL_SKILLS) 2>/dev/null | wc -l) skills):" && ls $(GLOBAL_SKILLS)/ 2>/dev/null || echo "(no skills)"

## List all agents
list-agents:
	@echo "Agents ($(shell ls $(AGENTS_SRC)/*.md 2>/dev/null | wc -l)):" && ls $(AGENTS_SRC)/*.md 2>/dev/null | xargs -n1 basename 2>/dev/null || echo "(no agents)"

## Run the converter and bin/ script tests (pytest from mise python)
test:
	python3 -m pytest -q tests/

## Validate skills, agents and docs, then run the tests
lint: check-pandoc lint-skills lint-agents lint-docs test

## Validate SKILL.md files before deploying
lint-skills:
	@ok=true; \
	for dir in $(GLOBAL_SKILLS)/*/; do \
		skill=$$(basename "$$dir"); \
		file="$$dir/SKILL.md"; \
		if [ ! -f "$$file" ]; then \
			echo "FAIL  $$skill: missing SKILL.md"; \
			ok=false; \
			continue; \
		fi; \
		if ! head -1 "$$file" | grep -q '^---$$'; then \
			echo "FAIL  $$skill: missing YAML frontmatter (no opening ---)"; \
			ok=false; \
			continue; \
		fi; \
		fm=$$(sed -n '2,/^---$$/p' "$$file"); \
		if ! echo "$$fm" | grep -q '^name:'; then \
			echo "FAIL  $$skill: frontmatter missing 'name:' field"; \
			ok=false; \
		fi; \
		if ! echo "$$fm" | grep -q '^description:'; then \
			echo "FAIL  $$skill: frontmatter missing 'description:' field"; \
			ok=false; \
		fi; \
		if echo "$$fm" | grep -q '^name:' && echo "$$fm" | grep -q '^description:'; then \
			echo "OK    $$skill"; \
		fi; \
	done; \
	$$ok

## Validate agent .md files before deploying
lint-agents:
	@ok=true; \
	for f in $(AGENTS_SRC)/*.md; do \
		agent=$$(basename "$$f" .md); \
		if ! head -1 "$$f" | grep -q '^---$$'; then \
			echo "FAIL  $$agent: missing YAML frontmatter (no opening ---)"; \
			ok=false; \
			continue; \
		fi; \
		fm=$$(sed -n '1,/^---$$/p' "$$f"); \
		description=$$(echo "$$fm" | yq eval 'select(di==0) | .description // ""' | grep -v '^null$$' | head -1); \
		if [ -z "$$description" ] || [ "$$description" = '""' ]; then \
			echo "FAIL  $$agent: frontmatter missing 'description:' field"; \
			ok=false; \
		fi; \
		perm_count=$$(echo "$$fm" | yq eval 'select(di==0) | .permissions | length' 2>/dev/null | grep -E '^[0-9]+$$' | grep -v '^0$$' | head -1); \
		if [ -z "$$perm_count" ]; then \
			echo "WARN  $$agent: missing 'permissions:' list (needed for opencode v2)"; \
		else \
			bad=$$(echo "$$fm" | yq eval 'select(di==0) | [.permissions[] | select((has("action") | not) or (has("resource") | not) or (has("effect") | not))] | length' 2>/dev/null | grep -E '^[1-9][0-9]*$$' | head -1); \
			if [ -n "$$bad" ]; then \
				echo "FAIL  $$agent: 'permissions' entry missing action/resource/effect"; \
				ok=false; \
			fi; \
		fi; \
		if [ -n "$$description" ] && [ "$$description" != '""' ]; then \
			echo "OK    $$agent"; \
		fi \
	done; \
	echo ""; \
	echo "=== Checking shared codemap state-hash snippet ==="; \
	tmp=$$(mktemp -d); \
	sed -n '/codemap-state-hash:begin/,/codemap-state-hash:end/p' "$(GLOBAL_SKILLS)/codemap/SKILL.md" > "$$tmp/skill"; \
	sed -n '/codemap-state-hash:begin/,/codemap-state-hash:end/p' "$(AGENTS_SRC)/observer.md" > "$$tmp/agent"; \
	if [ ! -s "$$tmp/skill" ] || [ ! -s "$$tmp/agent" ]; then \
		echo "FAIL  codemap state-hash snippet missing in /codemap or @observer"; \
		ok=false; \
	elif diff -q "$$tmp/skill" "$$tmp/agent" >/dev/null; then \
		echo "OK    codemap state-hash snippet identical"; \
	else \
		echo "FAIL  codemap state-hash snippet differs between /codemap and @observer"; \
		ok=false; \
	fi; \
	rm -rf "$$tmp"; \
	echo ""; \
	echo "=== Checking skills resolve work folders via ~/.agents/bin/artifact-dir ==="; \
	for f in $(ARTIFACT_DIR_CALLERS); do \
		if grep -qF '~/.agents/bin/artifact-dir' "$$f"; then \
			echo "OK    $$f calls artifact-dir"; \
		else \
			echo "FAIL  $$f does not call ~/.agents/bin/artifact-dir"; \
			ok=false; \
		fi; \
	done; \
	echo ""; \
	echo "=== Checking shared artifact-label snippet ==="; \
	tmp=$$(mktemp -d); \
	ref=""; \
	label_ok=true; \
	for f in "$(GLOBAL_SKILLS)/review/SKILL.md" "$(GLOBAL_SKILLS)/ship/SKILL.md"; do \
		out="$$tmp/$$(printf '%s' "$$f" | tr '/' '_')"; \
		sed -n '/artifact-label:begin/,/artifact-label:end/p' "$$f" > "$$out"; \
		if [ ! -s "$$out" ]; then \
			echo "FAIL  artifact-label snippet missing in $$f"; \
			ok=false; label_ok=false; \
		elif [ -z "$$ref" ]; then \
			ref="$$out"; \
		elif ! diff -q "$$ref" "$$out" >/dev/null; then \
			echo "FAIL  artifact-label snippet differs in $$f"; \
			ok=false; label_ok=false; \
		fi; \
	done; \
	if [ "$$label_ok" = true ] && [ -n "$$ref" ]; then \
		echo "OK    artifact-label snippet identical"; \
	fi; \
	rm -rf "$$tmp"; \
	echo ""; \
	echo "=== Checking shared .agents/.gitignore snippet ==="; \
	tmp=$$(mktemp -d); \
	ref=""; \
	gi_ok=true; \
	for f in "$(GLOBAL_SKILLS)/spec/SKILL.md" "$(GLOBAL_SKILLS)/arch/SKILL.md" "$(GLOBAL_SKILLS)/build/SKILL.md" "$(GLOBAL_SKILLS)/review/SKILL.md" "$(GLOBAL_SKILLS)/ship/SKILL.md" "$(GLOBAL_SKILLS)/codemap/SKILL.md" "$(GLOBAL_SKILLS)/handoff/SKILL.md" "$(GLOBAL_SKILLS)/learn/SKILL.md" "$(GLOBAL_SKILLS)/debt-ledger/SKILL.md" "$(AGENTS_SRC)/observer.md"; do \
		out="$$tmp/$$(printf '%s' "$$f" | tr '/' '_')"; \
		sed -n '/agents-gitignore:begin/,/agents-gitignore:end/p' "$$f" > "$$out"; \
		if [ ! -s "$$out" ]; then \
			echo "FAIL  .agents/.gitignore snippet missing in $$f"; \
			ok=false; gi_ok=false; \
		elif [ -z "$$ref" ]; then \
			ref="$$out"; \
		elif ! diff -q "$$ref" "$$out" >/dev/null; then \
			echo "FAIL  .agents/.gitignore snippet differs in $$f"; \
			ok=false; gi_ok=false; \
		fi; \
	done; \
	if [ "$$gi_ok" = true ] && [ -n "$$ref" ]; then \
		echo "OK    .agents/.gitignore snippet identical"; \
	fi; \
	rm -rf "$$tmp"; \
	echo ""; \
	echo "=== Checking generated Claude agent variants ==="; \
	gen=$$(mktemp -d); \
	if ! scripts/deploy-agents.sh --emit "$$gen" "$(AGENTS_SRC)" >/dev/null 2>&1; then \
		echo "FAIL  could not generate Claude agent variants"; \
		ok=false; \
	else \
		for f in "$$gen"/*.md; do \
			[ -e "$$f" ] || continue; \
			agent=$$(basename "$$f" .md); \
			fm=$$(sed -n '1,/^---$$/p' "$$f"); \
			if [ "$$(echo "$$fm" | yq eval 'select(di==0) | .name')" != "$$agent" ]; then \
				echo "FAIL  $$agent: generated 'name' missing or wrong"; \
				ok=false; \
				continue; \
			fi; \
			desc=$$(echo "$$fm" | yq eval 'select(di==0) | .description // ""' | grep -v '^null$$' | head -1); \
			if [ -z "$$desc" ] || [ "$$desc" = '""' ]; then \
				echo "FAIL  $$agent: generated 'description' missing"; \
				ok=false; \
				continue; \
			fi; \
			if [ "$$(echo "$$fm" | yq eval 'select(di==0) | .model')" != "inherit" ]; then \
				echo "FAIL  $$agent: generated model must be 'inherit'"; \
				ok=false; \
				continue; \
			fi; \
			tools=$$(echo "$$fm" | yq eval 'select(di==0) | .tools'); \
			for t in Read Grep Glob; do \
				echo "$$tools" | grep -qw "$$t" || { echo "FAIL  $$agent: generated tools missing $$t"; ok=false; }; \
			done; \
			if echo "$$fm" | grep -q 'opencode-go/'; then \
				echo "FAIL  $$agent: generated variant still references an OpenCode model"; \
				ok=false; \
			fi; \
			echo "OK    $$agent"; \
		done; \
	fi; \
	rm -rf "$$gen"; \
	$$ok

## Check slash-command references across AGENTS.md, every skill and every agent
lint-docs:
	@ok=true; \
	echo "=== Checking slash-command references ==="; \
	refs=$$(mktemp); \
	grep -hoP '\x60/\K[^/\x60 ,]+' AGENTS.md $(GLOBAL_SKILLS)/*/SKILL.md $(AGENTS_SRC)/*.md 2>/dev/null | sort -u > "$$refs"; \
	for ref in $$(cat "$$refs"); do \
		case "$$ref" in clear|skill-name|agent-name) continue ;; esac; \
		if [ -f "$(GLOBAL_SKILLS)/$$ref/SKILL.md" ] || [ -f "$(AGENTS_SRC)/$$ref.md" ]; then \
			echo "OK    /$$ref"; \
		else \
			echo "FAIL  /$$ref referenced but no skill or agent exists"; \
			ok=false; \
		fi \
	done; \
	rm -f "$$refs"; \
	echo ""; \
	echo "=== Checking @-references ==="; \
	at_refs=$$(mktemp); \
	grep -rhoP '\x60@\K[a-z][a-z0-9-]+' AGENTS.md README.md $(GLOBAL_SKILLS)/*/SKILL.md $(AGENTS_SRC)/*.md 2>/dev/null | sort -u > "$$at_refs"; \
	for ref in $$(cat "$$at_refs"); do \
		case "$$ref" in me|agent-name) continue ;; esac; \
		if [ -f "$(GLOBAL_SKILLS)/$$ref/SKILL.md" ] || [ -f "$(AGENTS_SRC)/$$ref.md" ]; then \
			echo "OK    @$$ref"; \
		else \
			echo "FAIL  @$$ref referenced but no skill or agent exists"; \
			ok=false; \
		fi \
	done; \
	rm -f "$$at_refs"; \
	echo ""; \
	echo "=== Checking agent references in AGENTS.md ==="; \
	for f in $(AGENTS_SRC)/*.md; do \
		agent=$$(basename "$$f" .md); \
		if grep -qE "\`@?$$agent\`" AGENTS.md; then \
			echo "OK    $$agent"; \
		else \
			echo "INFO  $$agent not referenced in AGENTS.md"; \
		fi \
	done; \
	echo ""; \
	echo "=== Checking artifact chain integrity ==="; \
	chain=$$(mktemp); \
	grep -oP '\x60<LABEL>-[^\x60]+\x60\s*\|\s*\x60[@/]\w+' AGENTS.md 2>/dev/null | sed 's/\x60//g' > "$$chain"; \
	while IFS='|' read -r artifact written_by; do \
		[ -n "$$artifact" ] || continue; \
		artifact=$$(echo "$$artifact" | xargs); \
		written_by=$$(echo "$$written_by" | xargs | cut -d' ' -f1); \
		sigil=$$(printf '%s' "$$written_by" | cut -c1); \
		name=$$(printf '%s' "$$written_by" | tr -d '/@'); \
		skill_file="$(GLOBAL_SKILLS)/$$name/SKILL.md"; \
		if [ ! -f "$$skill_file" ]; then \
			echo "FAIL  artifact '$$artifact' written by '$$name' but skill not found at $$skill_file"; \
			ok=false; \
		else \
			echo "OK    $$artifact ← $$sigil$$name"; \
		fi \
	done < "$$chain"; \
	rm -f "$$chain"; \
	echo ""; \
	$$ok
