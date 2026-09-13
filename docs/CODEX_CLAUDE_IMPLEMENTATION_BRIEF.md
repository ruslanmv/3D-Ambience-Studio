# Continuation brief for Codex / Claude Code

**Read `docs/architecture/` first** — it is the implementation-ready plan, built from direct
inspection of both repositories. Start with `00-EXECUTIVE-DECISION.md`, then
`01-AVATAR-RUNTIME-ANALYSIS.md`, then `08-ROADMAP-AND-PR-PLAN.md` for the PR sequence.

Preserve the separation:

`3D-Ambience-Studio -> versioned environment pack/catalog -> CDN -> 3D-Avatar-Chatbot`.

The boundary test: with the Studio stopped, every published environment still works.

## What the inspection changed

1. **The avatar runtime already has a scene contract** (`scene-journey.js`) that hard-rejects
   a manifest without `id`, `title` and `anchors`, and requires `fallbackColor`. We adapt to
   it with a thin declarative adapter; we do not replace it. See `05-CONTRACT-SCHEMAS.md`.
2. **The runtime cannot currently display a panorama**: `boot.js:566` injects no
   `loadTexture`, so every scene falls back to a solid colour. Avatar PR A2 is the
   highest-leverage change in the whole plan and depends on nothing in this repository.
3. **Entering VR overwrites `scene.background` with black** (`ViewerEngine.js:346`), so the
   Quest variant has no consumer until avatar PR A3 lands.
4. **PanFusion is not a usable production provider.** MIT code, Matterport3D-derived
   non-commercial weights. DreamScene360 is under the Inria non-commercial research licence.
   No open-weights panorama model has a verified commercial path — so V1 must not depend on
   one. See `03-LICENSING.md`.
5. **On Quest, texture memory is the whole budget** (~256 MB ceiling; a 4K panorama is 45 MB
   as RGBA8 and 12 MB as KTX2). This decides the format matrix and the budgets.

## Build order

Complete V1 with **no GPU and no model weights**: schema v1 + fixtures, the cross-field
validator (JSON Schema alone cannot enforce 2:1 aspect or the budgets), storage abstraction,
data model, job queue, image pipeline with measured `decodedTextureBytes`, panorama
validation and the 360 preview, audio with post-encode loop verification, the budget gate,
the atomic publish transaction, the Studio UI with an explicit human review step, and the
manual + mock providers. Then six published environments.

Run avatar PRs A1-A3 in parallel from day one; until they land, "published" is unobservable.

## Rules that do not bend

- Every generator implements the provider boundary and returns a normal 2:1 sRGB
  equirectangular panorama (or a normalised GLB in V2) plus provenance.
- Published manifests stay generator-neutral: no provider, model, seed or prompt, and never
  a script or a shader.
- Asset paths in a manifest are relative, so a version directory stays self-contained.
- Every published asset passes optimisation, validation and the budget gate, and carries a
  `Rights` row. A provider whose `licence_posture` is not `enabled` cannot publish.
- Human review before every publication. No automatic publishing.
- Never vendor model checkpoints. Never make the avatar runtime call a generation service or
  the Studio API.
