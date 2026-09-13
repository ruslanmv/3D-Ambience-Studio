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

## Configure a provider before generating

Open **SYSTEM CONFIGURATION** and choose where images come from: OpenAI, OllaBridge Cloud,
a local OllaBridge, HomePilot, or the built-in mock. Only the mock works with no credentials — it
draws sky and ground to the contract's horizon, which is enough to prove the pipeline end to end
but is not art.

> **This Space has no user accounts.** Anything you configure here is configured for everyone who
> can open it: an API key entered in the panel is stored in the container and used by any
> visitor's generate request, and a paired OllaBridge device is paired for all of them. The panel
> never displays a stored key, but it will happily spend it. **Set credentials only in a private
> Space**, or leave the mock provider selected in a public one.

## Persistence

Projects, generated plates and published catalogues are written inside the container, so a
restart or a rebuild starts clean. To keep them, enable persistent storage for the Space and add
the variable `AMBIENCE_DATA_DIR=/data`.

## Licence

Apache-2.0. See `LICENSE`; the repository's own README is included as `REPO_README.md`.
