import json
import requests

import numpy as np
import pandas as pd

from urllib.parse import urlparse

NUMBER_DTYPES = {
    np.float32: "float32",
    np.int8: "int8",
    np.int16: "int16",
    np.int32: "int32",
    np.uint8: "uint8",
    np.uint16: "uint16",
    np.uint32: "uint32",
    # Neuroglancer/ json only supports 32bit floats/ints
    np.float64: "float32",
    np.int64: "int32",
    np.uint64: "uint32",
}


__all__ = ["SegmentProperties"]


class SegmentProperties:
    """Class to create segment properties.

    See https://github.com/google/neuroglancer/blob/master/src/datasource/precomputed/segment_properties.md
    for a description of the Neuroglancer properties format.

    Parameters
    ----------
    ids :           iterable
                    Iterable of segment IDs. Must be unique.

    """

    def __init__(self, ids):
        self._ids = np.asarray(ids)
        self._dict = {
            "@type": "neuroglancer_segment_properties",
            "inline": {"ids": self._ids.astype(str).tolist(), "properties": []},
        }

    def __len__(self):
        """Number of properties."""
        return len(self._dict["inline"]["properties"])

    def __repr__(self):
        return f"SegmentProperties(segments={len(self._ids)},properties={len(self)})"

    def __str__(self):
        return self.__repr__()

    @property
    def properties(self):
        """Segment properties as {id: type} dictionary."""
        return {p["id"]: p["type"] for p in self._dict["inline"]["properties"]}

    @classmethod
    def from_pandas(cls, data, id_col="id"):
        """Create SegmentProperties from a pandas DataFrame.

        Parameters
        ----------
        data :          pandas DataFrame
                        Dataframe containing the segment properties. Must contain an
                        `id` column. By default columns will be interpreted as follows:
                          - numeric columns (float or int) will be treated as "number" properties
                          - the first string column will be treated as "label" properties;
                             subsequent string columns will be treated as "string" properties
                          - categorical columns and columns of lists will be treated as "tags" properties

        """
        assert isinstance(data, pd.DataFrame), "Input must be a pandas DataFrame"
        assert id_col in data.columns, f"ID col {id_col} not in DataFrame"

        # Instantiate class
        props = cls(data[id_col].values)

        # Fill properties
        for col in data.columns:
            if col == id_col:
                continue

            props.add_property(data[col])

        return props

    @classmethod
    def from_url(cls, url):
        """Create SegmentProperties from a Neuroglancer info URL.

        Parameters
        ----------
        url :           str
                        URL to the Neuroglancer info file. Can be:
                         - a source url (e.g. `precomputed://https://`)
                         - the url to an info file

        """
        assert isinstance(url, str), "`url` must be a string"

        if url.startswith("precomputed://"):
            url = url.replace("precomputed://", "")

        if url.startswith("gs://"):
            path = url.replace("gs://", "")
            url = f"https://storage.googleapis.com/{path}"

        if not url.endswith("info"):
            url = f"{url}/info"

        r = requests.get(url)
        r.raise_for_status()

        json = r.json()

        if not json.get("@type", None) == "neuroglancer_segment_properties":
            if "segment_properties" in json:
                new_url = url.replace("info", f'{json["segment_properties"]}/info')
                return cls.from_url(new_url)
            else:
                raise ValueError(f"Invalid Neuroglancer info file for {url}")

        return cls.from_dict(json)

    @classmethod
    def from_dict(cls, info):
        """Create SegmentProperties from a Neuroglancer info dictionary.

        Parameters
        ----------
        info :          dict
                        Neuroglancer info dictionary.

        """
        assert isinstance(info, dict), "`info` must be a dictionary"

        props = cls(info["inline"]["ids"])
        props._dict = info

        return props

    def add_property(self, data, name=None, type=None, description=None):
        """Add a new property to the segment properties.

        Parameters
        ----------
        data :          pandas Series | iterable
                        Data containing the property values. By default data will
                        be interpreted as follows:
                          - numeric data (float or int) will be treated as "number" properties
                          - the first string data will be treated as "label" properties;
                             subsequent string data will be treated as "string" properties
                          - categorical data/list of lists will be treated as "tags" properties
        name :          str, optional
                        Must be provided if input is not a pandas Series.
        type :          "label" | "description" | "string" | "tags" | "number", optional
                        By default, the type will be inferred from the data.
                        Use this to override the inferred type.
        description :   dict, optional
                        A dictionary mapping values to long descriptions.
                        For example: `{"CA1": "Cornu Ammonis 1", ...}`.

        """
        if not isinstance(data, pd.Series):
            if name is None:
                raise ValueError(
                    "Name must be provided if input is not a pandas Series."
                )
            data = pd.Series(data, name=name)

        if len(data) != len(self._ids):
            raise ValueError(
                f"Data length ({len(data)}) must match number of segments ({len(self._ids)})"
            )

        # Check if we have any NaNs
        if data.isnull().any():
            raise ValueError("Data contains NaNs")

        if type is None:
            if data.dtype.type in NUMBER_DTYPES:
                type = "number"
            elif isinstance(data.dtype, pd.CategoricalDtype):
                type = "tags"
            elif isinstance(data.values[0], list):
                type = "tags"
            elif data.dtype in ("object", "string"):
                # There can only be one "label" property
                if "label" not in self.properties.values():
                    type = "label"
                else:
                    print(
                        f"We already have a `label` property, adding {data.name} as a `string` property."
                    )
                    type = "string"
            else:
                raise ValueError(f"Unsupported dtype {data.dtype}")

        # Tags must not start with "#" and not contain spaces
        if type == "tags":
            prop = _parse_tags_property(data)
        elif type == "label":
            prop = _parse_label_property(data)
        elif type == "number":
            prop = _parse_number_property(data)
        elif type == "string":
            prop = _parse_string_property(data)
        else:
            raise ValueError(f"Unsupported property type {type}")

        self._dict["inline"]["properties"].append(prop)

    def as_dict(self):
        """Return the properties as a dictionary."""
        return self._dict.copy()

    def to_json(self, pretty=False):
        """Generate the JSON-formatted string encoding the properties."""
        return (
            json.dumps(
                self.as_dict(),
                indent=4 if pretty else None,
                sort_keys=True,
            )
            .replace("'", '"')
            .replace("True", "true")
            .replace("False", "false")
        )

    def to_info(self, fp):
        """Write the properties to a Neuroglancer info file.

        Parameters
        ----------
        fp :            str
                        Path to the info file.

        """
        with open(fp, "w") as f:
            f.write(self.to_json(pretty=True))

    def to_pandas(self):
        """Return the properties as a pandas DataFrame."""
        df = pd.DataFrame(index=self._ids)
        for prop in self._dict["inline"]["properties"]:
            df[prop["id"]] = prop["values"]

            if prop["type"] == "tags":
                if isinstance(prop["values"][0], list):
                    df[prop["id"]] = df[prop["id"]].apply(
                        lambda x: [prop["tags"][i] for i in x]
                    )
                else:
                    df[prop["id"]] = df[prop["id"]].map(lambda x: prop["tags"][x])

        return df


def _parse_property(series):
    """Parse pandas Series to Neuroglancer property."""
    pass


def _parse_number_property(series):
    if series.dtype.type not in NUMBER_DTYPES:
        raise ValueError(
            f"Numeric property {series.name} has unsupported dtype {series.dtype}"
        )
    return {
        "type": "number",
        "id": str(series.name),
        "data_type": NUMBER_DTYPES[series.dtype.type],
        "values": series.tolist(),
    }


def _parse_label_property(series):
    return {
        "type": "label",
        "id": str(series.name),
        "values": series.astype(str).tolist(),
    }


def _parse_tags_property(series):
    # series = series.astype(str)

    def fix_tag(tag):
        if not isinstance(tag, str):
            tag = str(tag)

        if tag.startswith("#"):
            tag = tag[1:]

        return tag.replace(" ", "_")

    # Translate tags to numbers
    if isinstance(series.values[0], list):
        # Flatten list of lists
        tags = np.unique([str(t) for l in series.values for t in l])
        tag_dict = {fix_tag(tag): i for i, tag in enumerate(tags)}
        series = series.apply(lambda x: [tag_dict[t] for t in x])
    else:
        tags = series.unique()
        tag_dict = {fix_tag(tag): i for i, tag in enumerate(tags)}
        series = series.map(tag_dict).apply(lambda x: [x])

    return {
        "type": "tags",
        "id": str(series.name),
        "values": series.tolist(),
        "tags": list(tags),
    }


def _parse_string_property(series):
    return {
        "type": "string",
        "id": str(series.name),
        "values": series.astype(str).tolist(),
    }
