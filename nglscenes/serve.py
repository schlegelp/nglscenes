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
import flask
import logging
import threading
import socket
import json
import uuid

from werkzeug.serving import make_server
from flask_cors import CORS
from collections import namedtuple, OrderedDict

from .utils import (is_iterable, is_mesh, is_skeleton,
                    to_precomputed_mesh, to_precomputed_skeleton, to_ng_skeleton)


Source = namedtuple('source', ['name', 'manifest', 'data'])

# Only show errors/warnings from HTTP server
logging.getLogger('werkzeug').setLevel('WARNING')


class Server:
    """A base class for a local source server.

    Parameters
    ----------
    ip :    str
            Local IP at which to serve the source.
    port :  int | "auto"
            Port at which to serve. If "auto" will auto-pick a free port.

    """

    def __init__(self, ip='127.0.0.1', port='auto'):
        self.ip = ip

        if port == 'auto':
            # Generate a sock and let OS choose the port for us
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(('localhost', 0))
            port = sock.getsockname()[1]
            sock.close()
        self.port = port

        # Initialize app
        self.app = flask.Flask(__name__)
        CORS(self.app)

        # Add base endpoint to app
        self.app.route('/', defaults={'path': ''})(self.app_serve_all)
        self.app.route('/<path:path>')(self.app_serve_all)

        self.thread = None
        self._sources = {}

    def __del__(self):
        """Stop server thread on exit."""
        self.stop()

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        status = f'running at {self.ip}:{self.port}' if self.thread else 'stopped'
        return f'{type(self).__name__}<status={status}, sources={len(self.sources)}>'

    @property
    def sources(self):
        """Registered sources."""
        return self._sources

    @property
    def running(self):
        """Server status."""
        if self.thread:
            return True
        return False

    @property
    def url(self):
        """Base URL for this server."""
        return f'http://{self.ip}:{self.port}'

    def start(self):
        """Start server."""
        if not self.thread:
            # Start app
            self.thread = ServerThread(self.app, self.ip, self.port)
            self.thread.start()

    def restart(self):
        """Restart server."""
        self.stop()
        self.start()

    def stop(self):
        """Stop server."""
        if self.thread:
            # Note to self:
            # Sometimes this does not work until the server gets another request
            self.thread.shutdown()
            self.thread = None

    def app_serve_all(self, path):
        """Method for app to catch all endpoints."""
        # Root path
        if path == '':
            #return flask.jsonify(self.sources)
            return flask.jsonify('')

        path = path.split('/')
        epath = path[0]
        if epath not in self.sources:
            return flask.abort(404)

        ep = self.sources[epath]
        subpath = '/'.join(path[1:])
        # Return manifest if info is queried
        if subpath == 'info':
            if ep.manifest:
                return flask.jsonify(ep.manifest)
            else:
                flask.abort(404)
        # Return data: either fragments if query ends
        if callable(ep.data):
            data = ep.data(subpath)
        elif isinstance(ep.data, dict):
            data = ep.data.get(subpath, None)
        if not data:
            flask.abort(404)
        return data

    def register_source(self, name, data, manifest=None, overwrite=False):
        """Add a new source to this server.

        Parameters
        ----------
        name :      str
                    This will be the path relative to root - e.g.
                    `127.0.0.1:5000/{name}/`
        data :      callable | dict
                    A function:
                      - for skeletons: must accept a single ID and return
                        a skeleton in precomputed format
                      - for meshes: must return a dictionary with list of
                        fragments (`{'fragments': [12345, 1234]}`) if input is
                        a segment ID (':0' suffix) or a mesh in precomputed
                        format if input is a fragment ID (i.e. no ':0' suffix)
                    If function returns None, will raise a 404. Can also use a
                    dictionary for the same thing. IDs will be strings!
        manifest :  dict, optional
                    A dictionary containing the `/info` for this source.
                    Depending on type (skeleton or mesh) this can specify
                    scales, transforms, etc.
        overwrite : bool
                    If False (default) will complain if the source already
                    exist.

        """
        assert callable(data) or isinstance(data, dict)

        if not overwrite:
            assert name not in self._sources, f'Path {self.url}/{name} already exists'

        self._sources[name] = Source(name=name,
                                     manifest=manifest,
                                     data=data)

        # Restart so this takes effect
        if self.running:
            self.restart()


class ServerThread(threading.Thread):
    """A stoppable thread for a flask app."""
    def __init__(self, app, ip='127.0.0.1', port=5000):
        threading.Thread.__init__(self, daemon=True)
        self.srv = make_server(ip, port, app)
        self.ctx = app.app_context()
        self.ctx.push()

    def run(self):
        """Run server in thread."""
        self.srv.serve_forever()

    def shutdown(self):
        """ShutDown server in this thread."""
        self.srv.shutdown()


class InMemoryDataSource:
    """A source for in-memory meshes/skeletons.

    Parameter
    ---------
    path :      string, optional
                Determines the path under which these data are served
                (if register=True). If not provided will generate a unique
                UUID.
    register :  bool
                If True, will register this source under `/{name}` with the
                default server.

    """
    _INFO = {"data_type": "uint64",
             'type': 'segmentation',
             "scales": [{"key": "fake",
                         "encoding": "raw",
                         "voxel_offset": [0, 0, 0],
                         "resolution": [995328, 536576, 282520],
                         "size": [1, 1, 1],
                         "chunk_sizes": [[256, 256, 16]]}],
            "mesh": "meshes",
            "skeleton": "skeletons",
            "segment_properties": "segment_properties",
            "num_channels": 1}

    def __init__(self, path=None, register=True):
        self.neurons = OrderedDict()
        self.info = copy.deepcopy(self._INFO)

        if not path:
            path = str(uuid.uuid4())[:5]
        self.path = path

        if register:
            server.register_source(name=self.path,
                                   data=self,
                                   manifest=self.info)
            server.start()

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return (f'{self.type} with {len(self.neurons)} neurons:\n {self.json}')

    def __call__(self, path):
        # Parse path
        path = path.split('/')

        if path[0] == 'meshes':
            if path[1] == 'info':
                return json.dumps({"@type": "neuroglancer_legacy_mesh"})
            return self._get_mesh(path[1])
        elif path[0] == 'skeletons':
            if path[1] == 'info':
                return json.dumps({
                                   "@type": "neuroglancer_skeletons",
                                   "transform": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0],
                                   #"vertex_attributes": [{"id": "radius", "data_type": "float32", "num_components": 1}],
                                   "segment_properties": "seg_props"
                                   })
            elif path[1] == 'seg_props':
                return json.dumps(self.segment_properties)
            return self._get_skeleton(path[1])
        elif path[0] == 'segment_properties':
            if path[1] == 'info':
                return json.dumps(self.segment_properties)
        return ''

    def _get_mesh(self, id):
        # If has ':0' suffix we return the fragments
        if id.endswith(':0'):
            id = id.split(':')[0]
            resp = {'fragments': []}
            if id in self.neurons and self.neurons[id]['mesh']:
                resp['fragments'].append(id)
            return json.dumps(resp)
        # If actual segment ID, return this segment
        else:
            mesh = self.neurons[id]['mesh']
            # Produce and return precomputed format
            return to_precomputed_mesh(mesh.vertices, mesh.faces)

    def _get_skeleton(self, id):
        # If has ':0' suffix we return the fragments
        if id.endswith(':0'):
            id = id.split(':')[0]
            resp = {'fragments': []}
            if id in self.neurons and self.neurons[id]['skeleton']:
                resp['fragments'].append(id)
            return json.dumps(resp)
        # If actual segment ID, return this segment
        else:
            sk = to_ng_skeleton(self.neurons[id]['skeleton'])
            # Produce and return precomputed format
            return to_precomputed_skeleton(sk.vertex_positions, sk.edges)

    @property
    def type(self):
        return 'DataSource'

    @property
    def url(self):
        return f"precomputed://{server.url}/{self.path}"

    @property
    def json(self):
        """The JSON state you would want to use to add this as a data source."""
        layer = copy.deepcopy(self.info)
        layer['source'] = self.url
        layer['name'] = f"{self.path}"
        layer["ignoreSegmentInteractions"] = True
        return json.dumps(layer)

    @property
    def segment_properties(self):
        # Collect names or IDs for each neuron
        props = {
                 '@type': 'neuroglancer_segment_properties',
                 'inline': {
                            'ids': list(self.neurons.keys()),
                            'properties': [{
                                'id': 'label',
                                'type': 'label',
                                'values': [getattr(v['mesh'],
                                                   'label',
                                                   getattr(v['skeleton'],
                                                          'label',
                                                          'NA')) for v in self.neurons.values()]
                                        }]
                            }
                 }
        return props

    def add_data(self, x, use_id=False):
        """Add data to source.

        Parameters
        ----------
        x :     mesh- or skeleton-like

        Returns
        -------
        list
                The ID(s) under which the segments can be found.

        """
        if is_iterable(x):
            segs = []
            for m in x:
                segs += self.add_data(m)
            return segs

        if not is_mesh(x) and not is_skeleton(x):
            raise TypeError(f'Object of type "{type(x)}" looks neither like a mesh nor a skeleton')

        if use_id and hasattr(x, 'id'):
            id = x.id
        else:
            id = len(self.neurons) + 1
        id = str(id)

        if id not in self.neurons:
            self.neurons[id] = {'mesh': None,
                                'skeleton': None}

        if is_mesh(x):
            self.neurons[id]['mesh'] = x
        else:
            self.neurons[id]['skeleton'] = x

        return [id]

    def clear(self):
        """Clear all data."""
        self.neurons = OrderedDict()

    def find_mesh(self, x):
        """Find and return index of mesh matching `x`."""
        return [i for i, m in enumerate(self.meshes) if getattr(m, 'id', None) == x or getattr(m, 'name', None) == x]

    def find_skeleton(self, x):
        """Find and return index of skeleton matching `x`."""
        return [i for i, m in enumerate(self.skeletons) if getattr(m, 'id', None) == x or getattr(m, 'name', None) == x]


# Initialize a single server that we can add mesh sources to
# Note that the server still needs to be started
server = Server()
