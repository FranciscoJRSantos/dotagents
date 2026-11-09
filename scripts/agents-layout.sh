#!/bin/bash
# Slice 8: agents-layout.sh - scan and reorganize legacy .agents/ directories
# D10a: Migration of existing artifacts

set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

usage() {
    cat <<EOF
Usage: $SCRIPT_NAME <command> [options]

Commands:
  scan <path> [path...]     Scan for legacy .agents/ directories
  reorganize <path>         Reorganize a legacy .agents/ directory

Options:
  --dry-run                 Show what would be done without making changes
  -h, --help                Show this help message

Examples:
  $SCRIPT_NAME scan .
  $SCRIPT_NAME scan ~/projects ~/work
  $SCRIPT_NAME reorganize ./.agents
  $SCRIPT_NAME reorganize ./.agents --dry-run

EOF
}

# Check if a file indicates open work (not closed/complete)
has_open_work() {
    local file="$1"
    if [[ ! -f "$file" ]]; then
        return 1
    fi

    # Check YAML frontmatter for status field
    if head -20 "$file" | grep -q "^status:"; then
        local status
        status=$(head -20 "$file" | grep "^status:" | head -1 | sed 's/^status:[[:space:]]*//' | tr -d '[:space:]')
        if [[ "$status" == "closed" || "$status" == "complete" ]]; then
            return 1
        fi
    fi

    return 0
}

# Scan mode: find legacy .agents/ directories
cmd_scan() {
    local roots=("$@")

    if [[ ${#roots[@]} -eq 0 ]]; then
        echo -e "${RED}Error: scan requires at least one path${NC}" >&2
        usage
        exit 1
    fi

    echo -e "${BLUE}Scanning for legacy .agents/ directories...${NC}"
    echo

    local found=0
    local total_legacy=0
    local total_open=0

    for root in "${roots[@]}"; do
        if [[ ! -d "$root" ]]; then
            echo -e "${YELLOW}Warning: $root is not a directory, skipping${NC}" >&2
            continue
        fi

        # Find all .agents directories
        while IFS= read -r -d '' agents_dir; do
            local is_legacy=0
            local legacy_files=()
            local open_work=()

            # Check for files directly under artifacts/
            if [[ -d "$agents_dir/artifacts" ]]; then
                while IFS= read -r -d '' file; do
                    if [[ -f "$file" ]]; then
                        is_legacy=1
                        legacy_files+=("$file")
                        if has_open_work "$file"; then
                            open_work+=("$file")
                        fi
                    fi
                done < <(find "$agents_dir/artifacts" -maxdepth 1 -type f -print0 2>/dev/null)
            fi

            # Check for files directly under handoffs/
            if [[ -d "$agents_dir/handoffs" ]]; then
                while IFS= read -r -d '' file; do
                    if [[ -f "$file" ]]; then
                        is_legacy=1
                        legacy_files+=("$file")
                        # Handoffs are always considered "open" for scan purposes
                        open_work+=("$file")
                    fi
                done < <(find "$agents_dir/handoffs" -maxdepth 1 -type f -name "*.md" -print0 2>/dev/null)
            fi

            # Check for STATE.md
            if [[ -f "$agents_dir/STATE.md" ]]; then
                is_legacy=1
                legacy_files+=("$agents_dir/STATE.md")
                if has_open_work "$agents_dir/STATE.md"; then
                    open_work+=("$agents_dir/STATE.md")
                fi
            fi

            if [[ $is_legacy -eq 1 ]]; then
                found=$((found + 1))
                total_legacy=$((total_legacy + ${#legacy_files[@]}))
                total_open=$((total_open + ${#open_work[@]}))

                local relative_path="${agents_dir#$root/}"
                echo -e "${GREEN}$relative_path${NC}"
                echo "  Legacy files: ${#legacy_files[@]}"
                echo "  Open work: ${#open_work[@]}"

                if [[ ${#open_work[@]} -gt 0 ]]; then
                    echo "  Open items:"
                    for item in "${open_work[@]}"; do
                        echo "    - $(basename "$item")"
                    done
                fi
                echo
            fi
        done < <(find "$root" -type d -name ".agents" -print0 2>/dev/null)
    done

    echo -e "${BLUE}Summary:${NC}"
    echo "  Legacy .agents/ directories found: $found"
    echo "  Total legacy files: $total_legacy"
    echo "  Files with open work: $total_open"

    if [[ $found -eq 0 ]]; then
        echo
        echo "No legacy .agents/ directories found. All repositories are up to date!"
    else
        echo
        echo "Run 'reorganize' on each directory to migrate to the new structure."
    fi
}

# move_one <src> <dest> — move a legacy file into its archive destination,
# never overwriting what is already there (bumps the moved/skipped counters).
move_one() {
    local src="$1"
    local dest="$2"

    if [[ -e "$dest" ]]; then
        echo -e "  ${YELLOW}skipped (destination exists): ${dest#"$agents_dir"/}${NC}"
        skipped=$((skipped + 1))
        return
    fi
    if [[ $dry_run -eq 1 ]]; then
        moved=$((moved + 1))
        return
    fi
    mkdir -p "$(dirname "$dest")"
    mv "$src" "$dest"
    moved=$((moved + 1))
}

# Determine the destination for a file during reorganization
get_destination() {
    local file="$1"
    local agents_dir="$2"
    local filename
    filename="$(basename "$file")"

    # Pattern 1: <label>-{plan,kanban-board,impl-progress,review-impl}.md
    if [[ "$filename" =~ ^([a-z0-9-]+)-(plan|kanban-board|impl-progress|review-impl)\.md$ ]]; then
        local label="${BASH_REMATCH[1]}"
        local artifact_type="${BASH_REMATCH[2]}"

        # Map review-impl to review
        if [[ "$artifact_type" == "review-impl" ]]; then
            artifact_type="review"
        fi

        echo "$agents_dir/archive/$label/$artifact_type.md"
        return
    fi

    # Pattern 2: grill-<slug>-decisions.md
    if [[ "$filename" =~ ^grill-([a-z0-9-]+)-decisions\.md$ ]]; then
        local slug="${BASH_REMATCH[1]}"
        echo "$agents_dir/archive/$slug/decisions.md"
        return
    fi

    # Pattern 3: <TICKET>-<rest>.md (ticket-prefixed files)
    # Tickets are uppercase letters followed by digits, e.g., PROJ-123
    if [[ "$filename" =~ ^([A-Z]+-[0-9]+)-(.+)\.md$ ]]; then
        local ticket="${BASH_REMATCH[1]}"
        local rest="${BASH_REMATCH[2]}"
        echo "$agents_dir/archive/$ticket/$rest.md"
        return
    fi

    # Pattern 4: STATE.md
    if [[ "$filename" == "STATE.md" ]]; then
        echo "$agents_dir/archive/STATE.md"
        return
    fi

    # Pattern 5: handoffs/*.md
    if [[ "$(dirname "$file")" == "$agents_dir/handoffs" && "$filename" == *.md ]]; then
        echo "$agents_dir/archive/handoffs/$filename"
        return
    fi

    # Pattern 6: anything else goes to misc/
    echo "$agents_dir/archive/misc/$filename"
}

# Reorganize mode: migrate a legacy .agents/ directory
cmd_reorganize() {
    local agents_dir=""
    local dry_run=0

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --dry-run)
                dry_run=1
                shift
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            -*)
                echo -e "${RED}Error: Unknown option $1${NC}" >&2
                usage
                exit 1
                ;;
            *)
                if [[ -z "$agents_dir" ]]; then
                    agents_dir="$1"
                else
                    echo -e "${RED}Error: reorganize takes only one path${NC}" >&2
                    usage
                    exit 1
                fi
                shift
                ;;
        esac
    done

    if [[ -z "$agents_dir" ]]; then
        echo -e "${RED}Error: reorganize requires a path${NC}" >&2
        usage
        exit 1
    fi

    if [[ ! -d "$agents_dir" ]]; then
        echo -e "${RED}Error: $agents_dir is not a directory${NC}" >&2
        exit 1
    fi

    # Normalize path (remove trailing slash)
    agents_dir="${agents_dir%/}"

    # Check if it's a .agents directory
    if [[ "$(basename "$agents_dir")" != ".agents" ]]; then
        # Maybe they passed the repo root, look for .agents inside
        if [[ -d "$agents_dir/.agents" ]]; then
            agents_dir="$agents_dir/.agents"
        else
            echo -e "${RED}Error: $agents_dir is not a .agents directory${NC}" >&2
            exit 1
        fi
    fi

    if [[ $dry_run -eq 1 ]]; then
        echo -e "${YELLOW}DRY RUN MODE - No changes will be made${NC}"
        echo
    fi

    echo -e "${BLUE}Reorganizing $agents_dir...${NC}"
    echo

    local moved=0
    local skipped=0

    # Process files in artifacts/
    if [[ -d "$agents_dir/artifacts" ]]; then
        while IFS= read -r -d '' file; do
            if [[ -f "$file" ]]; then
                local dest
                dest="$(get_destination "$file" "$agents_dir")"

                local relative_src="${file#$agents_dir/}"
                local relative_dest="${dest#$agents_dir/}"

                echo -e "  ${GREEN}$relative_src${NC} → $relative_dest"

                move_one "$file" "$dest"
            fi
        done < <(find "$agents_dir/artifacts" -maxdepth 1 -type f -print0 2>/dev/null)

        # Remove empty artifacts directory
        if [[ $dry_run -eq 0 && -d "$agents_dir/artifacts" ]]; then
            rmdir "$agents_dir/artifacts" 2>/dev/null || true
        fi
    fi

    # Process files in handoffs/
    if [[ -d "$agents_dir/handoffs" ]]; then
        while IFS= read -r -d '' file; do
            if [[ -f "$file" ]]; then
                local dest
                dest="$(get_destination "$file" "$agents_dir")"

                local relative_src="${file#$agents_dir/}"
                local relative_dest="${dest#$agents_dir/}"

                echo -e "  ${GREEN}$relative_src${NC} → $relative_dest"

                move_one "$file" "$dest"
            fi
        done < <(find "$agents_dir/handoffs" -maxdepth 1 -type f -name "*.md" -print0 2>/dev/null)

        # Remove empty handoffs directory
        if [[ $dry_run -eq 0 && -d "$agents_dir/handoffs" ]]; then
            rmdir "$agents_dir/handoffs" 2>/dev/null || true
        fi
    fi

    # Process STATE.md
    if [[ -f "$agents_dir/STATE.md" ]]; then
        local dest
        dest="$(get_destination "$agents_dir/STATE.md" "$agents_dir")"

        local relative_src="STATE.md"
        local relative_dest="${dest#$agents_dir/}"

        echo -e "  ${GREEN}$relative_src${NC} → $relative_dest"

        move_one "$agents_dir/STATE.md" "$dest"
    fi

    echo
    echo -e "${BLUE}Summary:${NC}"
    echo "  Files moved: $moved"
    echo "  Files skipped: $skipped"

    if [[ $dry_run -eq 1 ]]; then
        echo
        echo "This was a dry run. Run without --dry-run to apply changes."
    else
        echo
        echo -e "${GREEN}Reorganization complete!${NC}"
    fi
}

# Main entry point
if [[ $# -eq 0 ]]; then
    usage
    exit 1
fi

command="$1"
shift

case "$command" in
    scan)
        cmd_scan "$@"
        ;;
    reorganize)
        cmd_reorganize "$@"
        ;;
    -h|--help)
        usage
        exit 0
        ;;
    *)
        echo -e "${RED}Error: Unknown command '$command'${NC}" >&2
        usage
        exit 1
        ;;
esac
