"""The look of nook's maps: a soft, clean, phone-app style, in a light and a dark version.

The shapes come from OpenFreeMap's vector tiles (OpenStreetMap data cut into the OpenMapTiles
layout) and are drawn in the browser by MapLibre. This file is only the paint: colours, road
widths, which labels show when. Tiles and fonts are fetched through nook, so the browser never
talks to anyone else."""

FONT = ["Noto Sans Regular"]
BOLD = ["Noto Sans Bold"]
ITALIC = ["Noto Sans Italic"]

LIGHT = {
    "land": "#f3f0ea", "water": "#a8d4f2", "water_line": "#a8d4f2", "park": "#cfe6b8", "wood": "#c4e0ab", "grass": "#d6ebc0",
    "sand": "#f1e6c8", "ice": "#ffffff", "wetland": "#c9e6c4", "residential": "#efece5", "commercial": "#ebe6dd",
    "industrial": "#e7e4de", "school": "#efe6d6", "hospital": "#f6dcd6", "cemetery": "#d9e6cc", "pitch": "#cfe6b8",
    "building": "#e4e0d7", "building_line": "#d5d0c5", "road": "#ffffff", "road_casing": "#d8d4cb", "minor_casing": "#e1ddd4",
    "motorway": "#fcd37e", "motorway_casing": "#e3b04d", "trunk": "#fde3a3", "trunk_casing": "#e8c070",
    "path": "#d4cfc4", "rail": "#c8c3b8", "aeroway": "#e3e0d9", "boundary": "#b9b4c4",
    "label": "#3a3a3f", "label_soft": "#6e6e75", "halo": "rgba(255,255,255,0.85)", "place": "#1c1c1e",
    "water_label": "#4a8cc0", "park_label": "#5d8a47", "poi": "#8a8a90", "poi_green": "#58a04a", "poi_red": "#e0584b",
    "poi_orange": "#f0932b", "poi_blue": "#3b82d6", "extrusion": "#e6e2d9",
}
DARK = {
    "land": "#1d1e21", "water": "#12293f", "water_line": "#12293f", "park": "#1e3025", "wood": "#1c2e22", "grass": "#213428",
    "sand": "#2c2a22", "ice": "#2b2d30", "wetland": "#1d2e2a", "residential": "#202124", "commercial": "#242529",
    "industrial": "#222326", "school": "#28262a", "hospital": "#33252a", "cemetery": "#1f2c22", "pitch": "#1e3025",
    "building": "#2a2b2f", "building_line": "#35363a", "road": "#3a3b40", "road_casing": "#151618", "minor_casing": "#18191b",
    "motorway": "#8c6c2e", "motorway_casing": "#4b3917", "trunk": "#6e5827", "trunk_casing": "#3d2f14",
    "path": "#45464b", "rail": "#43444a", "aeroway": "#2b2c30", "boundary": "#5a5668",
    "label": "#d6d7dc", "label_soft": "#9a9ba3", "halo": "rgba(29,30,33,0.9)", "place": "#f2f2f7",
    "water_label": "#6aa2d2", "park_label": "#7fb06a", "poi": "#9a9ba3", "poi_green": "#6dbb5d", "poi_red": "#ee7468",
    "poi_orange": "#f5a54a", "poi_blue": "#5a9be8", "extrusion": "#303135",
}


def _width(*stops):
    """Zoom-dependent line width: _width((10, 1), (16, 8))."""
    return {"base": 1.4, "stops": [[z, w] for z, w in stops]}


def _road(id_, classes, fill, casing, widths, min_zoom, extra_filter=None):
    cond = ["match", ["get", "class"], classes, True, False]
    base = ["all", cond] + ([extra_filter] if extra_filter else [])
    return [
        {"id": f"{id_}-casing", "type": "line", "source": "map", "source-layer": "transportation", "minzoom": min_zoom,
         "filter": base, "layout": {"line-cap": "round", "line-join": "round"},
         "paint": {"line-color": casing, "line-width": _width(*[(z, w * 1.55 + 0.4) for z, w in widths])}},
        {"id": id_, "type": "line", "source": "map", "source-layer": "transportation", "minzoom": min_zoom,
         "filter": base, "layout": {"line-cap": "round", "line-join": "round"},
         "paint": {"line-color": fill, "line-width": _width(*widths)}},
    ]


def style(theme, base_url):
    c = DARK if theme == "dark" else LIGHT
    layers = [
        {"id": "background", "type": "background", "paint": {"background-color": c["land"]}},
        {"id": "landcover-grass", "type": "fill", "source": "map", "source-layer": "landcover",
         "filter": ["==", "class", "grass"], "paint": {"fill-color": c["grass"]}},
        {"id": "landcover-wood", "type": "fill", "source": "map", "source-layer": "landcover",
         "filter": ["==", "class", "wood"], "paint": {"fill-color": c["wood"], "fill-opacity": 0.8}},
        {"id": "landcover-sand", "type": "fill", "source": "map", "source-layer": "landcover",
         "filter": ["==", "class", "sand"], "paint": {"fill-color": c["sand"]}},
        {"id": "landcover-ice", "type": "fill", "source": "map", "source-layer": "landcover",
         "filter": ["==", "class", "ice"], "paint": {"fill-color": c["ice"]}},
        {"id": "landcover-wetland", "type": "fill", "source": "map", "source-layer": "landcover",
         "filter": ["==", "class", "wetland"], "paint": {"fill-color": c["wetland"], "fill-opacity": 0.7}},
        {"id": "landuse-residential", "type": "fill", "source": "map", "source-layer": "landuse", "minzoom": 6,
         "filter": ["in", "class", "residential", "suburb", "neighbourhood"],
         "paint": {"fill-color": c["residential"], "fill-opacity": {"stops": [[6, 0.4], [12, 0.8]]}}},
        {"id": "landuse-commercial", "type": "fill", "source": "map", "source-layer": "landuse", "minzoom": 10,
         "filter": ["in", "class", "commercial", "retail"], "paint": {"fill-color": c["commercial"]}},
        {"id": "landuse-industrial", "type": "fill", "source": "map", "source-layer": "landuse", "minzoom": 10,
         "filter": ["in", "class", "industrial", "garages", "railway", "quarry"], "paint": {"fill-color": c["industrial"]}},
        {"id": "landuse-school", "type": "fill", "source": "map", "source-layer": "landuse", "minzoom": 11,
         "filter": ["in", "class", "school", "university", "kindergarten", "college"], "paint": {"fill-color": c["school"]}},
        {"id": "landuse-hospital", "type": "fill", "source": "map", "source-layer": "landuse", "minzoom": 11,
         "filter": ["==", "class", "hospital"], "paint": {"fill-color": c["hospital"]}},
        {"id": "landuse-cemetery", "type": "fill", "source": "map", "source-layer": "landuse", "minzoom": 11,
         "filter": ["==", "class", "cemetery"], "paint": {"fill-color": c["cemetery"]}},
        {"id": "landuse-pitch", "type": "fill", "source": "map", "source-layer": "landuse", "minzoom": 13,
         "filter": ["in", "class", "pitch", "playground", "stadium", "track"], "paint": {"fill-color": c["pitch"]}},
        {"id": "park", "type": "fill", "source": "map", "source-layer": "park",
         "paint": {"fill-color": c["park"], "fill-opacity": {"stops": [[5, 0.5], [12, 1]]}}},
        {"id": "water", "type": "fill", "source": "map", "source-layer": "water",
         "filter": ["!=", "brunnel", "tunnel"], "paint": {"fill-color": c["water"]}},
        {"id": "waterway", "type": "line", "source": "map", "source-layer": "waterway", "minzoom": 9,
         "paint": {"line-color": c["water_line"], "line-width": _width((9, 0.6), (14, 2), (18, 8))}},
        {"id": "aeroway", "type": "fill", "source": "map", "source-layer": "aeroway", "minzoom": 11,
         "filter": ["==", "$type", "Polygon"], "paint": {"fill-color": c["aeroway"]}},
        {"id": "building", "type": "fill", "source": "map", "source-layer": "building", "minzoom": 14, "maxzoom": 16,
         "paint": {"fill-color": c["building"], "fill-outline-color": c["building_line"], "fill-opacity": 0.9}},
    ]
    layers += [
        {"id": "rail", "type": "line", "source": "map", "source-layer": "transportation", "minzoom": 11,
         "filter": ["==", "class", "rail"], "paint": {"line-color": c["rail"], "line-width": _width((11, 0.5), (16, 1.6)),
                                                       "line-dasharray": [3, 3]}},
        {"id": "path", "type": "line", "source": "map", "source-layer": "transportation", "minzoom": 14,
         "filter": ["in", "class", "path", "track"], "paint": {"line-color": c["path"], "line-width": _width((14, 0.6), (18, 2)),
                                                                "line-dasharray": [2, 2]}},
    ]
    layers += _road("service", ["service", "raceway"], c["road"], c["minor_casing"], [(14, 0.6), (18, 5)], 14)
    layers += _road("minor", ["minor"], c["road"], c["minor_casing"], [(12, 0.5), (14, 1.8), (18, 9)], 12)
    layers += _road("tertiary", ["tertiary"], c["road"], c["road_casing"], [(11, 0.6), (14, 2.4), (18, 12)], 11)
    layers += _road("secondary", ["secondary"], c["road"], c["road_casing"], [(9, 0.6), (14, 3), (18, 14)], 9)
    layers += _road("primary", ["primary"], c["road"], c["road_casing"], [(8, 0.6), (14, 3.4), (18, 16)], 8)
    layers += _road("trunk", ["trunk"], c["trunk"], c["trunk_casing"], [(6, 0.5), (14, 3.6), (18, 17)], 6)
    layers += _road("motorway", ["motorway"], c["motorway"], c["motorway_casing"], [(5, 0.5), (14, 4), (18, 18)], 5)
    layers += [
        {"id": "building-3d", "type": "fill-extrusion", "source": "map", "source-layer": "building", "minzoom": 16,
         "paint": {"fill-extrusion-color": c["extrusion"], "fill-extrusion-opacity": 0.8, "fill-extrusion-vertical-gradient": False,
                   "fill-extrusion-height": ["coalesce", ["get", "render_height"], 6],
                   "fill-extrusion-base": ["coalesce", ["get", "render_min_height"], 0]}},
        {"id": "boundary-country", "type": "line", "source": "map", "source-layer": "boundary", "maxzoom": 12,
         "filter": ["all", ["==", "admin_level", 2], ["!=", "maritime", 1]],
         "paint": {"line-color": c["boundary"], "line-width": _width((2, 0.6), (8, 1.4)), "line-dasharray": [3, 2]}},
        {"id": "boundary-state", "type": "line", "source": "map", "source-layer": "boundary", "minzoom": 4, "maxzoom": 12,
         "filter": ["all", ["==", "admin_level", 4], ["!=", "maritime", 1]],
         "paint": {"line-color": c["boundary"], "line-opacity": 0.6, "line-width": 0.8, "line-dasharray": [2, 3]}},
        {"id": "road-names", "type": "symbol", "source": "map", "source-layer": "transportation_name", "minzoom": 13,
         "filter": ["!=", "class", "motorway"],
         "layout": {"symbol-placement": "line", "text-field": ["coalesce", ["get", "name:latin"], ["get", "name"]],
                    "text-font": FONT, "text-size": {"stops": [[13, 10], [18, 13]]}, "text-letter-spacing": 0.02,
                    "text-max-angle": 30},
         "paint": {"text-color": c["label_soft"], "text-halo-color": c["halo"], "text-halo-width": 1.6}},
        {"id": "motorway-names", "type": "symbol", "source": "map", "source-layer": "transportation_name", "minzoom": 10,
         "filter": ["==", "class", "motorway"],
         "layout": {"symbol-placement": "line", "text-field": ["coalesce", ["get", "name:latin"], ["get", "name"], ["get", "ref"]],
                    "text-font": FONT, "text-size": 11, "text-max-angle": 30},
         "paint": {"text-color": c["label_soft"], "text-halo-color": c["halo"], "text-halo-width": 1.6}},
        {"id": "water-names", "type": "symbol", "source": "map", "source-layer": "water_name", "minzoom": 3,
         "layout": {"text-field": ["coalesce", ["get", "name:latin"], ["get", "name"]], "text-font": ITALIC,
                    "text-size": {"stops": [[3, 10], [14, 13]]}, "text-letter-spacing": 0.08, "text-max-width": 8},
         "paint": {"text-color": c["water_label"], "text-halo-color": c["halo"], "text-halo-width": 1}},
        {"id": "poi-dots", "type": "circle", "source": "map", "source-layer": "poi", "minzoom": 15,
         "filter": ["<=", ["get", "rank"], ["step", ["zoom"], 12, 16, 25, 17, 50, 18, 200]],
         "paint": {"circle-radius": {"stops": [[15, 3], [18, 5]]},
                   "circle-color": ["match", ["get", "class"],
                                    ["restaurant", "cafe", "fast_food", "bar", "ice_cream", "bakery", "food_court"], c["poi_orange"],
                                    ["park", "garden", "playground", "campsite", "golf"], c["poi_green"],
                                    ["hospital", "pharmacy", "doctors", "dentist", "clinic"], c["poi_red"],
                                    ["school", "college", "library", "museum", "theatre", "cinema", "town_hall"], c["poi_blue"],
                                    c["poi"]],
                   "circle-stroke-color": c["halo"], "circle-stroke-width": 1.5}},
        {"id": "poi-names", "type": "symbol", "source": "map", "source-layer": "poi", "minzoom": 16,
         "filter": ["<=", ["get", "rank"], ["step", ["zoom"], 14, 17, 40, 18, 200]],
         "layout": {"text-field": ["coalesce", ["get", "name:latin"], ["get", "name"]], "text-font": FONT, "text-size": 11,
                    "text-offset": [0, 0.9], "text-anchor": "top", "text-max-width": 7},
         "paint": {"text-color": c["label"], "text-halo-color": c["halo"], "text-halo-width": 1.4}},
        {"id": "aerodrome-names", "type": "symbol", "source": "map", "source-layer": "aerodrome_label", "minzoom": 9,
         "layout": {"text-field": ["coalesce", ["get", "name:latin"], ["get", "name"]], "text-font": FONT, "text-size": 11, "text-max-width": 7},
         "paint": {"text-color": c["label_soft"], "text-halo-color": c["halo"], "text-halo-width": 1.4}},
        {"id": "place-neighbourhood", "type": "symbol", "source": "map", "source-layer": "place", "minzoom": 13, "maxzoom": 17,
         "filter": ["in", "class", "neighbourhood", "quarter", "suburb"],
         "layout": {"text-field": ["coalesce", ["get", "name:latin"], ["get", "name"]], "text-font": FONT,
                    "text-size": {"stops": [[13, 10], [16, 13]]}, "text-transform": "uppercase", "text-letter-spacing": 0.1, "text-max-width": 7},
         "paint": {"text-color": c["label_soft"], "text-halo-color": c["halo"], "text-halo-width": 1.4}},
        {"id": "place-village", "type": "symbol", "source": "map", "source-layer": "place", "minzoom": 8,
         "filter": ["in", "class", "village", "hamlet", "isolated_dwelling"],
         "layout": {"text-field": ["coalesce", ["get", "name:latin"], ["get", "name"]], "text-font": FONT,
                    "text-size": {"stops": [[8, 10], [14, 14]]}, "text-max-width": 7},
         "paint": {"text-color": c["label"], "text-halo-color": c["halo"], "text-halo-width": 1.6}},
        {"id": "place-town", "type": "symbol", "source": "map", "source-layer": "place", "minzoom": 6,
         "filter": ["==", "class", "town"],
         "layout": {"text-field": ["coalesce", ["get", "name:latin"], ["get", "name"]], "text-font": BOLD,
                    "text-size": {"stops": [[6, 11], [14, 17]]}, "text-max-width": 7},
         "paint": {"text-color": c["place"], "text-halo-color": c["halo"], "text-halo-width": 1.8}},
        {"id": "place-city", "type": "symbol", "source": "map", "source-layer": "place", "minzoom": 3,
         "filter": ["==", "class", "city"],
         "layout": {"text-field": ["coalesce", ["get", "name:latin"], ["get", "name"]], "text-font": BOLD,
                    "text-size": {"stops": [[3, 11], [8, 15], [14, 20]]}, "text-max-width": 8},
         "paint": {"text-color": c["place"], "text-halo-color": c["halo"], "text-halo-width": 2}},
        {"id": "place-state", "type": "symbol", "source": "map", "source-layer": "place", "minzoom": 4, "maxzoom": 9,
         "filter": ["in", "class", "state", "province"],
         "layout": {"text-field": ["coalesce", ["get", "name:latin"], ["get", "name"]], "text-font": FONT,
                    "text-size": 11, "text-transform": "uppercase", "text-letter-spacing": 0.12, "text-max-width": 8},
         "paint": {"text-color": c["label_soft"], "text-halo-color": c["halo"], "text-halo-width": 1.4}},
        {"id": "place-country", "type": "symbol", "source": "map", "source-layer": "place", "maxzoom": 8,
         "filter": ["==", "class", "country"],
         "layout": {"text-field": ["coalesce", ["get", "name:latin"], ["get", "name"]], "text-font": BOLD,
                    "text-size": {"stops": [[1, 11], [6, 16]]}, "text-transform": "uppercase", "text-letter-spacing": 0.08, "text-max-width": 7},
         "paint": {"text-color": c["place"], "text-halo-color": c["halo"], "text-halo-width": 2}},
    ]
    return {
        "version": 8, "name": f"nook {theme}",
        "sources": {"map": {"type": "vector", "tiles": [base_url.rstrip("/") + "/vt/{z}/{x}/{y}"], "minzoom": 0, "maxzoom": 14,
                            "attribution": "OpenFreeMap, OpenMapTiles, OpenStreetMap contributors"}},
        "glyphs": base_url.rstrip("/") + "/glyphs/{fontstack}/{range}",
        "layers": layers,
    }
