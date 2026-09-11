# Continuation brief for Codex / Claude Code

Inspect this repository and `ruslanmv/3D-Avatar-Chatbot` before changing code. Preserve the separation:

`3D-Ambience-Studio → versioned environment pack/catalog → CDN → 3D-Avatar-Chatbot`.

First complete V1 without adding more AI complexity: harden project persistence, add interactive 360 preview, manual uploads, background job abstraction, S3-compatible storage adapter, manifest/catalog contract tests shared with the avatar app, and one real panorama worker adapter. Prefer PanFusion as the first open-source candidate only after its model/dependency licensing is audited. Treat Text2VR as an architecture reference and DreamScene360 as reference/experimental under its current restrictive root license. Do not vendor model checkpoints or make the avatar runtime call generation services.

Every new generator must implement the provider boundary and output a normal 2:1 panorama or normalized GLB; every published asset must pass Studio optimization and validation. Keep runtime manifests generator-neutral.
