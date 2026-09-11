# Contract with 3D-Avatar-Chatbot

## Principle

The avatar app loads published static assets. It does not call generation models or depend on the Studio being online.

## Public catalog

`catalog.json` contains enough metadata to render a catalog quickly:

- id / version / name
- category / tags
- preview URL
- manifest URL
- optional size metadata

## Environment manifest

The runtime contract is generator-neutral. Core V1 fields describe:

- desktop and Quest panorama variants,
- Companion behavior,
- ambience audio,
- semantic lighting preset,
- semantic effect presets,
- orientation/yaw,
- optional future geometry.

Runtime code owns the implementation of lighting/effects. A manifest must never deliver executable JavaScript or arbitrary shader source.

## Example runtime flow

```text
fetch catalog.json
   ↓
user selects Calm Forest
   ↓
fetch environment.json
   ↓
resolve desktop / quest / companion variant
   ↓
load panorama + audio
   ↓
apply semantic lighting/effects via trusted runtime code
```

## Compatibility target

The existing avatar renderer already has PMREM/RoomEnvironment, KTX2/Draco/Meshopt loaders, WebXR, adaptive performance, passthrough and Companion Mode. The Studio should produce assets that complement those systems rather than introduce another renderer.
