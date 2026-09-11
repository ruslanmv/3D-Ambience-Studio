# Open-source reuse strategy

## Rule

Reuse research/tooling **behind adapters**. Do not make the public runtime contract depend on any generator implementation.

```text
upstream project → adapter/provider → normalized Studio asset → validation → publication
```

## Reuse modes

1. **Direct tool dependency** — stable utilities such as glTF Transform.
2. **External worker/service** — GPU-heavy systems such as PanFusion or TripoSR.
3. **Maintained fork** — only if an adapter cannot provide required API/memory/error-handling behavior.
4. **Reference only** — useful architecture with licensing or scope reasons that make direct reuse undesirable.

## Current default classifications

- PanFusion: external panorama provider candidate.
- glTF Transform: direct/offline tool for V2 GLB optimization.
- TripoSR: V2 external image-to-3D provider candidate.
- Text2VR: architecture reference; selectively reimplement integration patterns, not a wholesale fork.
- DreamScene360: reference/experimental; do not ship by default under current root licensing without permission/clarification.

## Upstream upgrades

`upstreams.lock.json` records tested/observed revisions. `scripts/bootstrap_upstreams.py` checks out those revisions. Upgrade one upstream at a time, rerun provider contract tests, and record the new ref only after validation.

## Do not vendor checkpoints

Model checkpoints and large Docker images must not be committed to this repository. Workers should fetch/cache them separately under their own license terms.
