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
"""Credentials providers for neuroglancer.

Importing this module registers them with neuroglancer's default credentials
manager. nglscenes does that when it first links a layer to a viewer:

- "middleauthapp" for graphene (CAVE) sources; tokens are read via cloud-volume
- "DVID" for DVID sources; by default, no authentication is assumed. If you
  need authentication, set a DVID_APPLICATION_CREDENTIALS environment variable
  with the token to use. Without this provider, neuroglancer will simply throw
  an error when trying to access a DVID source.

This module requires the optional `neuroglancer` dependency.
"""

import os
import functools

from .utils import get_cave_credentials, import_optional

credentials_provider = import_optional('neuroglancer.credentials_provider')
run_on_new_thread = import_optional('neuroglancer.futures').run_on_new_thread
default_credentials_manager = import_optional(
    'neuroglancer.default_credentials_manager').default_credentials_manager


class GrapheneCredentialsProvider(credentials_provider.CredentialsProvider):
    def __init__(self, domain='prod.flywire-daf.com'):
        super(GrapheneCredentialsProvider, self).__init__()

        self.domain = domain
        self._credentials = {}
        self._credentials['token'] = get_cave_credentials(self.domain)

    def get_new(self):
        def func():
            return dict(tokenType=u'Bearer', accessToken=self._credentials['token'])

        return run_on_new_thread(func)


@functools.cache
def get_credentials_provider(domain):
    """Return (cached) graphene credentials provider for given domain."""
    return GrapheneCredentialsProvider(domain)


class TokenbasedDefaultCredentialsProvider(credentials_provider.CredentialsProvider):
    def __init__(self):
        super(TokenbasedDefaultCredentialsProvider, self).__init__()

        # Make sure logging is initialized.
        # Does nothing if logging has already been initialized.
        # logging.basicConfig()

        self._credentials = {}

    def get_new(self):
        def func():
            self._credentials = {}
            self._credentials["token"] = os.environ.get(
                "DVID_APPLICATION_CREDENTIALS", ""
            )
            return dict(tokenType="Bearer", accessToken=self._credentials["token"])

        return run_on_new_thread(func)


@functools.cache
def get_tokenbased_application_default_credentials_provider():
    return TokenbasedDefaultCredentialsProvider()


# Register authentication (module-level code runs only once)
default_credentials_manager.register(u'middleauthapp', get_credentials_provider)
default_credentials_manager.register(
    "DVID",
    lambda _parameters: get_tokenbased_application_default_credentials_provider(),
)
