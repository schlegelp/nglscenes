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

from .layers import SegmentationLayer
from .utils import is_graphene_source, map_source_urls

__all__ = ['FlyWireSegmentationLayer', 'FancSegmentationLayer', 'GrapheneSegmentationLayer']

def _add_middleauth(url):
    if url.startswith('graphene://') and not url.startswith('graphene://middleauth+'):
        url = url.replace('graphene://', 'graphene://middleauth+', 1)
    return url


def _remove_middleauth(url):
    if url.startswith('graphene://middleauth+'):
        url = url.replace('graphene://middleauth+', 'graphene://', 1)
    return url


# The two neuroglancer families spell a CAVE chunkedgraph layer differently:
#  - mainline neuroglancer / Spelunker: type "segmentation" with a
#    "graphene://middleauth+https://..." source
#  - the Seung-lab fork (e.g. ngl.flywire.ai): type "segmentation_with_graph"
#    with a bare "graphene://https://..." source
# Maps flavour -> (layer type, source conversion)
FLAVOURS = {
    'mainline': ('segmentation', _add_middleauth),
    'spelunker': ('segmentation', _add_middleauth),
    'seunglab': ('segmentation_with_graph', _remove_middleauth),
}


def convert_graphene_state(state, flavour):
    """Convert a graphene layer state to the given neuroglancer flavour.

    Parameters
    ----------
    state :     dict
                The layer state. Not modified in place but the returned
                state shares all values except `type` and `source`.
    flavour :   "spelunker" | "mainline" | "seunglab"
                The neuroglancer family to convert to.

    Returns
    -------
    dict

    """
    if flavour not in FLAVOURS:
        raise ValueError(f'Unknown flavour "{flavour}". Expected one of: '
                         f'{", ".join(FLAVOURS)}')
    ty, func = FLAVOURS[flavour]
    return {**state, 'type': ty, 'source': map_source_urls(state['source'], func)}


class GrapheneSegmentationLayer(SegmentationLayer):
    """Segmentation layer for a graphene (CAVE chunkedgraph) source.

    When constructed directly, the layer is set up for mainline neuroglancer
    and Spelunker (type "segmentation", "graphene://middleauth+" source).
    Layers parsed from an existing scene are kept as written. Use
    `.as_flavour()` (or `Scene.for_viewer()`) to convert between flavours.

    """

    def __init__(self, source, **kwargs):
        if not is_graphene_source(source):
            raise ValueError('Expected `source` to start with the "graphene://" protocol')
        # Base neuroglancer wants type "segmentation" and a middleauth+ source
        kwargs = convert_graphene_state({**kwargs, 'source': source}, 'mainline')
        super().__init__(**kwargs)

    @property
    def flavour(self):
        """Neuroglancer flavour this layer is written for."""
        if self.get('type') == FLAVOURS['seunglab'][0]:
            return 'seunglab'
        return 'mainline'

    def as_flavour(self, flavour):
        """Return copy of this layer converted to the given flavour.

        Parameters
        ----------
        flavour :   "spelunker" | "mainline" | "seunglab"
                    "spelunker" and "mainline" (e.g. ngl.cave-explorer.org)
                    use type "segmentation" with a "graphene://middleauth+"
                    source; "seunglab" (e.g. ngl.flywire.ai) uses type
                    "segmentation_with_graph" with a bare "graphene://" source.

        """
        return type(self).from_state(convert_graphene_state(self.as_dict(), flavour))


class FlyWireSegmentationLayer(GrapheneSegmentationLayer):
    def __init__(self, name='flywire_production', **kwargs):
        kwargs['source'] = 'graphene://middleauth+https://prod.flywire-daf.com/segmentation/1.0/fly_v31'
        super().__init__(name=name, **kwargs)


class FancSegmentationLayer(GrapheneSegmentationLayer):
    def __init__(self, name='fanc', **kwargs):
        kwargs['source'] = 'graphene://https://cave.fanc-fly.com/segmentation/table/mar2021_prod'
        super().__init__(name=name, **kwargs)
