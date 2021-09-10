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
import logging
import threading
import socket

from werkzeug.serving import make_server
from flask_cors import CORS
from collections import namedtuple

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
            return flask.jsonify(self.sources)

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

    def register_source(self, name, data, manifest=None):
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

        """
        assert callable(data) or isinstance(data, dict)
        self._sources[name] = Source(name=name,
                                     manifest=manifest,
                                     data=data)

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


server = Server()
