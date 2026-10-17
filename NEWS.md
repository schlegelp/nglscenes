# Unreleased

- **Breaking:** `neuroglancer`, `trimesh`, `cloud-volume`, `flask` and
  `flask-cors` are now optional dependencies and are imported lazily, which
  makes `import nglscenes` considerably faster. Install them via the `local`,
  `cave` and `serve` extras, or use `pip install "nglscenes[all]"` to get the
  previous behaviour.
- Graphene and DVID credentials providers now live in `nglscenes.credentials`
  and are registered with neuroglancer when a `LocalScene` first spawns its
  viewer or a layer is linked to a viewer (previously on `import nglscenes`). `nglscenes.dvid` is kept for
  backwards compatibility.
- `BaseLayer.NG_LAYER` is now the *name* of the neuroglancer layer class
  (e.g. `"SegmentationLayer"`) instead of the class itself.
