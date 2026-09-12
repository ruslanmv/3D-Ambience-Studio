# 00 — Executive recommendation and final decision

Covers task sections **A** (executive recommendation), **B** (repository boundaries) and
**§65** (the required final decision format).

---

## A. Executive recommendation

**Build `3D-Ambience-Studio` as a modular-monolith content pipeline whose only output is a
versioned, generator-neutral environment pack on a CDN; make "manual import" the first
provider and ship six environments with no GPU in the loop; and treat the three small
changes needed in `3D-Avatar-Chatbot` as part of the critical path rather than as a later
integration phase.**

The brief frames the hard problem as choosing and integrating AI models. The inspection
says otherwise. Three facts reframe the project:

1. **The runtime already has an environment format, and it cannot currently display a
   panorama.** `scene-journey.js` loads JSON scene manifests and hard-rejects any without
   `id`, `title` and `anchors`; but `boot.js:566` never injects a texture loader, so every
   scene today is a flat colour plus an audio loop (`01` §1.2–1.3). Entering VR then
   overwrites the background with black (`01` §1.4). Generation is not the bottleneck —
   about 150 lines of avatar-side work is.
2. **No open-weights 360° panorama model has a verified commercial path.** DreamScene360
   is under the Inria non-commercial research licence; PanFusion's MIT code rides on
   Matterport3D-derived weights (CC BY-NC-SA); MVDiffusion and DiT360 share that lineage,
   and DiT360 additionally wants ~37 GB VRAM to produce 2048×1024 (`03` §3.2–3.3). Any plan
   whose first milestone depends on one of these cannot ship.
3. **On Quest, texture memory is the entire budget.** A 4096×2048 panorama costs 45 MB
   resident as RGBA8 and 11 MB as KTX2/ASTC; at 8K the uncompressed figure is 134 MB
   against a ~256 MB practical ceiling (`01` §1.9). This single table determines the
   format matrix, the variant strategy and the budgets — and it validates the avatar
   repo's existing choice of `.ktx2`.

So the recommended architecture optimises for the contract, not for the models:

```
  creator ─► Studio (FastAPI + React, one deployable)
                │   providers: manual · mock · remote-API · self-hosted
                │   tools out-of-process: libvips · ffmpeg · ktx · gltf-transform
                ▼
            versioned environment pack  +  catalog.json
                ▼
            object storage / CDN        ← the only thing the runtime ever touches
                ▼
            3D-Avatar-Chatbot  (adapter → existing scene loader)
```

Five commitments make it work, and each is load-bearing rather than stylistic:

- **The manifest never names its generator.** Provenance is internal; the runtime sees
  only results (`05` §5.5).
- **Manual import is a permanent first-class provider**, not a scaffold — it is what lets
  the whole pipeline be proven and, today, the only path to publishable content (`08` §8.1).
- **Pre-generate per-target variants.** The runtime can adapt computation but cannot
  un-download a texture (`01` §1.8).
- **Lighting is semantic, and the panorama is not the IBL** — for a measured reason: an
  equirect texture assigned to `scene.environment` is pushed through `PMREMGenerator` in
  the vendored r147, paying an extra render target and blur chain to derive a flat LDR
  lighting probe (`01` §1.10).
- **The licence gate is code.** A provider carries a `licence_posture`, and the publish
  transaction refuses anything not `enabled` (`05` §5.7, `07` §7.3).

### What this recommendation rejects

Putting AI generation in the runtime; depending on one panorama model; Gaussian Splatting
(rejected on licence grounds before performance); Text2VR's always-on microservice
topology and LangGraph orchestration; storing binaries in Git; executing anything from a
manifest; requiring GPU weights to run the UI; and publishing without human review.

---

## B. Repository boundaries

| | `3D-Ambience-Studio` | Object storage / CDN | `3D-Avatar-Chatbot` |
|---|---|---|---|
| **Owns** | workflow, schemas, prompt templates, validation, optimisation policy, asset budgets, quality profiles, publication, catalog, provenance, licensing records | the published bytes: `catalog.json`, immutable `environments/{id}/{version}/…`, the published schema | rendering, VRM, lighting implementation, effect implementation, WebXR/passthrough behaviour, adaptive quality, companion presentation, interaction |
| **Decides** | what an environment *is*, what gets downloaded and how big it is | nothing — it is storage with HTTP semantics | what happens on screen, including overriding any declared intent |
| **Never** | renders the product; dictates Three.js internals; publishes without rights and review | holds logic or secrets | calls a generation model; calls the Studio API; needs a credential |
| **Depends on** | storage + optional GPU workers | nothing | the CDN only |

The boundary test, and the reason `catalog.json` is a CDN object rather than an API
endpoint: **stop the Studio entirely and every published environment still works, for
ever** (`06` §6.10, DoD item 17).

The one shared artifact is `packages/schema/` — schemas, `presets.json` and fixtures —
synced into the avatar repo so both sides test against the same cases (`05` §5.8).

---

## §65. RECOMMENDED 3D-AMBIENCE-STUDIO ARCHITECTURE

```text
Repository:
    ruslanmv/3D-Ambience-Studio — a modular monolith, not microservices.
    apps/api (FastAPI) · apps/web (React/Vite) · packages/schema (the contract,
    versioned independently and shared with the avatar repo) · workers/ (on-demand
    GPU providers, out of tree) · infrastructure/ (Docker, CDN config as code).
    Upstream projects are never vendored: pinned revisions cloned on request.

Frontend:
    React 18 + TypeScript + Vite. The 360 preview uses Three.js pinned to the
    avatar's own r0.147.0, with ACES Filmic tone mapping and sRGB output, so the
    preview predicts the runtime instead of flattering it.

Backend:
    FastAPI + Pydantic v2 on Python 3.11+. JSON Schema 2020-12 is the single
    source of truth for the contract, because it is the only form all three
    consumers can use — the avatar app is plain JS with no build step.

Database:
    SQLite (WAL) with SQLAlchemy + Alembic from day one. Promote to PostgreSQL on a
    written trigger: a second concurrent writer, >1000 jobs/day, multi-tenancy, or
    full-text catalogue search. Binaries never live in the database.

Job system:
    A database-backed queue polled by a worker process in the same codebase.
    Durable, inspectable, resumable; heartbeats detect crashes. No broker in V1.
    Rejected: FastAPI BackgroundTasks (dies with the process, cannot resume) and
    Celery/Redis (a broker and a second deployment unit for <10 jobs a day).

Panorama generation:
    A provider interface with four implementations, delivered in this order:
      1. manual import   — permanent, first-class, and V1's only requirement
      2. mock            — CI and UI work with no GPU
      3. remote API      — a commercially-licensed vendor (V1.1)
      4. self-hosted     — Diffusion360 is the leading candidate, Apache-2.0 code,
                           GATED on a weights audit (V1.2)
    DreamScene360, PanFusion, MVDiffusion and DiT360 are reference/evaluation only:
    non-commercial licences or non-commercially-trained weights.

Asset optimisation:
    libvips for equirect resizing and WebP; KTX-Software (`ktx`) for KTX2/Basis
    UASTC; glTF Transform for GLB in V2, with Blender headless out-of-process for
    geometry repair (GPL stays at the process boundary). Every derivation is a pure
    function of (master hash, pipeline version, encoder settings) and therefore
    reproducible.

Audio processing:
    FFmpeg + libopus. Trim, loop-shape with an equal-power crossfade, normalise to
    EBU R128 −23 LUFS, encode Opus-in-Ogg plus AAC-in-M4A, then verify the loop
    on the ENCODED bytes before the manifest may claim "seamless". The runtime
    uses a bare HTMLAudioElement, so seamlessness has to live in the file — loop
    points are unimplementable and therefore not in the schema.

Storage:
    S3 API behind a StorageProvider abstraction. MinIO locally, Cloudflare R2 or B2
    in production (zero egress matters for a texture catalogue). Strict separation:
    private/ holds masters, intermediates and reports; public/ holds immutable
    published versions. Intermediate AI artifacts never become public automatically.

CDN:
    Fronts the public prefix only. Versioned assets: max-age=31536000, immutable.
    catalog.json: max-age=60 with stale-while-revalidate. Correct CORS and correct
    Content-Types — image/ktx2 in particular, since a wrong type fails the
    transcoder opaquely. Headers are committed as code, not set in a console.

Manifest schema:
    environment.json v1 — generator-neutral and semantic. Per-target variants with
    format, dimensions, bytes, measured decodedTextureBytes and a content hash;
    an ordered audio source list; a lighting PRESET plus exposure and an optional
    small HDR; orientation with forward yaw, floor, avatar anchor and named
    anchors; separate declared intent for xr / passthrough / companion; relative
    asset paths only. fallbackColor is REQUIRED because the runtime requires it.
    No provider, model, seed or prompt. No script, no shader, ever.
    Schema validation alone is not the gate: the 2:1 aspect ratio and the budgets
    are cross-field rules enforced in code (verified — a 4096×1800 "panorama"
    passes the schema).

Catalog strategy:
    A single CDN-hosted catalog.json carrying everything the picker needs — including
    fallbackColor for instant paint, minRuntime for compatibility filtering, and
    per-target bytes plus decodedTextureBytes so a headset can decide before
    downloading. Manifests are referenced, never embedded. Monotonic revisions,
    each also written immutably, so rollback is repointing a pointer. Shard into
    pages above ~200 environments — an additive change that does not bump the
    schema version.

Quest asset strategy:
    Texture memory is the whole budget. The environment gets ≤64 MB of the ~256 MB
    envelope — a quarter — because the avatar is the product.
    Panorama 4096×2048 as KTX2/UASTC+zstd: ≤6 MB download, ≤12 MB resident versus
    45 MB as RGBA8. Audio ≤2.5 MB per encoding. Total first load ≤9 MB.
    V2 props: ≤25 K triangles, ≤6 draw calls, ≤4 materials, ≤1024² textures, ≤2
    transparent surfaces never overlapping the avatar. Three profiles
    (performance / balanced / quality) change encoder settings, not the workflow.
    The budget gate is code and blocks publication; it cannot be overridden.

Avatar integration:
    A thin, declarative adapter in the avatar repo maps the published manifest onto
    the shape SceneJourney.register() already accepts — renaming and selecting only,
    with no rendering logic. Three small avatar PRs:
      A1  replace the hard-coded ['forest','ocean','meditation'] with a catalog fetch
      A2  inject loadTexture at boot.js:566, reusing ViewerEngine's KTX2Loader
      A3  the adapter, honour presentation.xr.background instead of forcing black
          on XR entry, and the shared-fixture contract test
    A2 is the highest-leverage PR in the plan: small, independent of this
    repository, and nothing published is visible until it lands.

V1:
    Manual/licensed panorama + ambience + lighting preset → optimised desktop,
    Quest and mobile variants → validated with human review → published atomically
    → six environments consumed by the avatar app on desktop and Quest 3, with the
    Studio switched off.

V2:
    Segmentation (GroundingDINO + SAM) → a human selects objects → image-to-3D
    (TripoSR default, TRELLIS premium; MIT code and MIT weights both) → glTF
    Transform + Blender → geometry budgets → published as geometry[] with a raised
    minRuntime. Near-field props for parallax, distant panorama for the rest.
    No structural change to environment.json, catalog.json or the adapter.

V3:
    Depth-guided automatic placement, inpainting behind lifted props, video and
    procedural ambience, and WebXR Layers for the background (worth measuring).
    All optional providers. Gaussian Splatting stays rejected on licence grounds.
```

### IMPLEMENT FIRST

The first milestone, exactly as brief §60 proposes, with the avatar work included because
without it the milestone is unobservable:

```text
PR 0   correct the licensing record (PanFusion withdrawn; V1's real dependencies added)
PR 1   schema v1 + presets.json + valid and invalid fixtures
PR 2   the cross-field validator (the rules JSON Schema cannot express)
PR 3   storage abstraction, private/public separation, MinIO
PR 4   data model + migrations
PR 5   database-backed job queue + worker
PR 6   image pipeline: variants, WebP, KTX2, measured decodedTextureBytes
PR 7   panorama validation + the 360 preview that opens at the seam
PR 8   audio pipeline with post-encode loop verification
PR 9   budget gate + quality profiles
PR 10  packager + the atomic publish transaction + catalog revisions + rollback
PR 11  the V1 Studio UI, including an explicit human review verdict
PR 12  manual + mock providers
PR 13  six published environments

in parallel, from day one, in ruslanmv/3D-Avatar-Chatbot:
A2     inject loadTexture  ◄── start here; it is what makes anything visible
A1     catalog-driven scene list (removes the hard-coded ids)
A3     ambience adapter + xr background intent + the contract test
```

Done when `07` §7.6 passes — and its sharpest items are: the avatar app lists and loads
all six environments from the CDN with no hard-coded ids, a Quest 3 loads the KTX2 variant
at ≤12 MB resident and a sustained 72 FPS with the avatar present, and **everything still
works with the Studio stopped.**

### IMPLEMENT AFTER V1

```text
a commercially-licensed remote panorama provider, behind the same interface
prompt templates + provenance recording + reproducibility from seed
S3/R2 production storage and CDN, staging catalog at a separate prefix
the UASTC vs ETC1S measurement spike on a real Quest 3 (banding on sunset gradients)
the CLI, wrapping the same API — never reaching into the database
a self-hosted panorama provider, IF and only if a weights audit clears
V2: segmentation → human selection → TripoSR/TRELLIS → glTF Transform → geometry[]
WebXR Layers for the background, if measurement justifies it
PostgreSQL + a real queue + metrics, at the written trigger, not before
```

### DO NOT BUILD YET

```text
Gaussian Splatting anything                — non-commercial licence, then performance
a dependency on any single panorama model  — none has a clean commercial path today
PanFusion / DreamScene360 in production    — evaluation only; a fork cannot fix a licence
LangGraph or an always-on microservice mesh — one optional GPU stage does not need either
a full 3D scene editor                     — six calm environments do not need one
automatic scene reconstruction, physics, world navigation
arbitrary shaders or scripts in manifests  — the security line, never crossed
loop points in the audio schema            — unimplementable against HTMLAudioElement
AVIF panoramas                             — buys bytes on the axis we are not short of
automatic publishing without human review
a GPU or model weights as a requirement to run the UI
PostgreSQL, Celery/Redis, Prometheus       — until the trigger in 04 §4.2 fires
localisation, maturity ratings, offline packs — additive later; noise now
```

---

## Where this plan disagrees with the brief

Stated plainly, because the brief asked for assumptions to be challenged.

| Brief | This plan |
|---|---|
| Text2VR is a proven end-to-end architecture to study closely | 1 star, 128 commits. Its *decomposition* is useful; its topology is unvalidated and its MIT badge is contaminated by DreamScene360 (`02` §2.1, `03` §3.2) |
| PanFusion is a likely first panorama provider — and this repo already recommends it | Withdrawn. MIT code, Matterport3D-derived non-commercial weights (`03` §3.3). The correction is PR 0 |
| The runtime needs an `AmbientSceneManager` built for it | It has a working scene system already, with hard validation gates we must satisfy. We adapt, not replace (`05` §5.1) |
| `src/gltf-viewer/environments.js` is the environment system | It is a 24-line list of HDR/IBL options, unrelated to ambience (`01` §1.1) |
| Panorama-as-lighting is an aesthetic question | It is a measurable cost: PMREM runs on it in r147 (`01` §1.10) |
| Design the schema freely | Two fields (`title`, `anchors`) are hard gates in existing runtime code, and `fallbackColor` is required by its tests |
| One schema is sufficient for validation | Verified insufficient: a 4096×1800 "panorama" passes JSON Schema. Cross-field rules are a separate, equally binding half (`05` §5.12) |
| Companion supports six presentation values | The runtime implements three; publishing five more would be fiction (`01` §1.6) |
| Passthrough is the mode needing declared intent | VR needs it more urgently — VR entry currently destroys the background outright (`01` §1.4) |
| Validation and preview come late (Phase 8) | They come before optimisation: the preview is how a creator judges a panorama at all (`08` §8.1) |
| Integration with the avatar app is a late phase | It is the critical path. A2 should be the first PR anyone writes (`08` §8.4) |
