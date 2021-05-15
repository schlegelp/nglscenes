# nglscenes
A low-level interface to generate and manipulate neuroglancer scenes.

## Install

```bash
$ pip3 install git+git://github.com/schlegelp/nglscenes@main
```

## Usage

Manually construct a simple scene

```python
>>> from nglscenes import *
>>> # Generate empty scene
>>> scene = NeuroGlancerScene()

>>> # Generate some layers
>>> img = ImageLayer(source='precomputed://gs://neuroglancer-fafb-data/fafb_v14/fafb_v14_clahe')
>>> seg = SegmentationLayer(source="precomputed://gs://fafb-ffn1-20200412/segmentation")
>>> an = AnnotationLayer(source="precomputed://gs://neuroglancer-20191211_fafbv14_buhmann2019_li20190805")

>>> # Add layers to scene
>>> scene.add_layers(img, seg, an)
>>> scene
<NeuroGlancerScene(1 segmentation, 0 mesh, 1 image, 1 annotation)>

https://neuroglancer-demo.appspot.com/#!%7B%22laye[...]

>>> # Open in browser
>>> scene.open()

>>> # Copy to clipborad
>>> scene.to_clipboard()
URL copied to clipboard.
```

Manipulate a scene

```python
>>> from nglscenes import *
>>> # Read scene from URL or JSON-formatted string
>>> scene = NeuroglancerScene.from_clipboard()
>>> scene
<NeuroGlancerScene(3 segmentation, 1 mesh, 3 image, 1 annotation)>

https://fafb-dot-neuroglancer-demo.appspot.com/#!%7[...]

>>> # Inspect layers
>>> scene.layers[2]
<SegmentationLayer(name=fafb-ffn1-20200412, source=precomputed://gs://fafb-ffn1-20200412/segmentation, selected segments=1)>
>>> # Drop the last layer
>>> scene.drop_layer(-1)
>>> # Add segments to the segmentation layer
>>> len(scene.layers[2].segments)
1
>>> scene.layers[2].segments += [12345, 56789]
>>> len(scene.layers[2].segments)
3
```

Combine two scenes

```python
>>> # Read two scenes
>>> scene1 = NeuroglancerScene.from_clipboard()
>>> scene2 = NeuroglancerScene.from_clipboard()

>>> # Use addition to simply combine the layers of both scenes
>>> comb = scene1 + scene2
>>> len(comb) == len(scene1) + len(scene2)
True

>>> # Use OR operator to merge the layers
>>> # This will merge layers with the same data source
>>> # For segmentation layers, this will merge the selected segments
>>> merged = scene1 | scene2
>>> len(merged) < len(scene1) + len(scene2)
True

```
