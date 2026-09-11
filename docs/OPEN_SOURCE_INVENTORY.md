# Open-source inventory and initial licensing posture

This file is an engineering inventory, not legal advice. Code licenses, model licenses, datasets, checkpoints, hosted APIs, and generated-output rights must be reviewed independently.

| Project | Role | Initial strategy | Code-license observation | Production note |
|---|---|---|---|---|
| Text2VR/Text2VR | End-to-end reference | Reference/selective patterns | README states MIT | Bundled components include other terms; do not assume the entire tree is uniformly MIT. |
| ShijieZhou-UCLA/DreamScene360 | 360/3D research pipeline | Reference only by default | Root `LICENSE.md` is Gaussian-Splatting research/non-commercial oriented | Do not bundle/use commercially without explicit licensing review. |
| chengzhag/PanFusion | Text-to-360 panorama | V1 panorama provider candidate | MIT repository code | Audit model weights and Stable Diffusion-family dependencies before production. |
| VAST-AI-Research/TripoSR | Image-to-3D | V2 provider candidate | MIT repository code | Audit model weights and transitive dependencies. |
| donmccurdy/glTF-Transform | glTF/GLB optimization | Direct tool | MIT | Good fit for V2 asset normalization/compression. |

## Mandatory provider gate

A provider may be enabled in production only when its entry records:

- source repository/version,
- code license,
- model/checkpoint license,
- dataset restrictions when relevant,
- commercial-use status,
- redistribution requirements,
- attribution requirements,
- generated-output terms,
- decision owner/date.
