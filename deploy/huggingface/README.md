---
title: 3D Ambience Studio
emoji: 🌅
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
license: apache-2.0
short_description: Create camera-calibrated scenic backgrounds for 3D-Avatar-Chatbot
---

# 3D Ambience Studio

Ambient environment creation, optimisation and publishing for
[3D-Avatar-Chatbot](https://github.com/ruslanmv/3D-Avatar-Chatbot) — the wizard and the API in one
container, served on port 7860.

This Space is built and pushed from
[ruslanmv/3D-Ambience-Studio](https://github.com/ruslanmv/3D-Ambience-Studio) by
`.github/workflows/sync-hf-space.yml`. **Do not edit it here** — an edit in the Space is
overwritten by the next deploy, which force-pushes a freshly built tree.

## What it does

A scenic background for the avatar app is not a wallpaper. It is a flat image composed for one
specific camera: 30° vertical field of view, 16:9, the eye lifted slightly so the view tilts
1.72° down, which puts the horizon at **44.4%** of frame height rather than the middle. Get that
wrong and the character appears to float above the ground or sink into it.

So the Studio does the technical half for you. You write "moonlit Italian coastal terrace"; it
renders a conditioning guide showing the horizon, the ground plane and the band that must stay
clear of foreground detail, appends the constraints to your prompt, sends both to the image
provider you configured, then validates, crops and optimises the result to the master size.

The five steps of the wizard: **Describe → Target → Review prompt → Generate → Publish.** Step 3
shows the full prompt and negative prompt before anything is generated, because a hidden prompt is
one nobody can debug when a result surprises them.

## Where the images come from

**Hugging Face Inference Providers**, by default, using this Space's own `HF_TOKEN` secret. One
token routed to fal.ai, Replicate, Together, Nscale or HF's own stack; the default model is
`black-forest-labs/FLUX.1-schnell`, whose weights are Apache-2.0. No GPU runs in this Space — it is
CPU-basic and calls out.

The panel also offers OpenAI, Gemini, OllaBridge (cloud or local), HomePilot and a built-in mock,
which needs no credentials at all and draws sky and ground to the contract's horizon: enough to
prove the pipeline end to end, not art.

> **SYSTEM CONFIGURATION is read-only here, on purpose.** A Space has no user accounts: everyone
> who opens it shares one configuration and one billing account. So the provider and its credential
> come from Space secrets and variables set by whoever deployed it, and no visitor can repoint them
> — which would be a way to spend someone else's credits, and a way to send their key to a host of
> your choosing. Using the wizard still spends the deployer's credits; a public Space that cares
> should leave the mock selected.

## Persistence

Projects, generated plates and published catalogues are written inside the container, so a
restart or a rebuild starts clean. To keep them, enable persistent storage for the Space and add
the variable `AMBIENCE_DATA_DIR=/data`.

## Licence

Apache-2.0. See `LICENSE`; the repository's own README is included as `REPO_README.md`.
