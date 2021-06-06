[![Tests](https://github.com/schlegelp/nglscenes/actions/workflows/test-package.yml/badge.svg)](https://github.com/schlegelp/nglscenes/actions/workflows/test-package.yml)

# nglscenes
A low-level interface to generate and manipulate [neuroglancer](https://github.com/google/neuroglancer) scenes.

This is very much WIP and implementation details might change at any point!

## Install

```bash
$ pip3 install git+git://github.com/schlegelp/nglscenes@main
```

## Usage

### Overview

At this point, `nglscenes` has three different types of "scenes":

1. Use a basic `Scene` to construct and manipulate neuroglancer states.
2. A `StateScene` is a scene that works with a state server instead of encoding
   the JSON state into a long URL.
3. If you want to work locally, you should use a `LocalScene` which starts a
   local neuroglancer server and then keeps the state between the browser and
   Python synced.

### Examples

#### Basics

Manually construct a simple scene

```python
>>> from nglscenes import *
>>> # Generate empty scene
>>> scene = Scene(base_url='https://neuroglancer-demo.appspot.com')

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
>>> len(scene.layers[2]['segments'])
1
>>> scene.layers[2]['segments'] += [12345, 56789]
>>> len(scene.layers[2]['segments'])
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

All of the above examples will also work with the other scene types.


#### Remote controlling neuroglancer

```python
>>> from nglscenes import *
>>> # Generate empty scene
>>> scene = LocalScene()
>>> scene                                                                                                                        
<LocalScene(1 segmentation, 0 mesh, 1 image, 1 annotation)>

http://127.0.0.1:53955/v/4dc530306753007bd4fc39b745673d604e58d2a5/

>>> # Open scene in browser
>>> scene.open()

>>> # Generate and add layers
>>> # -> you should see the layers appear in the browser window
>>> scene.add_layers(ImageLayer(source='precomputed://gs://neuroglancer-fafb-data/fafb_v14/fafb_v14_clahe'))
>>> scene.add_layers(SegmentationLayer(source="precomputed://gs://fafb-ffn1-20200412/segmentation"))
>>> scene.add_layers(AnnotationLayer(source="precomputed://gs://neuroglancer-20191211_fafbv14_buhmann2019_li20190805"))

>>> # The state is automatically synced:
>>> scene.layers[-1].state
OrderedDict([('source',
              'precomputed://gs://neuroglancer-20191211_fafbv14_buhmann2019_li20190805'),
             ('type', 'annotation'),
             ('name', 'annotations'),
             ('tab', 'source'),
             ('visible', False)])
>>> # Hide the layer
>>> scene.layers[-1]['visible'] = False
>>> # Get the same layer by name and unhide
>>> scene.layers['annotations']['visible'] = True
>>> # Set selected segments
>>> scene.layers[1]['segments'] = [5280982928, 5517604362]

>>> # Serve skeletons from a local folder containing SWC files
>>> # (this also works from a zip file)
>>> scene.add_layers(LocalSkeletonLayer(LocalSkeletonLayer(source='~/skeletons/')))
>>> scene.layers[-1]['segments'] = [123456]
```
