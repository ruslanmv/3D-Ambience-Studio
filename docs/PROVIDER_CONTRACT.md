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
