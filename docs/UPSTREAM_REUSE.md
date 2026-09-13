# Open-source reuse strategy

## Rule

Reuse research/tooling **behind adapters**. Do not make the public runtime contract depend on any generator implementation.

```text
upstream project → adapter/provider → normalized Studio asset → validation → publication
```

## Reuse modes

1. **Direct tool dependency** — stable utilities such as glTF Transform.
2. **External worker/service** — GPU-heavy systems such as TripoSR or a licence-cleared panorama model.
3. **Maintained fork** — only if an adapter cannot provide required API/memory/error-handling behavior.
4. **Reference only** — useful architecture with licensing or scope reasons that make direct reuse undesirable.

## Current classifications (after the 2026-09-11 licence audit)

- **Manual import**: the first and permanent panorama provider. V1 needs no model.
- **KTX-Software / Basis**: V1 production dependency. KTX2 is what keeps a 4096x2048
  panorama at ~12 MB of Quest texture memory instead of ~45 MB.
- **libvips, FFmpeg + libopus**: V1 production dependencies. FFmpeg's *build* decides
  whether it is LGPL or GPL, which matters if we redistribute the worker image.
- **glTF Transform**: MIT, direct/offline tool for V2 GLB optimization.
- **TripoSR**: V2 image-to-3D default. MIT code **and** MIT weights, ~6 GB VRAM.
- **TRELLIS**: V2 premium. MIT code and weights; submodules need a separate audit.
- **Diffusion360 / SD-T2I-360PanoImage**: leading self-hosted panorama candidate
  (Apache-2.0 code), gated on its weights audit.
- **Text2VR**: architecture reference only. Reuse its stage decomposition, not its
  topology, and note that its root MIT licence does not cover what it integrates.
- **PanFusion**: **evaluation only, not a production provider.** MIT code, but the
  checkpoint is Matterport3D-derived (non-commercial; CC BY-NC-SA). *This withdraws the
  earlier recommendation.*
- **DreamScene360**: **rejected for production.** Inria/MPII Gaussian-Splatting research
  licence — non-commercial, no sublicensing.
- **MVDiffusion, DiT360**: reference only; same Matterport3D lineage.

A fork cannot fix a licence. If the weights are non-commercial, no amount of adapter,
Dockerfile or API work changes that — which is why the reuse mode is decided *after* the
licence audit, never before.

## Upstream upgrades

`upstreams.lock.json` records tested/observed revisions. `scripts/bootstrap_upstreams.py` checks out those revisions. Upgrade one upstream at a time, rerun provider contract tests, and record the new ref only after validation.

## Do not vendor checkpoints

Model checkpoints and large Docker images must not be committed to this repository. Workers should fetch/cache them separately under their own license terms.
