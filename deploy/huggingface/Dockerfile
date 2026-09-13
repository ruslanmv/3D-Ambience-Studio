# 3D Ambience Studio — Hugging Face Docker Space
#
# A Space exposes exactly one port, and the Studio is normally two processes: Vite serving the
# wizard on :5173 and FastAPI serving the API on :8000. So this image collapses them. Stage one
# builds the wizard to static files; stage two installs the API and serves those files from the
# same app, on 7860, which is the port a Docker Space must listen on.
#
# Build context is the *deploy tree*, not the repository — `apps/web` and `requirements.txt` sit
# at its root. Build it with deploy/huggingface/build-tree.sh, which is also what the sync
# workflow pushes, so what you test locally is what the Space builds:
#
#   bash deploy/huggingface/build-tree.sh /tmp/space
#   docker build -t ambience-space /tmp/space && docker run -p 7860:7860 ambience-space

# ── Stage 1: the wizard ───────────────────────────────────────────────────────────────────────
FROM node:22-alpine AS web

WORKDIR /build
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm install --no-audit --no-fund
COPY apps/web/ ./

# Empty, not absent. The bundle is served by FastAPI on the Space's own origin, so every fetch
# must be relative; src/api.ts turns an empty value into same-origin and an absent one into
# http://localhost:8000, which is right for development and fatal here — it would send the
# visitor's browser to a port on their own machine.
ENV VITE_API_BASE_URL=""
RUN npm run build

# ── Stage 2: the API, serving both halves ─────────────────────────────────────────────────────
FROM python:3.12-slim

# Spaces run the container as uid 1000. Creating that user and switching to it before anything is
# written keeps every path the app touches writable; skipping it is the usual cause of a Space
# that builds and then dies on its first write.
RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /home/user/app

COPY --chown=user requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --upgrade -r requirements.txt

COPY --chown=user pyproject.toml ./pyproject.toml
COPY --chown=user app.py ./app.py
COPY --chown=user apps/api ./apps/api
COPY --chown=user schemas ./schemas
# examples/ is not sample data here: examples/backplate-camera holds the camera contracts the
# plate endpoints resolve by filename, and main.py reads them from the working directory. Without
# it the wizard's target dropdown is empty and no plate can be generated.
COPY --chown=user examples ./examples
COPY --chown=user --from=web /build/dist ./apps/web/dist

# Generated projects, optimised work files and published catalogues. Inside the image, so a Space
# restart starts clean. With persistent storage enabled, set the Space variable
# AMBIENCE_DATA_DIR=/data to keep them — /data is owned by uid 1000 and survives restarts.
RUN mkdir -p /home/user/app/data
ENV PYTHONPATH=/home/user/app/apps/api \
    AMBIENCE_DATA_DIR=/home/user/app/data \
    AMBIENCE_WEB_DIST=/home/user/app/apps/web/dist \
    AMBIENCE_PUBLIC_BASE_URL=/public

# Credentials are not baked in. HF_TOKEN (and OPENAI_API_KEY, GEMINI_API_KEY, OLLABRIDGE_TOKEN,
# HOMEPILOT_TOKEN) arrive as Space secrets, and the settings layer prefers the environment over
# anything stored — so a Space authenticates with nothing written to disk and nothing shown in the
# browser. With HF_TOKEN present the Studio starts on Hugging Face Inference Providers.

EXPOSE 7860

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
