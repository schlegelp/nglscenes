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
import logging
import uuid

import numpy as np

from collections import OrderedDict

from .scenes import Scene, parse_layers
from .layers import BaseLayer
from .utils import (add_on_change_callback, remove_callback,
                    find_name, parse_json_scene, import_optional)

logger = logging.getLogger(__name__)

__all__ = ['LocalScene', 'LocalSkeletonLayer', 'LocalMeshLayer',
           'LocalAnnotationLayer', 'BundleUpdates']


def __getattr__(name):
    # The source classes subclass neuroglancer classes, so they live in a
    # separate module that is only imported when needed
    if name in ('LocalMeshSource', 'LocalSkeletonSource'):
        from . import _sources
        return getattr(_sources, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _xyz_dimensions(units, scales):
    """Return neuroglancer x/y/z coordinate space."""
    neuroglancer = import_optional('neuroglancer')
    return neuroglancer.CoordinateSpace(names=['x', 'y', 'z'],
                                        units=units,
                                        scales=scales)


class LocalMeshLayer(BaseLayer):
    """A local data layer for a single mesh.

    This will only work with LocalScenes.

    Parameters
    ----------
    source :        str | callable
                    Either a directory or zip file containing SWC files, or a
                    function that accepts and ID and returns a neuroglancer
                    Mesh.
    units,scales :  str, list of int
                    Units and scale the skeletons are in.
    **kwargs
                    Additional properties for the layer.

    """

    DEFAULTS = OrderedDict({'source': '',
                            'type': 'mesh',
                            'name': 'mesh'})
    MUST_HAVE = ['name', 'source']

    NG_LAYER = "SegmentationLayer"

    def __init__(self, source, units='nm', scales=[1, 1, 1], **kwargs):
        self.dimensions = _xyz_dimensions(units, scales)
        props = copy.deepcopy(self.DEFAULTS)
        from ._sources import LocalMeshSource
        props['source'] = LocalMeshSource(source, self.dimensions)
        props.update(**kwargs)
        super().__init__(**props)


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

    NG_LAYER = "SegmentationLayer"

    def __init__(self, source, units='nm', scales=[1, 1, 1], **kwargs):
        self.dimensions = _xyz_dimensions(units, scales)

        props = copy.deepcopy(self.DEFAULTS)
        from ._sources import LocalSkeletonSource
        props['source'] = LocalSkeletonSource(source, self.dimensions)
        props.update(**kwargs)
        super().__init__(**props)

    def push_state(self, on_error='raise'):
        """Push state to neuroglancer viewer."""
        if self._lock:
            logger.debug('Pushing state aborted: Layer locked')
            return

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


class LocalAnnotationLayer(BaseLayer):
    """Local annotation layer."""

    DEFAULTS = OrderedDict({'source': {'url': 'local://annotations'},
                            'type': 'annotation',
                            'name': 'annotations'})
    MUST_HAVE = ['name']

    NG_LAYER = "AnnotationLayer"

    def __init__(self, units='nm', scales=[1, 1, 1], **kwargs):
        self.dimensions = _xyz_dimensions(units, scales)
        props = copy.deepcopy(self.DEFAULTS)
        props.update(**kwargs)
        props['source']['transform'] = dict(outputDimensions=self.dimensions.to_json())
        super().__init__(**props)

    def __str__(self):
        return f'<{self.type}(name={self.name}, annotations={len(self.get("annotations", []))})>'

    def add_points(self, coords, ids=None):
        """Add points.

        Parameters
        ----------
        coords :    (N, 3) array
        ids :       (N, ) array, optional

        """
        coords = np.asarray(coords)

        if not coords.ndim == 2 or coords.shape[1] != 3:
            raise ValueError(f'`coords` must be (N, 3) array, got {coords.shape}')

        if isinstance(ids, type(None)):
            ids = [str(uuid.uuid4()) for c in coords]

        if len(ids) != len(coords):
            raise ValueError(f'Got {len(ids)} ids for {len(coords)} coords')

        new_an = []
        for i, co in zip(ids, coords):
            an = {"point": co.tolist(),
                  "type": "point",
                  "id": i}
            new_an.append(an)

        if 'annotations' not in self:
            self['annotations'] = []
        self['annotations'] += new_an

    def clear(self):
        """Clear all annotations."""
        self['annotations'] = []


class CatmaidSkeletonLayer(LocalSkeletonLayer):
    pass


class LocalScene(Scene):
    """A scene served via and synced to a local neuroglancer server.

    Parameters
    ----------
    auto_sync :     bool
                    If True, will automatically push changes of the state to
                    the viewer. If False, you'll need to call `.push_state()`
                    for changes to make it to the viewer.

    """

    def __init__(self, auto_sync=True, **kwargs):
        self._auto_sync = auto_sync  # This needs to be set before super()
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
            neuroglancer = import_optional('neuroglancer')
            # Make sure neuroglancer can authenticate against graphene/DVID sources
            from . import credentials  # noqa: F401
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

        if self._auto_sync:
            value = add_on_change_callback(value, callback=set_stale_and_push)

        self._state = value

    @classmethod
    def from_url(cls, url):
        """Generate a local scene from a remote neuroglancer URL.

        Parameters
        ----------
        url :       str

        """
        state = parse_json_scene(url)
        layers = parse_layers(state.pop('layers', []))

        # Update properties
        scene = cls(**state)

        if layers:
            scene.add_layers(*layers)

        scene.push_state()

        return scene

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

    def add_local_skeletons(self, source, name=None, **kwargs):
        """Add a layer for a local skeleton source.

        Parameters
        ----------
        source :    str | callable
                    Either a directory or a zip file containing SWCs, or a
                    function that accepts an ID and returns a
                    `neuroglancer.Skeleton`.
        name :      str, optional
                    Name for the new layer. Must be unique.
        **kwargs
                    Additional properties for the layer.

        """
        name = find_name(name=name, scene=self, default='skeletons')

        # The new layer
        self.add_layers(LocalSkeletonLayer(source=source, name=name, **kwargs))

    def add_local_meshes(self, source, name=None, **kwargs):
        """Add a layer for a local mesh source.

        Parameters
        ----------
        source :    str | callable
                    Either a directory or a zip file containing meshes (anything
                    that trimesh can read), or a function that accepts an ID and
                    returns a `neuroglancer.Mesh`.
        name :      str, optional
                    Name for the new layer. Must be unique.
        **kwargs
                    Additional properties for the layer.

        """
        name = find_name(name=name, scene=self, default='meshes')

        # The new layer
        self.add_layers(LocalMeshLayer(source=source, name=name, **kwargs))

    def keybind_function(self, func, name, key):
        """Bind function to key.

        Parameters
        ----------
        func :      callable
                    The function to be called. Must accept the viewer state
                    as the only argument.
        name :      str
                    Name under which the function should be registered.
        key :       str
                    The key to which the function should be bound.

        """
        assert callable(func)
        assert isinstance(name, str)
        assert isinstance(key, str)

        self.viewer.actions.add(name, func)
        with self.viewer.config_state.txn() as s:
            s.input_event_bindings.viewer[f'key{key}'] = name

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

    def push_state(self, exclude_layers=True, ignore_lock=False, on_error='raise'):
        """Push state to neuroglancer viewer."""
        if self._lock and not ignore_lock:
            logger.debug('Pushing state aborted: Scene locked')
            return

        # Update state
        if exclude_layers:
            curr_state = self._state
        else:
            curr_state = self.as_dict()

        ConcurrentModificationError = import_optional(
            'neuroglancer.trackable_state').ConcurrentModificationError

        # Only overwrite the viewer state if it hasn't changed (e.g. in the
        # browser) since we read it - otherwise retry with the newer state
        for _ in range(10):
            state, generation = self.viewer.shared_state.raw_state_and_generation
            state = copy.deepcopy(state)
            state.update(remove_callback(curr_state))
            try:
                self.viewer.set_state(state, existing_generation=generation)
                break
            except ConcurrentModificationError:
                continue
        else:
            raise ConcurrentModificationError('Viewer state kept changing while pushing state.')
        #print('State pushed. Layers excluded = ', exclude_layers)
        logger.debug(f'State pushed from scene {self}: {curr_state}')

    def pull_state(self, exclude_layers=True, on_error='raise'):
        """Pull state from neuroglancer viewer."""
        if self._lock:
            logger.debug('Pulling state aborted: Scene locked')
            return

        with self.viewer.txn() as s:
            state = s.to_json()

            if exclude_layers:
                state.pop('layers', None)

            self._state.update(state)

        logger.debug(f'State pulled to scene {self}: {state}')

    def set_status_message(self, msg):
        """Set status message in bottom bar.

        Parameters
        ----------
        msg :       str | None
                    String to set the the status message. Use `None` to clear.

        """
        assert isinstance(msg, (str, type(None)))
        with self.viewer.config_state.txn() as s:
            if msg is not None:
                # We can set multiple status messages by using different keys
                # But for this method we'll just always use "status" which
                # means there can only ever be one
                s.status_messages['status'] = msg
            else:
                s.status_messages.clear()

    def screen_segments(self, segments, layer, N=1):
        """Start screening segments.

        Use `q` and `w` keys to cycle through segments.
        Use `d` key to tag the currently selected segment. Tagged segments can
        be found in `SegmentCycler.tagged` (see return value).

        Parameters
        ----------
        segments :  list of str
                    Segment IDs to screen.
        layer :     int | str
                    Index or layer of target layer.
        N :         int
                    The number of segments to show at a time.

        Returns
        -------
        cycler :    SegmentCycler
                    The object holding the segments, the current index and
                    the tagged segments.

        """
        assert isinstance(segments, (list, np.ndarray))
        assert isinstance(layer, (int, str))
        assert isinstance(N, int)
        assert N > 0
        assert len(segments)

        segments = sorted(np.asarray(segments).astype(str))

        cycler = SegmentCycler(segments, layer, self, N=N)

        self.keybind_function(cycler.next, 'next', 'w')
        self.keybind_function(cycler.previous, 'previous', 'q')
        self.keybind_function(cycler.tag, 'tag', 'd')

        with BundleUpdates(self):
            self.layers[layer]['segmentQuery'] = ','.join(segments)
            self.layers[layer]['segments'] = list(segments[0:N])

        return cycler


class SegmentCycler:
    """Helper class for cycling through selected segments."""
    def __init__(self, segments, layer, scene, N=1):
        self.segments = list(set(list(segments)))
        self.layer = layer
        self.scene = scene
        self.N = N
        self.ix = 0
        self.tagged = []

    def __str__(self):
        return f"{type(self)}(segments={len(self)}, current index={self.ix}, tagged={len(self.tagged)})"

    def __repr__(self):
        return self.__str__()

    def __len__(self):
        return len(self.segments)

    @property
    def _ix_str(self):
        if self.N == 1:
            return str(self.ix + 1)
        else:
            return f'{self.ix + 1}-{self.ix + 1 + self.N}'

    def next(self, _):
        self.ix += self.N
        if self.ix > (len(self.segments) - self.N):
            self.ix = 0

        self.scene.layers[self.layer]['segments'] = self.segments[self.ix:self.ix + self.N]
        self.scene.set_status_message(f'Screening ({self._ix_str} of {len(self.segments)})')

    def previous(self, _):
        self.ix -= self.N
        if self.ix < 0:
            self.ix = len(self.segments)

        self.scene.layers[self.layer]['segments'] = self.segments[self.ix:self.ix + self.N]
        self.scene.set_status_message(f'Screening ({self._ix_str} of {len(self.segments)})')

    def tag(self, _):
        seg = self.scene.layers[self.layer]['segments']
        self.tagged += seg
        self.scene.set_status_message(f'Tagged segment(s) "{seg}"')


class BundleUpdates:
    """Context manager delays pushing states until after exit.

    Can be useful if you are changing many values at a time and want to wait
    till you are done for pushing the changes to neuroglancer.
    """
    def __init__(self, scene):
        if not isinstance(scene, LocalScene):
            raise TypeError(f'Expected LocalScene, got {type(scene)}')
        self.scene = scene

    def __enter__(self):
        self.scene.pull_state()
        self.scene._lock = True
        #print('Locking')
        for l in self.scene.layers:
            l.pull_state()
            l._lock = True

    def __exit__(self, type, value, traceback):
        self.scene.push_state(exclude_layers=False, ignore_lock=True)

        #print('Unlocking')
        self.scene._lock = False
        for l in self.scene.layers:
            l._lock = False
