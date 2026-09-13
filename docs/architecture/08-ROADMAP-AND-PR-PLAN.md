# 08 — Roadmap and PR plan

Covers task sections **W** (roadmap V1/V2/V3) and **X** (PR plan). The Definition of Done
is in `07` §7.6.

---

## 8.1 Challenging the brief's phase ordering

The brief proposes Phase 0–11 and asks whether manual panorama upload should come before
AI generation. **Yes — and more strongly than the brief suggests: manual import should be
a permanent first-class provider, not a temporary scaffold.** Three reasons, the third of
which the brief could not have known:

1. It de-risks everything. The contract, optimisation, validation, budgets, publication,
   catalog and the avatar integration are all exercised with zero GPU infrastructure.
2. It is the only path to six *publishable* environments today, given that no
   open-weights panorama model has a verified commercial licence (`03` §3.10).
3. **The binding constraint is not generation at all — it is the avatar runtime.** It
   cannot currently load a panorama (`01` §1.3) and it discards the background in VR
   (`01` §1.4). Building a generator first would mean producing assets nothing can
   display.

So the brief's ordering is largely right but its *risk model* is wrong: it treats AI
generation as the hard part. The hard part is the contract plus three small avatar-side
changes. Two further revisions:

- **The avatar-side work (A1–A3) is pulled forward and interleaved**, not left to
  "Phase 9 integration fixture". It should land alongside the first publish, because until
  it does, "published" is unobservable.
- **Preview and validation move earlier.** The brief has them at Phase 8, after
  optimisation and audio. But the 360 preview is how a creator judges a panorama at all,
  and seam/pole defects are the most common failure. Previewing before optimising avoids
  optimising assets that were never acceptable.

## 8.2 Roadmap

### V1 — prove the contract (no GPU required)

Manual or commercially-licensed panorama + ambience audio + lighting preset → optimised
desktop/Quest/mobile variants → validated → published → consumed by the avatar app on
desktop and Quest 3. Six environments. The `mock` and `manual` providers only.

Success is `07` §7.6, and its sharpest item is #17: with the Studio stopped, the avatar
app still works.

### V1.1 — first generating provider, and production storage

`RemoteAPIProvider` against a commercially-licensed panorama API; S3-compatible
private/public storage with a CDN; prompt templates and provenance recording; the
UASTC-vs-ETC1S measurement spike (`06` §6.3); the CLI. Generation slots into the existing
job pipeline without changing any published artifact — which is the test of whether the
provider boundary is real.

### V1.2 — self-hosted generation (gated)

`SelfHostedHTTPProvider` against a GPU worker, **only if** a weights audit clears
(Diffusion360 is the leading candidate, `02` §2.2). If no audit clears, V1.2 is skipped
and nothing else in the plan changes. That property is the point of the whole provider
architecture.

### V2 — foreground props

Segmentation (GroundingDINO + SAM behind one `SegmentationProvider`) → **human selects**
which objects become 3D → image-to-3D (TripoSR default, TRELLIS premium — both MIT code
and MIT weights, `03` §3.4) → glTF Transform + Blender optimisation → geometry budgets
→ published as `geometry[]` with a raised `minRuntime`.

Design philosophy per brief §18: near-field props for parallax, distant panorama for
everything else. Never reconstruct the world. The architectural test of V2 is that
`environment.json`, `catalog.json` and the avatar's adapter need **no structural change**
— only the already-specified `geometry[]` array and a runtime that honours `minRuntime`.

### V3 — automation, only after V1 and V2 are proven

Depth estimation and automatic placement; background inpainting where a prop is lifted
out; video ambience; procedural effects; WebXR Layers for the background (a genuinely
promising optimisation — a quad layer avoids resampling the panorama through the main
render target, and is worth measuring on Quest). All optional providers.

**Gaussian Splatting remains rejected**, on licence grounds first (`03` §3.2) and runtime
grounds second.

## 8.3 PR plan

Each PR states scope, tests, acceptance and rollback. Studio PRs are numbered; avatar PRs
are `A*`. Dependencies are noted; anything not chained can run in parallel.

### PR 0 — correct the licensing record *(docs only)*
- **Scope** Apply `03` §3.6: withdraw the PanFusion recommendation from `README.md`,
  `docs/OPEN_SOURCE_INVENTORY.md`, `docs/UPSTREAM_REUSE.md` and
  `docs/CODEX_CLAUDE_IMPLEMENTATION_BRIEF.md`; add inventory rows for libvips/Pillow,
  FFmpeg/Opus, KTX-Software/Basis and Blender; add the hardened provider gate.
- **Tests** none (docs).
- **Acceptance** no document recommends a non-commercially-licensed model as a production
  provider; every V1 production dependency has an inventory row.
- **Rollback** revert. **Why first:** it is the cheapest PR and it prevents someone
  implementing the withdrawn recommendation in the meantime.

### PR 1 — schema v1 + fixtures  *(depends: 0)*
- **Scope** Promote `docs/architecture/contracts/*.draft.schema.json` into
  `packages/schema/v1/`; add `presets.json`; build the fixture set (valid + `invalid/`);
  `CHANGELOG.md`. Replace the current `schemas/*.json` and `examples/`.
- **Tests** every valid fixture validates; every invalid fixture rejected **with the
  expected error**; `presets.json` fully covered by fixtures.
- **Acceptance** the published contract exists, is validated, and carries its own
  negative cases. **Rollback** the old schemas are untouched in history; nothing consumes
  v1 yet.

### PR 2 — cross-field validator  *(depends: 1)*
- **Scope** `validation/manifest.py`: the rules JSON Schema cannot express (`05` §5.12) —
  2:1 aspect, `decodedTextureBytes` consistency, variant/presentation coherence,
  `geometry` vs `minRuntime`, every `src` present with a matching hash.
- **Tests** `bad-aspect-ratio.json` now FAILs; each rule has a positive and negative case.
- **Acceptance** no manifest can be accepted on schema validation alone.

### PR 3 — storage abstraction  *(parallel with 1–2)*
- **Scope** `StorageProvider` with local and S3 (MinIO) implementations; private/public
  prefixes; content-hash keys; MinIO in compose.
- **Tests** round-trip, hash verification, public/private isolation (a private key is not
  readable through the public path), overwrite refusal on immutable prefixes.

### PR 4 — data model + migrations  *(parallel)*
- **Scope** SQLAlchemy models of `04` §4.5, Alembic baseline. Replaces the JSON-file
  repository.
- **Tests** migration up/down; state-machine transitions incl. illegal ones; a project
  cannot reach `READY` without a `Rights` row per asset.

### PR 5 — job queue + worker  *(depends: 4)*
- **Scope** DB-backed claim/heartbeat/retry, worker entrypoint, stage registry, `202 +
  job_id` plumbing, cancellation.
- **Tests** stale-heartbeat requeue; bounded retry by error class; a validation FAIL is
  not retried; cancellation leaves consistent state.

### PR 6 — image pipeline + measurement  *(depends: 3, 5)*
- **Scope** master ingest, variant derivation via libvips, WebP encoding, KTX2 via the
  `ktx` CLI, `decodedTextureBytes` computation, deterministic-output guarantee.
- **Tests** determinism (identical hashes on re-run); measured memory matches `01` §1.9
  per format; KTX2 output is a valid container with the declared Basis mode.

### PR 7 — panorama validation + 360 preview  *(depends: 6)*
- **Scope** seam/pole/horizon/aspect/content checks with measured values;
  validation-report rendering; the 360 preview in the web app using **three r0.147.0 with
  ACES + sRGB**, opening at the seam with one-click pole jumps; orientation (`forwardYaw`)
  set by rotating the preview.
- **Tests** synthetic broken-seam FAILs, good PASSes; preview maths (yaw ↔ pixel column).
- **Acceptance** a creator can see and judge a panorama, and a defective one cannot reach
  `READY`. Earlier than the brief's Phase 8, per §8.1.

### PR 8 — audio pipeline  *(depends: 3, 5)*
- **Scope** upload validation, loop shaping with crossfade, R128 normalisation, Opus +
  AAC encoding, **post-encode loop verification**, rights capture.
- **Tests** concatenated encoded output has no discontinuity above threshold;
  normalisation hits −23 LUFS ±0.5; a rights-less upload is refused.

### PR 9 — budget gate + quality profiles  *(depends: 6, 1)*
- **Scope** `policy.py` thresholds of `06` §6.7, `validation/budget.py`, the three
  profiles.
- **Tests** an over-budget variant FAILs and blocks publish; each profile produces output
  inside its own budget.

### PR 10 — packager + publish transaction  *(depends: 1, 2, 3, 6, 8, 9)*
- **Scope** manifest assembly, catalog generation with immutable revisions, the
  eight-step transaction, rollback, withdrawal, licence-posture precondition.
- **Tests** fault injection at every step leaves no catalog entry; idempotent re-run;
  rollback; republish refusal; a non-`enabled` provider cannot publish.
- **Acceptance** brief §30 satisfied structurally. **Rollback** the catalog pointer is the
  only mutable object; revert by repointing.

### PR 11 — Studio UI: project CRUD, review, publish  *(depends: 4, 5, 7, 10)*
- **Scope** the V1 screens of brief §43 — prompt/metadata, 360 preview, audio, lighting
  preset, forward direction, quality profile, validation panel, optimise/publish, explicit
  review verdict.
- **Tests** the Playwright e2e of `07` §7.2(5).
- **Acceptance** a creator completes the whole workflow without touching an API client.

### PR 12 — manual + mock providers  *(depends: 5)*
- **Scope** `ManualImportProvider`, `MockProvider`, the registry, `licence_posture`,
  `GET /api/providers`.
- **Acceptance** the complete pipeline runs with no GPU and no weights.

### PR 13 — first six environments  *(depends: 11, 12, A1–A3)*
- **Scope** content, not code: acquire/licence six panoramas and six ambience beds,
  publish them, record rights for each.
- **Acceptance** DoD items 12–17.

### Avatar-side PRs (in `ruslanmv/3D-Avatar-Chatbot`)

These are small, independently testable, and must not regress the existing behavioural
invariants — especially "ten enter/exit cycles leave the world unchanged".

**PR A1 — catalog-driven scene list** *(depends: Studio PR 10 for a real catalog; testable
earlier against a fixture)*
- **Scope** replace the hard-coded `['forest','ocean','meditation']` in
  `loadManifests` (`scene-journey.js:479-480`) with a fetch of `catalog.json` from a
  configured base URL; cache it; keep the three bundled manifests as an offline fallback.
- **Tests** catalog-driven registration; offline fallback; a malformed catalog does not
  break boot (the existing fail-soft posture).
- **Acceptance** adding an environment requires no avatar code change — brief §63's
  anti-pattern removed. **Rollback** revert to the literal array.

**PR A2 — inject `loadTexture`** *(independent; the true unblocker)*
- **Scope** at `boot.js:566`, pass `viewer`, `three` and a `loadTexture` that uses
  `ViewerEngine`'s **existing** `KTX2Loader` instance for `.ktx2` and `TextureLoader` for
  WebP, marking `__nexusScene` as the module already expects.
- **Tests** a KTX2 skybox loads and `stats.skyboxLoaded === true`; a missing asset still
  enters with `fallbackColor`; the epoch guard still discards a late texture; ten
  enter/exit cycles still leave the world unchanged.
- **Acceptance** `01` §1.3 is resolved — panoramas can actually appear.
- **Rollback** remove the injected dependency; behaviour returns to fallback colours.

**PR A3 — the ambience adapter, XR background intent, and the contract test**
*(depends: A1, A2, Studio PR 1)*
- **Scope** `AmbienceAdapter` per `05` §5.11 (rename and select only); honour
  `presentation.xr.background` instead of unconditionally overwriting `scene.background`
  at `ViewerEngine.js:346`; vendored fixtures + the contract test of `07` §7.2(1).
- **Tests** every fixture's adapter output is accepted by `SceneJourney.validate()`;
  per-device variant selection; audio source selection; every preset implemented; unknown
  fields ignored; VR entry preserves a panorama when intent says `panorama` and still
  paints a solid colour when it says `solid` or `none`.
- **Acceptance** the Quest variant has a consumer; DoD item 14 becomes achievable.
- **Rollback** the adapter is additive; reverting restores unconditional solid-colour VR.

### Deferred to V2 (named here so they are not smuggled into V1)

PR 14 segmentation provider · PR 15 object-selection UI · PR 16 image-to-3D provider ·
PR 17 glTF Transform + Blender optimiser · PR 18 geometry budgets and validation ·
PR 19 `geometry[]` publishing + `minRuntime` bump · PR A4 runtime geometry loading.

## 8.4 Critical path

```
PR 0 ─► PR 1 ─► PR 2 ──────────────────────────┐
                                               │
        PR 3 ─► PR 6 ─► PR 7 ─► PR 9 ──────────┤
                    └─► PR 8 ─────────────────► PR 10 ─► PR 11 ─► PR 13
        PR 4 ─► PR 5 ─► PR 12 ─────────────────┘                   ▲
                                                                   │
 avatar:  A2 (independent) ─► A1 ─► A3 ────────────────────────────┘
```

The two chains are independent until PR 13, so the avatar work can start on day one. **A2
is the single highest-leverage PR in the entire plan** — it is small, has no dependency on
this repository, and without it nothing the Studio publishes can be seen.

## 8.5 What would falsify this architecture

Stated so the plan is testable rather than merely plausible:

1. **If the avatar team will not accept A1–A3**, the Studio has no consumer and the plan
   must change — to the Studio producing asset bundles that are manually committed into
   the avatar repo. That is strictly worse, and it is worth knowing early.
2. **If 4096×2048 UASTC cannot hold 72 FPS on a Quest 3 with a VRM present**, the budgets
   in `06` §6.7 drop a tier and `performance` becomes the default. The numbers are derived
   from published guidance and arithmetic, not from a measurement on the target device;
   DoD item 14 is where they get tested.
3. **If ETC1S banding turns out to be acceptable on real content**, downloads shrink ~4×
   and the budgets loosen. That is the spike in `06` §6.3.
4. **If a commercially-licensed panorama source cannot be secured**, V1 ships with
   manually-sourced art only. The architecture is unaffected; only the content supply is.
5. **If `scene.environment` turns out to be wanted as the panorama after all** — for
   example because the flat IBL looks better than a preset on real content — then
   `lighting.hdr` becomes mandatory rather than optional, and the manifest gains an
   explicit `lighting.useBackgroundAsEnvironment` flag. That is an additive change, which
   is the test of whether `05` §5.9 was designed correctly.
