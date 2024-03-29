#    Tools to generate and manipulate neuroglancer scenes.
#
#    Copyright (C) 2021 Philipp Schlegel
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.


# Generate a bunch of example scenes for people to play with:
# - FAFB
# - hemibrain

from .local import LocalScene
from .layers import ImageLayer, SegmentationLayer, AnnotationLayer
from .graphene import FlyWireSegmentationLayer, FancSegmentationLayer

__all__ = ['FAFBScene', 'FancScene', 'FlyWireScene']


class FAFBScene(LocalScene):
    """NeuroGlancer scene containing FAFB data (image, segmentation, synapses)."""
    def __init__(self):
        super().__init__()

        # Add image layer
        self.add_layers(ImageLayer(source='precomputed://gs://neuroglancer-fafb-data/fafb_v14/fafb_v14_clahe',
                                   name='fafb_v14_clahe'))

        # Add segmentation layer
        self.add_layers(SegmentationLayer(source="precomputed://gs://fafb-ffn1-20200412/segmentation",
                                          name='fafb-ffn1-20200412',
                                          segments=["710435991"]))

        # Add annotation layer
        self.add_layers(AnnotationLayer(source="precomputed://gs://neuroglancer-20191211_fafbv14_buhmann2019_li20190805",
                                        linkedSegmentationLayer={"pre_segment": "fafb-ffn1-20200412",
                                                                 "post_segment": "fafb-ffn1-20200412"},
                                        annotationColor="#cecd11",
                                        shader="#uicontrol vec3 preColor color(default=\"blue\")\n#uicontrol vec3 postColor color(default=\"red\")\n#uicontrol float scorethr slider(min=0, max=1000)\n#uicontrol int showautapse slider(min=0, max=1)\n\nvoid main() {\n  setColor(defaultColor());\n  setEndpointMarkerColor(\n    vec4(preColor, 0.5),\n    vec4(postColor, 0.5));\n  setEndpointMarkerSize(5.0, 5.0);\n  setLineWidth(2.0);\n  if (int(prop_autapse()) > showautapse) discard;\n  if (prop_score()<scorethr) discard;\n}\n\n",
                                        shaderControls={"scorethr": 80},
                                        filterBySegmentation=["post_segment",
                                                              "pre_segment"],
                                        name='synapses_buhmann2019'))


class FlyWireScene(LocalScene):
    """NeuroGlancer scene containing FlyWire data (meshes, FAFB14 image data)."""
    def __init__(self):
        super().__init__()

        # Add image layer
        self.add_layers(ImageLayer(source='precomputed://https://bossdb-open-data.s3.amazonaws.com/flywire/fafbv14',
                                   name='fafb_v14'))

        # Add FlyWire mesh layer
        self.add_layers(FlyWireSegmentationLayer(segments=["720575940621039145"]))

        # Add FAFB mesh
        self.add_layers(SegmentationLayer(source="precomputed://gs://flywire_neuropil_meshes/whole_neuropil/brain_mesh_v141.surf",
                                          name='fafb-neuropil',
                                          selectedAlpha=0,
                                          objectAlpha=0.05,
                                          segmentColor={"1": "#ffffff"},
                                          segments=["1"]))

        # For some reason it won't work if try I initializing the scene with
        # these settings
        self.state.update({"position": [538699, 221231, 131019],
                           "dimensions": {"x": [1e-9, "m"],
                                          "y": [1e-9, "m"],
                                          "z": [1e-9, "m"]},
                           "layout": "3d",
                           "showSlices": False,
                           "projectionScale": 365017})
        self.push_state()


class FancScene(LocalScene):
    """NeuroGlancer scene containing FANC data."""
    def __init__(self):
        super().__init__()

        # Add image layer
        self.add_layers(ImageLayer(source='precomputed://gs://zetta_lee_fly_vnc_001_precomputed/fanc_v4_em',
                                   name='FANC_v4 '))

        # Add FANC layer
        self.add_layers(FancSegmentationLayer(segments=['648518346478550356',
                                                        '648518346476465526']))

        # For some reason it won't work if try I initializing the scene with
        # these settings
        self.state.update({"position": [176052, 478389, 132651],
                           "dimensions": {"x": [1e-9, "m"],
                                          "y": [1e-9, "m"],
                                          "z": [1e-9, "m"]},
                           "layout": "3d",
                           "showSlices": False,
                           "projectionScale": 1095841})
        self.push_state()
