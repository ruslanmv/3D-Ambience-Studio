# Roadmap

## Milestone 0 — contract first

- Environment schema v1
- Catalog schema v1
- fixtures shared with avatar runtime
- local atomic publisher

## Milestone 1 — complete non-AI path

- create project
- manual panorama upload
- optional ambience audio upload
- desktop/Quest/preview optimization
- validation
- publish and update catalog

## Milestone 2 — first AI panorama provider

- PanFusion adapter/worker contract
- async job abstraction
- prompt/provenance recording
- human review before publish

## Milestone 3 — production storage

- S3-compatible private working storage
- immutable public bucket/CDN
- durable database/job queue
- authentication

## Milestone 4 — V2 foreground geometry

- GroundingDINO/SAM-style segmentation provider
- creator selects useful foreground objects
- TripoSR/TRELLIS provider(s)
- glTF Transform optimization
- Quest asset budgets and validation

## Explicitly deferred

- Gaussian Splatting as default runtime
- full scene reconstruction
- physics/world navigation
- arbitrary remote shaders/scripts
- automatic publish without human review
