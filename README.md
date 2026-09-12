# 3D-Ambience-Studio

A production-oriented content pipeline for creating, optimizing, validating, packaging, and publishing lightweight ambient environments for **3D-Avatar-Chatbot**, desktop browsers, Desktop Companion, and Meta Quest/WebXR.

The project intentionally separates **content generation** from **runtime rendering**:

```text
Open-source generators / uploaded media
                ↓
       3D-Ambience-Studio
 CREATE → EDIT → OPTIMIZE → VALIDATE → PUBLISH
                ↓
     versioned environment packs
                ↓
         object storage / CDN
                ↓
        3D-Avatar-Chatbot
```

## Architecture plan

`docs/architecture/` holds the implementation-ready plan, produced from direct inspection of
both repositories. Read `00-EXECUTIVE-DECISION.md` first, then
`01-AVATAR-RUNTIME-ANALYSIS.md` (what the runtime actually does, with file:line evidence),
then `08-ROADMAP-AND-PR-PLAN.md` for the PR sequence.

## Why this repository exists

The avatar runtime should never know whether a scene came from PanFusion, Text2VR, photography, Blender, TripoSR, or a future model. It consumes a stable `environment.json` + `catalog.json` contract. This repository owns that contract and the production workflow around it.

## V1 scope

V1 deliberately starts with the lowest-risk path:

1. Create a project.
2. Upload a 2:1 equirectangular panorama **or** use the built-in mock provider.
3. Upload optional ambience audio.
4. Optimize desktop / Quest / preview variants.
5. Validate the package.
6. Publish an immutable version locally (S3/CDN adapters can replace local storage).
7. Update `catalog.json` atomically.

AI generation is a provider, not the architecture.

## Open-source reuse strategy

The repository does **not vendor huge upstream projects**. `scripts/bootstrap_upstreams.py` clones pinned upstream revisions into `upstream/` when requested.

Reuse classifications are recorded in `docs/OPEN_SOURCE_INVENTORY.md` and analysed in
`docs/architecture/02-UPSTREAM-ANALYSIS.md`. Licence audit results are in
`docs/architecture/03-LICENSING.md`.

Current position after the 2026-09-11 licence audit:

- **Manual import** — the first and permanent panorama provider. V1 requires no model.
- **glTF Transform** — MIT; direct dependency for V2 GLB optimization.
- **KTX-Software / Basis** — V1 production dependency, not optional: KTX2 is what makes a
  4096x2048 panorama cost ~12 MB of Quest texture memory instead of ~45 MB.
- **TripoSR** — V2 image-to-3D default. MIT code **and** MIT weights (verified), ~6 GB VRAM.
- **TRELLIS** — V2 premium image-to-3D. MIT code and MIT weights (verified); some
  submodules carry other licences and need a separate audit. Needs >=16 GB VRAM.
- **Diffusion360 / SD-T2I-360PanoImage** — leading self-hosted panorama candidate
  (Apache-2.0 code), **gated** on a weights audit.
- **Text2VR** — architecture reference only. Its stage decomposition is useful; its
  topology is unvalidated (1 star, 128 commits) and its MIT badge does not cover the
  components it integrates.
- **PanFusion** — **not a production provider.** Repository code is MIT, but the released
  checkpoint is trained on Matterport3D, which is non-commercial academic use and whose
  trained models carry CC BY-NC-SA terms. Evaluation/reference only. *This withdraws the
  earlier recommendation of PanFusion as the first V1 panorama adapter.*
- **DreamScene360** — **rejected for production.** Its `LICENSE.md` is the Inria/MPII
  Gaussian-Splatting research licence: research and evaluation only, no commercial use
  without explicit consent, no sublicensing.
- **MVDiffusion**, **DiT360** — reference only. Same Matterport3D-derived lineage; DiT360
  additionally needs ~37 GB VRAM to produce 1024x2048.

No open-weights 360 panorama model currently has a verified commercial path, which is why
V1 does not depend on one.

## Quick start

### API

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
uvicorn ambience.main:app --app-dir apps/api --reload --port 8000
```

Open:

- API docs: http://localhost:8000/docs
- public catalog: http://localhost:8000/public/catalog.json

### Web UI

```bash
cd apps/web
npm install
npm run dev
```

The Vite frontend expects the API at `http://localhost:8000` by default.

### End-to-end demo without GPU models

```bash
make demo
```

This copies the included tiny fixture panorama/audio into a project, optimizes the assets, validates the package, and publishes it under `data/public/`.

### Clone selected upstream projects

```bash
python scripts/bootstrap_upstreams.py --group core
python scripts/bootstrap_upstreams.py --group v2
python scripts/bootstrap_upstreams.py --group reference   # large / research repos
```

Use `--group all` only when you really want everything.

## Repository layout

```text
3D-Ambience-Studio/
├── apps/
│   ├── api/                 # FastAPI + CLI + services
│   └── web/                 # React/Vite starter UI
├── schemas/                 # Runtime contract schemas
├── docs/                    # Architecture and upstream decisions
├── examples/                # Sample published manifests
├── fixtures/                # Tiny test media, safe for Git
├── scripts/                 # Upstream bootstrap + GitHub helper
├── upstreams.lock.json      # Pinned upstream revisions observed during scaffold creation
├── docker-compose.yml
├── pyproject.toml
└── Makefile
```

## Data directories

Generated data is intentionally not committed:

```text
data/
├── projects/        # editable project metadata + source assets
├── work/            # optimized draft assets
└── public/          # published catalog and immutable environment versions
```

## Contract with 3D-Avatar-Chatbot

The runtime consumes only public assets, never the Studio API:

```text
GET /catalog.json
GET /environments/{id}/{version}/environment.json
GET referenced panorama/audio/GLB assets
```

See `docs/AVATAR_CONTRACT.md`.

## License

Code original to this repository is MIT licensed. Upstream projects, model weights, datasets, checkpoints, and generated outputs may have independent terms. Do not treat the project MIT license as relicensing third-party components.
