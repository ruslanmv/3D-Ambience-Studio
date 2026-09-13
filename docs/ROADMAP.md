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

## Milestone 2 — first generating panorama provider

- a **commercially-licensed** remote API provider behind the same interface
  (PanFusion and DreamScene360 are evaluation-only: see `OPEN_SOURCE_INVENTORY.md`)
- async job abstraction
- prompt templates + provenance recording + reproducibility from seed
- human review before publish
- a self-hosted provider only if a weights audit clears (Diffusion360 is the candidate)

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

## Avatar-side track (runs in parallel from day one)

Without these, nothing the Studio publishes can be seen. Detail in
`docs/architecture/08-ROADMAP-AND-PR-PLAN.md`.

- **A2** inject `loadTexture` so a panorama can load at all (start here)
- **A1** catalog-driven scene list, replacing the hard-coded three ids
- **A3** ambience adapter + XR background intent + the shared-fixture contract test

## Explicitly deferred

- Gaussian Splatting as default runtime
- full scene reconstruction
- physics/world navigation
- arbitrary remote shaders/scripts
- automatic publish without human review
