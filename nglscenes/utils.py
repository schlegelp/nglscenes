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
"""Collection of utility functions."""

import functools
import requests
import json

import numpy as np

from urllib.parse import urlparse, urlencode, unquote


class CallBackDict(dict):
    """A dictionary that executes a callback on change."""
    def __init__(self, callback, *args, **kwargs):
        assert callable(callback)
        self._callback = callback
        super().__init__(*args, **kwargs)

    def __setitem__(self, key, val):
        # Add callback to any container in `val` (including val itself)
        val = add_on_change_callback(val, self._callback, recursive=True)
        super().__setitem__(key, val)
        self._callback()

    @functools.wraps(dict.update)
    def update(self, *args, **kwargs):
        new_dict = dict(*args, **kwargs)
        new_dict = add_on_change_callback(new_dict, self._callback, recursive=True)
        super().update(**new_dict)
        self._callback()

    @functools.wraps(dict.pop)
    def pop(self, *args, **kwargs):
        super().pop(*args, **kwargs)
        self._callback()

    @functools.wraps(dict.clear)
    def clear(self, *args, **kwargs):
        super().clear(*args, **kwargs)
        self._callback()


class CallBackList(list):
    """A list that executes a callback on change."""
    def __init__(self, callback, *args, **kwargs):
        assert callable(callback)
        self._callback = callback
        super().__init__(*args, **kwargs)

    def __setitem__(self, key, val):
        # Add callback to any container in `val` (including val itself)
        val = add_on_change_callback(val, self._callback, recursive=True)
        super().__setitem__(key, val)
        self._callback()

    @functools.wraps(list.append)
    def append(self, object):
        object = add_on_change_callback(object, self._callback, recursive=True)
        super().append(object)
        self._callback()

    @functools.wraps(list.pop)
    def pop(self, index=-1):
        super().pop(index)
        self._callback()

    @functools.wraps(list.extend)
    def extend(self, iterable):
        iterable = add_on_change_callback(iterable, self._callback, recursive=True)
        super().extend(iterable)
        self._callback()

    @functools.wraps(list.sort)
    def sort(self, *, key=None, reverse=False):
        super().sort(key=None, reverse=False)
        self._callback()

    @functools.wraps(list.insert)
    def insert(self, index, object):
        object = add_on_change_callback(object, self._callback, recursive=True)
        super().insert(index, object)
        self._callback()

    @functools.wraps(list.remove)
    def remove(self, value):
        super().remove(value)
        self._callback()


def add_on_change_callback(x, callback, recursive=True):
    """Adds callback to object.

    Converts containers (currrently list dict and dicts) to CallBack{TYPE} and
    adds callback.

    Parameters
    ----------
    x :         list | dict
    callback :  callable
                The callback function. Will be called without arguments.
    recursive : bool
                If True, will recursively convert the input.

    Returns
    -------
    dict | list

    """
    if isinstance(x, dict):
        if recursive:
            x = {k: add_on_change_callback(v, callback, True) for k, v in x.items()}
        if not isinstance(x, CallBackDict):
            x = CallBackDict(callback, **x)
    elif isinstance(x, list):
        if recursive:
            x = [add_on_change_callback(v, callback, True) for v in x]
        if not isinstance(x, CallBackList):
            x = CallBackList(callback, x)
    return x


def remove_callback(x, recursive=True):
    """Remove callback from object.

    Parameters
    ----------
    x :         list | dict
    recursive : bool
                If True, will recursively convert the input.

    Returns
    -------
    dict | list

    """
    if isinstance(x, dict):
        if recursive:
            x = {k: remove_callback(v, True) for k, v in x.items()}
        if isinstance(x, CallBackDict):
            x = dict(**x)
    elif isinstance(x, list):
        if recursive:
            x = [remove_callback(v, True) for v in x]
        if not isinstance(x, CallBackList):
            x = list(x)
    return x


def parse_json_scene(scene):
    """Parse string (either URL or a JSON) into a dictionary."""
    if not isinstance(scene, str):
        raise ValueError(f'Expected str, got "{type(scene)}"')

    if is_url(scene):
        scene = unquote(urlparse(scene).fragment)[1:]

    return json.loads(scene)


def is_url(x):
    """Check if URL is valid."""
    try:
        result = urlparse(x)
        return all([result.scheme, result.netloc, result.path])
    except BaseException:
        return False


def make_url(*args, **GET):
    """Generate URL.

    Parameters
    ----------
    *args
                Will be turned into the URL. For example::

                    >>> make_url('http://my-server.com', 'skeleton', 'list')
                    'http://my-server.com/skeleton/list'

    **GET
                Keyword arguments are assumed to be GET request queries
                and will be encoded in the url. For example::

                    >>> make_url('http://my-server.com', 'skeleton', node_gt: 100)
                    'http://my-server.com/skeleton?node_gt=100'

    Returns
    -------
    url :       str

    """
    # Generate the URL
    url = args[0]
    for arg in args[1:]:
        arg_str = str(arg)
        joiner = '' if url.endswith('/') else '/'
        relative = arg_str[1:] if arg_str.startswith('/') else arg_str
        url = requests.compat.urljoin(url + joiner, relative)
    if GET:
        url += '?{}'.format(urlencode(GET))
    return url


def to_precomputed_mesh(vertices, faces):
    """Convert mesh to precomputed format.

    Parameters
    ----------
    vertices :      (N, 3) list-like
    faces :         (M, 3) list-like

    Returns
    -------
    str
                    Bytes string.

    """
    vertices = np.asarray(vertices, dtype='float32')
    faces = np.asarray(faces, dtype='uint32')
    vertex_index_format = [np.uint32(vertices.shape[0]),
                           vertices, faces]

    return b''.join([array.tobytes('C') for array in vertex_index_format])


def find_name(name, scene, default):
    """Find a name that's not already in the scene."""
    if not name:
        name = default

    i = 1
    while name in scene.layers:
        name = f'skeletons{i}'
        i += 1

    return name


def is_mesh(x):
    """Test if object is mesh-like."""
    if hasattr(x, 'vertices') and hasattr(x, 'faces'):
        return True
    return False


def is_iterable(x):
    """Check if object is iterable but not string."""
    if hasattr(x, '__contains__') and not isinstance(x, str):
        return True
    return False
