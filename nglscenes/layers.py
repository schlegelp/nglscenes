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
import neuroglancer

from abc import ABC
from collections import OrderedDict

from .utils import add_on_change_callback, remove_callback

__all__ = ['ImageLayer', 'SegmentationLayer', 'AnnotationLayer', 'MeshLayer']

logger = logging.getLogger(__name__)


class BaseLayer(ABC):
    """Abstract base class for layers."""

    # Defines required properties (at initialization)
    MUST_HAVE = ['name']
    MUST_NOT_HAVE = []
    MUST_ONLY_HAVE = []

    # This must be the corresponding layer in `neuroglancer`
    NG_LAYER = None

    # REMOVING THIS BREAKS COPYING
    _state = OrderedDict()

    def __init__(self, **kwargs):
        self._viewer = None
        self.state = kwargs
        self.validate_properties()

    def __init_layer__(self):
        return self.NG_LAYER(source=self['source'])

    @property
    def name(self):
        # This is the unique identifier for this layer
        return self._state['name']

    @property
    def state(self):
        # Sync with viewer if available
        if self._viewer:
            self.pull_state()
        return self._state

    @state.setter
    def state(self, value):
        if not isinstance(value, dict):
            raise TypeError('State must be a dictionary')
        if self._viewer:
            value = add_on_change_callback(value, callback=self.push_state)
        self._state = value

    @property
    def type(self):
        return self.__class__.__name__

    @property
    def viewer(self):
        return self._viewer

    def __eq__(self, other):
        if type(other) != type(self):
            return False
        if self.state != other.state:
            return False
        return True

    def __str__(self):
        return f'<{self.type}(name={self.name}, source={self.state["source"]})>'

    def __repr__(self):
        return self.__str__()

    def __getstate__(self):
        """Get state (used e.g. for pickling)."""
        state = dict(self.__dict__)

        # Set viewer to None if present
        if '_viewer' in state:
            state['_viewer'] = None
            state['_state'] = remove_callback(state['_state'])

        return state

    def __setstate__(self, d):
        """Set state (used e.g. for unpickling)."""
        # We have to implement this to make sure
        self.__dict__.clear()
        for k, v in d.items():
            self.__dict__[k] = v

    def __setitem__(self, name, value):
        """Set a layer attribute."""
        self._state[name] = value
        self._stale = True

    def __getitem__(self, name):
        """Get a layer property."""
        if name in self.state:
            return self.state[name]
        raise AttributeError(f'"{name}" not in state.')

    def __contains__(self, name):
        """Check if layer property exists."""
        if name in self.state:
            return True
        return False

    def __or__(self, other):
        if type(other) != type(self):
            raise NotImplementedError(f'Unable to combine {type(other)} with '
                                      f'{self.type}')
        raise NotImplementedError(f'Combination not implemented for {self.type}')


    def as_dict(self):
        """Return dictionary describing this layer."""
        return remove_callback(self.state)

    def copy(self):
        """Return copy."""
        return copy.deepcopy(self)

    def get(self, key, default=None):
        """Return the value for key if key is in the scene, else default."""
        return self.state.get(key, default)

    def link_viewer(self, viewer):
        """Link a neuroglancer viewer to this layer.

        Any changes to this layer will propagate to the viewer.
        """
        if not isinstance(viewer, neuroglancer.Viewer):
            raise TypeError(f'Expected neuroglancer.Viewer, got "{type(viewer)}"')

        # Inject self into viewer:
        with viewer.txn() as s:
            if self.name in s.layers:
                raise ValueError(f'Viewer already has a layer name "{self.name}"')
            s.layers[self.name] = self.__init_layer__()

        # Set viewer AFTER adding the layer
        self._viewer = viewer

        # Explicitly set state to add callback
        self.state = self._state

        # Push state to viewer
        self.push_state()

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

            # Update state
            state['layers'][ix[0]].update(self._state)

        self.viewer.set_state(state)

        logger.debug(f'State pushed from layer: {state}')

    def pull_state(self, on_error='raise'):
        """Pull state from neuroglancer viewer."""
        if not self.viewer:
            raise ValueError('Layer is not linked to a neuroglancer viewer.')

        with self.viewer.txn() as s:
            state = s.to_json()
            layer = [l for l in state.get('layers', []) if l.get('name', None) == self.name]
            if not layer:
                raise ValueError(f'Layer "{self.name}" not found in '
                                 'neuroglancer viewer.')
            elif len(layer) > 1:
                raise ValueError(f'Layer "{self.name}" duplicated.')
            self.state = layer[0]

        logger.debug(f'State pulled from layer: {state}')

    def validate_properties(self):
        """Check state for missing/forbidden values."""
        if self.MUST_ONLY_HAVE:
            for v in self._state:
                if v not in self.MUST_ONLY_HAVE:
                    raise ValueError(f'{self.type} must not have a "{v}" property')
        for v in self.MUST_HAVE:
            if v not in self._state:
                raise ValueError(f'{self.type} requires a "{v}" property')
        for v in self.MUST_NOT_HAVE:
            if v in self._state:
                raise ValueError(f'{self.type} must not have a "{v}" property')


class ImageLayer(BaseLayer):
    """Image layer."""

    DEFAULTS = OrderedDict({'source': '',
                            'type': 'image',
                            'blend': 'default',
                            'shaderControls': {},
                            'name': 'img'})
    MUST_HAVE = ['name', 'source']

    NG_LAYER = neuroglancer.ImageLayer

    def __init__(self, source, **kwargs):
        props = copy.deepcopy(self.DEFAULTS)
        props['source'] = source
        props.update(**kwargs)
        super().__init__(**props)

    def __or__(self, other):
        if type(other) != type(self):
            raise NotImplementedError(f'Unable to combine {type(other)} with '
                                      f'{self.type}')
        if self['source'] != other['source']:
            raise NotImplementedError('Unable to combine image layers with '
                                      'different sources')
        x = copy.deepcopy(self)
        x.state.update(other.state)
        return x


class SegmentationLayer(BaseLayer):
    """Segmentation layer."""

    DEFAULTS = OrderedDict({'source': '',
                            'type': 'segmentation',
                            'selectedAlpha': 0.14,
                            'segments': [],
                            'name': 'segmentation'})
    MUST_HAVE = ['name', 'source']

    NG_LAYER = neuroglancer.SegmentationLayer

    def __init__(self, source, **kwargs):
        props = copy.deepcopy(self.DEFAULTS)
        props['source'] = source
        props.update(**kwargs)
        super().__init__(**props)

    def __or__(self, other):
        if type(other) != type(self):
            raise NotImplementedError(f'Unable to combine {type(other)} with '
                                      f'{self.type}')
        if self['source'] != other['source']:
            raise NotImplementedError('Unable to combine segmentation layers '
                                      'with different sources')
        x = copy.deepcopy(self)
        # Combine selected segments
        x['segments'] = list(set(x['segments'] + other['segments']))
        return x

    def __str__(self):
        source = self['source']
        if isinstance(source, dict):
            source = source.get('url', source)

        return f'<{self.type}(name={self.name}, source={source}, selected segments={len(self["segments"])})>'


class AnnotationLayer(BaseLayer):
    """Annotation layer."""

    DEFAULTS = OrderedDict({'source': '',
                            'type': 'annotation',
                            'name': 'annotations'})
    MUST_HAVE = ['name', 'source']

    NG_LAYER = neuroglancer.AnnotationLayer

    def __init__(self, source, **kwargs):
        props = copy.deepcopy(self.DEFAULTS)
        props['source'] = source
        props.update(**kwargs)
        super().__init__(**props)


class MeshLayer(BaseLayer):
    """Mesh layer."""

    DEFAULTS = OrderedDict({'source': '',
                            'type': 'mesh',
                            'name': 'meshes'})
    MUST_HAVE = ['name', 'source']

    NG_LAYER = neuroglancer.SingleMeshLayer

    def __init__(self, source, **kwargs):
        props = copy.deepcopy(self.DEFAULTS)
        props['source'] = source
        props.update(**kwargs)
        super().__init__(**props)


class LayerManager:
    def __init__(self, scene):
        self.scene = scene

    def __str__(self):
        return f'LayerManager<{len(self)} layers>'

    def __repr__(self):
        lstr = "\n".join([str(l) for l in self.scene.layers])
        return f'LayerManager with {len(self)} layers:\n{lstr}'

    def __len__(self):
        return len(self.scene._layers)

    def __getitem__(self, layer):
        return self.get_layer(layer)

    def __setitem__(self, key, value):
        raise NotImplementedError('Please use Scene.add_layer layers.')

    def __iter__(self):
        """Iterator instanciates a new class every time it is called.
        This allows the use of nested loops on the same layer object.
        """
        class prange_iter:
            def __init__(self, layers, start):
                self.iter = start
                self.layers = layers

            def __next__(self):
                if self.iter >= len(self.layers):
                    raise StopIteration
                to_return = self.layers[self.iter]
                self.iter += 1
                return to_return

        return prange_iter(self.scene._layers, 0)

    def __contains__(self, layer):
        if not isinstance(layer, str):
            return False
        try:
            _ = self.get_layer(layer)
            return True
        except AttributeError:
            return False

    def get_layer(self, layer):
        if isinstance(layer, str):
            l = [l for l in self.scene._layers if l._state.get('name', None) == layer]
            if not l:
                raise AttributeError(f'No layer called "{layer}" found.')
            elif len(l) > 1:
                raise AttributeError(f'Multiple layers called "{layer}" found.')
            return l[0]
        elif isinstance(layer, int):
            return self.scene._layers[layer]
        else:
            raise AttributeError(f'Unable to index layers by "{type(layer)}"')
