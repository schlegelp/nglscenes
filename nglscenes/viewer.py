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

from .local import LocalScene, LocalAnnotationLayer
from .serve import server, InMemoryDataSource
from .layers import SegmentationLayer
from .examples import FlyWireScene, FancScene, FAFBScene
from .utils import parse_objects

__all__ = ['Viewer']

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
                Pass to connect to an existing scene instead of spawning a new
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

        if open:
            self.open()

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

    @property
    def scatter_layer(self):
        if not hasattr(self, '_scatter_layer'):
            self._scatter_layer = LocalAnnotationLayer(name='_scatter')
            self.scene.add_layers(self._scatter_layer)
        return self._scatter_layer

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
                    The layer to add the data to. If ``None``, will put the data
                    in genericically added layers.
        center :    bool
                    Whether to center on the newly added objects.
        clear :     bool, optional
                    If True, clear layer before adding new objects.
        select :    bool
                    If True, the added objects are immediately selected. If
                    False, will only add objects to data source, i.e. make them
                    available to be selected.

        Returns
        -------
        None

        """
        meshes, skeletons, annotations = parse_objects(x)

        if layer is not None:
            assert layer in self.scene.layers, f'Layer {layer} not in scene'

        if meshes:
            # First make the data available
            segs = self.data_source.add_data(meshes)

            if layer:
                l = self.scene.layers[l]
            else:
                l = self.mesh_layer

            if clear:
                l['segments'] = []

            # Actually select
            if select:
                l['segments'] = l.get('segments', []) + segs

        if skeletons:
            # First make the data available
            segs = self.data_source.add_data(skeletons)

            if layer:
                l = self.scene.layers[l]
            else:
                l = self.skel_layer

            if clear:
                l['segments'] = []

            # Actually select
            if select:
                l['segments'] = l.get('segments', []) + segs

    def clear(self):
        """Clear local objects from the data layer."""
        self.skel_layer['segments'] = []
        self.mesh_layer['segments'] = []

    def open(self):
        """Open the Viewer in browser."""
        self.scene.open()


primary_viewer = None
