# 04 — V1 architecture, stack, structure and data model

Covers task sections **F** (V1 architecture), **G** (technology stack), **H** (repository
structure), **I** (data model) and **V** (deployment).

---

## 4.1 Shape of the system

**A modular monolith with out-of-process tool workers and on-demand GPU providers.**
Not microservices, not a single process that imports a model.

```
                         ┌──────────────────────────────────────┐
  creator ──browser────► │  apps/web   React + Vite             │
                         │  project → preview → validate → publish
                         └───────────────┬──────────────────────┘
                                         │  JSON over HTTPS, session auth
                         ┌───────────────▼──────────────────────┐
                         │  apps/api   FastAPI (the monolith)   │
                         │                                      │
                         │  projects · assets · jobs · versions │
                         │  validation · publication · catalog  │
                         │                                      │
                         │  owns: schema, policy, budgets,      │
                         │        provenance, state machine     │
                         └──┬──────────┬────────────┬───────────┘
                            │          │            │
             ┌──────────────▼──┐  ┌────▼────────┐  ┌▼──────────────────┐
             │ job worker      │  │ StorageProvider│ │ ProviderRegistry │
             │ (same codebase, │  │  private ──┐  │ │                  │
             │  separate proc) │  │  public ───┼──┼─┼► panorama        │
             │                 │  └────────────┼──┘ │  ├ manual import │
             │ subprocess only:│               │    │  ├ remote API    │
             │  vips · ffmpeg  │               │    │  └ self-hosted ──┼─► GPU worker
             │  ktx · gltf-tf  │               │    │ (V2) segmentation│   (on demand,
             │  blender (V2)   │               │    │ (V2) image-to-3D │    its own
             └─────────────────┘               │    └──────────────────┘    container)
                                               │
                                    ┌──────────▼──────────┐
                                    │ object storage      │
                                    │ private/  working   │
                                    │ public/   immutable │──► CDN ──► 3D-Avatar-Chatbot
                                    └─────────────────────┘
```

### Why a modular monolith

The brief asks us to challenge Text2VR's topology. Three facts decide it:

1. **V1 has exactly one optional GPU stage.** A service mesh for one optional service is
   cost without benefit.
2. **The expensive work is already out-of-process** — vips, ffmpeg, ktx, gltf-transform
   are subprocesses by nature. The isolation Text2VR gets from containers, we get from
   `subprocess` for free, with no network hop and no orchestration.
3. **The seam that must be clean is the provider interface, not the deployment unit.**
   If `PanoramaProvider` is honest, moving an implementation from in-process to a remote
   container is a config change. Starting with microservices to "keep our options open"
   buys an option we already have.

### Component responsibilities

| Component | Owns | Must not |
|---|---|---|
| `apps/web` | creator workflow, 360 preview, review/approval UI | contain secrets; talk to storage or providers directly |
| `apps/api` | the state machine, schema validation, budget policy, publication transaction, catalog generation, provenance | import a model; do CPU-heavy encoding inline; serve public assets |
| job worker | one job stage at a time, resumably; spawning tools | own policy — it executes what the API decided |
| providers | one capability, normalised output | leak model-specific fields upward |
| storage | private/public separation, immutable public writes | be bypassed by any other component |
| CDN | serving published assets | be the Studio's dependency at runtime |

---

## 4.2 Technology choices (task G)

Each row states the decision and the reason it beat the alternative. "Because Text2VR
uses it" is not a reason anywhere.

| Concern | Choice | Why, and what it beat |
|---|---|---|
| **Frontend** | **React 18 + TypeScript + Vite** | Already scaffolded here; the creator UI is form-heavy with one 3D surface. Beat Next.js: no SSR/SEO need for an internal tool, and SSR complicates a WebGL preview. |
| **360 preview** | **Three.js, pinned to the avatar's r0.147.0** | Non-obvious and important: previewing in a *newer* three than the runtime would let colour-management and tone-mapping differences hide problems. The preview's job is to predict the runtime, so it must match it, ACES and `sRGBEncoding` included (`01` §1.7). |
| **Backend** | **FastAPI + Pydantic v2** (Python 3.11+) | Already scaffolded. Python is where the image/audio/ML ecosystem is. Pydantic v2 is the schema engine (below). Beat Node: the generation ecosystem is Python, and splitting languages across the provider boundary costs more than it saves. |
| **Schema authority** | **JSON Schema 2020-12 as the source of truth**, Pydantic models generated/validated against it, TypeScript types generated from it | The contract is consumed by three parties — Python, the Studio frontend, and the avatar runtime, which is **plain JS with no build step** (`01` §1.1). Only JSON Schema can serve all three. Pydantic-first would make the schema a Python artifact the avatar repo cannot consume. The avatar side gets shipped **fixtures + a published schema file**, not generated types. |
| **Database** | **SQLite in V1** (WAL), with SQLAlchemy + Alembic from day one | One creator, tens of environments, a single writer. SQLite removes a service from local dev entirely. Alembic from the start is the cheap insurance that makes the Postgres move a config change. Beat Postgres for V1 only; see the promotion trigger below. |
| **Job queue** | **Database-backed queue, polled by a worker process in the same codebase** | Jobs are minutes long, low-volume, and must be inspectable and resumable. A DB table gives durability, visibility in the same transaction as project state, and trivially survives a worker restart. Beat Celery/RQ/Dramatiq (a broker plus a second deployment unit for <10 jobs/day) and beat FastAPI `BackgroundTasks` outright — those die with the process and cannot be resumed, which the brief's §47 requires. Arq/Redis becomes reasonable at the same time Postgres does. |
| **GPU workers** | **Separate containers, started on demand, HTTP contract** | Their CUDA/PyTorch/weights must not touch the API's environment. On-demand because idle GPUs cost money and no V1 milestone needs one. |
| **Image processing** | **libvips via pyvips** (fallback Pillow) | Streams large images with low memory — relevant at 4096×2048 and above; fast WebP. Equirect seam/pole analysis is arithmetic on pixel regions, which both support. |
| **Texture compression** | **KTX-Software (`ktx`) CLI** for KTX2/Basis | The Quest-critical step (`01` §1.9). CLI rather than library: out-of-process, pinned, replaceable. |
| **Audio** | **FFmpeg** + **libopus**; loudness via FFmpeg's EBU R128 filters | Industry standard for transcode, normalisation and precise trimming. Licence caveat in `03` §3.5 is a build decision, not a tool decision. |
| **GLB optimisation (V2)** | **glTF Transform CLI**, Blender headless for geometry repair | MIT, active, covers dedupe/prune/simplify/Draco/Meshopt/KTX2/WebP. We write `AssetOptimizer` as a wrapper and own only the *policy*. |
| **Object storage** | **S3 API via boto3**, `StorageProvider` abstraction; MinIO locally, Cloudflare R2 or B2 in production | R2 has no egress fees, which matters for a CDN-served texture catalogue. The abstraction is what keeps this reversible. |
| **CDN** | Whatever fronts the bucket (R2's own, or CloudFront/Fastly) | The contract is HTTP semantics (`06` §6.8), not a vendor. |
| **Auth** | **Single-operator session auth in V1** (password → httpOnly cookie), publisher endpoints protected; OIDC when there is a second creator | Honest about the actual threat model: one creator, no public write path. Public assets are read-only and unauthenticated by design. |
| **Docker** | Compose for non-GPU infra (API, worker, MinIO, web); GPU workers in separate compose profiles not started by default | Direct answer to brief §49: a frontend developer must never download model weights to run the UI. |
| **Testing** | pytest + `jsonschema` for contract tests; Vitest for the web app; Playwright for one e2e publish flow; **shared fixtures consumed by both repositories** | §52's cross-repo contract test is the highest-value test in the plan. |
| **Observability** | `structlog` JSON logs, per-job stage timings in the DB, `/healthz` | Brief §48 says do not over-engineer. A jobs table with timings answers every V1 question. |

### Database promotion trigger

Move SQLite → Postgres when *any* of these becomes true. Writing the trigger down now
prevents both premature migration and a surprise:

- more than one concurrent writer (a second creator, or parallel job workers);
- job volume above ~1000/day, or any need for queue fairness;
- a hosted multi-tenant deployment;
- full-text search over catalogue metadata.

---

## 4.3 Repository structure (task H)

Evolves the existing scaffold rather than replacing it — the current layout is already
close and churn has no payoff.

```
3D-Ambience-Studio/
├── apps/
│   ├── api/
│   │   ├── ambience/
│   │   │   ├── main.py                 FastAPI app factory, routers, lifespan
│   │   │   ├── config.py               settings (env-driven, never secrets in code)
│   │   │   ├── db/
│   │   │   │   ├── models.py           SQLAlchemy: Project, Asset, Job, Version, …
│   │   │   │   ├── session.py
│   │   │   │   └── migrations/         Alembic
│   │   │   ├── api/                    routers: projects, assets, jobs, publish, catalog
│   │   │   ├── domain/
│   │   │   │   ├── state.py            the project/job state machines (§4.5, §4.6)
│   │   │   │   ├── policy.py           asset budgets + quality profiles (06 §6.7)
│   │   │   │   └── provenance.py
│   │   │   ├── pipelines/
│   │   │   │   ├── image.py            master → variants
│   │   │   │   ├── audio.py            upload → loop → normalise → transcode
│   │   │   │   ├── texture.py          KTX2/Basis encoding
│   │   │   │   └── geometry.py         (V2) glTF Transform + Blender
│   │   │   ├── validation/
│   │   │   │   ├── panorama.py         seam, poles, aspect, distortion
│   │   │   │   ├── audio.py            loudness, loop discontinuity, duration
│   │   │   │   ├── manifest.py         JSON Schema + cross-field rules
│   │   │   │   └── budget.py           per-target download + texture memory
│   │   │   ├── providers/
│   │   │   │   ├── base.py             the capability interfaces (05 §5.7)
│   │   │   │   ├── registry.py
│   │   │   │   └── panorama/           manual · mock · remote_api · self_hosted
│   │   │   ├── storage/
│   │   │   │   ├── base.py             StorageProvider
│   │   │   │   ├── local.py            dev
│   │   │   │   └── s3.py               MinIO / R2 / B2
│   │   │   ├── publishing/
│   │   │   │   ├── packager.py         build the pack + manifest
│   │   │   │   ├── transaction.py      the atomic publish (06 §6.9)
│   │   │   │   └── catalog.py          catalog generation + rollback
│   │   │   ├── jobs/
│   │   │   │   ├── queue.py            DB-backed claim/heartbeat/retry
│   │   │   │   ├── worker.py           the worker entrypoint
│   │   │   │   └── stages.py           stage implementations
│   │   │   └── cli.py                  `ambience …` (V1.1, §4.7)
│   │   └── tests/
│   │       ├── unit/  contract/  integration/  fixtures/
│   └── web/
│       └── src/
│           ├── routes/      projects · project detail · review · catalog
│           ├── features/
│           │   ├── preview360/          three r0.147.0, runtime-matched
│           │   ├── validation/          report rendering, seam/pole overlays
│           │   ├── orientation/         set forward yaw by rotating the preview
│           │   └── publish/
│           └── lib/api-client.ts        generated from OpenAPI
│
├── packages/
│   └── schema/                      ◄── the contract, versioned independently
│       ├── v1/
│       │   ├── environment.schema.json
│       │   └── catalog.schema.json
│       ├── fixtures/                ◄── consumed by BOTH repositories (05 §5.8)
│       │   ├── minimal-panorama/
│       │   ├── panorama-audio/
│       │   ├── panorama-audio-lighting/
│       │   ├── hybrid-diorama/            (V2)
│       │   └── invalid/                   negative cases
│       └── CHANGELOG.md             every schema change, with its migration note
│
├── workers/
│   ├── panorama-selfhosted/         Dockerfile + the normalising HTTP shim
│   └── README.md                    never vendor weights; cache them in a volume
│
├── docs/
│   ├── architecture/                this plan
│   ├── AVATAR_CONTRACT.md           the runtime-facing contract
│   └── licenses/OPEN_SOURCE_INVENTORY.md
│
├── infrastructure/
│   ├── docker/                      api · worker · web · minio
│   └── cdn/                         bucket policy, CORS, cache headers as code
│
├── docker-compose.yml               non-GPU only, by default
├── docker-compose.gpu.yml           opt-in profile
└── Makefile
```

Three structural decisions worth stating:

- **`packages/schema/` is the product.** It is the one directory another repository
  depends on, so it gets its own versioning and changelog and never imports from
  `apps/`.
- **`upstream/` stays out of the tree.** The existing `scripts/bootstrap_upstreams.py`
  plus `upstreams.lock.json` pattern is right: clone pinned revisions on request,
  gitignored. Keep it.
- **No `shared/` directory.** The scaffold's `shared/{schemas,contracts}` idea collapses
  into `packages/schema/`; two homes for one contract is how they drift.

---

## 4.4 Provider boundary

Capabilities, not projects (brief §5, §22). Full interface definitions are in
`05-CONTRACT-SCHEMAS.md` §5.7; the architectural rules:

- A provider returns **normalised output plus provenance**. For panorama: an sRGB 2:1
  equirectangular image, and a provenance record. Never a model-specific blob.
- A provider never writes to public storage and never decides publishability.
- Every provider is registered by name in config; swapping one is a config change.
- **Four V1 implementations**, in order of delivery: `manual` (creator uploads),
  `mock` (a generated gradient, for CI and UI work without a GPU), `remote_api`
  (commercial vendor), `self_hosted` (HTTP to a GPU worker).

`manual` being a first-class provider rather than a special case is what lets the entire
pipeline — validation, optimisation, packaging, publication, catalog, and the avatar
integration — be built and tested before any model exists.

---

## 4.5 Data model (task I)

Projects are mutable; publications are immutable. That split is the core of the model.

```
Project                        the editable unit of work
  id, slug, name, description, category, tags[]
  state                        DRAFT → GENERATED → VALIDATED → REVIEWED
                               → OPTIMIZED → READY → PUBLISHED → ARCHIVED
  orientation_yaw, floor_y, avatar_anchor
  lighting_preset, lighting_exposure
  companion_mode, xr_background_intent, passthrough_intent
  effects[]                    semantic presets only
  created_at, updated_at, created_by

Asset                          every file, at every stage
  id, project_id
  role                         PANORAMA_MASTER | PANORAMA_VARIANT | PREVIEW
                               | THUMBNAIL | AUDIO_MASTER | AUDIO_VARIANT
                               | LIGHTING_HDR | GEOMETRY (V2) | REPORT
  target                       null | desktop | quest | mobile | companion
  storage_key                  private/… (never a public key)
  content_hash                 sha256 — the identity of the bytes
  bytes, mime
  width, height                images
  duration_ms, sample_rate, channels, loudness_lufs, true_peak_db   audio
  decoded_texture_bytes        computed, not guessed — the Quest gate
  derived_from_asset_id        the provenance chain back to the master
  rights_id → Rights

Rights                         §3.8; one row per distinct provenance
  source, author, licence, commercial_use, attribution_text,
  modified, generator, model, model_version, prompt, negative_prompt,
  seed, parameters_json, generated_at

Job                            one queue row per stage
  id, project_id, stage, state, attempt, max_attempts
  progress (0..1), message
  claimed_by, claimed_at, heartbeat_at        crash detection
  input_json, output_json, error_json
  queued_at, started_at, finished_at          the observability data (07 §7.6)
  idempotency_key                             safe retry

ValidationReport
  id, project_id, job_id, kind (panorama|audio|manifest|budget|geometry)
  verdict  PASS | WARN | FAIL
  checks_json                  per-check result + measured value + threshold
  created_at

Publication                    immutable once written
  id, project_id, environment_id, version (semver)
  manifest_json                exactly what was published, byte-for-byte
  asset_map_json               published path → content_hash → bytes
  public_prefix                environments/{id}/{version}/
  state  PUBLISHING | LIVE | SUPERSEDED | ROLLED_BACK | WITHDRAWN
  published_at, published_by
  source_project_state_hash    what the project looked like at publish time

CatalogRevision                the catalog is versioned too, so rollback is real
  id, revision, catalog_json, content_hash, created_at, created_by
  previous_revision_id
```

Rules the schema enforces:

- **Binaries never live in the database.** Only keys, hashes and measurements.
- **`content_hash` is the asset's identity**, which gives deduplication and cache-busting
  for free (`06` §6.8).
- **`Publication.manifest_json` is stored verbatim.** Regenerating a manifest from
  current project state would make published history a lie.
- **`decoded_texture_bytes` is computed, never estimated by a human.** It is the number
  the Quest budget gate tests (`06` §6.7).
- **A `Rights` row is mandatory for every ingested asset.** No rights, no publication.

---

## 4.6 Jobs and the stage machine

One job row per stage, not one per pipeline — so a failed optimisation resumes without
regenerating.

```
queued → running → succeeded
              └──► failed ──(retry, bounded)──► queued
              └──► cancelled
```

V1 stages:

```
import-or-generate      provider call or upload ingest
validate-source         2:1, seam, poles, resolution, content flags
optimize-image          desktop / quest / mobile variants, preview, thumbnail
encode-textures         KTX2 for the Quest variant
process-audio           trim · loop · R128 normalise · transcode (ogg/opus + m4a/aac)
package                 assemble pack + manifest + checksums
validate-package        schema + cross-field + budget gates
await-review            ◄── a human gate, not a worker stage
publish                 the atomic transaction (06 §6.9)
```

V2 inserts `segment` → `select-objects` (human) → `image-to-3d` → `optimize-geometry`
→ `validate-geometry` before `package`, with no change to the stages around them. That
is the test of whether the decomposition is right.

Failure rules (brief §47):

- Every stage is **idempotent on retry**, keyed by `idempotency_key`; re-running
  overwrites its own outputs in private storage and never touches public storage.
- Retries are bounded and **only for transient classes** (network, storage 5xx, GPU OOM
  with a smaller tile). A validation FAIL is never retried — it is a result.
- A worker writes `heartbeat_at`; a job claimed with a stale heartbeat is requeued, which
  is how a worker crash resolves itself.
- `publish` is the one stage that may not be blindly retried — see the transaction
  design, which distinguishes a resumable upload phase from the single catalog commit.
- GPU OOM is classified separately and retried once at reduced resolution before failing,
  because it is the most common provider failure and is usually recoverable.

## 4.7 API surface and the CLI

```
POST   /api/projects                      create
GET    /api/projects?state=&category=     list
GET    /api/projects/{id}                 detail, incl. current validation reports
PATCH  /api/projects/{id}                 edit metadata, orientation, lighting, effects

POST   /api/projects/{id}/assets          upload a master (panorama | audio | hdr)
POST   /api/projects/{id}/generate        → 202 {job_id}   provider call
POST   /api/projects/{id}/optimize        → 202 {job_id}
POST   /api/projects/{id}/validate        → 202 {job_id}
POST   /api/projects/{id}/review          human verdict: approve | reject + notes
POST   /api/projects/{id}/publish         → 202 {job_id}   body: {version, bump}

GET    /api/jobs/{id}                     {state, stage, progress, message}
POST   /api/jobs/{id}/cancel

GET    /api/providers                     what is registered, and its licence posture
GET    /api/environments                  published history
POST   /api/environments/{id}/rollback    body: {to_version}
GET    /api/catalog/revisions             catalog history
GET    /healthz
```

Conventions: long work is always `202 + job_id`, never a held connection (brief §24).
Mutating endpoints take an idempotency key. `PATCH` uses optimistic concurrency via the
project's `updated_at`.

**The CLI is V1.1, not V1.** It must wrap the same API, never reach into the database —
otherwise there are two state machines. Deferring it is deliberate: the workflow shape
should settle in the UI first, because a CLI freezes an interface.

```
ambience project create|list|show
ambience asset add
ambience generate|optimize|validate
ambience publish --version 1.0.0
ambience catalog show|rollback
```

## 4.8 Deployment (task V)

**Local.** `docker compose up` starts API, worker, web and MinIO — **no GPU, no
weights** (brief §49). The `mock` and `manual` providers make the full pipeline
exercisable. `make demo` (already present) should continue to run the complete
publish path on the tiny committed fixtures.

**Development/staging.** Same compose, real S3-compatible bucket, CDN in front of the
public prefix, a staging catalog at a separate prefix so the avatar app can be pointed at
it without touching production.

**GPU.** `docker compose -f docker-compose.gpu.yml up panorama` starts a provider worker
on demand, with model weights in a named volume, never in an image we redistribute
(`02` §2.2, `03` §3.5).

**Production.** API + worker as two small always-on containers; storage and CDN are
managed services; GPU capacity rented per batch, not kept warm. The crucial property is
in `06` §6.10: **if the Studio is entirely offline, the avatar application keeps working**
from the published catalog. The Studio is a content tool, not a runtime dependency.
