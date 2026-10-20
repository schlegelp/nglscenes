# 0.7.1

- Fixed `scene1 | scene2` not merging anything: merged layers were computed
  but never put back into the scene, so e.g. segments of segmentation layers
  with the same source were not combined.
- Merging segmentation layers with `|` now also keeps the segment colours
  (`segmentColors`) of both layers and the order of the segments.
- `SegmentationLayer` with a graphene source now returns a
  `GrapheneSegmentationLayer` (set up for mainline neuroglancer), like parsing
  the same state does. Previously, it gave a plain `SegmentationLayer` that
  `Scene.for_viewer()` didn't convert. This replaces the warning for bare
  `graphene://` sources.

# 0.7.0

- **Breaking:** parsed scenes now round-trip unchanged: layers read from a
  state (`Scene.from_dict`, `from_string`, `from_url`, ...) no longer get the
  constructor defaults (`selectedAlpha`, `segments`, `blend`, `shaderControls`,
  `annotations`) filled in. New `BaseLayer.from_state()` for this.
- **Breaking:** parsed graphene layers keep their type and source as written
  (no more `segmentation_with_graph` -> `segmentation` or added
  `middleauth+`). Use the new `Scene.for_viewer("spelunker" | "seunglab")` or
  `GrapheneSegmentationLayer.as_flavour()` to convert explicitly. Plain
  `segmentation` layers with a graphene source now parse as
  `GrapheneSegmentationLayer`.
- `GrapheneSegmentationLayer` accepts object (`{url, subsources}`) and list
  sources.
- Layers of unknown type (e.g. neuroglancer's `new`) are carried through as
  `GenericLayer` instead of failing the whole parse.
- `layers` given as a `{name: layer}` map are now parsed.
- New `base_url` parameter for `Scene.from_dict`/`from_string`/`from_url`/
  `from_file`/`from_clipboard` and a public `Scene.base_url` property.
- Fixed URLs for page bases: `.../neuroglancer.html` now gives
  `.../neuroglancer.html#!...` instead of `.../neuroglancer.html/#!...`.
- URLs use compact JSON (no spaces after `,`/`:`); `to_json(pretty=False)`
  is compact too.
- `Scene.from_dict` no longer modifies the input dictionary.

# 0.6.0

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
