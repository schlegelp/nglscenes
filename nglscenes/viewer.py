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

from .local import LocalScene
from .serve import server, InMemoryDataSource
from .layers import SegmentationLayer
from .examples import FlyWireScene, FancScene, FAFBScene

__all__ = ['Neuroglancer']

PRECONFIG_SCENES = {
    'FlyWire': FlyWireScene,
    'FANC': FancScene,
    'FAFB': FAFBScene
}


class Viewer:
    """Local neuroglancer viewer.

    This is effectively a wrapper around LocalScene that provides some
    high-level convenience functions.

    Parameters
    ----------
    scene :     LocalScene
                Pass to plug into an existing scene instead of spawning a new
                viewer.

    """
    def __init__(self, scene=None, open=True):
        # Set the last instantiated viewer as the active one
        global primary_viewer
        primary_viewer = self

        if scene:
            self.scene = scene
        else:
            self.scene = LocalScene()

        # Set up sources and layers for the data we will want to add
        self.data_source = InMemoryDataSource()
        self.ann_layer = SegmentationLayer(source=self.data_source.url + '/annotations',
                                           ignoreSegmentInteractions=True,
                                           name='_annotations')

        if open:
            self.scene.open()

    @property
    def mesh_layer(self):
        if not hasattr(self, '_mesh_layer'):
            self._mesh_layer = SegmentationLayer(source=self.data_source.url,
                                                 ignoreSegmentInteractions=True,
                                                 name='_meshes')
            self.scene.add_layers(self._mesh_layer)
        return self._mesh_layer

    @property
    def skel_layer(self):
        if not hasattr(self, '_skel_layer'):
            self._skel_layer = SegmentationLayer(source=self.data_source.url + '/skeletons',
                                                ignoreSegmentInteractions=True,
                                                name='_skeletons')
            self.scene.add_layers(self._skel_layer)
        return self._skel_layer

    @classmethod
    def from_url(cls, url, **kwargs):
        """Create viewer from URL."""
        return cls(scene=LocalScene.from_url(url), **kwargs)

    @classmethod
    def from_preconfigured(cls, scene, **kwargs):
        """Load viewer for a pre-configured scene.

        Parameters
        ----------
        scene :    "FlyWire" | "FANC" | "FAFB"

        """
        if scene not in PRECONFIG_SCENES:
            raise ValueError(f'Unknown scene "{scene}".')

        return cls(scene=PRECONFIG_SCENES[scene](), **kwargs)

    def add(self, x, layer=None, center=False, clear=False, select=True):
        """Add objects to the `data` layer.

        Parameters
        ----------
        x :         Neuron/List | Dotprops | Volumes | Points
                    Object(s) to add to the scene:
                      - Points are added as separate annotation layer
                      - Dotprops are converted to skeletons
        layer :     str | int, optional
                    The layer to add the data to. If ``None``, will pick the
                    first available local data layer or create a new one if
                    required.
        center :    bool
                    Whether to center on the newly add objects.
        clear :     bool, optional
                    If True, clear layer before adding new objects.
        select :    bool
                    If True, the added objects are immediately selected.

        Returns
        -------
        None

        """
        if layer is None:
            layer = ['_meshes', '_skeletons']
        for l in layer:
            assert l in self.scene.layers

        # First make the data available
        segs = self.data_source.add_data(x)

        # Clear the viewer
        for l in layer:
            if clear:
                self.scene.layers[l]['segments'] = []

            # Actually select
            if select:
                self.scene.layers[l]['segments'] = self.scene.layers[l].get('segments', []) + segs




primary_viewer = None
