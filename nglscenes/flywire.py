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

from .layers import MeshLayer
from .utils import to_precomputed_mesh
from .serve import server

vol = None

__all__ = ['LocalFlywireMeshLayer']


class LocalFlywireMeshLayer(MeshLayer):
    """A layer for FlyWire meshes.

    This layer works like a bypass between the FlyWire mesh storage and the
    precomputed format neuroglancer expects. It uses cloudvolume and requires
    you to have your cave/chunked-graph secret set properly.

    """

    def __init__(self, **kwargs):
        # Lazy initialization of volume
        global vol
        if not vol:
            vol = cv.CloudVolume('graphene://https://prodv1.flywire-daf.com/segmentation/table/fly_v31',
                                 use_https=True,
                                 progress=False)

        # Setup server
        self.server = server
        if 'flywire' not in self.server.sources:
            self.server.register_source(name='flywire',
                                        data=flywire_data,
                                        manifest={'@type': 'neuroglancer_legacy_mesh',
                                                  'scales': [1, 1, 1]})
        self.server.start()

        DEFAULTS = dict(name='flywire-meshes', type='segmentation')
        DEFAULTS.update(kwargs)

        super().__init__(source='precomputed://http://127.0.0.1:5000/flywire',
                         **DEFAULTS)


def flywire_data(id):
    """Fetch FlyWire meshes."""
    global cache
    # If has ':0' suffix we return the fragments
    if id.endswith(':0'):
        id = id.split(':')[0]
        level = vol.mesh.meta.meta.decode_layer_id(id)
        # manifest is dict of {'fragments': ['path1', 'path2', ...]}
        mf = vol.mesh.fetch_manifest(id, level=level)

        # When we fetch the manifest, we will also directly fetch the fragments
        # in anticipation of the next request
        frags = vol.mesh._get_mesh_fragments(mf['fragments'])
        for fname, frag in frags:
            mesh = cv.Mesh.from_draco(frag)
            cache[fname.split('/')[1]] = to_precomputed_mesh(mesh.vertices, mesh.faces)

        return flask.jsonify(mf)
    # If actual segment ID, return this segment
    else:
        # We really should have this cached but just in case will keep
        # the download as backup
        if id in cache:
            return cache.pop(id)
        # Fetch the fragment (DracoEncode)
        frag = vol.mesh._get_mesh_fragments([id])[0][1]
        mesh = cv.Mesh.from_draco(frag)

        # Produce and return precomputed format
        return to_precomputed_mesh(mesh.vertices, mesh.faces)


cache = {}
