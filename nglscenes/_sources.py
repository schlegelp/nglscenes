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

"""Local mesh and skeleton sources for `LocalScene`.

These subclass neuroglancer classes, so this module requires the optional
`neuroglancer` dependency and is only imported when needed.
"""

import io

import pandas as pd
import numpy as np

from pathlib import Path
from zipfile import ZipFile

from .utils import to_precomputed_mesh, to_ng_skeleton, import_optional

neuroglancer = import_optional('neuroglancer')
skeleton = import_optional('neuroglancer.skeleton')
tm = import_optional('trimesh')

__all__ = ['LocalMeshSource', 'LocalSkeletonSource']


class LocalMeshSource(neuroglancer.LocalVolume):
    """A local mesh source."""

    def __init__(self, source, dimensions, **kwargs):
        if callable(source):
            pass
        else:
            source = Path(source)
            if source.is_file():
                if not source.name.endswith('.zip'):
                    raise ValueError(f'Invalid skeleton source: {source}')
            elif not source.is_dir():
                raise ValueError(f'Invalid skeleton source: {source}')

        # Initialize with mock data
        kwargs['volume_type'] = 'segmentation'
        kwargs['dimensions'] = dimensions
        super().__init__(np.random.randint(0, 100, size=(10, 10, 10), dtype=np.uint8), **kwargs)
        self.source = source

    def get_object_mesh(self, object_id):
        """Read mesh for given object and return in precomputed format."""
        if callable(self.source):
            return self.source(object_id)
        elif self.source.name.endswith('.zip'):
            return self.read_from_zip(object_id)
        else:
            try:
                # Try finding a file that has a matching name
                file = next(self.source.glob(f'{object_id}.*')).name
            except StopIteration:
                print(f'Object {object_id} not found in directory.')
                return None
            try:
                # Try reading that file
                return self.read_file(file)
            except BaseException:
                print(f'File {file} could not be read.')
                return None

    def read_file(self, file):
        """Read mesh from file."""
        if not (self.source / file).is_file():
            return None

        mesh = tm.load_mesh(self.source / file)

        return to_precomputed_mesh(mesh.vertices, mesh.faces)

    def read_buffer(self, buffer, file_type):
        """Read mesh from buffer."""
        mesh = tm.load_mesh(buffer, file_type=file_type)

        return to_precomputed_mesh(mesh.vertices, mesh.faces)

    def read_from_zip(self, object_id):
        """Read mesh from inside a ZIP archive.

        Parameters
        ----------
        object_id :     str | int

        Returns
        -------
        str
                        Bytes string of precomputed format.

        """
        with ZipFile(self.source, 'r') as zip:
            for file in zip.namelist():
                if file.startswith(f'{object_id}.'):
                    return self.read_buffer(io.BytesIO(zip.read(file)),
                                            file_type=file.split('.')[-1])

        print(f'Object {object_id} not found in zip.')
        return None


class LocalSkeletonSource(skeleton.SkeletonSource):
    """A local skeleton source."""

    def __init__(self, source, dimensions):
        if callable(source):
            pass
        else:
            source = Path(source)
            if source.is_file():
                if not source.name.endswith('.zip'):
                    raise ValueError(f'Invalid skeleton source: {source}')
            elif not source.is_dir():
                raise ValueError(f'Invalid skeleton source: {source}')

        super().__init__(dimensions)
        self.source = source

    def get_skeleton(self, id):
        if callable(self.source):
            return self.source(id)
        elif self.source.name.endswith('.zip'):
            return self.read_from_zip(f'{id}.swc')
        else:
            return self.read_from_swc(self.source / f'{id}.swc')

    def read_from_zip(self, file):
        """Read skeleton from SWC file inside a ZIP archive.

        Parameters
        ----------
        file :      str

        Returns
        -------
        neuroglancer.Skeleton

        """
        with ZipFile(self.source, 'r') as zip:
            if file not in zip.namelist():
                print(f'File {file} not found in zip.')
                return None
            return self.read_from_swc(io.StringIO(zip.read(file).decode()))

    def read_from_swc(self, file):
        """Read skeleton from SWC file (or buffer).

        Parameters
        ----------
        file :      str

        Returns
        -------
        neuroglancer.Skeleton

        """
        if isinstance(file, io.StringIO):
            if isinstance(file.read(0), bytes):
                file = io.TextIOWrapper(file, encoding="utf-8")
        elif not Path(file).is_file():
            return None

        swc = pd.read_csv(file,
                          delimiter=' ',
                          skipinitialspace=True,
                          comment='#',
                          header=None)

        swc.columns = ['PointNo', 'Label', 'X', 'Y', 'Z', 'Radius', 'Parent']

        return to_ng_skeleton(swc)
