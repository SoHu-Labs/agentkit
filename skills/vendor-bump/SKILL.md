---
name: vendor-bump
description: Bump the pinned agentkit ref in every consumer repo's CI after tagging a new agentkit release. Use right after creating an agentkit tag (see streamline.md T6) to roll all consumers to it deliberately.
---

# Bump pinned agentkit ref across consumers

## Steps
1. Tag + push the new agentkit version first (e.g. `git tag v0.1.1 && git push origin v0.1.1`).
2. `python skills/vendor-bump/scripts/bump_agentkit.py v0.1.1`.
3. Review the diffs it reports, commit each consumer repo, and let CI run on the
   pinned ref.
