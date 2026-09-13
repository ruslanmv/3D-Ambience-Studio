# 06 — Asset pipelines, budgets, storage, publishing

Covers task sections **O** (image pipeline), **P** (audio pipeline), **Q** (Quest
budgets), **M** (storage/CDN) and **N** (publishing workflow).

---

## 6.1 Pipeline overview

```
  PROVIDER or UPLOAD
        │
        ▼
  ┌─────────────┐   reject early: a bad master must never reach optimisation
  │ MASTER      │   4096×2048 sRGB, 2:1, lossless or near-lossless, private
  └──────┬──────┘
         ├──────────────► validate-source  (§6.4)  ─── FAIL ──► back to creator
         │
         ▼
  ┌──────────────────────────────────────────────────┐
  │ derive variants — deterministic, reproducible    │
  │   desktop  4096×2048  WebP                       │
  │   quest    4096×2048  KTX2 / UASTC               │
  │   mobile   2048×1024  WebP                       │
  │   preview  1024×512   WebP                       │
  │   thumb     320×160   WebP                       │
  └──────┬───────────────────────────────────────────┘
         ▼
  measure → bytes, decoded texture memory, hash  (§6.7 gate)
         ▼
  package → manifest + checksums   ──► human review   ──► publish (§6.9)
```

**Reproducibility rule.** Every derivation is a pure function of (master content hash,
pipeline version, encoder settings). Those three are recorded per asset, so the same
master plus the same pipeline version always yields identical bytes. Without this, a
"re-optimise" silently changes published output and cache behaviour.

## 6.2 Prompt templates (brief §41)

Applies to any generating provider; harmless and useful for the manual path too, as a
creator-facing brief.

```
<scene>, <time-of-day>, <mood>,
seamless 360-degree equirectangular panorama,
consistent geometry and architecture in every direction,
clean unbroken horizon at eye level approximately 1.6 meters,
no people, no text, no logos, no watermarks,
no duplicated landmarks, natural scale,
calm relaxing composition, soft even lighting,
VR-friendly, nothing intrusive in the near field
```

The negative prompt is where VR-friendliness is actually enforced: `people, text,
letters, logo, watermark, signature, fisheye distortion, warped horizon, duplicated
objects, floating objects, tilted camera, harsh highlights, high contrast, clutter`.

Per-scene templates are stored as data (`beach`, `forest`, `river`, `rain-room`,
`zen-garden`, `campfire`, `library`, `mountain-lake`, `snow-forest`, `fantasy-forest`),
each with its own seed ranges and preferred lighting preset, and each versioned —
because a template change alters output and therefore belongs in provenance.

Two constraints the template cannot fix, and that validation must catch instead: the
**seam** (generators frequently fail at the ±180° boundary) and the **poles** (zenith
and nadir smearing). Prompts reduce their frequency; they do not remove them.

## 6.3 Format decisions (task O)

The brief's rule — runtime compatibility beats compression ratio — is right, and the
device split follows from `01` §1.9 rather than from codec preference.

| Asset | Desktop / mobile | Quest | Why |
|---|---|---|---|
| Panorama background | **WebP**, quality 82–88, sRGB | **KTX2 / Basis UASTC 4×4 + zstd** | WebP: universally supported, one decode, fine on a machine with GB of VRAM. KTX2 on Quest because it stays GPU-compressed into VRAM — 4096×2048 costs 11 MB resident instead of 45 MB (`01` §1.9). |
| Preview (360 spin) | WebP | WebP | Preview is a desktop-UI concern. |
| Thumbnail | WebP | WebP | Grid of many; must be tiny. |
| Lighting HDR (optional) | `.hdr` (RGBE) | `.hdr` | Small (≤256×128). EXR is larger for no benefit at this size; three r147 has both loaders but `RGBELoader` output is cheaper to PMREM. |
| Ambient audio | **Opus in Ogg** + **AAC-LC in M4A** | Opus in Ogg | Opus is the best quality-per-byte and is native to Chromium and the Quest Browser. AAC is the fallback for Safari. |
| V2 geometry | GLB, Meshopt, WebP textures | GLB, Meshopt, **KTX2 textures** | All three decoders already wired into the runtime's `GLTFLoader` (`01` §1.7). |

**AVIF is deliberately not used in V1.** It compresses better than WebP, but decode is
slower and support is less uniform across the exact targets that matter (Quest Browser,
older Safari). It buys bytes on the one axis we are not constrained by, and risks the
axis we are. Revisit with a measurement, never on reputation.

**UASTC vs ETC1S is an open empirical question and must be settled by measurement, not
by this document.** ETC1S gives roughly 4× smaller downloads and half the resident
memory, but it is a 4×4 block codec with limited endpoints and **skies are smooth
gradients — the exact content where block artifacts and banding are most visible**.
Sunset gradients are the worst case in our entire content catalogue. So:

- **Default: UASTC + zstd supercompression** (safe, ~5–6 MB per 4K panorama).
- **Spike task in V1.1:** encode three representative panoramas (sunset gradient, dense
  forest, rainy interior) both ways, view them on an actual Quest 3, and record a
  per-content-type decision plus an automated banding metric. Only then make ETC1S a
  per-environment option.

## 6.4 Panorama validation (brief §13)

Generation succeeding is not publishability. Automatic checks produce a report with
measured values; a human makes the call.

| Check | Method | Default verdict |
|---|---|---|
| Aspect ratio exactly 2:1 | `width == height * 2` | **FAIL** (hard — and note JSON Schema cannot express this, `05` §5.12) |
| Minimum resolution | `width >= 4096` for a master | FAIL |
| Colour space | must be sRGB; ICC profile stripped after conversion | FAIL if unconvertible |
| **Horizontal seam continuity** | compare the leftmost and rightmost N-pixel columns: per-row mean abs difference and a gradient-discontinuity score, evaluated in linear light | FAIL above threshold; WARN near it |
| **Pole artifacts** | variance of the top/bottom 2% rows after accounting for equirect convergence; detect smearing and pinching | WARN |
| Horizon level | estimate the horizon row; flag a tilt beyond a few degrees | WARN |
| Extreme distortion | straight-line/structure detection in the mid-band | WARN |
| Duplicated objects | correlation between rotated crops | WARN (advisory; false positives are common in foliage) |
| Text / logos | OCR pass; any confident detection | WARN, surfaced prominently |
| People | detector; policy-dependent | WARN |
| Unwanted content | classifier | FAIL on the policy list |
| Corruption / truncation | full decode, byte-length check | FAIL |
| Near-flat output | global variance floor, catches a failed generation that returned a gradient | FAIL |

Two process decisions:

- **The preview must render through the runtime's own pipeline** — ACES Filmic,
  `sRGBEncoding`, exposure as published — because a panorama graded without tone mapping
  looks different in the app (`01` §1.7, `04` §4.2). A preview that lies is worse than no
  preview.
- **The seam and pole checks drive the UI, not just a verdict.** The 360 preview opens
  looking *at the seam* and offers a one-click jump to each pole. Brief §36 asks that
  seam/pole problems be obvious; making the preview start where the defects live is how.

**V1 requires human approval before publish.** No automatic publication (brief §63).

## 6.5 Audio pipeline (task P)

Constrained hard by the runtime: `new Audio(url)`, `loop = true`, no Web Audio, no loop
points (`01` §1.11). Seamlessness must therefore be solved in the file.

```
upload (wav/flac preferred) or licensed library asset
   │
   ├─ validate: duration 60–300 s, sample rate, channels, not clipped,
   │            no silence at the ends, rights metadata present
   │
   ├─ trim to an integer number of "texture" cycles where the content allows
   │
   ├─ LOOP SHAPING  ◄── the step that actually matters
   │     find the best loop point by cross-correlating candidate windows,
   │     then equal-power crossfade the tail into the head (100–400 ms)
   │     so that head and tail are sample-continuous
   │
   ├─ loudness normalise to EBU R128, target −23 LUFS, true peak ≤ −1 dBTP
   │     (consistency across environments matters more than absolute level;
   │      the published loudnessLufs lets the runtime compensate further)
   │
   ├─ encode  Opus ~96 kbps stereo → .opus.ogg     (primary)
   │          AAC-LC ~128 kbps     → .m4a          (Safari fallback)
   │
   └─ VERIFY THE LOOP AFTER ENCODING  ◄── the step everyone forgets
         decode the encoded file, concatenate it with itself, and measure the
         discontinuity at the join. Opus has encoder delay and padding; a loop
         that was gapless in the WAV can click in the Ogg. Only if this passes
         does the manifest claim "seamless": true.
```

That last step is why `audio.seamless` is an assertion in the manifest rather than an
aspiration: it is something the Studio *measured* on the published bytes.

Rights: no audio is ingested without a `Rights` row (`04` §4.5). Library music with
unclear terms is rejected at upload, not at publish — the brief's §15 warning, enforced
at the earliest possible gate.

## 6.6 Lighting presets

The Studio publishes `{preset, exposure}` and optionally a small HDR; it never publishes
light rigs (`01` §1.10, `05` §5.4). What the Studio *does* own is choosing sensible values
per environment and verifying them: the 360 preview renders the VRM-stand-in under the
chosen preset and exposure so the creator sees the avatar lit as the user will.

## 6.7 Quest asset budgets (task Q)

Derived, not invented. Inputs: Meta's WebXR guidance (72 FPS minimum / 90 target,
practical texture-memory ceiling around 256 MB, total scene triangle budgets in the
50–150 K range for mobile VR), and the resident-memory arithmetic in `01` §1.9.

**The allocation principle is that the avatar is the product.** The environment gets what
is left after the VRM, its animation, lip-sync, expressions, hands, the chat and media
panels and the VR UI are satisfied. So the environment is budgeted at **≤ 64 MB of the
~256 MB texture envelope — a quarter**, leaving roughly 190 MB for everything the avatar
experience needs.

### Per-environment budgets

| Metric | Quest budget | Desktop budget | Basis |
|---|---|---|---|
| Panorama resolution | 4096×2048 (fall back to 3072×1536 if over budget) | 4096×2048 | 4K equirect gives ~11 px/degree horizontally — adequate for a distant background; 8K doubles cost for a detail the user cannot resolve at this angular size. |
| Panorama download | **≤ 6 MB** | ≤ 1.5 MB | UASTC+zstd at 4K measures ~5–6 MB; WebP q85 at 4K is ~0.9–1.4 MB for photographic sky content. |
| Panorama resident | **≤ 12 MB** | ≤ 45 MB | ASTC 4×4 + mips at 4096×2048 = 11.2 MB. Desktop pays RGBA8 and can afford it. |
| Ambient audio, per encoding | ≤ 2.5 MB | ≤ 2.5 MB | Opus 96 kbps × 180 s ≈ 2.2 MB. |
| Preview / thumbnail | ≤ 150 KB / ≤ 20 KB | same | Catalogue grid responsiveness. |
| **Total first load** | **≤ 9 MB** | ≤ 4 MB | Sum of the above. Roughly 10 s on a typical home connection; acceptable for a deliberate scene change with a fallback colour painted instantly. |
| **Total resident (environment)** | **≤ 64 MB** | — | A quarter of the envelope, as above. |
| V2 foreground triangles | **≤ 25 K total** | ≤ 60 K | A VRM is commonly 30–70 K. 25 K for props keeps the scene inside the 50–150 K guidance with the avatar present. |
| V2 draw calls (environment) | **≤ 6** | ≤ 12 | Draw calls are CPU-bound on Quest and the dominant risk; the panorama itself is 1. |
| V2 materials | ≤ 4 | ≤ 8 | State changes between draws. |
| V2 texture dimensions | ≤ 1024² per prop | ≤ 2048² | A 1 m prop viewed from 1.5 m does not resolve more. |
| V2 transparent surfaces | **≤ 2, never overlapping the avatar** | ≤ 4 | Overdraw on a tiled GPU is the classic Quest framerate killer. |
| V2 GLB download | ≤ 3 MB total | ≤ 8 MB | |
| V2 geometry resident textures | ≤ 8 MB | — | Inside the 64 MB. |

### Quality profiles

The creator picks one per environment; it selects encoder settings, not a different
workflow.

| Profile | Quest panorama | Intended for |
|---|---|---|
| `performance` | 2048×1024 UASTC (≈3 MB resident) | Quest 2, or environments stacked with V2 props |
| `balanced` *(default)* | 4096×2048 UASTC | Everything, unless measured otherwise |
| `quality` | 4096×2048 UASTC, higher rate | Gradient-heavy skies where banding shows |

### How the gate works

The budget is **code, not advice**: `validation/budget.py` compares the *measured*
`bytes` and computed `decodedTextureBytes` against the profile's thresholds and returns
PASS/WARN/FAIL. A FAIL blocks publication; a creator may not override it, but they may
re-run at a lower profile. This is the mechanism that stops an over-heavy environment
reaching a headset, and it is the reason `decodedTextureBytes` is a published field
(`05` §5.3).

## 6.8 Storage and CDN (task M)

### Private vs public

```
private/                              never world-readable
  projects/{project_id}/
    masters/      the 4096×2048 originals, lossless
    intermediate/ provider output, crops, masks, segmentation (V2)
    reports/      validation reports, measured values
  cache/          provider responses, keyed by request hash

public/                               immutable, CDN-fronted, read-only
  catalog.json                        mutable pointer
  catalog/{revision}.json             immutable history
  schema/environment-v1.schema.json   the published contract
  schema/presets.json
  environments/{id}/{version}/
    environment.json
    preview.webp  thumb.webp
    panorama/{desktop.webp,quest.ktx2,mobile.webp}
    audio/{ambience.opus.ogg,ambience.m4a}
    lighting/lighting.hdr             optional
    geometry/*.glb                    V2
```

Rules:

- **Intermediate AI artifacts never become public automatically** (brief §28). Masters
  stay private: they are the re-optimisation source and often the rights-restricted
  original.
- **A version directory is immutable and self-contained.** Nothing is ever overwritten
  under `environments/{id}/{version}/`. A fix is `1.0.1`, never a re-upload.
- **Deduplication by content hash** happens within a version directory's manifest, not by
  sharing files across versions — self-containment is worth more than the bytes saved.
- Publishing the schema itself under `public/schema/` lets the avatar repo and any third
  party validate against exactly what produced the data.

### HTTP semantics (brief §54)

| Header | Value | Why |
|---|---|---|
| `Cache-Control` on versioned assets | `public, max-age=31536000, immutable` | The path contains the version; it can never change. |
| `Cache-Control` on `catalog.json` | `public, max-age=60, stale-while-revalidate=600` | The one mutable document. Short TTL so a publish is visible quickly; SWR so a CDN miss never blocks the app. |
| `ETag` | content hash | Cheap revalidation for the catalog. |
| `Access-Control-Allow-Origin` | the avatar app's origins (or `*` for genuinely public assets) | WebGL textures and XHR/fetch are cross-origin; without this the texture upload fails, and `three`'s loaders set `crossOrigin = 'anonymous'` (`ViewerEngine.js:156`). |
| `Content-Type` | `image/webp`, **`image/ktx2`**, `audio/ogg`, `audio/mp4`, `model/gltf-binary`, `application/json` | A wrong type on `.ktx2` is the classic failure: the transcoder receives HTML or `application/octet-stream` and fails opaquely. |
| `Content-Length` | always | Progress reporting. |
| Compression | gzip/brotli for JSON **only** | WebP, KTX2 (already zstd-supercompressed), Opus and GLB are incompressible; compressing them wastes CPU on both ends. |
| Range requests | enabled | Useful for audio seeking; harmless otherwise. |

These live as code in `infrastructure/cdn/` (bucket policy + headers), because a hand-set
header in a console is a header that will be wrong after the next migration.

## 6.9 Publishing transaction (task N)

Publication is the one place where a partial failure is visible to end users, so it is
designed as a transaction with a single commit point.

```
 1. PRECONDITIONS     project state == READY, human approval recorded,
                      every provider used has licence_posture == "enabled",
                      every asset has a Rights row
 2. RESOLVE VERSION   semver bump; refuse if {id}/{version} already exists
 3. BUILD PACK        derive manifest, compute hashes, run schema validation
                      AND the cross-field rules (05 §5.12) AND the budget gate
 4. UPLOAD ASSETS     to environments/{id}/{version}/… — every file EXCEPT
                      environment.json. Idempotent and resumable.
 5. VERIFY UPLOADS    re-read each object: size and hash must match the manifest.
                      A CDN that 404s or truncates must be caught here, not by a user.
 6. UPLOAD MANIFEST   environment.json last. Until this exists the version is
                      invisible, so steps 4–5 are freely retryable.
 7. COMMIT CATALOG    write catalog/{revision+1}.json, verify it,
                      then atomically repoint catalog.json.   ◄── THE COMMIT POINT
 8. RECORD            Publication row → LIVE, previous version → SUPERSEDED
```

Why this ordering is the whole design: **the catalog is the only mutable object, and it
is written last.** Before step 7 nothing is discoverable, so a failure at steps 1–6
leaves orphaned objects in a version directory nobody references — garbage, not
corruption, collected by a later sweep. The brief's §30 rule ("do not update the public
catalog before all required assets are available") is satisfied structurally rather than
by careful sequencing.

**Rollback** is therefore cheap and real: repoint `catalog.json` at the previous
revision. The superseded version's assets are still present and immutable, so rollback
is instant and cannot fail halfway. A *withdrawal* (for a rights problem) is different —
it removes the entry from the catalog and, only after a retention period, deletes the
objects; anyone who already cached them keeps working, which is honest rather than
pretending deletion is instant.

Failure handling per step: 1–3 fail fast with a report and no remote writes; 4–6 are
retried with the same idempotency key; 7 is a single small write that either lands or
does not; 8 is local and re-derivable.

## 6.10 The isolation property

This is the most important operational requirement and it falls out of the design above:

```
3D-Avatar-Chatbot  ──HTTPS──►  CDN  ◄──publishes──  3D-Ambience-Studio
                                   (asynchronously, rarely)
```

The runtime talks only to static objects on a CDN. It never calls the Studio API, never
authenticates to it, and holds no knowledge of it. **If the Studio is offline, deleted,
or replaced, every already-published environment keeps working forever.** That is the
test of whether the separation is real, and it is why `catalog.json` lives on the CDN
rather than behind an API endpoint that would have been marginally more convenient.
