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
import json
import pyperclip
import webbrowser

from urllib.parse import quote, urldefrag

from . layers import (ImageLayer, SegmentationLayer, AnnotationLayer,
                      MeshLayer, BaseLayer)
from . import utils


__all__ = ['NeuroGlancerScene']


class NeuroGlancerScene:
    """A NeuroGlancer scene.

    Parameters
    ----------
    base_url :      str
                    The URL to the neuroglancer instance.

    """

    _properties = {}

    def __init__(self, base_url='https://neuroglancer-demo.appspot.com/'):
        self.__dict__['base_url'] = base_url
        self.__dict__['_layers'] = []
        self.__dict__['_properties'] = {}
        self.__dict__['_stale'] = True
        self.__dict__['_url'] = ''

    @property
    def layers(self):
        """Layers present."""
        return self._layers

    @layers.setter
    def layers(self):
        raise AttributeError('Please use `.add_layers()` to edit the layers.')

    @property
    def properties(self):
        return self._properties

    @property
    def type(self):
        return self.__class__.__name__

    @property
    def url(self):
        """Url to self."""
        if self._stale:
            self._url = self.make_url()
        return self._url

    def __add__(self, other):
        if not isinstance(other, NeuroGlancerScene):
            raise NotImplementedError(f'Unable to combine {type(other)} with '
                                      f'{self.type}')
        x = copy.deepcopy(self)
        x.layers += copy.deepcopy(other.layers)
        return x

    def __or__(self, other):
        if not isinstance(other, NeuroGlancerScene):
            raise NotImplementedError(f'Unable to merge {type(other)} with '
                                      f'{self.type}')

        x = copy.deepcopy(self)
        for l1 in copy.deepcopy(other.layers):
            merged = False
            for l2 in x.layers:
                if isinstance(l1, type(l2)):
                    try:
                        l2 |= l1
                        merged = True
                        break
                    except BaseException:
                        pass
            if not merged:
                x.add_layers(l1)

        return x

    def __eq__(self, other):
        if type(other) != type(self):
            return False
        if self.properties != other.properties:
            return False
        return True

    def __setattr__(self, name, value):
        """Set a scene attribute."""
        self._properties[name] = value
        self.__dict__['_stale'] = True

    def __getattr__(self, name):
        if name in self.__dict__:
            return self.__dict__.get(name)

        """Get a scene property."""
        if name not in self._properties:
            raise AttributeError(f'"{name}" not in scene properties.')
        return self._properties[name]

    def __len__(self):
        return len(self.layers)

    def __str__(self):
        layer_str = []
        for lt, ty in LAYER_FACTORY.items():
            this = [l for l in self.layers if isinstance(l, ty)]
            layer_str.append(f'{len(this)} {lt}')
        return f'<{self.type}({", ".join(layer_str)})>\n\n{self.url}'

    def __repr__(self):
        return self.__str__()

    @classmethod
    def from_clipboard(cls):
        """Generate scene from either a JSON or URL."""
        # Read clipboard
        scene = pyperclip.paste()

        return cls.from_string(scene)

    @classmethod
    def from_string(cls, scene):
        """Generate scene from either a JSON or URL."""
        # Extract json
        properties = utils.parse_json_scene(scene)

        # If input is URL, reuse the base URL
        if utils.is_url(scene):
            url, frag = urldefrag(scene)
            x = cls(url)
        else:
            x = cls()

        layers = parse_layers(properties.pop('layers'))

        # Update properties
        x.properties.update(properties)

        if layers:
            x.add_layers(*layers)

        return x

    def add_layers(self, *layers):
        """Add layer to scene.

        Parameters
        ----------
        *layers
                    The layer(s) to add.

        """
        for l in layers:
            if not isinstance(l, BaseLayer):
                raise TypeError(f'Expected Layer, got {type(l)}')

            self._layers.append(l)
            self.__dict__['_stale'] = True

    def drop_layer(self, which):
        """Remove layer from scene.

        Parameters
        ----------
        which :     str | int
                    Either index (int) or name (str) of layer to drop.

        """
        self.__dict__['_stale'] = True
        if isinstance(which, str):
            names = [getattr(l, 'name', None) for l in self.layers]
            if which not in names:
                raise ValueError(f'No layer named "{which}".')
            self._layers.pop(names.index(which))
        elif isinstance(which, int):
            if len(self.layers) < (which + 1):
                raise ValueError(f'Unable to drop layer {which}: only '
                                 f'{len(self.layers)} present.')
            self._layers.pop(which)
        else:
            raise TypeError(f'Expected str or int, got {type(which)}')

    def make_json(self, pretty=False):
        """Generate the JSON-formatted string describing the scene."""
        props = self.properties
        props['layers'] = [l.as_dict() for l in self.layers]

        return json.dumps(props,
                          indent=4 if pretty else None,
                          sort_keys=True,
                          ).replace("'", '"'
                                    ).replace("True", "true"
                                              ).replace("False", "false")

    def make_url(self):
        """Generate/Update URL."""
        scene_str = self.make_json(pretty=False)
        self.__dict__['_url'] = utils.make_url(self.base_url, f'#!{quote(scene_str)}')
        self.__dict__['_stale'] = False
        return self._url

    def open(self, new_window=False):
        """Open URL in webbrowser."""
        try:
            wb = webbrowser.get('chrome')
        except BaseException:
            wb = webbrowser

        if new_window:
            wb.open_new(self.url)
        else:
            wb.open_new_tab(self.url)

    def to_clipboard(self, scene_only=False):
        """Copy URL to clipboard."""
        if scene_only:
            pyperclip.copy(self.make_json(pretty=True))
            print('Scene copied to clipboard.')
        else:
            pyperclip.copy(self.url)
            print('URL copied to clipboard.')


LAYER_FACTORY = {
    'segmentation': SegmentationLayer,
    'mesh': MeshLayer,
    'image': ImageLayer,
    'annotation': AnnotationLayer
}


def parse_layers(layer, skip_unknown=False):
    if isinstance(layer, list):
        res = [parse_layers(l) for l in layer]
        # Drop "None" if skip_unknown=True
        return [l for l in res if l]

    if not isinstance(layer, dict):
        raise TypeError(f'Expected dicts or list thereof, got "{type(layer)}"')

    ty = layer.get('type', 'NA')
    if ty not in LAYER_FACTORY:
        if skip_unknown:
            return
        raise ValueError(f'Unable to parse layer of type {ty}')

    return LAYER_FACTORY[ty](**layer)
