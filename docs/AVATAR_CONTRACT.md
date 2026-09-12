# Contract with 3D-Avatar-Chatbot

Summary of the runtime-facing contract. The detailed analysis that produced it is in
`docs/architecture/01-AVATAR-RUNTIME-ANALYSIS.md`; the schema design and the adapter
specification are in `docs/architecture/05-CONTRACT-SCHEMAS.md`.

## Principle

The avatar app loads published static assets from a CDN. It never calls a generation
model, never calls the Studio API, and holds no credential.

**The boundary test:** stop the Studio entirely and every published environment keeps
working.

## What the runtime actually does today

Verified against `ruslanmv/3D-Avatar-Chatbot` at `251e07b`. This matters because the
contract has to fit existing, tested code rather than a hypothetical loader.

- Scenes are loaded by `src/features/together/activities/scene-journey.js`, which
  **hard-rejects** any manifest without a non-empty string `id`, a string `title`, and an
  array `anchors`. It consumes `fallbackColor`, `skybox`, `ambient` and
  `lighting.exposure`. `lighting.hemi` and `avatarPlacement` are present in the bundled
  manifests but **unused by any runtime code**.
- Manifests are discovered from a **hard-coded list of three ids** under a repo-relative
  path — the anti-pattern a catalog replaces.
- **No panorama can load today**: `src/behavior/boot.js:566` injects no `loadTexture`, so
  every scene falls back to its `fallbackColor`.
- **Entering VR overwrites `scene.background` with a solid colour**
  (`ViewerEngine.js:346`), so a Quest panorama variant currently has no consumer.
- **Passthrough/AR already skips the background** and keeps the overlay, anchors and
  ambience — correct behaviour that the Studio must not fight.
- Companion mode already implements transparent and solid backdrops by nulling
  `scene.background` and setting the clear colour.
- Renderer: three **r0.147.0** (vendored), `sRGBEncoding`, **ACES Filmic** tone mapping,
  `pixelRatio min(dpr, 2)`, shadows off by default, headset `pixelRatio 1.0`.
  `KTX2Loader`, `DRACOLoader` and `MeshoptDecoder` exist but are attached only to
  `GLTFLoader`.
- Audio is a bare `HTMLAudioElement` with `loop = true` — so **loop points are
  unimplementable**, and seamlessness must be solved in the encoded file.

## Public catalog

`catalog.json` carries everything the picker needs so that no manifest is fetched until a
user selects an environment: id, version, name, description, category, tags, thumbnail,
preview, manifest URL, `fallbackColor` (for instant paint), `minRuntime` (for compatibility
filtering) and per-target `bytes` + `decodedTextureBytes` (so a headset can decide before
downloading).

## Environment manifest

Generator-neutral. V1 fields describe: per-target panorama variants (desktop, quest,
mobile, companion) with format, dimensions, byte size, measured decoded texture memory and
a content hash; an ordered audio source list; a **semantic** lighting preset plus exposure
and an optional small HDR; orientation (forward yaw, floor, avatar anchor, named anchors);
separately declared intent for XR, passthrough and companion; and optional V2 geometry.

`fallbackColor` is **required**, because the runtime requires it.

Runtime code owns the implementation of lighting and effects. A manifest never carries
executable JavaScript, HTML or shader source, and every asset path is relative so a version
directory stays self-contained.

Note that **schema validation alone is not the gate**: the 2:1 aspect ratio and the asset
budgets are cross-field rules JSON Schema cannot express, enforced separately by the
Studio validator.

## Runtime flow (after avatar PRs A1–A3)

```text
fetch catalog.json                      (replaces the hard-coded id list)
   ↓
user selects an environment
   ↓
fetch environment.json
   ↓
AmbienceAdapter — renames and selects only, no rendering logic
   ├── name → title, orientation.anchors → anchors, fallbackColor
   ├── pick the variant for this device
   └── pick the first playable audio source
   ↓
journey.register(mapped) ; journey.enter(id)      (unchanged, still gated)
```

## Required avatar-side changes

Small, independently testable, and they must not regress the existing invariant that ten
enter/exit cycles leave the world unchanged.

- **A1** — replace the hard-coded `['forest','ocean','meditation']` with a catalog fetch,
  cached, bundled scenes as the offline fallback.
- **A2** — inject `loadTexture` at `boot.js:566`, reusing `ViewerEngine`'s existing
  `KTX2Loader` instance for `.ktx2` and `TextureLoader` for WebP. **The highest-leverage
  change in the plan: nothing the Studio publishes is visible until it lands.**
- **A3** — the adapter, honour `presentation.xr.background` instead of forcing a solid
  colour on XR entry, and the shared-fixture contract test.

## Division of labour

The Studio owns what cannot be recovered at runtime: resolution, codec, byte size, decoded
texture memory, loop seamlessness, provenance, licensing, identity and version.

The runtime owns what is decided per frame: post-processing, pixel ratio, shadows, adaptive
quality, what a lighting preset means, what an effect does, and whether a background is
shown at all in XR or passthrough. Declared intent in the manifest is advice; the runtime
has the final say.
