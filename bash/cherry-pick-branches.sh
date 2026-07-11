#!/bin/bash

# Cherry-pick commit across multiple 389-ds-base branches
# Usage:
#   ./cherry-pick-branches.sh           # Full process: cherry-pick and push
#   ./cherry-pick-branches.sh --dry-run # Cherry-pick only (test for conflicts)
#   ./cherry-pick-branches.sh --push    # Push previously cherry-picked commits

set -euo pipefail

# Check for flags
DRY_RUN=false
PUSH_ONLY=false

if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=true
    echo "🧪 DRY RUN MODE - Cherry-picking without pushing"
    echo "==============================================="
elif [[ "${1:-}" == "--push" ]]; then
    PUSH_ONLY=true
    echo "📤 PUSH MODE - Pushing previously cherry-picked commits"
    echo "====================================================="
fi

# The commit to cherry-pick (updated after each successful pick so later
# branches inherit the previously resolved commit)
COMMIT="xxxxxxxxxxxx"

# Editor used to resolve conflicts (override with EDITOR / VISUAL)
EDITOR_CMD="${VISUAL:-${EDITOR:-vim}}"

# Array of branches to process
BRANCHES=(
    "389-ds-base-3.2"
    "389-ds-base-3.1"
    "389-ds-base-3.0"
    "389-ds-base-2.9"
    "389-ds-base-2.8"
    "389-ds-base-2.7"
    "389-ds-base-2.6"
    "389-ds-base-2.4"
    "389-ds-base-2.2"
    "389-ds-base-1.4.3"
)

# Returns 0 if a cherry-pick is in progress
cherry_pick_in_progress() {
    [[ -d "$(git rev-parse --git-path cherry-pick-head)" ]] \
        || [[ -f "$(git rev-parse --git-path CHERRY_PICK_HEAD)" ]]
}

# List unmerged / conflicted paths
list_conflicted_files() {
    git diff --name-only --diff-filter=U
}

# True if file still contains conflict markers
file_has_conflict_markers() {
    local file="$1"
    grep -qE '^(<<<<<<<|=======|>>>>>>>)' "$file"
}

# Prompt until the user answers y/n (always uses the real terminal)
ask_yes_no() {
    local prompt="$1"
    local reply
    while true; do
        printf '%s [y/n]: ' "$prompt" > /dev/tty
        read -r reply < /dev/tty
        case "$reply" in
            [Yy]|[Yy][Ee][Ss]) return 0 ;;
            [Nn]|[Nn][Oo]) return 1 ;;
            *) echo "Please answer y or n." > /dev/tty ;;
        esac
    done
}

# Interactively resolve all conflicted files, then continue the cherry-pick.
# Prints status on stderr; echoes only the resulting commit hash on stdout.
resolve_cherry_pick_conflicts() {
    local conflicted_files=()
    local file
    local remaining

    mapfile -t conflicted_files < <(list_conflicted_files)

    if [[ ${#conflicted_files[@]} -eq 0 ]]; then
        echo "⚠️  Cherry-pick failed but no unmerged files were found." >&2
        echo "    Inspect the repo state manually, then re-run." >&2
        return 1
    fi

    echo >&2
    echo "⚠️  CONFLICT on branch $(git branch --show-current)" >&2
    echo "Files that need resolution (${#conflicted_files[@]}):" >&2
    for file in "${conflicted_files[@]}"; do
        echo "  - $file" >&2
    done
    echo >&2

    if ! ask_yes_no "Open each conflicted file in $EDITOR_CMD to resolve?"; then
        echo "Aborting cherry-pick..." >&2
        git cherry-pick --abort
        return 1
    fi

    for file in "${conflicted_files[@]}"; do
        echo >&2
        echo "────────────────────────────────────────" >&2
        echo "Resolving: $file" >&2
        echo "Edit conflict markers, then save and exit." >&2
        echo "────────────────────────────────────────" >&2

        while true; do
            "$EDITOR_CMD" "$file" < /dev/tty > /dev/tty 2>&1 || true

            if file_has_conflict_markers "$file"; then
                echo >&2
                echo "❌ Conflict markers still present in: $file" >&2
                if ask_yes_no "Re-open $file to finish resolving?"; then
                    continue
                fi
                echo "Aborting cherry-pick..." >&2
                git cherry-pick --abort
                return 1
            fi

            git add -- "$file"
            echo "✅ Resolved and staged: $file" >&2
            break
        done
    done

    # Catch any leftover unmerged paths (e.g. added mid-resolution)
    mapfile -t remaining < <(list_conflicted_files)
    if [[ ${#remaining[@]} -gt 0 ]]; then
        echo "❌ Still unmerged after editing:" >&2
        printf '  - %s\n' "${remaining[@]}" >&2
        echo "Aborting cherry-pick..." >&2
        git cherry-pick --abort
        return 1
    fi

    echo >&2
    echo "All conflicts resolved. Continuing cherry-pick..." >&2
    # GIT_EDITOR=true skips the commit-message editor and keeps the original message.
    # Redirect continue output to stderr so only the hash below is captured by callers.
    if ! GIT_EDITOR=true git cherry-pick --continue >&2; then
        echo "❌ git cherry-pick --continue failed." >&2
        if cherry_pick_in_progress; then
            echo "Cherry-pick still in progress — aborting." >&2
            git cherry-pick --abort
        fi
        return 1
    fi

    git rev-parse HEAD
}

# Collected from git push output: "abc1234..def5678 branch -> branch"
PUSH_RESULTS=()

# Run git push and append any "old..new ref -> ref" lines to PUSH_RESULTS.
# Prints the full push output as usual.
push_branch() {
    local branch="$1"
    local push_output
    local line
    local summary

    echo "Pushing to upstream..."
    # git push writes the range summary to stderr
    set +e
    push_output="$(git push origin "$branch" 2>&1)"
    local push_status=$?
    set -e

    printf '%s\n' "$push_output"

    if [[ $push_status -ne 0 ]]; then
        echo "❌ Push failed for $branch"
        return "$push_status"
    fi

    while IFS= read -r line; do
        # Match: <old>..<new> <local> -> <remote>  (optional leading spaces)
        if [[ "$line" =~ ([0-9a-fA-F]+\.\.[0-9a-fA-F]+)[[:space:]]+([^[:space:]]+)[[:space:]]+\-\>[[:space:]]+([^[:space:]]+) ]]; then
            summary="${BASH_REMATCH[1]} ${BASH_REMATCH[2]} -> ${BASH_REMATCH[3]}"
            PUSH_RESULTS+=("$summary")
        fi
    done <<< "$push_output"
}

echo "Starting cherry-pick process for commit: $COMMIT"
echo "Branches to process: ${#BRANCHES[@]}"
echo "Editor for conflicts: $EDITOR_CMD"
echo

# Process each branch
for branch in "${BRANCHES[@]}"; do
    echo "Processing branch: $branch"
    echo "----------------------------------------"

    if [[ "$PUSH_ONLY" == false ]]; then
        echo "Checking out $branch..."
        git checkout "$branch"

        echo "Pulling latest changes from upstream..."
        git pull origin "$branch"

        echo "Cherry-picking commit $COMMIT..."
        set +e
        git cherry-pick "$COMMIT"
        pick_status=$?
        set -e

        if [[ $pick_status -ne 0 ]]; then
            if cherry_pick_in_progress; then
                if ! new_commit="$(resolve_cherry_pick_conflicts)"; then
                    echo "❌ Failed to resolve conflicts on $branch — stopping."
                    exit 1
                fi
                # Keep only the bare hash (ignore any accidental extra output)
                new_commit="$(printf '%s\n' "$new_commit" | awk 'NF{line=$0} END{print line}')"
                if ! git rev-parse --verify --quiet "$new_commit^{commit}" >/dev/null; then
                    echo "❌ Could not parse resolved commit hash from: $new_commit"
                    exit 1
                fi
                echo "📌 Conflict resolved. New commit: $new_commit"
                echo "   Using this hash for subsequent branches."
                COMMIT="$new_commit"
            else
                echo "❌ Cherry-pick failed on $branch (not a conflict). Stopping."
                exit 1
            fi
        else
            # Clean cherry-pick — still advance COMMIT so later branches
            # pick the tip of the chain we just built
            COMMIT="$(git rev-parse HEAD)"
            echo "📌 Cherry-pick clean. New commit: $COMMIT"
        fi
    fi

    # Push to upstream (skip in dry-run mode)
    if [[ "$DRY_RUN" == false ]]; then
        push_branch "$branch"
        echo "✅ Successfully processed $branch"
    else
        echo "⏸️  Cherry-pick completed for $branch (not pushed)"
    fi
    echo
done

if [[ "$DRY_RUN" == true ]]; then
    echo "🧪 DRY RUN COMPLETE"
    echo "Cherry-picks applied successfully to all branches but not pushed."
    echo "Review the changes, then run: $0 --push"
elif [[ "$PUSH_ONLY" == true ]]; then
    echo "📤 All previously cherry-picked commits pushed successfully!"
else
    echo "✅ All branches processed and pushed successfully!"
    echo "Cherry-pick operation completed."
fi

if [[ "$DRY_RUN" == false && ${#PUSH_RESULTS[@]} -gt 0 ]]; then
    echo
    echo "Push summary:"
    printf '%s\n' "${PUSH_RESULTS[@]}"
fi
