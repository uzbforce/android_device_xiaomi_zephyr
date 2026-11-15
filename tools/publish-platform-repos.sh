#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
#
# Mirror the platform projects pinned by local_manifests/zephyr.xml into your own
# GitHub org and (optionally) point the manifest at the copies.
#
# Why: the SM6225 platform tree is the one part of this port that LineageOS
# 23.2 does not ship, so it is taken from third-party forks
# (rn124g-development). As long as the manifest names those repos, the build
# depends on somebody else's account staying up and their branches not being
# rewritten. Mirroring them makes the port self-contained.
#
# Usage:
#   ./tools/publish-platform-repos.sh <github-owner> [options]
#
#   --rewrite-manifest  rewrite local_manifests/zephyr.xml to name the copies
#   --work DIR          where to keep the mirror clones (default: .platform-mirrors
#                       next to this repo, git-ignored)
#   --dry-run           print what would happen, touch nothing
#
# Needs an authenticated `gh` (gh auth login) to create the repos, and a git
# credential helper that can push to <github-owner>.
#
# Each mirror is named from its manifest path - android_<path, / replaced by _>.
# That is the LineageOS project name for every platform tree, so the copies read
# the same as the manifests every qcom device uses. It also fixes the upstream
# names that do not follow it (rn124g-development/hardware_qcom-caf_common, the
# fork of android_hardware_qcom-caf_common).
#
# The revisions in the manifest are commit SHAs, and a mirror push carries every
# ref, so the pinned commits stay valid after the rewrite - that is why the
# script verifies each pinned SHA exists in the mirror before it claims success.

set -eu

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
manifest="$repo_root/local_manifests/zephyr.xml"
owner="${1:-}"
shift || true

rewrite=false
dry_run=false
work=""

while [ $# -gt 0 ]; do
    case "$1" in
        --rewrite-manifest) rewrite=true ;;
        --dry-run) dry_run=true ;;
        --work) shift; work="$1" ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
    shift
done

if [ -z "$owner" ]; then
    sed -n '12,16p' "$0" | sed 's/^# \{0,1\}//'
    exit 2
fi

[ -f "$manifest" ] || { echo "not found: $manifest" >&2; exit 1; }
[ -n "$work" ] || work="$(dirname "$repo_root")/.platform-mirrors"
mkdir -p "$work"

if [ "$dry_run" = false ]; then
    command -v gh >/dev/null 2>&1 || { echo "gh not installed; see the script header" >&2; exit 1; }
    gh auth status >/dev/null 2>&1 || { echo "gh is not authenticated; run 'gh auth login'" >&2; exit 1; }
fi

# name<TAB>revision<TAB>path, straight out of the manifest.
projects=$(python3 - "$manifest" <<'PY'
import sys
import xml.etree.ElementTree as ET

root = ET.parse(sys.argv[1]).getroot()
for p in root.iter('project'):
    revision = p.get('revision') or ''
    print(f"{p.get('name')}\t{revision}\t{p.get('path')}")
PY
)

if [ -z "$projects" ]; then
    echo "no <project> entries in $manifest" >&2
    exit 1
fi

echo "mirroring $(printf '%s\n' "$projects" | wc -l) platform projects into $owner/"
echo "mirrors: $work"
echo

failed=0
rewrites=""

while IFS=$'\t' read -r name revision path; do
    [ -n "$name" ] || continue
    upstream="https://github.com/$name"
    # Named after the path, not the upstream repo: see the header.
    short="android_$(printf '%s' "$path" | tr '/' '_')"
    target="$owner/$short"
    mirror="$work/$short.git"

    printf '%-58s ' "$short"

    if [ "$dry_run" = true ]; then
        echo "would mirror $upstream -> $target (pin ${revision:-<none>})"
        rewrites="$rewrites$name $target\n"
        continue
    fi

    if [ -d "$mirror" ]; then
        # `git remote update` takes no --quiet; fetch --all is the same refresh.
        git -C "$mirror" fetch --all --prune --quiet || { echo "FETCH FAILED"; failed=$((failed + 1)); continue; }
    else
        git clone --mirror --quiet "$upstream" "$mirror" || { echo "CLONE FAILED"; failed=$((failed + 1)); continue; }
    fi

    if ! gh repo view "$target" >/dev/null 2>&1; then
        gh repo create "$target" --public >/dev/null || { echo "CREATE FAILED"; failed=$((failed + 1)); continue; }
    fi

    # A mirror clone carries the upstream's refs/pull/*, and GitHub rejects a
    # push to those ("deny updating a hidden ref") - which fails the whole push,
    # branches included. Drop them locally so --mirror cannot name them; the
    # branches and tags that carry the pinned commits are unaffected.
    git -C "$mirror" for-each-ref --format='%(refname)' refs/pull \
        | while read -r pull_ref; do git -C "$mirror" update-ref -d "$pull_ref"; done

    git -C "$mirror" push --mirror --quiet "https://github.com/$target.git" \
        || { echo "PUSH FAILED"; failed=$((failed + 1)); continue; }

    if [ -n "$revision" ] && ! git -C "$mirror" cat-file -e "$revision^{commit}" 2>/dev/null; then
        echo "PUSHED, but pinned $revision is missing from the mirror"
        failed=$((failed + 1))
        continue
    fi

    echo "mirrored -> $target${revision:+ (pin $revision present)}"
    rewrites="$rewrites$name $target\n"
done <<< "$projects"

echo
if [ "$failed" -ne 0 ]; then
    echo "$failed project(s) failed; manifest left alone"
    exit 1
fi

if [ "$dry_run" = true ]; then
    echo "dry run: nothing was created or pushed"
    exit 0
fi

if [ "$rewrite" = true ]; then
    cp "$manifest" "$manifest.bak"
    while read -r from to; do
        [ -n "$from" ] || continue
        sed -i "s#name=\"$from\"#name=\"$to\"#g" "$manifest"
    done < <(printf '%b' "$rewrites")
    echo "rewrote $manifest (backup: $manifest.bak)"
    echo "revisions were not touched: the pinned SHAs are the ones just verified in the mirrors"
    echo
    echo "Review it, then re-sync:"
    echo "  cp device/xiaomi/zephyr/local_manifests/zephyr.xml .repo/local_manifests/"
    echo "  repo sync -c -j8 --force-sync hardware/qcom-caf device/qcom/sepolicy_vndr"
else
    echo "Repos are on GitHub. To stop depending on the upstream forks, run this"
    echo "again with --rewrite-manifest, or edit local_manifests/zephyr.xml so the"
    echo "name= attributes read $owner/<repo> (keep the revisions as they are)."
fi
