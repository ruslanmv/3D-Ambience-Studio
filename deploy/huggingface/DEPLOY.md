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

## Image generation on a Space

A Space that has a Hugging Face token already has an image generator, so that is what it defaults
to: with `HF_TOKEN` set and nothing stored, the Studio starts on the **Hugging Face** provider with
`black-forest-labs/FLUX.1-schnell`, and draws through Hugging Face Inference Providers — no GPU, no
worker, no second account.

Set `HF_TOKEN` as a Space **secret** (Settings → Variables and secrets → New secret). The token
needs the fine-grained permission **"Make calls to Inference Providers"**; without it the model
list still loads, so the panel looks configured, and generation fails with
`403 … does not have sufficient permissions to call Inference Providers`. TEST CONNECTION reports
that verbatim.

The same mechanism covers the other providers — `OPENAI_API_KEY`, `GEMINI_API_KEY`,
`OLLABRIDGE_TOKEN`, `HOMEPILOT_TOKEN`. A credential in the environment always wins over one stored
in the settings file, never passes through the browser and is never written to disk. The panel
shows `● Configured by deployment` in place of the key field.

## The settings panel is read-only on a Space

Detected from `SPACE_ID`, which Hugging Face sets for every Space container. Writes to the settings
endpoints are refused with 403 and the panel renders disabled with the reason shown.

This is not only about a surprise bill. A writable base URL on a public instance is a
credential-exfiltration route: point the provider at a host you control and the deployment's own key
arrives in your logs on the next generate.

Configure a locked Space with variables instead:

| Variable                   | Example                            |
| -------------------------- | ---------------------------------- |
| `AMBIENCE_IMAGE_PROVIDER`  | `huggingface`                      |
| `AMBIENCE_IMAGE_MODEL`     | `Qwen/Qwen-Image`                  |
| `AMBIENCE_HF_ROUTING`      | `auto`, `fal-ai`, `replicate`, …   |
| `AMBIENCE_HF_USE_GUIDE`    | `1` to condition on the camera guide (image-to-image models only) |

Running a private Space and want the panel back? Set `AMBIENCE_SETTINGS_LOCKED=0`.

What the lock does **not** do is make generation free. Anyone who can open a public Space can spend
its credits by using it — that is the app working as intended. If that matters, make the Space
private, or leave the mock provider selected.

## Space configuration

| Variable                   | Default                     | Why you would change it                                |
| -------------------------- | --------------------------- | ------------------------------------------------------ |
| `AMBIENCE_DATA_DIR`        | `/home/user/app/data`        | Set to `/data` with persistent storage enabled to keep projects across restarts. |
| `AMBIENCE_WEB_DIST`        | `/home/user/app/apps/web/dist` | Only if the bundle is mounted elsewhere.            |
| `AMBIENCE_PUBLIC_BASE_URL` | `/public`                    | Set to an absolute URL if published catalogues are consumed from another origin. |

Set them as Space **variables** (not secrets) under the Space's Settings.

## Two things the Space cannot do that a desk install can

**There are no user accounts.** Everyone who can open the Space shares one configuration and one
billing account. That is why the panel is read-only there and credentials come from secrets — see
the two sections above — and it is still true of generation itself: a visitor who uses the wizard
spends the deployer's credits.

**A local OllaBridge is unreachable.** The `local-trust` route assumes the bridge is on the same
machine as the Studio. From a Space, `http://localhost:11434` is the Space's own container. Use
OllaBridge Cloud, or a bridge published at a URL the Space can reach.

## What is not in the deploy tree

`docs/`, `workers/`, `upstream/`, `fixtures/`, `scripts/` and the tests. The Space builds a
runtime, not a checkout — and a Space repository is public by default, which is a second reason to
push only what the image needs. `build-tree.sh` is the list; change it there, and
`test_hf_deploy.py` will tell you if the Dockerfile disagrees.
