#!/bin/bash
# Deploy provenance (ADR-001 amendment 9) -- sourced by common.sh.

# Every deployed image carries an immutable source identity (IMAGE_REVISION, handed to compose):
# the caller's, else `git describe --tags --always --dirty`; none is refused. A production deploy
# from a checkout with uncommitted changes is refused -- what runs must be what was committed.
deploy_require_provenance() {
  local env="${1:-prod}" root
  root="${STACK_KIT_PROJECT_ROOT:-$(pwd)}"
  if [[ -z "${IMAGE_REVISION:-}" ]]; then
    IMAGE_REVISION="$(git -C "$root" describe --tags --always --dirty 2>/dev/null || true)"
  fi
  if [[ -z "$IMAGE_REVISION" || "$IMAGE_REVISION" == "unknown" ]]; then
    echo "  ERROR: IMAGE_REVISION cannot be determined; refusing a deploy without provenance" >&2
    return 1
  fi
  if [[ "$env" == "prod" && -n "$(git -C "$root" status --porcelain 2>/dev/null)" ]]; then
    echo "  ERROR: a production deploy needs a clean checkout (git status shows uncommitted or untracked files)" >&2
    return 1
  fi
  export IMAGE_REVISION
}
