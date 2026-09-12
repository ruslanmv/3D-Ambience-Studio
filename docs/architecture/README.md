# 3D-Ambience-Studio — Master Architecture Plan

Planning deliverable. **No production code is part of this set of documents.** The only
machine-readable artifacts here are *draft* contracts under `contracts/`, which are
proposals for `schemas/` rather than replacements for it.

Prepared: 2026-09-11. Evidence base: direct inspection of `ruslanmv/3D-Avatar-Chatbot`
at `251e07b` and of this repository at `46a7c99`, plus upstream licence/maintenance
checks recorded in `03-LICENSING.md`.

## Read in this order

| # | Document | Covers (task section) |
|---|---|---|
| 00 | [Executive decision](00-EXECUTIVE-DECISION.md) | A, B, §65 final decision, implement-first / after / never |
| 01 | [Avatar runtime analysis](01-AVATAR-RUNTIME-ANALYSIS.md) | C, R — what the runtime *actually* does, with file:line evidence |
| 02 | [Upstream analysis](02-UPSTREAM-ANALYSIS.md) | D, §19 per-project classification, §20 reuse matrix |
| 03 | [Licensing review](03-LICENSING.md) | E, §14 licensing gate |
| 04 | [V1 architecture](04-V1-ARCHITECTURE.md) | F, G, H, I, V |
| 05 | [Contract and schemas](05-CONTRACT-SCHEMAS.md) | J, K, L, §52–53 |
| 06 | [Asset pipelines](06-ASSET-PIPELINES.md) | M, N, O, P, Q |
| 07 | [Quality, security, ops](07-QUALITY-SECURITY-OPS.md) | S, T, U |
| 08 | [Roadmap and PR plan](08-ROADMAP-AND-PR-PLAN.md) | W, X, Y |

## The five findings that changed the plan

Each is evidenced in document 01 or 03. They are listed here because each one
invalidates an assumption in the original brief.

1. **The runtime already has an environment contract, and it is not the one this
   repository publishes.** `src/features/together/activities/scene-journey.js` loads
   JSON scene manifests with fields `id`, `title`, `skybox`, `ambient`,
   `fallbackColor`, `lighting.exposure`, `anchors[]`, `avatarPlacement`,
   `profileOverlay`, `guidedScript`. The Studio's `schemas/environment.schema.json`
   shares almost none of those names. Two of the runtime's field requirements are
   *hard validation gates* — a manifest without a string `title` and an array
   `anchors` is rejected outright. The contract work is therefore reconciliation,
   not greenfield design.

2. **The runtime cannot currently load a panorama at all.** `src/behavior/boot.js:566`
   constructs the journey with `{bus, blackboard, gate}` and no `loadTexture`, so
   `_loadTexture` is `null` and `_applySkybox` always falls through to
   `fallbackColor`. Scenes today are a solid colour plus an audio loop. Publishing
   perfect panoramas changes nothing until a small, well-scoped avatar-side change
   lands. This is the real first milestone dependency.

3. **Entering VR destroys the environment.** `ViewerEngine.js:346` overwrites
   `scene.background` with a solid `THREE.Color` on XR session start. The Quest
   panorama variant this repository is designed to produce is discarded by the
   runtime at exactly the moment it matters most.

4. **No open-weights 360° panorama model currently has a clean commercial path.**
   DreamScene360 ships under the Inria/MPII Gaussian-Splatting **non-commercial
   research** licence. PanFusion's MIT code is trained on Matterport3D, whose
   academic EULA and CC BY-NC-SA terms follow the weights. DiT360 is MIT but
   Matterport3D-derived and needs ~37 GB VRAM for 2048×1024 output. The existing
   recommendation of PanFusion as the first V1 provider is withdrawn in
   `03-LICENSING.md`.

5. **Panorama-as-IBL is the wrong default, for a measurable reason.** The runtime
   assigns one texture to both `scene.background` and `scene.environment`
   (`scene-journey.js:334-335`). In the vendored three r147, any equirect texture
   assigned to `scene.environment` is pushed through `PMREMGenerator`
   (`three.module.js:16177-16182`), allocating an extra cubeUV render target and a
   blur chain — paid on a Quest, for an LDR sky that yields flat lighting anyway.
   Lighting belongs in semantic presets plus an optional tiny HDR, not in the
   8-megapixel background.

## What this plan deliberately refuses to do

- Adopt Text2VR's service topology. It is a 1-star, 128-commit research integration
  whose value is its stage decomposition, not its deployment model (`02`).
- Make any V1 milestone depend on a GPU model (`08`).
- Let the published manifest name its generator (`05`).
- Put generated binaries in Git, or let the runtime call the Studio API (`06`).
