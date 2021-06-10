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

import copy
import neuroglancer
import logging
import io

import pandas as pd

from collections import OrderedDict
from pathlib import Path
from zipfile import ZipFile

from .scenes import Scene
from .layers import BaseLayer
from .utils import add_on_change_callback, remove_callback

logger = logging.getLogger(__name__)

__all__ = ['LocalScene', 'LocalSkeletonLayer']


class LocalSkeletonLayer(BaseLayer):
    """A local data layer for skeletons.

    This will only work with LocalScenes.

    Parameters
    ----------
    source :        str | callable
                    Either a directory or zip file containing SWC files, or a
                    function that accepts and ID and returns a neuroglancer
                    Skeleton.
    units,scales :  str, list of int
                    Units and scale the skeletons are in.
    **kwargs
                    Additional properties for the layer.

    """

    DEFAULTS = OrderedDict({'source': '',
                            'type': 'segmentation',
                            'name': 'skeletons'})
    MUST_HAVE = ['name', 'source']

    NG_LAYER = neuroglancer.SegmentationLayer

    def __init__(self, source, units='nm', scales=[1, 1, 1], **kwargs):
        self.dimensions = neuroglancer.CoordinateSpace(names=['x', 'y', 'z'],
                                                       units=units,
                                                       scales=scales)

        props = copy.deepcopy(self.DEFAULTS)
        props['source'] = LocalSkeletonSource(source, self.dimensions)
        props.update(**kwargs)
        super().__init__(**props)

    def push_state(self, on_error='raise'):
        """Push state to neuroglancer viewer."""
        if not self.viewer:
            raise ValueError('Layer is not linked to a neuroglancer viewer.')

        with self.viewer.txn() as s:
            state = s.to_json()
            ix = [i for i, l in enumerate(state.get('layers', [])) if l.get('name', None) == self.name]
            if not ix:
                raise ValueError(f'Layer "{self.name}" not found in '
                                 'neuroglancer viewer.')
            elif len(ix) > 1:
                raise ValueError(f'Layer "{self.name}" duplicated.')

            # Update states
            this_state = {k: v for k, v in self._state.items() if k not in ['source']}
            state['layers'][ix[0]].update(this_state)

        self.viewer.set_state(state)

        logger.debug(f'State pushed from layer: {state}')


class LocalSkeletonSource(neuroglancer.skeleton.SkeletonSource):
    """A local skeleton source."""

    def __init__(self, source, dimensions):
        if callable(source):
            pass
        else:
            source = Path(source)
            if source.is_file():
                if not source.name.endswith('.zip'):
                    raise ValueError(f'Invalid skeleton source: {source}')
            elif not source.is_dir():
                raise ValueError(f'Invalid skeleton source: {source}')

        super().__init__(dimensions)
        self.source = source

    def get_skeleton(self, id):
        if callable(self.source):
            return self.source(id)
        elif self.source.name.endswith('.zip'):
            return self.read_from_zip(f'{id}.swc')
        else:
            return self.read_from_swc(self.source / f'{id}.swc')

    def read_from_zip(self, file):
        """Read skeleton from SWC file inside a ZIP archive.

        Parameters
        ----------
        file :      str

        Returns
        -------
        neuroglancer.Skeleton

        """
        with ZipFile(self.source, 'r') as zip:
            if file not in zip.namelist():
                print(f'File {file} not found in zip.')
                return None
            return self.read_from_swc(io.StringIO(zip.read(file).decode()))

    def read_from_swc(self, file):
        """Read skeleton from SWC file (or buffer).

        Parameters
        ----------
        file :      str

        Returns
        -------
        neuroglancer.Skeleton

        """
        if isinstance(file, io.StringIO):
            if isinstance(file.read(0), bytes):
                file = io.TextIOWrapper(file, encoding="utf-8")
        elif not (self.source / file).is_file():
            return None

        swc = pd.read_csv(file,
                          delimiter=' ',
                          skipinitialspace=True,
                          comment='#',
                          header=None)

        swc.columns = ['PointNo', 'Label', 'X', 'Y', 'Z', 'Radius', 'Parent']

        # Make sure points are in ascending order (should really already)
        swc.sort_values('PointNo', inplace=True)

        # In case node IDs start at 1
        swc['Parent'] -= swc['PointNo'].min()
        swc['PointNo'] -= swc['PointNo'].min()

        return neuroglancer.skeleton.Skeleton(
                                vertex_positions=swc[['X', 'Y', 'Z']].values,
                                edges=swc.loc[swc.Parent >= 0,
                                              ['Parent', 'PointNo']].values)


class LocalScene(Scene):
    """A scene served via and synced to a local neuroglancer server."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        del self._url
        self._viewer = None
        self._lock = False

    def __setstate__(self, d):
        super().__setstate__(d)

        # During pickling/copying the viewer is ditched and all layers are
        # therefore unlinked. Let's link them again
        for l in self._layers:
            l.link_viewer(self.viewer)

    @property
    def url(self):
        """URL to local neuroglancer server."""
        return str(self.viewer)

    @property
    def viewer(self):
        """Viewer instance for local neuroglancer server."""
        # Viewer will be spawned on first request
        if not self._viewer:
            self._viewer = neuroglancer.Viewer()
        return self._viewer

    @property
    def state(self):
        # Update state
        self.pull_state()
        return self._state

    @state.setter
    def state(self, value):
        def set_stale_and_push():
            self._stale = True
            self.push_state()

        if not isinstance(value, dict):
            raise TypeError('State must be a dictionary')
        value = add_on_change_callback(value, callback=set_stale_and_push)
        self._state = value

    def add_layers(self, *layers):
        """Add layer to scene.

        Parameters
        ----------
        *layers
                    The layer(s) to add.

        """
        # Make sure layers are not linked to anything
        for l in layers:
            l._viewer = None
        super().add_layers(*layers)
        for l in layers:
            # Link layer to viewer
            # The layer then takes care of the syncing
            l.link_viewer(self.viewer)

    def drop_layer(self, which):
        """Remove layer from scene.

        Parameters
        ----------
        which :     str | int
                    Either index (int) or name (str) of layer to drop.

        """
        # Drop the layer using the parent class' method
        layer = super().drop_layer(which)

        # Do the clean-up by updating the state
        with self.viewer.txn() as s:
            state = s.to_json()
            state['layers'] = [l for l in state['layers'] if l['name'] != layer.name]

        self.viewer.set_state(state)

        return layer

    def push_state(self, exclude_layers=True, on_error='raise'):
        """Push state to neuroglancer viewer."""
        with self.viewer.txn() as s:
            state = s.to_json()

        # Update state
        if exclude_layers:
            curr_state = self._state
        else:
            curr_state = self.as_dict()

        state.update(remove_callback(curr_state))

        self.viewer.set_state(state)
        logger.debug(f'State pushed from scene {self}: {curr_state}')

    def pull_state(self, exclude_layers=True, on_error='raise'):
        """Pull state from neuroglancer viewer."""
        with self.viewer.txn() as s:
            state = s.to_json()

            if exclude_layers:
                state.pop('layers', None)

            self._state.update(state)

        logger.debug(f'State pulled to scene {self}: {state}')


class BundleUpdate:
    """Context manager that prevents update of a given scene.

    Can be useful if you are changing many values at a time and want to wait
    till you are done for pushing the changes to neuroglancer.
    """
    def __init__(self, scene):
        if not isinstance(scene, LocalScene):
            raise TypeError(f'Expected LocalScene, got {type(scene)}')
        self.scene = scene

    def __enter__(self):
        self.scene._lock = True
        for l in self.scene.layers:
            l._lock = True

    def __exit__(self):
        self.scene._lock = False
        for l in self.scene.layers:
            l._lock = False
        self.scene.push_state()
