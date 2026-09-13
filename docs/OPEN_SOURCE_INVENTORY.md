# Open-source inventory and licensing posture

Engineering inventory, not legal advice. Code licences, model licences, datasets,
checkpoints, hosted APIs and generated-output rights are reviewed **independently** of one
another.

Audit performed **2026-09-11** against primary sources (repository `LICENSE` files, Hugging
Face model cards, dataset EULAs). Full reasoning: `docs/architecture/03-LICENSING.md`.
Fitness and integration analysis: `docs/architecture/02-UPSTREAM-ANALYSIS.md`.

`UNVERIFIED` means no primary source was read. **An `UNVERIFIED` row may not be promoted to
`ENABLED`.**

## Generation — panorama

| Project | Role | Code licence | Weights / data | Commercial | Decision |
|---|---|---|---|---|---|
| `ShijieZhou-UCLA/DreamScene360` | text → 360 → 3DGS | **Inria/MPII Gaussian-Splatting research licence** (verified; root `LICENSE.md`) | SD 2.1 + Omnidata + 3DGS | **No** — *"THE USER CANNOT USE, EXPLOIT OR DISTRIBUTE THE SOFTWARE FOR COMMERCIAL PURPOSES WITHOUT PRIOR AND EXPLICIT CONSENT OF LICENSORS"*; no sublicensing | **REJECTED** for production. Evaluation only; output must not be published. |
| `chengzhag/PanFusion` | text → 360 panorama | MIT (verified) | Trained on **Matterport3D** (non-commercial academic EULA; trained models under Matterport3D ToU + **CC BY-NC-SA 3.0**) | **No** — the weights are the blocker, not the code | **EVALUATION-ONLY.** Withdraws the earlier recommendation of PanFusion as V1's first panorama provider. |
| `Tangshitao/MVDiffusion` | multi-view / panorama | `UNVERIFIED` | Same Matterport3D lineage; assume tainted until proven | Unknown | **EVALUATION-ONLY**, pending audit. |
| `Insta360-Research-Team/DiT360` | panorama (CVPR 2026) | MIT (verified) | *Refined* Matterport3D; weights terms `UNVERIFIED` | Unknown | **EVALUATION-ONLY.** Also impractical: ~37 GB VRAM, output fixed at 1024×2048. |
| `ArcherFMY/SD-T2I-360PanoImage` (Diffusion360) | text/image → 360 | **Apache-2.0** (verified) | Weights on HF `archerfmy0831/sd-t2i-360panoimage`; licence and training data `UNVERIFIED` | Unknown — **gate** | **CANDIDATE** — leading self-hosted option (V1.2), blocked on the weights audit. |
| Commercial panorama API (e.g. Blockade Labs Skybox AI) | text → 360 | n/a (service) | n/a | Paid tiers advertise full commercial licensing; free tier has **no export rights**; vendor ToS takes a perpetual non-exclusive licence-back | **CANDIDATE** for V1.1 via `RemoteAPIProvider`. Record the licence-back. |
| Manual import | creator-supplied or licensed art | n/a | per-asset `Rights` row required | per asset | **ENABLED** — V1's first and permanent provider. |

## Generation — segmentation and image-to-3D (V2)

| Project | Role | Code licence | Weights | Commercial | Decision |
|---|---|---|---|---|---|
| `IDEA-Research/GroundingDINO` | open-vocabulary detection | `UNVERIFIED` (Apache-2.0 expected) | `UNVERIFIED` | Unknown | Audit before V2. |
| `facebookresearch/segment-anything` (SAM) | segmentation | `UNVERIFIED` | `UNVERIFIED` | Unknown | Audit before V2 — **separately from SAM 2**. |
| `facebookresearch/sam2` (SAM 2) | segmentation | `UNVERIFIED` | `UNVERIFIED` | Unknown | Audit separately; terms differ by generation and checkpoint. |
| `VAST-AI-Research/TripoSR` | image → 3D | MIT (verified) | **MIT** (verified, `stabilityai/TripoSR`) | **Yes** | **V2 DEFAULT.** ~6 GB VRAM, <0.5 s on A100. |
| `microsoft/TRELLIS` | image → 3D (premium) | MIT (verified), **submodules differ** (`diffoctreerast`, modified Flexicubes) | **MIT** (verified, `microsoft/TRELLIS-image-large`) | Yes, subject to submodules | **V2 PREMIUM**, pending submodule audit. ≥16 GB VRAM. |

## Asset pipeline — the V1 production dependencies

These are what V1 actually ships and they carry the obligations that affect what we may
**distribute**, not just what we may run.

| Component | Role | Licence | Distribution note | Decision |
|---|---|---|---|---|
| `donmccurdy/glTF-Transform` | GLB dedupe/prune/simplify, Draco, Meshopt, KTX2, WebP | **MIT** (verified) | none | **ENABLED** (V2 tool) |
| `KhronosGroup/KTX-Software` (`ktx`) | KTX2 / Basis encoding | Apache-2.0 expected — **`UNVERIFIED`**; bundles Basis Universal and ships `LICENSES/` + `NOTICE.md` that must be read | Apache-2.0 would impose NOTICE propagation | **GATE before V1 ships** — this is a V1 production dependency |
| `BinomialLLC/basis_universal` | Basis codec (via KTX-Software) | Apache-2.0 expected — `UNVERIFIED` | as above | Gate with KTX-Software |
| `zeux/meshoptimizer` | geometry compression | MIT expected — `UNVERIFIED` | none expected | Audit before V2; use via glTF Transform |
| Draco | geometry compression | Apache-2.0 expected — `UNVERIFIED` | NOTICE | Audit before V2 |
| libvips / pyvips | equirect resize, WebP encode, seam analysis | **LGPL-2.1** | Fine as a dynamically-linked library; do not statically link into a closed binary | **ENABLED** |
| Pillow | image fallback | MIT-CMU | none | ENABLED |
| **FFmpeg** | audio transcode, R128 normalisation, trimming | **LGPL-2.1+ by default; GPL if built `--enable-gpl`** (as most distro/static builds are) | **Redistributing a worker image containing a GPL build carries GPL terms.** Pin an LGPL build, or keep FFmpeg in a private worker we never redistribute | **DECISION REQUIRED** — record the build choice before V1 ships |
| libopus | Opus encoding | BSD-3-Clause | none | ENABLED |
| **Blender** | mesh cleanup, UVs, baking, colliders (V2) | **GPL** | Invoking `blender --background --python` as a **separate process** does not make our code derivative; bundling or linking triggers GPL. Keep our Blender scripts free of proprietary logic | **ENABLED as an out-of-process tool only** |
| Three.js r0.147.0 (vendored in the avatar repo) | runtime renderer | MIT | none | Note: vendored, so upgrades are deliberate |

## Reference only

| Project | Why it is here |
|---|---|
| `Text2VR/Text2VR` | Architecture reference. MIT at the root, but integrates DreamScene360 (non-commercial), SD 2 Inpaint, TRELLIS and Gaussian Splatting — the root licence does not cover them. 1 star, 128 commits: a research integration, not a proven system. Study its stage decomposition; do not adopt its topology. |

## The provider gate

No provider enters a production pipeline until its row records **all** of the following,
with a named owner and a date. This is enforced in code: a provider carries a
`licence_posture`, and the publish transaction refuses anything not `enabled`.

```
Component / version        Code licence (read from LICENSE, not the GitHub badge)
Weights licence            read from the model card / checkpoint distribution
Training data + its terms  and whether they follow the weights
Commercial use             yes / no / conditional, with the clause quoted
Redistribution             may we serve derived output from a CDN?
Share-alike                does any NC/SA term attach to our output?
Attribution                exact text, and where it is surfaced
Output rights              ownership; any vendor licence-back
Patent / codec             encumbrance on the formats produced
Decision                   ENABLED / EVALUATION-ONLY / REJECTED + owner + date
```

Three rules that make the gate real rather than ceremonial:

1. **A GitHub licence badge is not evidence.** It reflects the root `LICENSE` file only.
   DreamScene360 is the counterexample.
2. **Weights and training data are audited separately from code, always.** PanFusion is why.
3. **`UNVERIFIED` blocks production.** A row may sit there indefinitely for an
   evaluation-only component; it may never be promoted to `ENABLED` while it does.

## Never

- Commit model checkpoints, datasets or large Docker images to this repository.
- Assume a repository licence covers bundled components, weights, or generated output.
- Publish an asset without a `Rights` row.
