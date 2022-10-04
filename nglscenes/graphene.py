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

import flask

import cloudvolume as cv

from functools import partial
from neuroglancer import credentials_provider
from neuroglancer.futures import run_on_new_thread
from neuroglancer.default_credentials_manager import default_credentials_manager

from .layers import MeshLayer, SegmentationLayer
from .utils import to_precomputed_mesh
from .serve import server

__all__ = ['FlyWireSegmentationLayer', 'LocalFancMeshLayer']

_global_flywire_credentials_provider = None


class FlyWireCredentialsProvider(credentials_provider.CredentialsProvider):
    domain = 'prod.flywire-daf.com'
    def __init__(self):
        super(FlyWireCredentialsProvider, self).__init__()

        self._credentials = {}
        self._credentials['token'] = cv.secrets.cave_credentials(self.domain).get('token', None)

        if not self._credentials['token']:
            raise ValueError(f'No cave credentials for domain {self.domain} '
                             'found. See cloud-volume for details on how to set it.')

    def get_new(self):
        def func():
            return dict(tokenType=u'Bearer', accessToken=self._credentials['token'])

        return run_on_new_thread(func)


def get_flywire_credentials_provider():
    """Copy pasted from neuroglancer."""
    global _global_flywire_credentials_provider
    if _global_flywire_credentials_provider is None:
        _global_flywire_credentials_provider = FlyWireCredentialsProvider()
    return _global_flywire_credentials_provider


# Register authentication
default_credentials_manager.register(
     u'middleauthapp',
     lambda _parameters: get_flywire_credentials_provider())


class FlyWireSegmentationLayer(SegmentationLayer):
    def __init__(self, name='flywire_production', **kwargs):
        kwargs['source'] = 'graphene://middleauth+https://prod.flywire-daf.com/segmentation/1.0/fly_v31'
        super().__init__(name=name, **kwargs)


class LocalFancMeshLayer(MeshLayer):
    """A layer for FANC meshes.

    This layer works like a bypass between the FANC mesh storage and the
    precomputed format neuroglancer expects. It uses cloudvolume and requires
    you to have your cave/chunked-graph secret set properly.

    """

    def __init__(self, parallel=5, cache=False, **kwargs):
        # Lazy initialization of volume
        url = 'graphene://https://cave.fanc-fly.com/segmentation/table/mar2021_prod'
        vol = cv.CloudVolume(url,
                             use_https=True,
                             parallel=parallel,
                             cache=cache,
                             progress=False)

        # Setup server
        self.server = server
        if 'fanc' not in self.server.sources:
            self.server.register_source(name='fanc',
                                        data=partial(fetch_data, vol=vol),
                                        manifest={'@type': 'neuroglancer_legacy_mesh',
                                                  'scales': [1, 1, 1]})
        self.server.start()

        DEFAULTS = dict(name='fanc-meshes', type='segmentation')
        DEFAULTS.update(kwargs)

        super().__init__(source=f'precomputed://{self.server.url}/fanc',
                         **DEFAULTS)


def fetch_data(id, vol):
    """Fetch FlyWire meshes."""
    global cache

    is_sharded = isinstance(vol.mesh,
                            cv.datasource.graphene.mesh.GrapheneShardedMeshSource)

    # If has ':0' suffix we return the fragments
    if id.endswith(':0'):
        id = id.split(':')[0]
        level = vol.mesh.meta.meta.decode_layer_id(id)
        # manifest is dict of {'fragments': ['path1', 'path2', ...]}
        mf = vol.mesh.fetch_manifest(id, level=level)

        # When we fetch the manifest, we will also directly fetch the fragments
        # in anticipation of the next request
        if not is_sharded:
            frags = vol.mesh._get_mesh_fragments(mf['fragments'])

            for fname, frag in frags:
                mesh = cv.Mesh.from_draco(frag)
                cache[fname.split('/')[1]] = to_precomputed_mesh(mesh.vertices, mesh.faces)
        else:
            # For sharded meshes the process of fetching fragments is so much
            # more complicated that it's not worth trying to bypass fetching the
            # manifest a second time
            frags = vol.mesh.get_meshes_via_manifest_byte_offsets(id,
                                                                  bounding_box=None)

            for fname, mesh in zip(mf['fragments'], frags):
                cache[fname] = to_precomputed_mesh(mesh.vertices, mesh.faces)

        return flask.jsonify(mf)
    # If actual segment ID, return this segment
    else:
        # We really should have this cached but just in case will keep
        # the download as backup
        if id in cache:
            return cache[id]

        mesh = vol.mesh.get(id)

        # Produce and return precomputed format
        return to_precomputed_mesh(mesh.vertices, mesh.faces)


cache = {}
