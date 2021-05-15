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

__all__ = ['ImageLayer', 'SegmentationLayer', 'AnnotationLayer', 'MeshLayer']


class BaseLayer:
    """Base class for layers."""

    MUST_HAVE = ['name']
    MUST_NOT_HAVE = []
    MUST_ONLY_HAVE = []

    # We need this to make sure that _properties always exists
    _properties = {}

    def __init__(self, **kwargs):
        self.__dict__['_properties'] = kwargs
        self.validate_properties()

    @property
    def properties(self):
        return self._properties

    @property
    def type(self):
        return self.__class__.__name__

    def __eq__(self, other):
        if type(other) != type(self):
            return False
        if self.properties != other.properties:
            return False
        return True

    def __str__(self):
        return f'<{self.type}(name={self.name}, source={self.properties["source"]})>'

    def __repr__(self):
        return self.__str__()

    def __setattr__(self, name, value):
        """Set a scene attribute."""
        self._properties[name] = value
        self.validate_properties()

    def __getattr__(self, name):
        """Get a scene property."""
        if name in self.__dict__:
            return self.__dict__.get(name)

        if name not in self._properties:
            raise AttributeError(f'"{name}" not in layer properties.')
        return self._properties[name]

    def __or__(self, other):
        if type(other) != type(self):
            raise TypeError(f'Unable to combine {type(other)} with {self.type}')
        raise NotImplementedError('Combination not implemented for {self.type}')

    def as_dict(self):
        """Return dictionary describing this layer."""
        return self.properties

    def validate_properties(self):
        """Check properties for missing/forbidden values."""
        if self.MUST_ONLY_HAVE:
            for v in self.properties:
                if v not in self.MUST_ONLY_HAVE:
                    raise ValueError(f'{self.type} must not have a "{v}" property')
        for v in self.MUST_HAVE:
            if v not in self.properties:
                raise ValueError(f'{self.type} requires a "{v}" property')
        for v in self.MUST_NOT_HAVE:
            if v in self.properties:
                raise ValueError(f'{self.type} must not have a "{v}" property')


class ImageLayer(BaseLayer):
    """Image layer."""

    DEFAULTS = {'type': 'image',
                'blend': 'default',
                'shaderControls': {},
                'name': 'img'}
    MUST_HAVE = ['name', 'source']

    def __init__(self, source, **kwargs):
        props = copy.deepcopy(self.DEFAULTS)
        props['source'] = source
        props.update(**kwargs)
        super().__init__(**props)

    def __or__(self, other):
        if type(other) != type(self):
            raise TypeError(f'Unable to combine {type(other)} with {self.type}')
        if self.source != other.source:
            raise ValueError('Unable to combine image layers with '
                             'different sources')
        x = copy.deepcopy(self)
        x.properties.update(other.properties)
        return x


class SegmentationLayer(BaseLayer):
    """Segmentaion layer."""

    DEFAULTS = {'type': 'segmentation_with_graph',
                'selectedAlpha': 0.14,
                'segments': [],
                'skeletonRendering': {'mode2d': 'lines_and_points', 'mode3d': 'lines'},
                'graphOperationMarker': [{'annotations': [], 'tags': []},
                                         {'annotations': [], 'tags': []}],
                'pathFinder': {'color': '#ffff00',
                               'pathObject': {'annotationPath': {'annotations': [], 'tags': []},
                                              'hasPath': False}
                               },
                'name': 'segmentation'}
    MUST_HAVE = ['name', 'source']

    def __init__(self, source, **kwargs):
        props = copy.deepcopy(self.DEFAULTS)
        props['source'] = source
        props.update(**kwargs)
        super().__init__(**props)

    def __or__(self, other):
        if type(other) != type(self):
            raise TypeError(f'Unable to combine {type(other)} with {self.type}')
        if self.source != other.source:
            raise ValueError('Unable to combine segmentation layers with '
                             'different sources')
        x = copy.deepcopy(self)
        # Combine selected segments
        x.segments = list(set(x.segments + other.segments))
        return x

    def __str__(self):
        source = self.source
        if isinstance(source, dict):
            source = source.get('url', source)

        return f'<{self.type}(name={self.name}, source={source}, selected segments={len(self.segments)})>'


class AnnotationLayer(BaseLayer):
    """Annotation layer."""

    DEFAULTS = {'type': 'annotation',
                'name': 'annotations'}
    MUST_HAVE = ['name', 'source']

    def __init__(self, source, **kwargs):
        props = copy.deepcopy(self.DEFAULTS)
        props['source'] = source
        props.update(**kwargs)
        super().__init__(**props)


class MeshLayer(BaseLayer):
    """Mesh layer."""

    DEFAULTS = {'type': 'mesh',
                'name': 'meshes'}
    MUST_HAVE = ['name', 'source']

    def __init__(self, source, **kwargs):
        props = copy.deepcopy(self.DEFAULTS)
        props['source'] = source
        props.update(**kwargs)
        super().__init__(**props)
