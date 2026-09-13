# 01 — What `3D-Avatar-Chatbot` actually does

Covers task sections **C** (existing avatar architecture) and **R** (runtime
compatibility). Every claim here cites a file and line in `ruslanmv/3D-Avatar-Chatbot`
at commit `251e07b` (branch `master`). Nothing in this document is inferred from the
brief; where the brief's assumptions turned out to be wrong, that is stated.

No change was made to the avatar repository during this planning work.

---

## 1.1 Corrections to the brief's assumptions

The brief asked us to inspect a list of files and search for a list of symbols. The
results differ from what the brief implies in four ways that matter:

| Brief assumed | Reality |
|---|---|
| `src/gltf-viewer/environments.js` is the environment system | It is a 24-line hard-coded list of **IBL/HDR options** (`None`, `neutral`, two remote `.exr` files). It has nothing to do with ambient scenes. |
| The environment system is yet to be designed | A working one exists: **Together "Journeys"**, `src/features/together/activities/scene-journey.js` (509 lines) plus five JSON manifests in `src/features/together/scenes/`. |
| The runtime has `AmbientSceneManager`, `EnvironmentCatalog`, `EnvironmentLoader`, … | None of these exist. The brief said not to assume the names; in fact none of the *concepts* exist either, except scene loading. There is no catalog concept anywhere in the repo — `grep -rn "catalog\.json"` in `src/` returns nothing. |
| `src/gltf-viewer/PassthroughEnhancer.js` participates in background decisions | It does not touch `scene.background` or `scene.environment` at all. Passthrough background suppression lives in `scene-journey.js` instead (§1.5). |

Two more context facts that shape every recommendation downstream:

- **Three.js is vendored at r0.147.0** (`vendor/three-0.147.0/`), loaded by relative
  path, not npm. `package.json` has no `three` dependency and no bundler — `"build":
  "echo 'Static site served by nexus-proxy (no bundle step)'"`. Assets and loader
  paths are therefore resolved against the site root at runtime.
- The app is served as static files by `nexus-proxy/server.js`. There is no build step
  that could rewrite asset URLs, which makes **absolute CDN URLs in manifests the only
  workable linking strategy** (see `05-CONTRACT-SCHEMAS.md` §5.6).

---

## 1.2 The existing scene contract (this is the contract that matters)

`src/features/together/scenes/sunset.json`, verbatim:

```json
{
  "id": "sunset",
  "title": "Late sun",
  "skybox": "src/features/together/scenes/assets/sunset_8k.ktx2",
  "ambient": "src/features/together/scenes/assets/sunset_loop.ogg",
  "fallbackColor": "#3a2436",
  "lighting": { "exposure": 0.9, "hemi": "#e6a07a" },
  "anchors": [
    { "name": "horizon", "dir": [0, -0.05, -1] },
    { "name": "you", "dir": [0.2, 0, -0.4] }
  ],
  "avatarPlacement": { "pos": [0.5, 0, -0.9], "faceUser": true },
  "profileOverlay": {
    "idleProfile": "warm-attentive",
    "commentaryOpenings": ["user:silent>15000"],
    "initiative": { "budgetPerSession": 2, "minGapMs": 120000 }
  },
  "guidedScript": null
}
```

### Which fields are enforced, consumed, or dead

This distinction is the single most useful output of the inspection. A field that is
*validated* constrains what we may publish. A field that is *dead* must not be
designed around.

| Field | Status | Evidence |
|---|---|---|
| `id` | **Hard gate** — non-empty string or manifest rejected | `scene-journey.js:68` |
| `title` | **Hard gate** — must be a string | `scene-journey.js:69` |
| `anchors` | **Hard gate** — must be an array; each entry needs `name` and 3-component `dir` | `scene-journey.js:70-76` |
| `fallbackColor` | Consumed; tests assert `/^#[0-9a-f]{6}$/` on every shipped manifest | `scene-journey.js:359-363`, `tests/behavior/scenes.test.js:135` |
| `skybox` | Consumed — *only if* a `loadTexture` dependency is injected (§1.3) | `scene-journey.js:338-355` |
| `ambient` | Consumed via `new Audio(url)`, `loop = true`, `volume = 0.35` | `scene-journey.js:466-472` |
| `lighting.exposure` | Consumed — written to `renderer.toneMappingExposure` | `scene-journey.js:316-318` |
| `lighting.hemi` | **Dead.** No consumer anywhere in `src/` | `grep -rn '\.hemi\b' src/` → no hits |
| `avatarPlacement` | **Dead in runtime**, but asserted in tests | only `tests/behavior/scenes.test.js:128` |
| `profileOverlay` | Consumed — merges into the behaviour profile | `scene-journey.js:104-127`, `296-303` |
| `guidedScript` | Consumed — timed speech lines | `scene-journey.js:424-456` |

`profileOverlay` and `guidedScript` are **behavioural, not environmental**. They
control when the avatar speaks and what it says. They are the avatar application's
business and the Studio should not own them — see `05-CONTRACT-SCHEMAS.md` §5.4 for how
the manifest stays out of their way without blocking them.

### How manifests are discovered today

```js
// scene-journey.js:479-480
async function loadManifests(journey, { base = 'src/features/together/scenes', ids, fetcher } = {}) {
    const names = ids || ['forest', 'ocean', 'meditation'];
```

A hard-coded list of three ids, under a repo-relative base path. This is precisely the
anti-pattern the brief names in §63 ("modify the runtime application every time a new
environment is added"). Replacing that array with a fetched `catalog.json` is the
smallest change that makes this repository worth building, and it is PR A1 in
`08-ROADMAP-AND-PR-PLAN.md`.

---

## 1.3 Finding: the skybox path is wired but not connected

```js
// src/behavior/boot.js:566-571
director.journey = global.NEXUS_BD_JOURNEY.attach({
    bus,
    blackboard,
    gate: director.watch && director.watch.gate,
});
global.NEXUS_BD_JOURNEY.loadManifests(director.journey).catch(() => {});
```

`attach` passes no `loadTexture`, no `viewer`, no `three`. In the constructor,
`this._loadTexture = loadTexture || null` (`scene-journey.js:150`) — so it stays
`null`, and `_applySkybox` skips the entire load branch
(`if (this._loadTexture && manifest.skybox)`, line 338) and goes straight to
`fallbackColor`.

`viewer` and `three` do fall back to globals (`window.NEXUS_VIEWER`, set at
`src/engine-bridge.js:104`; `window.THREE`, set at `index-vr.html:183` only).
`loadTexture` has no such fallback.

**Consequences for this plan.** Today the five shipped scenes render as a flat colour
with an audio loop. The scene README states the art is absent by design, which is true,
but the loader is also not connected to any art even if present. So:

- The Studio's first milestone is **not** blocked on generation, optimisation, or a
  CDN. It is blocked on an avatar-side PR of perhaps 40 lines that injects a KTX2/image
  texture loader. That PR belongs to the avatar repo and is tracked as PR A2.
- Any "it works end to end" claim before that PR lands would be false. The milestone
  definition in `08` reflects this.

---

## 1.4 Finding: VR entry discards the background

```js
// src/gltf-viewer/ViewerEngine.js:345-346
this._vrBackgroundColor = this._vrBackgroundColor || 'black';
this.scene.background = new THREE.Color(this._vrBackgroundColor === 'blue' ? 0x1a1a2e : 0x000000);
```

and on exit, `ViewerEngine.js:500` writes another solid colour. Exposure is also
force-set to `1.0` on entry (`:354-355`) and restored on exit (`:508-510`).

So the current VR behaviour is: **black void plus a ground grid**, regardless of what
scene is active. A Quest panorama variant — the asset this repository exists to produce
— is overwritten on session start, and the scene's `lighting.exposure` is overridden
too.

This is not a bug to report; it is a deliberate choice for a character-focused VR mode
(`'void'` mode hides even the grid, `:358-360`). But it means the Quest variant has **no
consumer today**, and the contract must let the runtime make this choice explicitly
rather than by accident. The manifest therefore carries `xr.background` intent
(`05-CONTRACT-SCHEMAS.md` §5.3) and the runtime keeps the final say — per the brief's
§34 rule, which is correct and which we extend to VR, not just passthrough.

---

## 1.5 Passthrough / AR is already handled correctly

```js
// scene-journey.js:218-221
const sky = this.inAR
    ? Promise.resolve(false)
    : Promise.resolve(this._applySkybox(manifest, epoch)).catch(() => false);
```

`inAR` reads `viewer.arSupport.isARActive` (`:180`). In AR, a journey is "the overlay,
the anchors and the ambience" and the sky is skipped entirely — documented in the file's
own header comment and covered by `tests/behavior/scenes.test.js:409-416`.

This is exactly the behaviour the brief asks for in §34, already implemented. The
Studio's job is to **not fight it**: publish an environment whose value survives having
its background removed (audio, lighting intent, and in V2 the foreground props), and
declare that intent rather than assuming opacity.

## 1.6 Companion mode already implements three of the brief's five companion values

`src/CompanionMode.js` snapshots and nulls the scene background in two different modes:

- `_enableTransparentBackground()` (`:2761-2785`) — `scene.background = null`, clear
  colour `(0x000000, 0)`: the avatar floats in a transparent PiP window.
- `_applyBackdrop(hex)` (`:2787-2806`) — `scene.background = null`, clear colour
  `(hex, 1)`: a solid backdrop.
- `_restoreBackground()` (`:2808-2818`) — restores the snapshot.

So `transparent`, `gradient`/solid (`none` by degenerate case) already exist as runtime
behaviours. The brief's proposed companion enum (`inherit | none | transparent |
gradient | panorama | minimal`) is larger than the runtime can honour. The contract
should offer what exists plus `inherit`, and treat `panorama` in a 340×460 PiP window
as something to be justified by a measurement, not shipped speculatively
(`05-CONTRACT-SCHEMAS.md` §5.3).

Note the interaction risk: CompanionMode and scene-journey both snapshot
`scene.background` and both restore it. Entering a scene while Companion is active, or
the reverse ordering, can cross the two snapshots. The Studio cannot fix this, but it
**must not** make it worse by publishing environments that mutate renderer state
outside the two fields the runtime already guards (`SCENE_STATE = ['background',
'environment']`, `scene-journey.js:57`). This is an argument for semantic lighting over
renderer-level instructions.

---

## 1.7 Renderer configuration the Studio must satisfy

From `ViewerEngine.js:53-72` and `:158-166`:

| Setting | Value | Implication for published assets |
|---|---|---|
| `WebGLRenderer` | `antialias: true, alpha: true, xrCompatible: true` | `alpha: true` means a transparent clear is supported — Companion transparency works. |
| `setPixelRatio` | `min(devicePixelRatio, 2)`; capped lower at `:920` | Desktop can be a 2× display — a 4K panorama is not wasted. |
| `outputEncoding` | `sRGBEncoding` | Publish **sRGB** panoramas. Do not publish linear-light LDR images. |
| `toneMapping` | `ACESFilmicToneMapping`, exposure `1.0` | ACES will desaturate and roll off highlights. A panorama graded to look right *untonemapped* will look flat here. Validation must preview through ACES (`06-ASSET-PIPELINES.md` §6.4). |
| `physicallyCorrectLights` | `true` | Lighting presets must be specified in physical terms, not arbitrary multipliers. |
| `shadowMap.enabled` | `false` by default, `PCFSoftShadowMap` when on | Do not rely on environment-cast shadows. Contact shadow is the avatar app's concern. |
| GLTF loader | `DRACOLoader` (`/vendor/.../libs/draco/`), `KTX2Loader` (`.../libs/basis/`), `MeshoptDecoder` | **All three V2 compression paths are already available** — for GLB. |

The KTX2 decisive detail: `KTX2Loader` is instantiated and `detectSupport(renderer)` is
called, but it is attached **only to `GLTFLoader`** (`:162-165`). There is no standalone
KTX2 texture load path. The avatar-side PR A2 should reuse this same instance for
skybox loading rather than creating a second transcoder worker pool.

---

## 1.8 Adaptive quality: what the runtime already decides for itself

`src/gltf-viewer/PerformanceMonitor.js` runs four quality levels (0 full → 3 low),
downgrading after 3 s below 50 FPS and immediately below 30 FPS, upgrading after 8 s
above 55 FPS. `src/DeviceDetector.js:265-295` sets per-device renderer settings:

```
headset : pixelRatio 1.0, antialias only on Quest 3, shadows off
phone   : pixelRatio min(dpr, 1.5), no antialias, shadows off
desktop : pixelRatio min(dpr, 2.0), antialias, shadows on
```

**This settles a brief question (§32).** The runtime already degrades *rendering*
quality adaptively. What it cannot do is un-download a 6 MB texture or re-encode it
smaller at runtime. So the division of labour is:

- **Studio** owns what is *downloaded and resident* — resolution, codec, file size,
  texture memory. These are unrecoverable at runtime.
- **Runtime** owns what is *computed per frame* — post-processing, pixel ratio,
  shadows. The Studio must not try to control these.

This is why pre-generated per-target variants are right and "download desktop then
lower quality" is wrong — the brief's instinct in §32 is correct, and the reason is
texture memory, quantified next.

---

## 1.9 Texture memory: the real Quest constraint

Meta's WebXR guidance puts a practical ceiling around **256 MB of texture memory** and
requires 72 FPS minimum (90 FPS target). An equirect background is one draw call and
negligible geometry, so for panorama environments **texture memory is the entire
budget**, not triangles.

Decoded cost of one equirectangular panorama (4 B/px for RGBA8, 1 B/px for ASTC 4×4,
0.5 B/px for ETC2 RGB; a full mip chain adds ≈33%):

| Resolution | RGBA8 | RGBA8 + mips | ASTC 4×4 | ASTC + mips | ETC2 RGB |
|---|---|---|---|---|---|
| 2048×1024 | 8.4 MB | 11.2 MB | 2.1 MB | 2.8 MB | 1.0 MB |
| 3072×1536 | 18.9 MB | 25.2 MB | 4.7 MB | 6.3 MB | 2.4 MB |
| 4096×2048 | 33.6 MB | 44.7 MB | 8.4 MB | 11.2 MB | 4.2 MB |
| 6144×3072 | 75.5 MB | 100.6 MB | 18.9 MB | 25.2 MB | 9.4 MB |
| 8192×4096 | **134.2 MB** | 178.9 MB | 33.6 MB | 44.7 MB | 16.8 MB |

Two conclusions:

1. **The existing manifests' choice of 8K KTX2 is defensible; 8K as WebP would not
   be.** At 8192×4096 an uncompressed upload costs 134 MB — over half the headset's
   entire texture budget for the sky alone, before the VRM, its textures, the UI panels
   and the media surfaces. KTX2 is not a nicety on Quest; it is the reason the number
   fits. This independently validates the avatar repo's `.ktx2` decision.
2. **A browser-decoded format (WebP/AVIF/JPEG) is acceptable on desktop and wrong on
   Quest.** `KTX2Loader` transcodes to a GPU-native format and stays compressed into
   VRAM, cutting memory 4–8×. This is the basis for the format matrix in
   `06-ASSET-PIPELINES.md` §6.3.

---

## 1.10 Finding: `scene.environment` triggers a PMREM pass

`scene-journey.js:332-336` assigns the *same* texture to both:

```js
texture.mapping = THREE.EquirectangularReflectionMapping;
texture.__nexusScene = true;
scene.background = texture;
scene.environment = texture;
```

In the vendored r147, `WebGLCubeUVMaps.get()` gates on
`isEquirectMap && image && image.height > 0` and then runs
`pmremGenerator.fromEquirectangular(texture)`
(`vendor/three-0.147.0/build/three.module.js:16177-16182`). A KTX2 `CompressedTexture`
has an `image` with a non-zero `height`, so it passes the gate and **PMREM runs on it**:
an extra cubeUV render target plus a multi-pass blur chain, on a headset, every time a
scene is entered.

And the result is poor lighting regardless of cost: the source is an LDR sRGB sky with
no values above 1.0, so the derived IBL has no sun, no specular punch, and flat
ambient energy.

**Decision.** The published manifest must not imply "use the background as the IBL".
Lighting is published as a **semantic preset** (a name plus an exposure), with an
*optional* small HDR (e.g. 256×128 half-float or RGBE, single-digit MB) when an
environment genuinely needs directional character. The runtime keeps ownership of what
a preset means. This is the brief's §16 instinct, now with a measured reason rather
than an aesthetic one.

---

## 1.11 Audio: what the runtime can actually play

```js
// scene-journey.js:466-472
const audio = new Audio(url);
audio.loop = true;
audio.volume = 0.35;
```

An `HTMLAudioElement`, not Web Audio. The consequences are strict and they constrain
the audio pipeline in `06-ASSET-PIPELINES.md` §6.5:

- **No sample-accurate looping.** `loop = true` on a media element gaps audibly unless
  the file's own encoder delay/padding is clean. Loop-point metadata in a manifest
  would be **unimplementable** today, so the Studio must solve seamlessness *in the
  file* — encode so that naive `loop = true` is gapless — rather than describing it in
  metadata.
- **No crossfade, no filtering, no positional audio.** `defaultVolume` in a manifest is
  meaningful only if the runtime reads it; today the volume is hard-coded to `0.35`.
  The field is worth publishing (it is the creator's intent and costs nothing), but
  document it as advisory.
- **One URL, one format.** The element picks nothing; it is handed a string. So the
  *manifest* should offer a small ordered source list and the adapter should choose
  with `canPlayType`, because Ogg/Opus is fine on Chromium and the Quest Browser but
  historically weak on Safari. Publishing both Opus-in-Ogg and AAC-in-M4A costs ~2 MB
  and removes a browser-support question permanently.

---

## 1.12 Runtime compatibility summary (task section R)

How `3D-Avatar-Chatbot` will consume an environment, target state after PRs A1–A3:

```
boot
 │
 ├─ fetch  <CDN>/catalog.json                  ← replaces the hard-coded id array
 │         (cached, versioned, Studio-owned)
 │
 ├─ user picks an environment in the Together panel
 │
 ├─ fetch  <CDN>/environments/{id}/{version}/environment.json
 │
 ├─ AmbienceAdapter  (new, avatar-side, ~100 lines, purely declarative)
 │     │   maps published manifest → the shape `journey.register()` already accepts
 │     │   resolves the variant for this device (desktop | quest | mobile | companion)
 │     │   picks the audio source via canPlayType
 │     └─> { id, title, skybox, ambient, fallbackColor, lighting, anchors, … }
 │
 ├─ journey.register(mapped)   ← unchanged, still the hard gate on id/title/anchors
 ├─ journey.enter(id)          ← unchanged
 │
 └─ loadTexture injected at boot (PR A2), reusing ViewerEngine's KTX2Loader instance
```

What stays the runtime's decision, and the Studio must never override:

- whether to show a background at all in XR or passthrough (§1.4, §1.5);
- post-processing, pixel ratio, shadows, adaptive quality (§1.8);
- what a lighting preset *means* in Three.js terms (§1.10);
- what a named effect preset *does* — the manifest names effects, the runtime
  implements them, and no manifest ever carries GLSL or JavaScript.

What the Studio owns absolutely, because the runtime cannot recover it:

- resolution, codec, byte size, decoded texture memory, loop seamlessness, provenance,
  licensing, and the identity and version of the environment.
