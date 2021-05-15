from setuptools import setup, find_packages

import re

VERSIONFILE = "nglscenes/__version__.py"
verstrline = open(VERSIONFILE, "rt").read()
VSRE = r"^__version__ = ['\"]([^'\"]*)['\"]"
mo = re.search(VSRE, verstrline, re.M)
if mo:
    verstr = mo.group(1)
else:
    raise RuntimeError("Unable to find version string in %s." % (VERSIONFILE,))


with open('requirements.txt') as f:
    requirements = f.read().splitlines()
    requirements = [l for l in requirements if not l.startswith('#')]

with open("README.md") as f:
    long_description = f.read()

setup(
    name='nglscenes',
    version=verstr,
    packages=find_packages(include=["nglscenes", "nglscenes.*"]),
    license='GNU GPL V3',
    description='Tools to generate and manipulate neuroglancer scenes',
    long_description=long_description,
    long_description_content_type="text/markdown",
    url='https://github.com/schlegelp/nglscenes',
    project_urls={
     "Documentation": "https://github.com/schlegelp/nglscenes",
     "Source": "https://github.com/schlegelp/nglscenes",
     "Changelog": "https://github.com/schlegelp/nglscenes/blob/main/NEWS.md",
    },
    author='Philipp Schlegel',
    author_email='pms70@cam.ac.uk',
    keywords='Neuroglancer scenes FlyWire',
    classifiers=[
        'Development Status :: 4 - Beta',

        'Intended Audience :: Science/Research',
        'Topic :: Scientific/Engineering :: Bio-Informatics',

        'License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)',

        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
    ],
    install_requires=requirements,
    # CI runs against >=3.7
    # but R-Python interface ships with 3.6 so this is necessary
    python_requires='>=3.6',
    zip_safe=False,

    include_package_data=True

)
