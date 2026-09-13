# 05 — The contract: environment manifest, catalog, providers

Covers task sections **J** (environment schema), **K** (catalog schema), **L** (provider
architecture), **§52** (cross-repo contract testing) and **§53** (schema versioning).

Draft machine-readable files: [`contracts/environment-v1.draft.schema.json`](contracts/environment-v1.draft.schema.json),
[`contracts/catalog-v1.draft.schema.json`](contracts/catalog-v1.draft.schema.json), with
an example manifest in [`contracts/fixtures/`](contracts/fixtures/). These are **drafts**
proposed to replace `schemas/*.json`; that replacement is PR 2 in `08`.

---

## 5.1 The constraint the brief did not know about

The brief invites us to design a schema from scratch. We cannot: the runtime already
validates manifests and **rejects** any without a non-empty string `id`, a string
`title`, and an array `anchors` (`scene-journey.js:68-70`). It also consumes
`fallbackColor`, `skybox`, `ambient` and `lighting.exposure` (`01` §1.2).

Meanwhile this repository's current `schemas/environment.schema.json` shares only `id`
with that shape. Neither side is wrong; they were designed independently. So there are
three options:

| Option | Assessment |
|---|---|
| **A.** Studio adopts the runtime's scene shape as the published format | Rejected. It embeds runtime concerns (`profileOverlay`, `guidedScript`) in a published artifact, has no variants, no versioning, no integrity, no licensing, and a single `skybox` path with no per-target asset. It is a local art format, not a distribution contract. |
| **B.** Runtime adopts the Studio schema directly; `scene-journey.js` is rewritten | Rejected for V1. It means changing a 509-line module with a 637-line behavioural test suite, whose `enter`/`exit` snapshot-restore invariants are load-bearing ("ten enter/exit cycles leaving the world unchanged"). High risk, no product benefit. |
| **C.** Studio schema is canonical; the avatar gains a thin declarative **adapter** that maps published manifest → the shape `journey.register()` already accepts | **Chosen.** The Studio contract stays clean and generator-neutral; the runtime keeps its tested internals; the mapping is ~100 lines of pure data transformation with no new rendering logic. |

Option C is only cheap if the Studio schema is *designed* for it. Two concrete
consequences, and they are why this section exists before any implementation:

1. **`fallbackColor` is required, not optional.** The runtime needs it for the
   panorama-fails and AR paths, and its tests assert `/^#[0-9a-f]{6}$/` on every shipped
   manifest. The Studio should *compute* it from the panorama (a dominant/average colour
   at the horizon band) rather than asking a creator to pick it — it is a derived
   property of the art.
2. **The manifest must carry everything the adapter needs without inference.** The
   adapter chooses nothing except the device variant and the audio source. No
   guessing, no defaults invented at runtime.

---

## 5.2 Design principles for the manifest

1. **Generator-neutral.** No `provider`, `model`, `seed` or `prompt`. Provenance is
   internal (`§5.5`).
2. **Semantic, never implementation.** `"preset": "sunset-soft"` not a light rig;
   `{"type":"rain"}` not GLSL. The runtime owns meaning (brief §37, §38).
3. **Declarative intent, runtime authority.** The manifest says what the environment
   *is for*; the runtime decides what to do in XR, passthrough and PiP (`01` §1.4–1.6).
4. **Cheap to parse.** It is fetched per selection on a headset browser: flat, small,
   no `$ref` chasing, target under 4 KB.
5. **Self-describing and verifiable.** Every asset carries size, dimensions, hash and —
   for textures — its decoded memory cost, so the runtime and the CI gate can both reason
   about budget without downloading.
6. **Additive evolution.** Unknown fields must be ignorable by consumers; see §5.9.

## 5.3 Manifest structure (annotated)

```json
{
  "schemaVersion": 1,
  "id": "sunset-beach",
  "version": "1.0.0",
  "minRuntime": "1.0.0",

  "name": "Sunset Beach",
  "description": "A calm tropical beach at sunset.",
  "category": "relax",
  "tags": ["beach", "ocean", "sunset", "meditation"],

  "fallbackColor": "#3a2436",

  "preview": { "src": "preview.webp", "width": 1024, "height": 512, "bytes": 84210,
               "hash": "sha256-…" },
  "thumbnail": { "src": "thumb.webp", "width": 320, "height": 160, "bytes": 11204,
                 "hash": "sha256-…" },

  "variants": {
    "desktop": {
      "kind": "panorama",
      "projection": "equirectangular",
      "src": "panorama/desktop.webp",
      "format": "webp", "width": 4096, "height": 2048,
      "bytes": 912344, "decodedTextureBytes": 44739242,
      "hash": "sha256-…"
    },
    "quest": {
      "kind": "panorama",
      "projection": "equirectangular",
      "src": "panorama/quest.ktx2",
      "format": "ktx2", "textureFormat": "uastc", "width": 4096, "height": 2048,
      "bytes": 4812003, "decodedTextureBytes": 11744051,
      "hash": "sha256-…"
    },
    "mobile": { "kind": "panorama", "projection": "equirectangular",
                "src": "panorama/mobile.webp", "format": "webp",
                "width": 2048, "height": 1024, "bytes": 284110,
                "decodedTextureBytes": 11184810, "hash": "sha256-…" },
    "companion": { "kind": "solid", "color": "#3a2436" }
  },

  "audio": {
    "sources": [
      { "src": "audio/ambience.opus.ogg", "mime": "audio/ogg; codecs=opus",
        "bytes": 1984220, "hash": "sha256-…" },
      { "src": "audio/ambience.m4a", "mime": "audio/mp4; codecs=mp4a.40.2",
        "bytes": 2310554, "hash": "sha256-…" }
    ],
    "loop": true,
    "seamless": true,
    "durationMs": 182000,
    "defaultVolume": 0.45,
    "loudnessLufs": -23.0
  },

  "lighting": {
    "preset": "sunset-soft",
    "exposure": 0.9,
    "hdr": null
  },

  "orientation": {
    "forwardYawDegrees": 118,
    "floorY": 0,
    "avatarAnchor": { "position": [0.5, 0, -0.9], "faceUser": true },
    "anchors": [
      { "name": "horizon", "dir": [0, -0.05, -1] },
      { "name": "sun",     "dir": [-0.6, 0.12, -0.8] }
    ]
  },

  "effects": [],

  "presentation": {
    "xr":          { "background": "panorama" },
    "passthrough": { "behavior": "hidden" },
    "companion":   { "behavior": "solid" }
  },

  "geometry": [],

  "credits": null
}
```

### Why each non-obvious field exists

| Field | Reason |
|---|---|
| `minRuntime` | A V2 manifest with foreground geometry must be skippable by an old runtime instead of half-loaded. Semver on the *runtime's* ambience support, not the app version. |
| `fallbackColor` | Runtime hard requirement (§5.1). Computed by the Studio. |
| `variants.*.kind` | Not every variant is a panorama — `solid`, `gradient`, `none`, and in V2 `diorama`. Naming the kind lets the adapter branch without sniffing file extensions. |
| `projection` | Says explicitly that the image is 2:1 equirectangular. A future cubemap or stereo-over-under variant becomes a new value, not a silent reinterpretation. |
| `format` / `textureFormat` | The runtime must choose a loader (`KTX2Loader` vs `TextureLoader`) **before** fetching. Extension-sniffing is the alternative, and it is worse. |
| `decodedTextureBytes` | The real Quest constraint (`01` §1.9). Publishing the measured number lets the runtime, the budget gate and a reviewer all use one authority. |
| `hash` | Integrity and cache identity. Also lets the runtime detect a CDN serving a stale object. |
| `audio.sources[]` as an ordered list | The runtime hands one URL to `new Audio()` (`01` §1.11). Two encodings remove the Ogg/Safari question permanently; the adapter picks with `canPlayType`. |
| `audio.seamless` | An *assertion by the Studio* that naive `loop = true` is gapless, because the runtime cannot do loop points. If it is false, the runtime may prefer to fade. |
| `audio.loudnessLufs` | Lets the runtime normalise perceived volume across environments instead of each creator guessing at `defaultVolume`. |
| `lighting.hdr` | Optional, small, and usually `null`. The reason it is not the panorama is measured in `01` §1.10. |
| `orientation.forwardYawDegrees` | Answers brief §35: rotate the panorama so the interesting direction is in front, instead of whatever the generator's seam happened to be. |
| `orientation.anchors` | Satisfies the runtime's hard gate, and is genuinely useful — it is how the avatar can look at "the horizon". Published as **named directions**, which is data, not behaviour. |
| `presentation.*` | Declared *intent*, three separate axes because they are three different runtime decisions (`01` §1.4–1.6). The runtime overrides freely; the brief's §34 rule is right and is extended to XR. |
| `credits` | `null` unless attribution is contractually required (`03` §3.8). |

### Deliberate omissions, and why

| Not in the manifest | Why |
|---|---|
| `provider`, `model`, `seed`, `prompt` | The whole point (brief §10). Internal only. |
| `profileOverlay`, `guidedScript` | Avatar behaviour, not environment content. If a future "guided meditation" product needs scripted speech, it belongs in a separate, separately-versioned document fetched by the avatar app — not smuggled into an asset manifest. |
| `loopStart` / `loopEnd` | Unimplementable against `HTMLAudioElement` (`01` §1.11). Publishing an unenforceable field invites a runtime change we have not justified. Solve it in the encode. |
| Per-effect parameters beyond `preset` + `intensity` | Opens the door to the runtime implementing a configuration language. Named presets keep the blast radius at the runtime's own code. |
| Arbitrary shader / script | Security (`07` §7.3). Non-negotiable. |
| `requirements.webgl` | Meaningless — a WebGL1-only device cannot run the app at all. Replaced by `minRuntime`. |
| Localisation of `name`/`description` | V1 is single-locale. When needed, add `i18n: {"de": {...}}` additively (§5.9) rather than restructuring now. |

### Changes from the brief's draft schema

| Brief proposed | Decision |
|---|---|
| `variants.{desktop,quest,companion}` with `type: "panorama"` | Kept, renamed `type`→`kind`, added `mobile`, `projection`, `format`, `decodedTextureBytes`, `hash`. |
| `audio: {ambient, loop, defaultVolume}` | Replaced with an ordered `sources[]` + `seamless` + `durationMs` + `loudnessLufs`. |
| `lighting: {preset, keyIntensity}` | `keyIntensity` dropped — it is a renderer implementation detail and the avatar's `hemi`-style field is already dead code. Kept `preset` + `exposure` (the one lighting value the runtime actually consumes) + optional `hdr`. |
| `effects: {rain: false, particles: null}` | Replaced with an array of `{type, preset, intensity}`, as the brief's own §37 proposes. An object of booleans cannot express two effects or an intensity. |
| `requirements: {webgl, xr}` | Replaced by `minRuntime`. |
| `preview: {src}` | Added dimensions/bytes/hash, plus a separate `thumbnail` — a catalogue grid must not download 1024-wide previews. |
| — | **Added** `fallbackColor` (runtime-required), `presentation.*`, `orientation.*`, `credits`. |

## 5.4 Lighting and effect presets are a registry, not free text

`preset` is an enum-like string, but the authority over which values exist is shared:
the Studio may only publish a preset the runtime implements. So the allowed values live
in **`packages/schema/v1/presets.json`**, shipped with the schema, and:

- the Studio validates `lighting.preset` and `effects[].type`/`preset` against it at
  publish time — publishing an unimplemented preset is a failed validation, not a runtime
  surprise;
- the avatar repo's contract test asserts it implements every value in that file;
- adding a preset is therefore a deliberate, two-repo, additive change.

V1 lighting presets: `neutral`, `soft-nature`, `sunset-soft`, `forest-green`,
`cool-rain`, `warm-study`, `campfire`, `night`.
V1 effect types: none shipped. The machinery exists; the first effect ships in V2 with a
runtime implementation beside it.

## 5.5 Public manifest vs. internal provenance

```
PUBLIC   environments/{id}/{version}/environment.json
         ── generator-neutral, ~3 KB, immutable, CDN-cached, world-readable

INTERNAL Studio database (Rights, Asset, Job, ValidationReport rows)
         ── provider, model, model version, prompt, negative prompt, seed,
            parameters, source images, pipeline version, licence, validation
            measurements, reviewer and decision
```

Provenance must be reproducible and auditable, and must not be fetchable by the runtime.
The single exception is `credits`, carried publicly only when attribution is required.

## 5.6 Asset path strategy

All `src` values are **relative to the manifest's own directory**. The runtime resolves
them against the manifest URL.

```
<CDN>/environments/sunset-beach/1.0.0/environment.json
<CDN>/environments/sunset-beach/1.0.0/panorama/desktop.webp
```

Rationale: the avatar app is served as static files with **no build step** (`01` §1.1),
so it cannot rewrite URLs; and relative paths make a version directory wholly
self-contained — copyable, mirrorable, and immutable as a unit. Absolute URLs in the
manifest would bake the CDN hostname into published history and break mirroring. The
*catalog* carries absolute URLs (it is the entry point); manifests carry relative ones.

## 5.7 Provider interfaces (task L)

One interface per capability. Each returns normalised output plus provenance, and knows
nothing about publication.

```python
class PanoramaResult:
    image_path: Path          # local/private; sRGB, 2:1 equirectangular
    width: int; height: int
    provenance: Provenance    # provider, model, version, prompt, seed, params

class PanoramaProvider(Protocol):
    name: str
    licence_posture: Literal["enabled", "evaluation-only", "rejected"]

    async def capabilities(self) -> PanoramaCapabilities:
        """Max resolution, seed support, negative prompts, typical latency."""

    async def generate(
        self, *, prompt: str, negative_prompt: str | None = None,
        seed: int | None = None, width: int | None = None, height: int | None = None,
        on_progress: Callable[[float, str], None] | None = None,
    ) -> PanoramaResult: ...

    async def health(self) -> ProviderHealth: ...
```

V1 implementations: `ManualImportProvider` (ingests an upload; provenance is the
uploader and the rights declaration — it satisfies the interface honestly, which is why
the pipeline can be complete before any model exists), `MockProvider`,
`RemoteAPIProvider`, `SelfHostedHTTPProvider`.

V2 adds, with the same shape:

```python
class SegmentationProvider(Protocol):
    async def detect_and_segment(self, *, image, prompt: str) -> list[DetectedObject]
    # DetectedObject: label, bbox, mask_path, confidence, crop_path

class ImageTo3DProvider(Protocol):
    async def generate(self, *, image, options) -> Mesh3DResult
    # Mesh3DResult: glb_path, triangles, materials, textures, bounds, provenance

class OptimizerProvider / StorageProvider / AudioProvider   # see 04 §4.3, 06
```

Two rules that make the boundary real:

- **`licence_posture` is a field on the provider**, checked by the publish transaction.
  An `evaluation-only` provider physically cannot publish — the licensing gate is code,
  not a wiki page (`03` §3.7).
- **The HTTP worker contract is the Studio's, not the model's.** A worker exposes
  `GET /health`, `POST /generate` → `202 {job_id}`, `GET /jobs/{id}`, and returns either
  an image body or a short-lived `download_url`. Every upstream quirk is absorbed inside
  the worker. This generalises the existing `docs/PROVIDER_CONTRACT.md`, which is already
  close.

## 5.8 Cross-repository contract testing (task §52)

The highest-value test in the plan, because it is the only thing preventing silent
divergence.

`packages/schema/fixtures/` is the shared artifact:

```
minimal-panorama/          desktop panorama only, no audio, no effects
panorama-audio/            + two audio encodings
panorama-audio-lighting/   + lighting preset and an HDR
hybrid-diorama/            V2: panorama + foreground GLB
invalid/                   missing fallbackColor · bad aspect · unknown preset
                           · over-budget quest variant · absolute src path
                           · a manifest carrying a script field
```

- **Studio side:** every fixture validates against the schema; the publisher produces
  byte-identical manifests for the fixture projects; every `invalid/` case is rejected
  with a specific error.
- **Avatar side:** a test that, for each valid fixture, runs the adapter and asserts
  `journey.register()` **accepts** the result (the `id`/`title`/`anchors` gate), that the
  resolved variant matches the device profile, and that every `lighting.preset` and
  `effects[].type` in `presets.json` has an implementation.
- Fixtures are vendored into the avatar repo by a small sync script with the schema
  version recorded, so a schema bump is a visible diff in both repositories. No
  submodule, no npm dependency — the avatar app has no build step.

## 5.9 Schema versioning and migration (task §53)

```json
{ "schemaVersion": 1 }
```

Rules:

- **`schemaVersion` is for breaking changes only.** Adding an optional field, a new
  variant `kind`, a new preset, or a new effect type is **additive** and does not bump it.
- **Consumers must ignore unknown fields.** This is a contract requirement on the
  runtime, tested on the avatar side. Note the tension with the Studio's own
  `"additionalProperties": false` — the Studio is strict about what it *writes*, the
  runtime is lenient about what it *reads*. That asymmetry is deliberate and is the
  thing that makes additive evolution possible.
- **`minRuntime` is the real compatibility signal.** A runtime that cannot honour a
  manifest skips it rather than rendering it wrongly. The catalog repeats `minRuntime` so
  an incompatible environment can be filtered out or greyed out *without* fetching its
  manifest.
- **A breaking change publishes both versions for one release cycle.** `schemaVersion: 2`
  manifests appear at a new path, the catalog lists both, the old runtime keeps using v1.
  The Studio drops v1 only once telemetry or a deliberate decision says no v1 runtimes
  remain.
- **Every change is recorded in `packages/schema/CHANGELOG.md`** with the migration note,
  even additive ones.

## 5.10 Catalog schema (task K)

The catalog must build the picker UI **without fetching any manifest** (brief §10).

```json
{
  "schemaVersion": 1,
  "revision": 42,
  "generatedAt": "2026-09-11T10:00:00Z",
  "baseUrl": "https://cdn.example/environments/",
  "categories": ["relax", "meditation", "study", "sleep", "nature",
                 "cozy", "fantasy", "focus", "chill", "seasonal"],
  "environments": [
    {
      "id": "sunset-beach",
      "version": "1.0.0",
      "name": "Sunset Beach",
      "description": "A calm tropical beach at sunset.",
      "category": "relax",
      "tags": ["beach", "ocean", "sunset", "meditation"],
      "thumbnail": "sunset-beach/1.0.0/thumb.webp",
      "preview": "sunset-beach/1.0.0/preview.webp",
      "manifest": "sunset-beach/1.0.0/environment.json",
      "fallbackColor": "#3a2436",
      "minRuntime": "1.0.0",
      "hasAudio": true,
      "hasGeometry": false,
      "targets": {
        "desktop": { "bytes": 912344,  "decodedTextureBytes": 44739242 },
        "quest":   { "bytes": 4812003, "decodedTextureBytes": 11744051 },
        "mobile":  { "bytes": 284110,  "decodedTextureBytes": 11184810 }
      },
      "featured": true,
      "publishedAt": "2026-09-11T09:58:00Z"
    }
  ]
}
```

Decisions:

- **Reference manifests, don't embed them.** Embedding would make every catalog fetch
  grow with the library and force a catalog rewrite on any manifest edit. The catalog
  carries only what the *picker* needs.
- **`fallbackColor` is duplicated into the catalog** so the runtime can paint the
  background the instant a user selects an environment, before the manifest arrives.
  Cheap, and it removes a visible flash.
- **Per-target `bytes` and `decodedTextureBytes` are in the catalog** so a headset can
  filter or warn *before* committing to a download. This is the catalog's most useful
  non-obvious field.
- **`revision` is monotonic**, and each revision is also written to an immutable
  `catalog/{revision}.json`. `catalog.json` is the mutable pointer; rollback is
  re-copying an old revision (`06` §6.9).
- **Relative paths plus `baseUrl`.** Keeps the document mirrorable and shrinks it;
  the runtime joins the two.

### Scaling (brief §10: design for thousands)

At the brief's V1 target of six environments, one file is obviously right. The growth
path, unimplemented until the thresholds are hit:

| Library size | Strategy |
|---|---|
| ≤ 200 | single `catalog.json` (≈ 400 bytes/entry → ~80 KB, gzip ~15 KB) |
| 200 – 2 000 | `catalog.json` becomes an index of shards: `{ "pages": ["catalog/p1.json", …], "byCategory": {…} }`, plus a prebuilt `featured.json` for first paint |
| > 2 000 | static shards stay for offline/CDN use; add a real search API in front — at that point the selector is an application, not a document |

`schemaVersion` does not change when sharding arrives: the index gains a `pages` field,
and `environments` becomes optional. That is additive, which is the point of §5.9.

## 5.11 The avatar-side adapter (the whole integration, specified)

```
published manifest ──► AmbienceAdapter.toSceneManifest(manifest, { device, caps })
                       │
                       │  id            ← manifest.id
                       │  title         ← manifest.name          (runtime gate)
                       │  anchors       ← manifest.orientation.anchors ?? []   (gate)
                       │  fallbackColor ← manifest.fallbackColor  (gate-adjacent)
                       │  skybox        ← resolve(variants[target].src) if kind=panorama
                       │  ambient       ← first audio.sources[] passing canPlayType
                       │  lighting      ← { exposure: manifest.lighting.exposure }
                       │  avatarPlacement ← manifest.orientation.avatarAnchor
                       └─► journey.register(…) ; journey.enter(id)
```

Target selection: `quest` when an immersive XR session is available (`DeviceDetector`
reports `headset`), `mobile` for `phone`/`tablet`, else `desktop`; `companion` when
CompanionMode is active. Falls back down the chain if a variant is absent.

The adapter's discipline is that it **only renames and selects**. It computes no
colours, invents no defaults, and contains no rendering logic — all of which stay in
`scene-journey.js` and `ViewerEngine.js`. If the adapter ever needs a conditional about
*how something looks*, the schema is wrong and should be fixed here instead.

Three avatar-side changes accompany it, all specified in `08` as PRs A1–A3:

- **A1** — replace the hard-coded `['forest','ocean','meditation']` id list with a
  catalog fetch, cached, with the bundled scenes as an offline fallback.
- **A2** — inject `loadTexture` at `boot.js:566`, reusing `ViewerEngine`'s existing
  `KTX2Loader` instance for `.ktx2` and `TextureLoader` for WebP (`01` §1.3, §1.7).
- **A3** — make VR background behaviour respect `presentation.xr.background` instead of
  unconditionally overwriting `scene.background` (`01` §1.4).

A1 and A2 are prerequisites for the first end-to-end milestone. A3 is required before
the Quest variant has any consumer, and is the reason `08` treats "it works on Quest" as
a separate milestone from "it works".

## 5.12 What the schema cannot enforce (verified, not assumed)

The draft schemas in `contracts/` were validated with `jsonschema` (Draft 2020-12)
against the reference fixture and six deliberately-broken ones. Five of the six were
rejected; **one was accepted, and that is a finding**:

| Negative fixture | Result | Rejected by |
|---|---|---|
| `missing-fallback-color.json` | rejected | `required` |
| `unknown-lighting-preset.json` | rejected | `enum` on `lighting.preset` |
| `absolute-asset-url.json` | rejected | `relativePath` pattern |
| `manifest-carrying-shader.json` | rejected | `additionalProperties: false` on the effect object |
| `ktx2-without-texture-format.json` | rejected | conditional `if/then` requiring `textureFormat` |
| `bad-aspect-ratio.json` (4096×1800) | **accepted** | nothing — JSON Schema cannot compare two fields |

So **schema validation alone must never be the publish gate.** JSON Schema has no
arithmetic across fields, which means none of the following can live in the schema:

1. `height * 2 == width` for every equirectangular variant — the defining property of the
   format, and silently absent today;
2. the per-target download and texture-memory budgets (`06` §6.7) — they compare a
   measured value against a policy threshold;
3. `decodedTextureBytes` being *consistent* with `width`, `height` and `textureFormat`
   — a manifest could otherwise understate its own cost, which is exactly the number the
   budget gate trusts;
4. `variants.quest` being present whenever `presentation.xr.background == "panorama"`;
5. `geometry` being non-empty only when `minRuntime` is a version that supports it;
6. every `src` actually existing in the published pack, with a matching `hash`.

These are the **cross-field rules** implemented in `validation/manifest.py` and
`validation/budget.py` (`04` §4.3), and the publish transaction runs them *after* schema
validation. The brief's §45 instinct to have one authoritative schema is right, but the
schema is necessary and not sufficient — the contract is "schema + cross-field rules",
and both halves ship to the avatar repo as fixtures so the runtime's contract test
exercises the same cases.
