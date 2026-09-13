# Architecture

Overview only. The implementation-ready plan — with the avatar-runtime
inspection, the licence audit, the full contract and the PR sequence — is in
`docs/architecture/` (start at `00-EXECUTIVE-DECISION.md`).

## System boundary

```text
                    OFFLINE / AUTHORING

 upstream AI/tooling ──► provider adapters ──► Studio project
                                              │
                                              ▼
                                       optimize / validate
                                              │
                                              ▼
                                     immutable publication
                                              │
                    ──────────────────────────┼────────────
                                              ▼
                                       Object storage/CDN
                                              │
                    ──────────────────────────┼────────────
                                              ▼
                       3D-Avatar-Chatbot runtime
```

`3D-Ambience-Studio` owns authoring, provenance, optimization policy, validation, manifests, and publication. `3D-Avatar-Chatbot` owns rendering, VRM lighting implementation, WebXR behavior, adaptive runtime quality, and interaction.

## V1 modular monolith

V1 intentionally avoids a microservice explosion:

```text
React/Vite UI
      │
      ▼
 FastAPI API
      │
      ├── ProjectRepository (JSON/filesystem in V1)
      ├── PanoramaProvider registry
      ├── ImagePipeline
      ├── AudioPipeline
      ├── Validator
      └── Publisher
                │
                ▼
         local public storage
```

The provider boundary allows GPU generators to run in isolated containers or remote workers later.

## Why not embed Text2VR

Text2VR is a useful architectural reference for orchestration, GPU service isolation, segmentation and image-to-3D. The first product only needs a panorama + audio + optimized package, so V1 keeps those advanced stages optional.

## Production evolution

- V1: manual upload + mock + first panorama provider.
- V1.1: S3-compatible public/private storage and durable job queue.
- V2: segmentation + selected foreground props + image-to-3D + GLB optimization.
- V3: deeper automation, inpainting, video/procedural ambience, optional experimental representations.
