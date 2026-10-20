import copy

import pytest

import nglscenes as ngs

# Modelled on a published neuPrint scene: layers omit keys nglscenes has
# defaults for (`selectedAlpha`, `segments`, `blend`, `annotations`, ...)
PUBLISHED = {
    "dimensions": {"x": [8e-9, "m"], "y": [8e-9, "m"], "z": [8e-9, "m"]},
    "position": [17213.5, 19737.5, 20577.5],
    "layout": "xy-3d",
    "layers": [
        {
            "type": "image",
            "source": "precomputed://gs://neuroglancer-janelia-flyem-hemibrain/emdata/clahe_yz/jpeg",
            "name": "emdata",
        },
        {
            "type": "segmentation",
            "source": "precomputed://gs://neuroglancer-janelia-flyem-hemibrain/v1.2/segmentation",
            "segmentColors": {"1734350788": "#FF0000"},
            "name": "segmentation",
        },
        {
            "type": "annotation",
            "source": "precomputed://gs://neuroglancer-janelia-flyem-hemibrain/v1.2/synapses",
            "name": "synapses",
        },
    ],
}

SEUNGLAB_LAYER = {
    "type": "segmentation_with_graph",
    "source": "graphene://https://prod.flywire-daf.com/segmentation/1.0/flywire_public",
    "name": "flywire",
}

SPELUNKER_LAYER = {
    "type": "segmentation",
    "source": {
        "url": "graphene://middleauth+https://prod.flywire-daf.com/segmentation/1.0/flywire_public",
        "subsources": {"bounds": False},
    },
    "name": "flywire",
}


def _scene(*layers):
    return {"layout": "3d", "layers": [copy.deepcopy(l) for l in layers]}


def _url_state(url):
    return ngs.utils.parse_json_scene(url)


# Issue 1
def test_roundtrip_unchanged():
    s = copy.deepcopy(PUBLISHED)
    assert ngs.Scene.from_dict(s).as_dict() == PUBLISHED
    # Input is not modified
    assert s == PUBLISHED


def test_constructed_layers_get_defaults():
    layer = ngs.SegmentationLayer(source="precomputed://gs://x/seg")
    assert "selectedAlpha" in layer
    assert layer["segments"] == []


def test_edits_still_normalised():
    scene = ngs.Scene.from_dict(PUBLISHED)
    seg = scene.layers["segmentation"]
    seg["segments"] = ["10001", "!10002", 10003]
    assert seg["segments"] == ["10001", "!10002", "10003"]


# Issue 2
@pytest.mark.parametrize(
    "base, expected",
    [
        ("https://ngl.cave-explorer.org", "https://ngl.cave-explorer.org/#!"),
        ("https://spelunker.cave-explorer.org/", "https://spelunker.cave-explorer.org/#!"),
        ("https://coda.science/neuroglancer.html", "https://coda.science/neuroglancer.html#!"),
        ("https://x.org?foo=1", "https://x.org/?foo=1#!"),
        ("https://x.org/neuroglancer.html?foo=1", "https://x.org/neuroglancer.html?foo=1#!"),
        ("https://ngl.cave-explorer.org/#!%7B%22layout%22%3A%224panel%22%7D",
         "https://ngl.cave-explorer.org/#!"),
    ],
)
def test_url_base(base, expected):
    scene = ngs.Scene(base_url=base)
    scene["layout"] = "3d"
    url = scene.url
    assert url.startswith(expected)
    assert url.count("#!") == 1
    assert _url_state(url) == scene.as_dict()


# Issue 3
def test_base_url():
    base = "https://ngl.cave-explorer.org/"
    scene = ngs.Scene.from_dict(PUBLISHED, base_url=base)
    assert scene.base_url == base
    assert scene.url.startswith(base + "#!")

    scene.base_url = "https://coda.science/neuroglancer.html"
    assert scene.url.startswith("https://coda.science/neuroglancer.html#!")

    # Explicit base wins over the URL's own
    url = ngs.Scene.from_dict(PUBLISHED).url
    scene = ngs.Scene.from_string(url, base_url=base)
    assert scene.url.startswith(base + "#!")
    assert ngs.Scene.from_string(url).base_url == "https://neuroglancer-demo.appspot.com/"


# Issue 4
@pytest.mark.parametrize("layer", [SEUNGLAB_LAYER, SPELUNKER_LAYER])
def test_graphene_kept_on_parse(layer):
    scene = ngs.Scene.from_dict(_scene(layer))
    assert scene.as_dict()["layers"] == [layer]
    assert isinstance(scene.layers[0], ngs.GrapheneSegmentationLayer)


def test_graphene_constructed_is_mainline():
    layer = ngs.GrapheneSegmentationLayer(
        source=SEUNGLAB_LAYER["source"], type="segmentation_with_graph"
    )
    assert layer["type"] == "segmentation"
    assert layer["source"].startswith("graphene://middleauth+https://")


def test_for_viewer():
    seung = ngs.Scene.from_dict(_scene(SEUNGLAB_LAYER, PUBLISHED["layers"][0]))
    spel = ngs.Scene.from_dict(_scene(SPELUNKER_LAYER, PUBLISHED["layers"][0]))

    x = seung.for_viewer("spelunker")
    assert x.layers[0]["type"] == "segmentation"
    assert x.layers[0]["source"] == SEUNGLAB_LAYER["source"].replace(
        "graphene://", "graphene://middleauth+"
    )
    # Original untouched; non-graphene layers untouched
    assert seung.as_dict()["layers"][0] == SEUNGLAB_LAYER
    assert x.as_dict()["layers"][1] == PUBLISHED["layers"][0]

    # Object source keeps its shape and subsources (issue 5)
    y = spel.for_viewer("seunglab")
    assert y.layers[0]["type"] == "segmentation_with_graph"
    assert y.layers[0]["source"] == {
        "url": SEUNGLAB_LAYER["source"],
        "subsources": {"bounds": False},
    }

    # Idempotent and reversible
    assert x.for_viewer("spelunker").as_dict() == x.as_dict()
    assert y.for_viewer("seunglab").as_dict() == y.as_dict()
    assert y.for_viewer("spelunker").as_dict() == spel.as_dict()

    with pytest.raises(ValueError):
        seung.for_viewer("foo")


def test_layer_as_flavour():
    layer = ngs.Scene.from_dict(_scene(SEUNGLAB_LAYER)).layers[0]
    assert layer.flavour == "seunglab"
    assert layer.as_flavour("mainline").flavour == "mainline"
    assert layer.flavour == "seunglab"


# Issue 5
@pytest.mark.parametrize(
    "source",
    [
        SPELUNKER_LAYER["source"],
        [SPELUNKER_LAYER["source"], "precomputed://gs://x/skeletons"],
    ],
)
def test_graphene_object_source(source):
    layer = ngs.GrapheneSegmentationLayer(source=source)
    urls = ngs.utils.source_urls(layer["source"])
    assert urls[0].startswith("graphene://middleauth+")
    assert type(layer["source"]) is type(source)

    state = _scene({**SEUNGLAB_LAYER, "source": source})
    assert ngs.Scene.from_dict(state).as_dict()["layers"][0]["source"] == source


# Issue 6
def test_unknown_layer_type():
    draft = {"type": "new", "name": "draft"}
    future = {"type": "some_future_type", "name": "future", "source": "x://y"}
    s = _scene(PUBLISHED["layers"][0], draft, future)
    scene = ngs.Scene.from_dict(s)
    assert len(scene) == 3
    assert isinstance(scene.layers["draft"], ngs.GenericLayer)
    assert scene.as_dict() == s
    assert isinstance(str(scene), str)

    with pytest.raises(ValueError):
        ngs.scenes.parse_layers({"name": "no type", "source": "x://y"})
    assert ngs.scenes.parse_layers([future], skip_unknown=True) == []


# Issue 7
def test_layer_map():
    s = {"layers": {"em": {"type": "image", "source": "precomputed://gs://x/em"}}}
    scene = ngs.Scene.from_dict(s)
    assert len(scene) == 1
    assert scene.layers[0].name == "em"
    assert scene.as_dict()["layers"] == [
        {"type": "image", "source": "precomputed://gs://x/em", "name": "em"}
    ]


# Issue 8
def test_compact_url_json():
    scene = ngs.Scene.from_dict(PUBLISHED)
    url = scene.url
    assert "%20" not in url
    assert _url_state(url) == PUBLISHED
    assert ": " in scene.to_json(pretty=True)
