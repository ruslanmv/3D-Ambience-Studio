# 02 — Upstream analysis and reuse classification

Covers task section **D** (Text2VR analysis), **§19** (per-project analysis) and **§20**
(reuse decision matrix). Licensing detail is in `03-LICENSING.md`; this document is about
fitness, maintenance and integration cost.

Verification date: **2026-09-11**. Where a fact could not be verified from a primary
source it is marked `UNVERIFIED` rather than guessed — an unverified row may not pass
the provider gate (`03-LICENSING.md` §3.5).

---

## 2.1 Text2VR: useful decomposition, unusable topology

`https://github.com/Text2VR/Text2VR` — MIT, 128 commits, **1 star, 2 forks**, 0 open
issues.

Its pipeline is `Query Rewrite → Panorama Generation → Segmentation → 3D Asset Gen →
Inpainting → PLY Generation`, integrating DreamScene360, GroundingDINO, SAM, TRELLIS,
Stable Diffusion 2 Inpaint, Gaussian Splatting and GPT-4o behind FastAPI + LangGraph +
Docker Compose + NVIDIA Container Toolkit, with a React/TypeScript/Vite frontend.

**The brief treats Text2VR as a proven end-to-end architecture. It is not.** One star
and 128 commits is a research integration, not a system with production mileage. Taking
its deployment model on faith would mean inheriting an unvalidated topology *and* its
dependency licensing (§2.2). So the posture is: study the decomposition, reject the
topology.

### What is genuinely worth taking

| Pattern | Why it is right | Where it lands in our plan |
|---|---|---|
| **Stage decomposition** — panorama → segmentation → image-to-3D → inpainting are separate, inspectable stages | Each stage has a different failure mode, GPU profile and review need. Fusing them makes failures undiagnosable. | Job stages, `04-V1-ARCHITECTURE.md` §4.6 |
| **Per-model process isolation** | Each model wants its own CUDA/PyTorch/weights. One shared environment is a permanent dependency-resolution tax. | Provider workers speak HTTP; the API never imports a model, `04` §4.4 |
| **A thin client per service** | The orchestrator should know one contract per capability, not one SDK per model | `PanoramaProvider` / `ImageTo3DProvider`, `05-CONTRACT-SCHEMAS.md` §5.7 |
| **Explicit progress reporting** | Generation is minutes long; an HTTP request cannot hold it | Job polling, `04` §4.6 |
| **A query-rewrite stage before generation** | Prompt shaping is where VR-friendliness is cheaply enforced | Prompt templates, `06-ASSET-PIPELINES.md` §6.2 |

### What to reject, and why

| Rejected | Reason |
|---|---|
| **Always-on microservices via Docker Compose** | Text2VR defines every GPU service up-front. Our V1 has exactly one optional GPU stage. Idle GPU containers cost money and complicate local dev for frontend work. GPU workers launch on demand. |
| **LangGraph for orchestration** | It buys conditional multi-agent branching we do not have. V1 is a fixed linear pipeline with human review gates; a state machine in the DB is simpler, inspectable, and resumable. Revisit only if V3 branching appears. |
| **Gaussian Splatting / PLY output as the scene representation** | Not consumable by the avatar runtime (three r147, no splat renderer), and the licence is non-commercial (`03` §3.2). Nothing in the brief's product vision needs it. |
| **GPT-4o in the generation path** | Fine as an optional prompt helper; unacceptable as a hard dependency of the pipeline — it adds a paid external API to a step a template handles. |
| **DreamScene360 as the panorama engine** | Non-commercial licence (`03` §3.2). This is the single most consequential rejection. |
| **Its repository layout** (bundled upstream source trees in-tree) | Exactly the anti-pattern the reuse strategy forbids. Upstreams stay out-of-tree and pinned. |

**Conclusion.** Text2VR is classified `USE ONLY AS REFERENCE`. We should read its
service boundaries and stage contracts, and write our own much smaller orchestrator.

---

## 2.2 Per-project analysis

Classification vocabulary, per brief §19: `USE DIRECTLY` · `WRAP AS SERVICE` ·
`FORK AND MODIFY` · `USE ONLY AS REFERENCE` · `REJECT`.

### Panorama generation

#### DreamScene360 — `ShijieZhou-UCLA/DreamScene360`
- **Purpose** text → 360° panorama → 3D Gaussian scene.
- **Maintenance** 6 commits; a paper release, not a maintained product.
- **Licence** `LICENSE.md` is the **Inria/MPII Gaussian-Splatting research licence**:
  *"THE USER CANNOT USE, EXPLOIT OR DISTRIBUTE THE SOFTWARE FOR COMMERCIAL PURPOSES
  WITHOUT PRIOR AND EXPLICIT CONSENT OF LICENSORS"*, research use only, no sublicensing.
- **Dependencies** 3D Gaussian Splatting, Stable Diffusion 2.1 (StitchDiffusion),
  Omnidata depth, tiny-cuda-nn, custom CUDA rasterisers.
- **GPU** unstated; CUDA 12.4 / PyTorch 2.4 with a `--data_device cpu` escape for VRAM.
  Realistically a 24 GB+ card.
- **Integration cost** High — custom CUDA builds, no API, no Docker, no health endpoint.
- **Classification** **REJECT for production; USE ONLY AS REFERENCE.** Not a licensing
  technicality to work around: the whole 3DGS lineage is non-commercial. Permitted use
  is internal research evaluation only, never publication of output.

#### PanFusion — `chengzhag/PanFusion`
- **Purpose** CVPR'24 text → 360° panorama ("Taming Stable Diffusion"), dual-branch.
- **Licence** repository code **MIT** — and this is where the brief's trap is real.
- **The disqualifying detail** PanFusion trains on the **Matterport3D skybox dataset**,
  which requires a signed academic Terms-of-Use sent from an institutional email;
  Matterport3D is non-commercial academic use, and models trained on it are distributed
  under Matterport3D's terms and **CC BY-NC-SA 3.0**. The released checkpoint is a
  derivative of non-commercial data. *MIT code plus non-commercial weights is a
  non-commercial system.*
- **Maintenance** 10 commits. No Docker, no inference API.
- **Classification** **REJECT as the V1 production provider.** `USE ONLY AS REFERENCE`
  / internal evaluation. **This withdraws the recommendation currently in this
  repository's `README.md` and `docs/OPEN_SOURCE_INVENTORY.md`**, which name PanFusion
  as the first V1 panorama adapter candidate (corrected in `03` §3.6).

#### MVDiffusion — `Tangshitao/MVDiffusion`
- **Purpose** multi-view consistent generation, incl. panorama.
- **Licence / training data** `UNVERIFIED`; the panorama model is in the same
  Matterport3D-trained lineage and must be assumed tainted until proven otherwise.
- **Classification** `USE ONLY AS REFERENCE` pending a licence audit. Not a V1 fallback.

#### DiT360 — `Insta360-Research-Team/DiT360` (not in the brief; found during research)
- **Purpose** CVPR 2026 high-fidelity panorama generation, hybrid training.
- **Licence** repository **MIT**; pretrained weights published on Hugging Face.
- **Training data** a *refined Matterport3D* dataset — same non-commercial question
  (`UNVERIFIED` whether the refinement changes the downstream terms; assume it does not).
- **Hard practical limits** **~37 GB VRAM** for unoptimised inference, and output fixed
  at **1024×2048**. That is below our 4096×2048 desktop master target and needs an
  A100-80G/H100 class card.
- **Classification** `USE ONLY AS REFERENCE` for now. Worth re-examining if the weights'
  terms clear and a memory-optimised inference path appears — it is the most *current*
  option of the four.

#### Diffusion360 / SD-T2I-360PanoImage — `ArcherFMY/SD-T2I-360PanoImage`
- **Purpose** text→360 and image→360 on Stable Diffusion, with super-resolution.
- **Licence** code **Apache-2.0**; weights on Hugging Face
  (`archerfmy0831/sd-t2i-360panoimage`) and Baidu Disk, weights licence and training
  data `UNVERIFIED`.
- **Maintenance** last substantive note May 2024; pins `diffusers <= 0.26.0`.
- **Classification** **`WRAP AS SERVICE` — the leading self-hosted candidate**, *subject
  to the weights audit*. Apache-2.0 code is the most permissive starting point of any
  panorama option found, and it is the only one whose base-model lineage (SD under
  CreativeML OpenRAIL++-M) has a commercial path. Treat the audit as a gate, not a
  formality.

#### Commercial panorama APIs (e.g. Blockade Labs Skybox AI)
- Paid tiers advertise full commercial licensing for exported assets; the free tier has
  no export rights. Their ToS grants the vendor a perpetual non-exclusive licence to
  content created with the service — acceptable for our use, but a fact to record.
- **Classification** **`USE DIRECTLY` via a `RemoteAPIProvider`.** This is the
  pragmatic way to get six publishable environments with clean rights and zero GPU
  infrastructure. It is a provider behind the same interface, so it is replaceable.

**Net position on panorama generation.** There is currently **no open-weights panorama
model with a verified clean commercial path**. Therefore V1 must not depend on one. The
V1 order is: manual import first, then a commercial API provider, then a self-hosted
provider if and when an audit clears. This is the central reason the implementation
sequence in `08` puts generation last rather than first.

### Segmentation and detection (V2)

| Project | Purpose | Notes | Classification |
|---|---|---|---|
| **GroundingDINO** (`IDEA-Research`) | open-vocabulary detection from a text prompt | Apache-2.0 expected, `UNVERIFIED`; weights terms must be checked separately. Exactly the right tool for "rocks, chairs, plants" → boxes. | `WRAP AS SERVICE` (V2) |
| **SAM / SAM 2** (`facebookresearch`) | promptable segmentation | Licence `UNVERIFIED` and it differs by generation and by checkpoint — SAM 1 and SAM 2 must be audited separately, not as one row. | `WRAP AS SERVICE` (V2) |

Both are V2 and both sit behind one `SegmentationProvider`, because the creator-facing
operation is "find candidate objects", not "run two models".

### Image-to-3D (V2)

| Project | Code | Weights | GPU | Output | Classification |
|---|---|---|---|---|---|
| **TripoSR** (`VAST-AI-Research`) | MIT | **MIT** (verified on `stabilityai/TripoSR`) | **~6 GB VRAM**, <0.5 s on A100 | mesh, vertex colours or `--bake-texture` | **`WRAP AS SERVICE` — the V2 default.** Cheapest, permissive both halves. |
| **TRELLIS** (`microsoft`) | MIT, *some submodules differ* (`diffoctreerast`, modified Flexicubes) | **MIT** (verified on `microsoft/TRELLIS-image-large`) | **≥16 GB VRAM**, tested A100/A6000 | higher-fidelity 3D | `WRAP AS SERVICE` — V2 premium tier. Audit submodule licences before shipping. |

Both are genuinely permissive in code *and* weights — the cleanest licensing story of
any AI component examined. The quality/cost split (6 GB vs 16 GB) maps naturally onto a
default and a premium provider behind one `ImageTo3DProvider`.

### Asset pipeline (V1 and V2)

| Project | Role | Licence | Classification |
|---|---|---|---|
| **glTF Transform** (`donmccurdy`) | GLB inspection, dedupe, prune, Draco, Meshopt, KTX2/Basis (UASTC + ETC1S), WebP; CLI + library, Node LTS | **MIT** (verified) | **`USE DIRECTLY`.** Actively developed (2,100+ commits, CI). Do not write a GLB optimiser. |
| **meshoptimizer** (`zeux`) | geometry compression / simplification | MIT expected, `UNVERIFIED` | `USE DIRECTLY`, via glTF Transform rather than directly |
| **Basis Universal** (`BinomialLLC`) / **KTX-Software** (`KhronosGroup`) | KTX2 supercompressed textures; transcodes to BC/ASTC/ETC2 at load, 4–8× texture-memory saving | Apache-2.0 expected for both, `UNVERIFIED` — KTX-Software bundles Basis and carries a `LICENSES/` folder that must be read properly | `USE DIRECTLY`. **This is the Quest-critical dependency** (`01` §1.9). |
| **Draco** | geometry compression | Apache-2.0 expected, `UNVERIFIED` | `USE DIRECTLY` where it beats Meshopt; decoder already present in the runtime |
| **Blender** | mesh cleanup, origin/scale/orientation, UVs, lightmap UVs, baking, colliders | **GPL**. Critical distinction: invoking `blender --background --python x.py` as a **separate process** does not make our code a derivative work; *linking* or bundling would. Scripts we write for Blender's Python API are a genuine grey area and should be kept free of proprietary logic. | `USE DIRECTLY` as an **out-of-process offline tool** (V2). Never a library, never bundled into an image we redistribute without GPL compliance. |

### Image and audio tooling (V1 production dependencies)

These are the components V1 actually ships, and they are the ones the existing
inventory does not cover at all.

| Tool | Role | Licence note | Classification |
|---|---|---|---|
| **libvips / pyvips** or **Pillow** | equirect resize, WebP/AVIF encode, seam checks | libvips is LGPL-2.1 — fine when used as a library via a dynamically linked binding; Pillow is MIT-CMU | `USE DIRECTLY` |
| **FFmpeg** | audio transcode, loudness normalisation, loop shaping | **The build matters.** A default `--enable-gpl` build is GPL; an LGPL build is not. If we redistribute a Docker image containing FFmpeg we inherit that build's terms. Pin an LGPL build or accept GPL for the worker image and keep it out of the published product. | `USE DIRECTLY` as an out-of-process tool |
| **Opus / libopus** | ambience codec | BSD-3-Clause | `USE DIRECTLY` |

---

## 2.3 Final reuse decision matrix (task §20)

The brief's draft table is revised. Changes from the brief are marked **▲**.

| Project | Purpose | Strategy | V | Change vs. the brief |
|---|---|---|---|---|
| Text2VR | End-to-end reference | **Reference only** — decomposition yes, topology no | — | ▲ demoted: 1 star, unvalidated; not "selective reuse" of code |
| DreamScene360 | Panorama | **REJECT for production** (non-commercial); reference only | — | ▲ was "provider or isolated fork"; a fork cannot fix a licence |
| PanFusion | Panorama | **REJECT as production provider** (Matterport3D-derived weights); reference only | — | ▲ was "alternative provider"; also withdraws this repo's own V1 recommendation |
| MVDiffusion | Panorama | Reference only, pending audit | — | ▲ not a usable fallback |
| DiT360 | Panorama | Reference only; re-examine (37 GB VRAM, 1024×2048) | — | ▲ **new row** — more current than the brief's three |
| Diffusion360 / SD-T2I-360PanoImage | Panorama | **Wrap as service — leading self-hosted candidate**, gated on weights audit | V1.2 | ▲ **new row** — the only Apache-2.0 code path found |
| Commercial panorama API | Panorama | **Use directly** via `RemoteAPIProvider` — clean rights, no GPU | V1.1 | ▲ **new row** — the realistic first *generating* provider |
| Manual import | Panorama | **Use directly** — the first provider implementation | **V1** | ▲ **new row** — proves the whole contract without a GPU |
| GroundingDINO | Detection | Wrap as service, pending audit | V2 | unchanged |
| SAM / SAM 2 | Segmentation | Wrap as service; audit each generation separately | V2 | ▲ split: one row for two licences was wrong |
| TripoSR | Image-to-3D | **Wrap as service — V2 default** (MIT code *and* MIT weights, 6 GB) | V2 | ▲ promoted above TRELLIS on cost and clarity |
| TRELLIS | Image-to-3D | Wrap as service — V2 premium; audit submodules | V2 | unchanged in role |
| glTF Transform | GLB optimisation | **Use directly** (MIT, active) | V2 | unchanged |
| Meshopt | Geometry compression | Use directly *via* glTF Transform | V2 | unchanged |
| KTX2 / Basis | Texture compression | **Use directly — Quest-critical, not optional** | **V1** | ▲ promoted to V1: it is what makes Quest texture memory fit |
| Draco | Geometry compression | Use directly where it wins | V2 | unchanged |
| Blender | Cleanup / baking | Use directly, **out-of-process only** (GPL) | V2 | ▲ GPL boundary made explicit |
| libvips / Pillow | Image pipeline | Use directly | **V1** | ▲ **new row** — V1's actual image dependency |
| FFmpeg + Opus | Audio pipeline | Use directly out-of-process; **pin the build's licence** | **V1** | ▲ **new row** — V1's actual audio dependency |

The shape of the corrected table is the finding: **every V1 row is a deterministic
tool, and every AI row is V2 or gated.** That is not a compromise; it is what makes V1
deliverable and legally defensible.
