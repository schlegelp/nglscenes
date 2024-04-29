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
import neuroglancer
import requests
import json

import numpy as np
import pandas as pd

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
        if isinstance(x, CallBackList):
            x = list(x)
    return x


def parse_json_scene(scene):
    """Parse string (either URL or a JSON) into a dictionary."""
    if isinstance(scene, dict):
        return scene

    if not isinstance(scene, str):
        raise ValueError(f'Expected str, got "{type(scene)}"')

    if is_url(scene):
        if is_state_url(scene):
            scene = parse_state_url(scene)
        else:
            scene = unquote(urlparse(scene).fragment)[1:]
            scene = json.loads(scene)

    return scene


def parse_state_url(x):
    """Fetch scene from a state server."""
    if "json_url" in x:
        parsed = urlparse(x)
        url = parsed.query.replace('json_url=', '')

        # FlyWire needs authentication
        headers = {}
        if urlparse(url).netloc == 'globalv1.flywire-daf.com':

            # Fetch state
            token = get_cave_credentials()
            headers['Authorization'] = f"Bearer {token}"

        r = requests.get(url, headers=headers)
        r.raise_for_status()
    # Parse URLs with a link to Google buckets
    elif '!gs://' in x:
        path = urlparse(x).fragment.replace('!gs://', '')
        r = requests.get(f'https://storage.googleapis.com/{path}')
        r.raise_for_status()
    else:
        raise ValueError(f'Unable to parse state from URL: {x}')

    return r.json()


def get_cave_credentials(domain='prod.flywire-daf.com'):
    """Get CAVE credentials.

    Parameters
    ----------
    domain :    str
                Domain to get the secret for. Only relevant for
                ``cloudvolume>=3.11.0``.

    Returns
    -------
    token :     str

    """
    # Lazy import
    import cloudvolume as cv

    token = cv.secrets.cave_credentials(domain).get('token', None)
    if not token:
        raise ValueError(f'No chunkedgraph secret for domain {domain} found')
    return token


def is_url(x):
    """Check if URL is valid."""
    try:
        result = urlparse(x)
        return all([result.scheme, result.netloc, result.path])
    except BaseException:
        return False

def is_state_url(x):
    """Check if URL points to a state server."""
    if not is_url(x):
        return False
    if ('json_url=http' in x) or ('!gs:// 'in x):
        return True
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


def to_precomputed_skeleton(vertices, edges, radius=None):
    """Write skeleton to neuroglancers binary format."""
    vertices = np.asarray(vertices, dtype='float32', order='C')
    edges = np.asarray(edges, dtype='uint32', order='C')
    vertex_index_format = [np.uint32(vertices.shape[0]),
                           np.uint32(edges.shape[0]),
                           vertices, edges]
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


def is_skeleton(x):
    """Test if object is skeleton-like."""
    if hasattr(x, 'vertices') and hasattr(x, 'edges'):
        return True
    elif hasattr(x, 'nodes'):
        return True
    elif 'Dotprops' in str(type(x)):
        return True
    return False


def parse_objects(x, raise_unknown=True):
    """Sort objects into skeleton, meshes and annotations.

    Parameters
    ----------
    x
                    Objects to sort.
    raise_unknown : bool
                    If True, an unknown object type will raise an exception.

    Returns
    -------
    meshes :        list
    skeletons :     list
    annotations :   list

    """
    if not is_iterable(x):
        x = [x]

    skeletons = []
    meshes = []
    annotations = []

    for o in x:
        if is_mesh(o):
            meshes.append(o)
        elif is_skeleton(o):
            skeletons.append(o)
        elif isinstance(o, np.ndarray) and (o.ndim == 2) and (o.shape[1] == 3):
            annotations.append(o)
        elif raise_unknown:
            raise TypeError(f'Unknown object type {type(o)}')

    return meshes, skeletons, annotations


def to_ng_skeleton(x):
    """Convert object to neuroglancer Skeleton.

    Parameters
    ----------
    x :     pd.DataFrame | navis.TreeNeuron | cloudvolume.Skeleton | navis.Dotprops

    Returns
    -------
    neuroglancer.Skeleton

    """
    if 'Dotprops' in str(type(x)):
        x = x.to_skeleton()

    if 'TreeNeuron' in str(type(x)):
        # Extract node table and make SWC-compliant
        x = x.nodes[['node_id', 'parent_id', 'x', 'y', 'z']].copy()
        x.columns = ['PointNo', 'Parent', 'X', 'Y', 'Z']

        node_ids = dict(zip(x.PointNo.values, range(0, len(x))))
        node_ids[-1] = -1
        x['PointNo'] = x.PointNo.map(node_ids)
        x['Parent'] = x.Parent.map(node_ids)

    if isinstance(x, pd.DataFrame):
        # Make sure points are in ascending order (should really already)
        x.sort_values('PointNo', inplace=True)

        # In case node IDs start at 1
        x['Parent'] -= x['PointNo'].min()
        x['PointNo'] -= x['PointNo'].min()

        vertices = x[['X', 'Y', 'Z']].values
        edges = x.loc[x.Parent >= 0, ['Parent', 'PointNo']].values
    elif hasattr(x, 'vertices') and hasattr(x, 'edges'):
        vertices, edges = x.vertices, x.edges
    else:
        raise TypeError(f'Unable to convert object of type "{type(x)}" to '
                        'neuroglancer skeleton.')

    return neuroglancer.skeleton.Skeleton(
                            vertex_positions=vertices,
                            edges=edges)


def is_iterable(x):
    """Check if object is iterable but not string."""
    if hasattr(x, '__contains__') and not isinstance(x, str):
        return True
    return False
