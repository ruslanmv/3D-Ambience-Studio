# GPU workers

This directory intentionally contains integration documentation rather than vendored upstream source.

Use `python scripts/bootstrap_upstreams.py --group core` or `--group v2` to check out pinned upstreams into `upstream/` locally. Build provider-specific worker images separately so their CUDA/PyTorch/model dependencies do not contaminate the Studio API environment.

Recommended first worker: PanFusion panorama adapter. V2 candidate: TripoSR image-to-3D adapter.

See `docs/PROVIDER_CONTRACT.md`.
