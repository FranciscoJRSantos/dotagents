GLOBAL_SKILLS      := skills
AGENTS_SRC         := agents

## Files that resolve the active work folder: each must call ~/.agents/bin/artifact-dir
## (checked by lint-agents).
ARTIFACT_DIR_CALLERS := $(GLOBAL_SKILLS)/arch/SKILL.md $(GLOBAL_SKILLS)/build/SKILL.md $(GLOBAL_SKILLS)/review/SKILL.md $(GLOBAL_SKILLS)/ship/SKILL.md \
  $(GLOBAL_SKILLS)/handoff/SKILL.md $(GLOBAL_SKILLS)/assess/SKILL.md $(GLOBAL_SKILLS)/reporting/SKILL.md

## Generated Claude Code agent variants (gitignored build output, linked by stow/claude).
CLAUDE_AGENTS_BUILD := build/claude-agents

## Set DRY_RUN=1 to preview what `make link` would change (stow -n, migration dry run).
DRY_RUN ?=
ifeq ($(DRY_RUN),1)
STOW_FLAGS := -n -v
else
STOW_FLAGS :=
endif

.PHONY: check-cmds check-pandoc link stow-gen build-claude lint-links test-plugins lint lint-skills lint-agents lint-docs test list-skills list-agents

## Link everything into OpenCode, Claude Code and ~/.agents with stow. Edits to skills,
## agents, plugins, bin/ and global/AGENTS.md take effect in place; there is no deploy step.
## --no-folding keeps the live skills/ and agents/ dirs real, so harness-owned entries
## (synced/, nono-sandbox.ts) never land inside this repo.
link: check-cmds stow-gen build-claude
	@scripts/migrate-manifests.sh $(if $(filter 1,$(DRY_RUN)),--dry-run)
	@cd stow && stow $(STOW_FLAGS) --no-folding -R -t "$(HOME)" opencode claude agents-home \
		$(if $(filter 1,$(DRY_RUN)),|| echo "NOTE  stow conflicts above are expected until the old copies are removed by a real make link")

## Regenerate stow/ from the repo sources (a deleted skill or agent drops out of stow/).
stow-gen:
	@scripts/gen-stow.sh

## Claude Code variants of the agents (frontmatter rebuilt) → build/claude-agents/.
build-claude:
	@scripts/build-claude.sh "$(AGENTS_SRC)" "$(CLAUDE_AGENTS_BUILD)"

## Every link under stow/ must resolve.
lint-links: stow-gen build-claude
	@scripts/lint-stow-links.sh

## Fail before anything is written when a required tool is missing.
check-cmds: check-pandoc
	@command -v stow >/dev/null 2>&1 || { echo "FAIL  stow not found — install it (dnf install stow)"; exit 1; }
	@command -v yq >/dev/null 2>&1 && yq --version 2>&1 | grep -q mikefarah || { echo "FAIL  mikefarah yq not found — install it (mise use yq)"; exit 1; }

## bin/md2org needs pandoc; fail before linting without it.
check-pandoc:
	@command -v pandoc >/dev/null 2>&1 || { echo "FAIL  pandoc not found — install it (dnf install pandoc); bin/md2org needs it"; exit 1; }

## List all skills
list-skills:
	@echo "Custom ($(shell ls $(GLOBAL_SKILLS) 2>/dev/null | wc -l) skills):" && ls $(GLOBAL_SKILLS)/ 2>/dev/null || echo "(no skills)"

## List all agents
list-agents:
	@echo "Agents ($(shell ls $(AGENTS_SRC)/*.md 2>/dev/null | wc -l)):" && ls $(AGENTS_SRC)/*.md 2>/dev/null | xargs -n1 basename 2>/dev/null || echo "(no agents)"

## Run the converter and bin/ script tests (pytest from mise python)
test: test-plugins
	python3 -m pytest -q tests/

## Plugin unit tests (node's built-in runner strips TS types; no install needed)
test-plugins:
	@for d in plugins/*/; do (cd "$$d" && node --test 'test/*.test.ts') || exit 1; done

## Validate skills, agents, docs and stow links, then run the tests
lint: check-pandoc lint-skills lint-agents lint-docs lint-links test

## Validate SKILL.md files before linking
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

## Validate agent .md files before linking
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
	echo "=== Checking shared .agents/.gitignore snippet ==="; \
	tmp=$$(mktemp -d); \
	ref=""; \
	gi_ok=true; \
	for f in "$(GLOBAL_SKILLS)/spec/SKILL.md" "$(GLOBAL_SKILLS)/arch/SKILL.md" "$(GLOBAL_SKILLS)/build/SKILL.md" "$(GLOBAL_SKILLS)/review/SKILL.md" "$(GLOBAL_SKILLS)/ship/SKILL.md" "$(GLOBAL_SKILLS)/handoff/SKILL.md"; do \
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
	if ! scripts/build-claude.sh "$(AGENTS_SRC)" "$$gen" >/dev/null 2>&1; then \
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
	grep -oP '\x60<slug>/[^\x60]+\x60\s*\|\s*\x60[@/]\w+' AGENTS.md 2>/dev/null | sed 's/\x60//g' > "$$chain"; \
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
