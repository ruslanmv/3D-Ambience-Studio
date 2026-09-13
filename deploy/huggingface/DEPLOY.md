# Running 3D Ambience Studio on Hugging Face

Everything in this directory exists to run the Studio as a **Docker Space** on port 7860. The
repository is the source of truth; the Space is a build output that is replaced on every deploy.

```
deploy/huggingface/
├── README.md         the Space card — YAML frontmatter (sdk: docker, app_port: 7860) + docs
├── Dockerfile        two stages: build the wizard, then serve it and the API from one process
├── requirements.txt  runtime dependencies, mirrored from pyproject.toml (a test pins them)
├── app.py            `uvicorn app:app` — re-exports ambience.main:app, nothing else
├── .dockerignore
├── build-tree.sh     assembles exactly what gets pushed
└── DEPLOY.md         this file
```

## The one design decision

A Space exposes a single port. The Studio is normally two processes — Vite on 5173, FastAPI on
8000 — so something had to give. What gives is Vite: stage one of the Dockerfile builds the wizard
to static files, and FastAPI serves them.

That has one consequence worth understanding, because it is the failure that would otherwise be
found by a visitor rather than by us. The wizard's API base URL is a build-time constant. Built
with no `VITE_API_BASE_URL` it points at `http://localhost:8000`, which is right on a developer's
machine and catastrophic in a Space — the visitor's browser would try to reach port 8000 on their
own laptop. So the image builds it with `VITE_API_BASE_URL=""`, and `apps/web/src/api.ts` treats
an empty value as "same origin" and only an absent one as "use localhost". An empty string is
falsy, so the usual `env || fallback` cannot express this; that file exists for that reason.

In `ambience.main`, the static mount is declared **after** every route. A `StaticFiles` mount at
`/` matches everything, so declared earlier it would shadow `/api` and `/health`, and the Space
would answer every request with `index.html`.

## First-time setup

1. **Create the Space** (once), as `sdk: docker`, at
   `https://huggingface.co/spaces/<user>/3D-Ambience-Studio`.
2. **Add three repository secrets** on GitHub, under
   _Settings → Secrets and variables → Actions_:

   | Secret        | Value                                            |
   | ------------- | ------------------------------------------------ |
   | `HF_TOKEN`    | a Hugging Face token with **write** on the Space |
   | `HF_USERNAME` | e.g. `ruslanmv`                                  |
   | `SPACE_NAME`  | e.g. `3D-Ambience-Studio`                        |

3. **Push to `main`** (or run the workflow by hand). `.github/workflows/sync-hf-space.yml` runs
   the deploy checks, builds the tree and force-pushes it as a single orphan commit.

Never commit a token. The workflow reads all three from secrets, and a test fails the build if
anything shaped like `hf_…` appears in the deploy tree.

## Testing the image before deploying

The Space builds the tree, so test the tree — not the repository:

```bash
bash deploy/huggingface/build-tree.sh /tmp/space
docker build -t ambience-space /tmp/space
docker run --rm -p 7860:7860 ambience-space
# → http://localhost:7860
```

Without Docker, the same single-process arrangement runs directly:

```bash
(cd apps/web && VITE_API_BASE_URL="" npm run build)
PYTHONPATH=apps/api AMBIENCE_WEB_DIST="$PWD/apps/web/dist" \
  python -m uvicorn app:app --app-dir deploy/huggingface --port 7860
```

And the checks that would otherwise fail in a Space build log:

```bash
pytest apps/api/tests/test_hf_deploy.py -q
```

## Space configuration

| Variable                   | Default                     | Why you would change it                                |
| -------------------------- | --------------------------- | ------------------------------------------------------ |
| `AMBIENCE_DATA_DIR`        | `/home/user/app/data`        | Set to `/data` with persistent storage enabled to keep projects across restarts. |
| `AMBIENCE_WEB_DIST`        | `/home/user/app/apps/web/dist` | Only if the bundle is mounted elsewhere.            |
| `AMBIENCE_PUBLIC_BASE_URL` | `/public`                    | Set to an absolute URL if published catalogues are consumed from another origin. |

Set them as Space **variables** (not secrets) under the Space's Settings.

## Two things the Space cannot do that a desk install can

**There are no user accounts.** Everyone who can open the Space shares one configuration. A key
entered in SYSTEM CONFIGURATION is stored in the container and spent by any visitor's generate
request; a paired OllaBridge device is paired for all of them. `generation_settings` redacts keys
on read, so nobody can *see* the key — they can still *use* it. Configure credentials only in a
private Space; in a public one, leave the mock provider selected.

**A local OllaBridge is unreachable.** The `local-trust` route assumes the bridge is on the same
machine as the Studio. From a Space, `http://localhost:11434` is the Space's own container. Use
OllaBridge Cloud, or a bridge published at a URL the Space can reach.

## What is not in the deploy tree

`docs/`, `workers/`, `upstream/`, `fixtures/`, `scripts/` and the tests. The Space builds a
runtime, not a checkout — and a Space repository is public by default, which is a second reason to
push only what the image needs. `build-tree.sh` is the list; change it there, and
`test_hf_deploy.py` will tell you if the Dockerfile disagrees.
