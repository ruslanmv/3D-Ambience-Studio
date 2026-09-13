# External provider contract

Heavy AI models should run outside the Studio API process. A worker normalizes an upstream model into a tiny HTTP contract.

## Panorama worker

`POST /generate`

```json
{"prompt":"A calm forest river...","seed":42}
```

The worker may return either:

1. the final panorama as an `image/*` response, or
2. JSON containing a temporary `download_url`.

The output must be a 2:1 equirectangular image. The Studio still validates and optimizes it before publication.

## Why normalize upstream APIs

Panorama models (PanFusion, Diffusion360, DiT360 — see `OPEN_SOURCE_INVENTORY.md` for which are usable), commercial APIs, and maintained forks all have different invocation details. Their worker owns those details; `3D-Ambience-Studio` sees one provider contract.

## Future image-to-3D worker

V2 should define a similarly small contract returning a GLB plus provenance metadata. The Studio then runs its own GLB validation/optimization before publication.

## Hugging Face Inference Providers

The exception to "heavy models run in a worker", and the reason it is worth stating: nothing runs
here at all. `providers/huggingface.py` calls Hugging Face's router, which forwards to fal.ai,
Replicate, Together, Nscale, WaveSpeed or HF's own inference stack. One token reaches all of them,
no worker is deployed and no GPU is rented, which is what makes it the practical default when the
Studio itself is a CPU-basic Space.

It is a `BackplateProvider` like any other, so nothing upstream of it changes:

| Choice                  | What it does                                              |
| ----------------------- | --------------------------------------------------------- |
| `hf_routing`            | `auto` (HF chooses and fails over) or one pinned company. |
| `model`                 | Any Hub repo id. Default `black-forest-labs/FLUX.1-schnell`. |
| `hf_use_guide`          | Off: `text_to_image`. On: `image_to_image` with the guide. |

Two things behave differently from the HTTP worker contract above.

**The size asked for is not the master size.** 1920 on an edge is frequently refused or quietly
re-quantised, so the adapter asks for the largest multiple-of-16 size within 1536 at the *exact*
master aspect — 1536×864 for landscape — and lets `optimize_backplate` resize to 1920×1080. Aspect
is what must not move; resolution is recoverable and the optimise step already upscales.

**A failed conditioned generation is raised, never retried unconditioned.** A worker is allowed to
ignore `guide_png_base64` and produce a looser plate. This adapter is not allowed to substitute
`text_to_image` when `image_to_image` fails, because the substitute succeeds: it returns an
attractive plate with the horizon in the wrong place, which passes review and is discovered in the
runtime by a character standing in mid-air.

### Token permissions

A fine-grained Hugging Face token needs **"Make calls to Inference Providers"** in addition to
whatever repository scopes it carries. Without it the Hub model list still works — so the panel
looks configured — and generation fails with `403 … does not have sufficient permissions to call
Inference Providers`. That is the error TEST CONNECTION exists to surface.

### Model licences

The shortlist offered in the panel is Apache-2.0 weights only (`FLUX.1-schnell`, `Qwen-Image`),
usable commercially. "Fetch Models" lists everything the router can serve, which includes the FLUX
"dev" family under a non-commercial licence. Those remain reachable and are deliberately never the
default: a default is a licence decision taken on the operator's behalf.
