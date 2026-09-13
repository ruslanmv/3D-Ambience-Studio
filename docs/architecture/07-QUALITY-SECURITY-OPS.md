# 07 — Testing, security, observability

Covers task sections **S** (testing), **T** (security) and **U** (observability), plus the
quality workflow of brief §42 and the failure-recovery requirements of §47.

---

## 7.1 The environment quality workflow (brief §42)

Every transition names who or what performs it. A workflow where "the system" advances
state is a workflow nobody owns.

| State | Meaning | Advanced by | Gate |
|---|---|---|---|
| `DRAFT` | project exists, no usable master | creator | — |
| `GENERATED` | a master panorama exists (uploaded or generated) | provider job | master decodes, is 2:1, meets minimum resolution |
| `VALIDATED` | automatic source checks have run | validation job | no FAIL-class check (`06` §6.4) |
| `REVIEWED` | a human has looked at the 360 preview, the seam and both poles | **creator/reviewer, explicitly** | recorded verdict + notes; WARNs individually acknowledged |
| `OPTIMIZED` | all target variants derived and measured | optimise job | every variant produced, hashes recorded |
| `READY` | package assembled and passing every gate | package job | schema + cross-field + budget all PASS |
| `PUBLISHED` | a version is live in the catalog | publish transaction | preconditions in `06` §6.9 |
| `ARCHIVED` | withdrawn from the catalog | creator/admin | retention period before object deletion |

Two rules that make this more than a diagram:

- **`REVIEWED` can only be set by a human.** There is no automatic path from `VALIDATED`
  to `REVIEWED`, in V1 or later. Brief §63 forbids publishing generated content without
  validation; we go further and require a person to have *seen* it.
- **A state never moves backwards silently.** Editing a `READY` project returns it to
  `GENERATED` and invalidates its reports, because a report that describes different
  bytes is worse than no report.

## 7.2 Testing strategy (task S)

Ordered by value, which is not the same as ordered by volume.

### 1. Contract tests — the highest-value tests in the plan

Because they are the only thing that prevents the two repositories drifting apart, and
drift is silent until a user sees a black sky.

Studio side:
- every fixture in `packages/schema/fixtures/` validates against the published schema;
- every `invalid/` fixture is rejected, **with the expected error** — the assertion is on
  the reason, not merely on failure, so a rule cannot accidentally be enforced by a
  different rule (`05` §5.12 shows why: `bad-aspect-ratio` passes the schema and must be
  caught by the cross-field validator instead);
- the publisher, run on a fixture project, produces a **byte-identical** manifest
  (golden-file test) — this is what makes manifest changes visible in review;
- every value in `presets.json` is emitted by at least one fixture.

Avatar side (a small test file added by PR A3, consuming the synced fixtures):
- for each valid fixture, `AmbienceAdapter.toSceneManifest()` produces an object that
  `SceneJourney.validate()` accepts — i.e. non-empty string `id`, string `title`, array
  `anchors` (`01` §1.2);
- variant selection returns the expected target for each simulated device profile;
- audio source selection picks the first playable `mime`;
- **every lighting preset and effect type in `presets.json` has an implementation** — the
  test that stops the Studio publishing a preset the runtime silently ignores;
- an unknown future field in a manifest is ignored rather than fatal (`05` §5.9).

### 2. Pipeline tests with real (tiny) media

Fixtures stay small enough to commit (brief §50): a 256×128 panorama, a 2-second audio
clip. `fixtures/` already holds `demo-panorama.webp` and `demo-audio.wav` — keep that
pattern.

- **Deterministic derivation**: same master + same pipeline version → identical output
  hash. Catches an encoder upgrade changing published bytes unnoticed.
- **Measurement correctness**: `decodedTextureBytes` computed for a known
  size/format equals the hand-derived value from the table in `01` §1.9. This number
  gates publication, so it gets a test that does not trust the implementation.
- **Seam detection**: a synthetic panorama with a deliberately broken seam must FAIL; a
  known-good one must PASS. Both directions, or the check is decorative.
- **Loop verification**: an encoded clip concatenated with itself has no discontinuity
  above threshold (`06` §6.5).
- **Budget gate**: an over-budget variant FAILs and blocks the publish path.

### 3. Publish-transaction tests

The highest-risk code, tested by fault injection against a local MinIO:

- failure at each of steps 4, 5, 6, 7 (`06` §6.9) leaves **no catalog entry** — the
  invariant that matters;
- a re-run with the same idempotency key converges rather than duplicating;
- an upload that returns the wrong size/hash on verification aborts the publish;
- rollback repoints the catalog and the previous version still resolves completely;
- republishing an existing `{id}/{version}` is refused.

### 4. API and job tests

State machine transitions including illegal ones; `202 + job_id` for every long
operation; cancellation mid-stage leaves consistent state; a stale heartbeat requeues a
claimed job (`04` §4.6); a validation FAIL is not retried while a storage 5xx is.

### 5. End-to-end

One Playwright test covering the first milestone exactly: create project → upload
panorama → upload audio → optimise → validate → review → publish → fetch the resulting
`catalog.json` and `environment.json` over HTTP and validate both. If this test passes,
the architecture is proven (brief §60).

### What is deliberately not tested heavily in V1

Provider implementations beyond the mock and manual paths (they are thin HTTP clients,
and the upstreams are not ours to test); UI unit tests beyond the preview's maths;
anything requiring a GPU in CI. CI must run with no model weights and no GPU (`04` §4.8).

## 7.3 Security (task T)

### Published manifests are untrusted content

The manifest is fetched from a CDN by a browser and by a headset. Treat it as hostile
input even though we produced it, because a compromised bucket or a cache poisoning turns
our own artifact into an attack.

Runtime-side rules (contract obligations on the avatar app, tested by PR A3):

- **No executable content, ever.** No JavaScript, no GLSL, no HTML, no `eval`, no
  remote script URLs. Effects are *named presets* the runtime implements (`05` §5.4); the
  `manifest-carrying-shader` negative fixture exists to prove the schema rejects a
  smuggled shader, and it does (`05` §5.12).
- **Asset paths are validated before use.** Relative only, no leading `/`, no `..` — the
  `relativePath` pattern enforces this and the `absolute-asset-url` fixture proves it.
  Resolved against the manifest URL, so a manifest cannot reach outside its own version
  directory or point at a third-party host.
- **Size and type are checked before committing to a load.** The manifest declares
  `bytes`, `format` and `decodedTextureBytes`; the runtime may refuse an asset that
  exceeds its device budget rather than OOM-ing a headset. This is a *security* property
  as much as a performance one — an oversized texture is a denial of service on a
  memory-constrained device.
- **Hashes are available** for integrity checking where the runtime chooses to verify.

### Upload handling (Studio side)

- Validate by **decoding**, never by extension or client-supplied MIME. An uploaded
  "panorama" is an image only once libvips has decoded it to the expected dimensions.
- Enforce size limits before buffering; stream to private storage, never to a temp path
  inside the web root.
- Strip metadata: EXIF/GPS/ICC from images (after sRGB conversion), ID3/cover art from
  audio. Uploaded media routinely carries location data that must not reach a CDN.
- Re-encode everything. A published asset is always our own encoder's output, never the
  uploaded bytes passed through — which removes polyglot-file and malformed-container
  risks in one step.
- Generated filenames only. A creator-supplied filename never becomes a storage key.

### Secrets (brief §55)

- Provider API keys, storage credentials and the publisher password are **server-side
  only**, from environment or a secret manager. `.env` is gitignored; `.env.example`
  carries names and never values.
- The frontend receives **no** credentials. Uploads go through the API, or via a
  short-lived scoped presigned URL the API mints — never a long-lived bucket credential.
- The public bucket is **read-only to the world**; only the API's credential can write.
  The avatar runtime needs no credential at all, which is the strongest possible statement
  of the separation.
- A CI secret-scan on every PR, and an explicit test that no `dist/` or `apps/web` bundle
  contains a string matching known key shapes.

### Authorisation

Publisher endpoints require authentication; read endpoints for project browsing may be
relaxed in single-operator V1. Public runtime assets are unauthenticated by design.
The single most important authorisation rule is not about users at all: **a provider
whose `licence_posture` is not `enabled` cannot publish** (`05` §5.7) — the licensing
decision of `03` §3.7 is enforced in the publish transaction's preconditions rather than
trusted to discipline.

### Content safety

The validation pass includes NSFW and unwanted-content classification (`06` §6.4), and a
human reviews every environment before publication. Category and tag vocabularies are
closed enums, so a manifest cannot introduce arbitrary creator-supplied text into the
runtime UI beyond `name`/`description`, which are length-capped and rendered as text,
never as markup.

## 7.4 Failure recovery (brief §47)

| Failure | Behaviour |
|---|---|
| GPU OOM | classified as transient-recoverable: retried **once** at a reduced resolution/tile setting, then failed with the measured VRAM need recorded |
| Model crash / worker restart | job's `heartbeat_at` goes stale, the job is requeued and re-run from its own stage — not from the start of the pipeline |
| Generation timeout | per-stage deadline; job fails with the provider's last progress message preserved |
| Invalid panorama | a *result*, not an error: FAIL verdict, report shown to creator, never retried |
| Storage upload failure | retried with backoff under the same idempotency key; publish steps 4–6 are resumable by design (`06` §6.9) |
| Optimiser/tool failure | stage fails with the subprocess's stderr captured in `error_json`; masters are untouched, so a retry is safe |
| Lost DB connection | the worker loses its claim; the stale-heartbeat sweep requeues. Jobs are rows, so nothing is lost with the process |
| Publish partially completed | structurally impossible to leave a partial catalog entry: the catalog is written last and the manifest second-to-last (`06` §6.9) |
| A bad environment reaches users | `catalog.json` repointed to the previous revision — instant, cannot fail halfway |

The unifying principle: **every stage is resumable because state lives in the database
and outputs live in private storage, and the only irreversible action is a single small
catalog write.**

## 7.5 Observability (task U)

Brief §48 says do not over-engineer, and the `Job` row already carries the data that
answers every V1 question. No metrics backend in V1.

Recorded per job, in the jobs table:

```
queue wait          started_at  − queued_at
stage duration      finished_at − started_at
attempt count, terminal state, error class
provider, model, model version (generation stages)
GPU duration, peak VRAM (reported by the worker)
output bytes, output dimensions, measured decodedTextureBytes
validation verdict + per-check measured values
publish duration, number of objects uploaded, total bytes
```

That makes these answerable with a SQL query and no extra infrastructure: what is the
median generation time per provider; which validation check fails most often (the single
most useful number for improving prompt templates); are we near the Quest budget on
average or occasionally; how long does a publish take; what is the failure rate by stage
and by error class.

Logging is `structlog` JSON with a correlation id per job, propagated to provider
workers so a GPU worker's logs join to the job that caused them. `/healthz` covers
process, database and storage reachability; `GET /api/providers` reports each provider's
health and licence posture, which doubles as the operational view of the licensing gate.

Promote to real metrics (Prometheus/OTel) at the same trigger as Postgres (`04` §4.2):
more than one worker, or a deployment someone other than the author operates.

## 7.6 Definition of Done for V1 (task Y)

Measurable, and every item is verifiable by someone who did not write it.

**Contract**
1. `packages/schema/v1/` contains the environment and catalog schemas plus `presets.json`,
   published to `public/schema/` and versioned with a changelog.
2. All valid fixtures validate; all `invalid/` fixtures are rejected with the expected
   error; the aspect-ratio case is caught by the cross-field validator rather than the
   schema.
3. The avatar repo's contract test passes against the synced fixtures: every adapter
   output is accepted by `SceneJourney.validate()`, and every preset in `presets.json` has
   an implementation.

**Pipeline**
4. A 4096×2048 master yields desktop/quest/mobile/preview/thumbnail variants
   deterministically (identical hashes on re-run at the same pipeline version).
5. Measured `decodedTextureBytes` matches the derivation in `01` §1.9 for each format.
6. The budget gate FAILs an over-budget variant and blocks publication.
7. Audio publishes as Opus-in-Ogg **and** AAC-in-M4A, R128-normalised to −23 LUFS, with
   post-encode loop verification passing before `seamless: true` is claimed.

**Publication**
8. Publish is atomic: injected failures at every step leave no catalog entry.
9. Rollback repoints the catalog and the previous version resolves completely.
10. Republishing an existing `{id}/{version}` is refused.
11. Every published asset carries a `Rights` row; a provider that is not `enabled` cannot
    publish.

**Integration** — the milestone that actually matters
12. Six environments published: Sunset Beach, Calm Forest, River Meditation, Rainy Study
    Room, Zen Garden, Night Campfire.
13. `3D-Avatar-Chatbot` lists all six from the CDN catalog with **no hard-coded ids**
    (`01` §1.2 anti-pattern removed).
14. Selecting one loads its panorama and audio on desktop Chrome, and on a Quest 3 loads
    the KTX2 variant, with measured resident texture cost ≤ 12 MB and a sustained 72 FPS
    with the avatar present.
15. A scene whose panorama fails to load still enters, painted in `fallbackColor` — the
    existing runtime guarantee, preserved.
16. Passthrough still skips the background, and `enter`/`exit` still leaves the world
    unchanged over ten cycles (the runtime's existing invariant must not regress).
17. **With the Studio stopped entirely, the avatar app still loads all six environments.**

**Hygiene**
18. `docker compose up` runs the full pipeline with no GPU and no model weights.
19. No binary environment assets in Git beyond the tiny test fixtures.
20. The licensing inventory has a decided row — with an owner and date — for every
    component in the V1 production path, including libvips, FFmpeg (with its build
    decision recorded), KTX-Software/Basis and Opus.
