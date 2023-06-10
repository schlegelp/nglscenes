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

from neuroglancer import credentials_provider
from neuroglancer.futures import run_on_new_thread
from neuroglancer.default_credentials_manager import default_credentials_manager

from .layers import SegmentationLayer

__all__ = ['FlyWireSegmentationLayer', 'FancSegmentationLayer']

_global_graphene_credentials_provider = {}


class GrapheneCredentialsProvider(credentials_provider.CredentialsProvider):
    def __init__(self, domain='prod.flywire-daf.com'):
        super(GrapheneCredentialsProvider, self).__init__()

        self.domain = domain
        self._credentials = {}
        self._credentials['token'] = cv.secrets.cave_credentials(self.domain).get('token', None)

        if not self._credentials['token']:
            raise ValueError(f'No CAVE credentials for domain {self.domain} '
                             'found. See cloud-volume for details on how to set it.')

    def get_new(self):
        def func():
            return dict(tokenType=u'Bearer', accessToken=self._credentials['token'])

        return run_on_new_thread(func)


def get_credentials_provider(domain):
    """Copy pasted from neuroglancer."""
    global _global_graphene_credentials_provider
    if domain not in _global_graphene_credentials_provider:
        _global_graphene_credentials_provider[domain] = GrapheneCredentialsProvider(domain)
    return _global_graphene_credentials_provider[domain]


# Register authentication
default_credentials_manager.register(
     u'middleauthapp',
     lambda domain: get_credentials_provider(domain))


class GrapheneSegmentationLayer(SegmentationLayer):
    def __init__(self, source, **kwargs):
        if not source.startswith('graphene://'):
            raise ValueError('Expected `source` to start with the "graphene://" protocol')
        # Add middleauth to source
        if not source.startswith('graphene://middleauth+'):
            source = source.replace('graphene://', 'graphene://middleauth+')

        # Base neuroglancer does not like this type
        if kwargs.get('type', None) == 'segmentation_with_graph':
            kwargs['type'] = 'segmentation'

        super().__init__(source=source, **kwargs)


class FlyWireSegmentationLayer(GrapheneSegmentationLayer):
    def __init__(self, name='flywire_production', **kwargs):
        kwargs['source'] = 'graphene://middleauth+https://prod.flywire-daf.com/segmentation/1.0/fly_v31'
        super().__init__(name=name, **kwargs)


class FancSegmentationLayer(GrapheneSegmentationLayer):
    def __init__(self, name='fanc', **kwargs):
        kwargs['source'] = 'graphene://https://cave.fanc-fly.com/segmentation/table/mar2021_prod'
        super().__init__(name=name, **kwargs)
