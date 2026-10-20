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
import json
import pyperclip
import webbrowser

from urllib.parse import quote, urldefrag, urlparse, urlunparse

from .layers import (
    ImageLayer,
    SegmentationLayer,
    AnnotationLayer,
    MeshLayer,
    BaseLayer,
    GenericLayer,
    LayerManager,
)
from .graphene import GrapheneSegmentationLayer
from . import utils

__all__ = ["Scene"]


class Scene:
    """A NeuroGlancer scene.

    Parameters
    ----------
    base_url :      str
                    The URL to the neuroglancer instance.

    """

    # REMOVING THIS BREAKS COPYING
    _state = {}

    def __init__(self, base_url="https://neuroglancer-demo.appspot.com/", **kwargs):
        self.base_url = base_url
        self._layers = []
        self.state = kwargs
        self._url = ""
        self._layermanager = LayerManager(self)

    @property
    def layers(self):
        """Managed layers present."""
        return self._layermanager

    @layers.setter
    def layers(self):
        raise AttributeError("Please use `.add_layers()` to edit the layers.")

    @property
    def state(self):
        """JSON state of scene."""
        return self._state

    @state.setter
    def state(self, value):
        self._stale = True

        def set_stale():
            self._stale = True

        if not isinstance(value, dict):
            raise TypeError("State must be a dictionary")
        value = utils.add_on_change_callback(value, callback=set_stale)
        self._state = value

    @property
    def type(self):
        return self.__class__.__name__

    @property
    def base_url(self):
        """URL of the neuroglancer instance (host or page) for `.url`."""
        return self._base_url

    @base_url.setter
    def base_url(self, value):
        if not isinstance(value, str):
            raise TypeError(f'Expected str, got "{type(value)}"')
        self._base_url = value
        self._stale = True

    @property
    def url(self):
        """Url to self."""
        self._url = self.make_url()
        return self._url

    def __add__(self, other):
        if not isinstance(other, Scene):
            raise NotImplementedError(
                f"Unable to combine {type(other)} with {self.type}"
            )
        x = copy.deepcopy(self)
        x.add_layers(*copy.deepcopy(other._layers))

        return x

    def __or__(self, other):
        if not isinstance(other, Scene):
            raise NotImplementedError(f"Unable to merge {type(other)} with {self.type}")

        x = copy.deepcopy(self)
        for l1 in copy.deepcopy(other._layers):
            merged = False
            for i, l2 in enumerate(x._layers):
                if isinstance(l1, type(l2)):
                    try:
                        # `__or__` returns a new layer: put it in the scene
                        x._layers[i] = l2 | l1
                        merged = True
                        break
                    except NotImplementedError:
                        pass
            if not merged:
                x.add_layers(l1)

        return x

    def __eq__(self, other):
        if type(other) is not type(self):
            return False
        if self.state != other.state:
            return False
        return True

    def __getstate__(self):
        """Get state (used e.g. for pickling)."""
        state = dict(self.__dict__)

        # Drop layermanager
        _ = state.pop("_layermanager", None)

        # Set viewer to None if present
        if "_viewer" in state:
            state["_viewer"] = None

        return state

    def __setstate__(self, d):
        """Set state (used e.g. for unpickling)."""
        # We have to implement this to make sure
        self.__dict__.clear()
        for k, v in d.items():
            self.__dict__[k] = v

        self._layermanager = LayerManager(self)

    def __setitem__(self, name, value):
        """Set a scene attribute."""
        self._state[name] = value
        self._stale = True

    def __getitem__(self, name):
        """Get a scene property."""
        if name in self.state:
            return self.state[name]
        raise AttributeError(f'"{name}" not in state.')

    def __contains__(self, name):
        """Check if attribute is in state."""
        return name in self._state

    def __len__(self):
        """Return number of layers in scene."""
        return len(self.layers)

    def __str__(self):
        if not len(self):
            layer_str = "none"
        else:
            layer_str = []
            for lt, ty in LAYER_FACTORY.items():
                this = [l for l in self.layers if isinstance(l, ty)]
                if this:
                    layer_str.append(f"{len(this)} {lt}")
            layer_str = ", ".join(layer_str)

        url = self.url
        if len(url) >= 60:
            url = url[:30] + "[...]" + url[-30:]
        return f"<nglscenes.{type(self).__name__}(layers={layer_str}; url={url})>"

    def __repr__(self):
        return self.__str__()

    def _repr_html_(self):
        if not len(self):
            layer_str = "none"
        else:
            layer_str = []
            for lt, ty in LAYER_FACTORY.items():
                this = [l for l in self.layers if isinstance(l, ty)]
                if this:
                    layer_str.append(f"{len(this)} {lt}")
            layer_str = ", ".join(layer_str)

        url = self.url
        if len(url) >= 60:
            url = url[:30] + "[...]" + url[-30:]
        return f'&lt;nglscenes.{type(self).__name__}(layers={layer_str}; url=<a href="{self.url}" target="_blank">{url}</a>)&gt;'

    @classmethod
    def from_clipboard(cls, base_url=None):
        """Generate scene from either a JSON or URL on the clipboard."""
        # Read clipboard
        scene = pyperclip.paste()

        return cls.from_string(scene, base_url=base_url)

    @classmethod
    def from_dict(cls, dict, base_url=None):
        """Generate scene from a state dict.

        Parameters
        ----------
        dict :          dict
                        The state. Not modified.
        base_url :      str, optional
                        URL of the neuroglancer instance to use for the
                        scene's URL.

        """
        return cls.from_string(dict, base_url=base_url)

    @classmethod
    def from_file(cls, fp, base_url=None):
        """Generate scene from a file."""
        with open(fp, "r") as f:
            scene = json.load(f)

        return cls.from_string(scene, base_url=base_url)

    @classmethod
    def from_string(cls, string, skip_archived=False, base_url=None):
        """Generate scene from either a JSON or URL.

        Parameters
        ----------
        string :        str | dict
                        Either a JSON-formatted string, a state dict or a URL
                        containing a JSON fragment.
        skip_archived : bool, optional
                        If True, skip archived layers. Default: False.
        base_url :      str, optional
                        URL of the neuroglancer instance to use for the
                        scene's URL. If not provided and `string` is a URL,
                        will reuse that URL's base.

        """
        # Extract json
        state = utils.parse_json_scene(string)

        # Neuroglancer accepts `layers` as a list or a `{name: layer}` map
        layers = state.get("layers", [])
        if isinstance(layers, dict):
            layers = [{**v, "name": k} for k, v in layers.items()]

        # Copy so we don't modify the input (layers are copied when parsed)
        state = {k: copy.deepcopy(v) for k, v in state.items() if k != "layers"}

        if base_url is None and utils.is_url(string):
            # If input is URL, reuse the base URL
            base_url = urldefrag(string).url

        x = cls()
        if base_url is not None:
            x.base_url = base_url

        layers = parse_layers(layers, skip_archived=skip_archived)

        # Update properties
        x._state.update(state)

        if layers:
            x.add_layers(*layers)

        return x

    @classmethod
    def from_url(cls, url, skip_archived=False, base_url=None):
        """Generate scene from URL.

        Parameters
        ----------
        url :           str
                        The URL.
        skip_archived : bool, optional
                        If True, skip archived layers. Default: False.
        base_url :      str, optional
                        URL of the neuroglancer instance to use for the
                        scene's URL. Defaults to the base of `url`.

        """
        return cls.from_string(url, skip_archived=skip_archived, base_url=base_url)

    @classmethod
    def from_pandas(cls, df, layer_col=None, color_col=None, **kwargs):
        """Generate scene from a pandas DataFrame.

        Parameters
        ----------
        df :        pd.DataFrame
                    Must contain the following columns:
                     - `id` or `segment_id` (int or str)
                     - `source` (str): the source URL (e.g. "precomputed://gs://...")
        layer_col : str, optional
                    Name of a column to use to sort segments into
                    layers. If not provided, each source will get its own layer.
        color_col : str, optional
                    Name of a column to use to color segments.
        **kwargs
                    Additional keyword arguments to pass to the Scene constructor.

        """
        assert (
            "id" in df.columns or "segment_id" in df.columns
        ), 'DataFrame must contain an "id" or "segment_id" column.'
        assert "source" in df.columns, 'DataFrame must contain a "source" column.'

        if layer_col is not None:
            assert layer_col in df.columns, f'Column "{layer_col}" not in DataFrame.'
        if color_col is not None:
            assert color_col in df.columns, f'Column "{color_col}" not in DataFrame.'

        # Rename `segment_id`` column to `id`
        if "id" not in df.columns:
            df = df.rename(columns={"segment_id": "id"})

        # Generate the scene
        x = cls(**kwargs)

        # Add the layers
        for source, df in df.groupby("source"):
            if layer_col is not None:
                for layer_name, sdf in df.groupby(layer_col):
                    layer = SegmentationLayer(source=source)
                    layer["name"] = str(layer_name)
                    layer["segments"] = sdf["id"].values.astype(str).tolist()
                    if color_col is not None:
                        layer.set_colors(
                            sdf.astype({"id": str}).set_index("id")[color_col].to_dict()
                        )

                    x.add_layers(layer)
            else:
                layer = SegmentationLayer(source=source)
                layer["segments"] = df["id"].values.astype(str).tolist()

                if color_col is not None:
                    layer.set_colors(
                        df.astype({"id": str}).set_index("id")[color_col].to_dict()
                    )

                x.add_layers(layer)

        return x

    def add_layers(self, *layers, index=None):
        """Add layer to scene.

        Non-unique names will be given a suffix, e.g. "-2".

        Parameters
        ----------
        *layers
                    The layer(s) to add. Must be instances of BaseLayer such as
                    ngl.SegmentationLayer.
        index :     int, optional
                    Index at which to insert the layer(s). Default is to append.

        """
        for l in layers:
            if not isinstance(l, BaseLayer):
                raise TypeError(f"Expected Layer, got {type(l)}")

            # We are enforcing unique name here
            i = 2
            org_name = str(l.name)
            while l["name"] in self.layers:
                if i <= 2:
                    l["name"] = f"{org_name}-{i}"
                else:
                    l["name"] = f"{org_name}-{i}"
                i += 1

            if index is None:
                self._layers.append(l)
            elif isinstance(index, int):
                self._layers.insert(index, l)
                index += 1

            self._stale = True

    def copy(self):
        """Return copy."""
        return copy.deepcopy(self)

    def for_viewer(self, flavour):
        """Return copy of the scene with graphene layers converted for a viewer.

        The two neuroglancer families spell CAVE chunkedgraph layers
        differently and each refuses the other's spelling. This converts every
        `GrapheneSegmentationLayer` for the target family. Other layers are
        left untouched.

        Parameters
        ----------
        flavour :   "spelunker" | "mainline" | "seunglab"
                    See `GrapheneSegmentationLayer.as_flavour`.

        Returns
        -------
        Scene

        """
        x = self.copy()
        x._layers = [
            l.as_flavour(flavour) if isinstance(l, GrapheneSegmentationLayer) else l
            for l in x._layers
        ]
        x._stale = True
        return x

    def drop_layer(self, which):
        """Remove layer from scene.

        Parameters
        ----------
        which :     str | int
                    Either index (int) or name (str) of layer to drop.

        """
        self._stale = True
        if isinstance(which, str):
            if which not in self.layers:
                raise ValueError(f'No layer named "{which}".')
            ix = [
                i
                for i, l in enumerate(self._layers)
                if getattr(l, "name", None) == which
            ][0]
            return self._layers.pop(ix)
        elif isinstance(which, int):
            if len(self.layers) <= which:
                raise ValueError(
                    f"Unable to drop layer {which}: only {len(self.layers)} present."
                )
            return self._layers.pop(which)
        else:
            raise TypeError(f"Expected str or int, got {type(which)}")

    def move_layer(self, which, index):
        """Move layer to a new position.

        Parameters
        ----------
        which :     str | int
                    Either index (int) or name (str) of layer to move.
        index :     int
                    The new index for the layer.

        """
        self._stale = True
        if isinstance(which, str):
            if which not in self.layers:
                raise ValueError(f'No layer named "{which}".')
            ix = [
                i
                for i, l in enumerate(self._layers)
                if getattr(l, "name", None) == which
            ][0]
            l = self._layers.pop(ix)
            self._layers.insert(index, l)
        elif isinstance(which, int):
            if len(self.layers) <= which:
                raise ValueError(
                    f"Unable to move layer {which}: only {len(self.layers)} present."
                )
            l = self._layers.pop(which)
            self._layers.insert(index, l)
        else:
            raise TypeError(f"Expected str or int, got {type(which)}")

    def as_dict(self):
        """Generate a dictionary of the JSON state."""
        state = utils.remove_callback(self.state)
        state["layers"] = [l.as_dict() for l in self.layers]
        return utils.remove_callback(state)

    def to_json(self, pretty=False):
        """Generate the JSON-formatted string describing the scene."""
        return json.dumps(
            self.as_dict(),
            indent=4 if pretty else None,
            # Compact separators keep URLs short
            separators=None if pretty else (",", ":"),
            sort_keys=True,
        )

    def to_file(self, fp):
        """Save scene to file."""
        with open(fp, "w") as f:
            f.write(self.to_json(pretty=True))

    def to_clipboard(self, scene_only=False):
        """Copy URL to clipboard."""
        if scene_only:
            pyperclip.copy(self.to_json(pretty=True))
            print("Scene copied to clipboard.")
        else:
            pyperclip.copy(self.url)
            print("URL copied to clipboard.")

    def make_url(self):
        """Generate/Update URL."""
        scene_str = self.to_json(pretty=False)
        # The state is a fragment, not a path segment: append it to the base
        # as given (e.g. ".../neuroglancer.html#!...") replacing any existing
        # fragment. Only a bare host gets a trailing slash.
        base = urlparse(urldefrag(self._base_url).url)
        if not base.path:
            base = base._replace(path="/")
        base = urlunparse(base)
        self._url = f"{base}#!{quote(scene_str)}"
        self._stale = False
        return self._url

    def open(self, new_window=False, browser=None):
        """Open URL in default webbrowser.

        Parameters
        ----------
        new_window : bool, optional
                     If True, open URL in a new window. Defaults
                     to opening in a new tab (if possible).
        browser :    str, optional
                     The name of the browser to use. If None, the
                     default browser will be used.

        """
        if not browser:
            wb = webbrowser
        else:
            wb = webbrowser.get(browser)

        if new_window:
            wb.open_new(self.url)
        else:
            wb.open_new_tab(self.url)


LAYER_FACTORY = {
    "segmentation": SegmentationLayer,
    "mesh": MeshLayer,
    "image": ImageLayer,
    "annotation": AnnotationLayer,
    "segmentation_with_graph": GrapheneSegmentationLayer,
}


def parse_layers(layer, skip_unknown=False, skip_archived=True):
    """Parse layer state(s) into layer objects.

    Layer states are taken as is (see `BaseLayer.from_state`).

    Parameters
    ----------
    layer :         dict | list
                    A single layer state or a list thereof.
    skip_unknown :  bool
                    If True, skip layers of unknown type. If False (default),
                    they are kept as `GenericLayer`.
    skip_archived : bool
                    If True, skip archived layers.

    """
    if isinstance(layer, list):
        res = [parse_layers(l, skip_unknown=skip_unknown, skip_archived=skip_archived) for l in layer]
        # Drop "None" if skip_unknown=True
        return [l for l in res if l]

    if not isinstance(layer, dict):
        raise TypeError(f'Expected dicts or list thereof, got "{type(layer)}"')

    # Layers can be archived which I think means they have been deleted?
    if layer.get("archived", False) and skip_archived:
        return

    ty = layer.get("type")
    if ty not in LAYER_FACTORY:
        if skip_unknown:
            return
        if ty is None:
            raise ValueError(f'Layer "{layer.get("name", "")}" has no type')
        return GenericLayer.from_state(layer)

    cls = LAYER_FACTORY[ty]
    # Mainline neuroglancer writes graphene layers as plain segmentation
    if cls is SegmentationLayer and utils.is_graphene_source(layer.get("source")):
        cls = GrapheneSegmentationLayer

    return cls.from_state(layer)
