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
"""Kept for backwards compatibility: importing this module registers the
DVID (and graphene) credentials providers with neuroglancer.

See `nglscenes.credentials` for details. Note that providers are also
registered automatically when nglscenes links a layer to a viewer.
"""

from .credentials import (TokenbasedDefaultCredentialsProvider,  # noqa: F401
                          get_tokenbased_application_default_credentials_provider)
