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
"""This module simply registers a credential provider for DVID sources.

By default, that provider doesn't do anything (i.e. assumes no authenticaiton
is required). If you need authentication, set a DVID_APPLICATION_CREDENTIALS
environment variable with the token to use.

Without registering this provider, neuroglancer will simply throw an error
when trying to access a DVID source.
"""

import os

from neuroglancer import credentials_provider
from neuroglancer.futures import run_on_new_thread
from neuroglancer.default_credentials_manager import default_credentials_manager


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


_global_tokenbased_application_default_credentials_provider = None


def get_tokenbased_application_default_credentials_provider():
    global _global_tokenbased_application_default_credentials_provider
    if _global_tokenbased_application_default_credentials_provider is None:
        _global_tokenbased_application_default_credentials_provider = (
            TokenbasedDefaultCredentialsProvider()
        )
    return _global_tokenbased_application_default_credentials_provider


default_credentials_manager.register(
    "DVID",
    lambda _parameters: get_tokenbased_application_default_credentials_provider(),
)
