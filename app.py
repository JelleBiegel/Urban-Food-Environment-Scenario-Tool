import asyncio



import csv



import json



import os

import socket



import shutil



import tempfile



import zipfile



from pathlib import Path



import matplotlib.pyplot as plt



import pandas as pd



import shapefile



import streamlit as st



import websockets
from websockets.exceptions import ConnectionClosed



from matplotlib.lines import Line2D



from matplotlib.patches import Patch



from pyproj import CRS, Transformer



import requests



import pydeck as pdk



from shapely.geometry import shape, Point
from shapely.ops import transform as shapely_transform



import math



# ---------------------------------------------------------------------



# CONFIGURATION



# ---------------------------------------------------------------------



PROJECT_ROOT = Path(__file__).resolve().parent



RUNTIME_DIR = PROJECT_ROOT / ".runtime"



RUNTIME_DIR.mkdir(exist_ok=True)



LOCAL_OSM_FILE = (



    PROJECT_ROOT



    / "Data"



    / "osm"



    / "noord_holland_food_environment.geojson"



)



MODEL = Path(



    os.getenv(



        "GAMA_MODEL_PATH",



        str(PROJECT_ROOT / "models" / "Food_outlets_on_Strandeiland.gaml"),



    )



)



OUTPUT = Path(



    os.getenv(



        "GAMA_OUTPUT_PATH",



        str(PROJECT_ROOT / "Results" / "web_result.csv"),



    )



)



GAMA_URI = os.getenv("GAMA_URI", "ws://gama:6868").strip()



NUMBER_OF_RUNS = 5



RUN_TIMEOUT_SECONDS = 180



GAMA_CONNECT_RETRY_SECONDS = 30



GAMA_CONNECT_RETRY_INTERVAL_SECONDS = 2



GAMA_RUN_RETRY_LIMIT = 1



SELECT_CATEGORY = "-- Select category --"



IGNORE_CATEGORY = "-- Ignore / not used --"



GAMA_TYPES = [



    "Nature",



    "Residential",



    "School",



    "Fastfood",



    "Grillroom",



    "Sweet shop",



    "Liquor store",



    "Tobacconist",



    "Gas station",



    "Pastry shop",



    "Chocolate shop",



    "Drug store",



    "Ice cream shop",



    "Take-away",



    "Pancake restaurant",



    "Café",



    "Night shop",



    "Café-restaurant",



    "Lunchroom",



    "Cheese store",



    "Restaurant",



    "Butcher",



    "Delicacies shop",



    "Mini mart",



    "Poulterer",



    "Reform/bio shop",



    "Bakery",



    "Coffee/tea shop",



    "Asian supermarket",



    "Supermarket",



    "Turkish Supermarket",



    "Nut shop",



    "Fish store",



    "Vegetable store",



]



FOOD_OUTLET_TYPES = [



    category



    for category in GAMA_TYPES



    if category not in {



        "Nature",



        "Residential",



        "School",



    }



]



# ---------------------------------------------------------------------



# SHAPEFILE HELPERS



# ---------------------------------------------------------------------



def prepare_shapefile(uploaded_zip):



    """Extract one shapefile ZIP and return the .shp path."""



    upload_folder = Path(



    tempfile.mkdtemp(



        prefix="food_environment_",



        dir=RUNTIME_DIR



        )



    )



    zip_path = upload_folder / "uploaded_environment.zip"



    with open(zip_path, "wb") as file:



        file.write(uploaded_zip.getbuffer())



    with zipfile.ZipFile(zip_path, "r") as zip_ref:



        zip_ref.extractall(upload_folder)



    shapefiles = [



        path



        for path in upload_folder.rglob("*.shp")



        if "__MACOSX" not in path.parts



        and not path.name.startswith("._")



    ]



    if not shapefiles:



        raise ValueError(



            "No .shp file was found in the ZIP."



        )



    if len(shapefiles) > 1:



        raise ValueError(



            "The ZIP contains more than one .shp file. "



            "Please upload one shapefile per ZIP."



        )



    shp = shapefiles[0]



    for extension in [".shp", ".shx", ".dbf", ".prj"]:



        component = shp.with_suffix(extension)



        if not component.exists():



            raise ValueError(



                f"Missing {extension} file for {shp.name}."



            )



    return str(shp)



def get_shapefile_fields(shp_path):



    with shapefile.Reader(shp_path) as reader:



        return [



            field[0]



            for field in reader.fields[1:]



        ]



def get_unique_values(shp_path, field_name):



    with shapefile.Reader(shp_path) as reader:



        field_names = [



            field[0]



            for field in reader.fields[1:]



        ]



        field_index = field_names.index(field_name)



        values = set()



        for record in reader.records():



            value = record[field_index]



            if value is None or str(value).strip() == "":



                cleaned_value = "<blank>"



            else:



                cleaned_value = str(value).strip()



            values.add(cleaned_value)



        return sorted(values)



def get_value_counts(shp_path, field_name):



    with shapefile.Reader(shp_path) as reader:



        field_names = [



            field[0]



            for field in reader.fields[1:]



        ]



        field_index = field_names.index(field_name)



        counts = {}



        for record in reader.records():



            value = record[field_index]



            if value is None or str(value).strip() == "":



                cleaned_value = "<blank>"



            else:



                cleaned_value = str(value).strip()



            counts[cleaned_value] = (



                counts.get(cleaned_value, 0) + 1



            )



        return counts



AMSTERDAM_NEIGHBOURHOODS_URL = (



    "https://api.data.amsterdam.nl/v1/gebieden/wijken/"



)



@st.cache_data(ttl=86400)



def load_amsterdam_neighbourhoods():



    """Load Amsterdam neighbourhood names from the official Amsterdam API."""



    neighbourhoods = []



    url = AMSTERDAM_NEIGHBOURHOODS_URL



    params = {



        "_pageSize": 100,



        "_sort": "naam",



        "_fields": "naam,identificatie",



    }



    while url:



        response = requests.get(



            url,



            params=params,



            headers={"Accept": "application/hal+json"},



            timeout=60,



        )



        response.raise_for_status()



        data = response.json()



        records = data.get("_embedded", {}).get("wijken", [])



        for record in records:



            neighbourhoods.append(



                {



                    "name": record.get("naam"),



                    "id": record.get("identificatie"),



                }



            )



        next_link = data.get("_links", {}).get("next")



        if next_link:



            url = next_link["href"]



            params = None



        else:



            url = None



    return neighbourhoods



@st.cache_data(ttl=86400)



def load_amsterdam_neighbourhood_geometry(neighbourhood_id):



    """Load the geometry of one selected Amsterdam neighbourhood."""



    response = requests.get(



        AMSTERDAM_NEIGHBOURHOODS_URL,



        params={



            "identificatie": neighbourhood_id,



            "_pageSize": 1,



            "_fields": "naam,identificatie,geometrie",



        },



        headers={



            "Accept": "application/hal+json",



            "Accept-Crs": "urn:ogc:def:crs:OGC::CRS84",



        },



        timeout=60,



    )



    response.raise_for_status()



    data = response.json()



    records = data.get("_embedded", {}).get("wijken", [])



    if not records:



        raise ValueError(



            "No geometry was found for the selected neighbourhood."



        )



    return records[0]["geometrie"]



def get_geometry_center(geometry):



    """Calculate an approximate centre for Polygon/MultiPolygon GeoJSON."""



    coordinate_pairs = []



    def collect_coordinates(value):



        if (



            isinstance(value, list)



            and len(value) >= 2



            and isinstance(value[0], (int, float))



            and isinstance(value[1], (int, float))



        ):



            coordinate_pairs.append(value[:2])



        elif isinstance(value, list):



            for item in value:



                collect_coordinates(item)



    collect_coordinates(geometry["coordinates"])



    longitudes = [point[0] for point in coordinate_pairs]



    latitudes = [point[1] for point in coordinate_pairs]



    return {



        "longitude": sum(longitudes) / len(longitudes),



        "latitude": sum(latitudes) / len(latitudes),



    }



AMSTERDAM_BAG_WFS_URL = (



    "https://api.data.amsterdam.nl/v1/wfs/bag/"



)



def get_geometry_bounds(geometry):



    """Return min/max longitude and latitude of a GeoJSON geometry."""



    geom = shape(geometry)



    min_lon, min_lat, max_lon, max_lat = geom.bounds



    return min_lon, min_lat, max_lon, max_lat



@st.cache_data(ttl=86400)



def load_amsterdam_buildings(neighbourhood_geometry):



    """



    Load BAG building polygons around the selected neighbourhood



    and retain only buildings intersecting the neighbourhood.



    """



    neighbourhood_shape = shape(



        neighbourhood_geometry



    )



    min_lon, min_lat, max_lon, max_lat = (



        get_geometry_bounds(



            neighbourhood_geometry



        )



    )



    response = requests.get(



        AMSTERDAM_BAG_WFS_URL,



        params={



            "SERVICE": "WFS",



            "VERSION": "2.0.0",



            "REQUEST": "GetFeature",



            "TYPENAMES": "app:panden",



            "OUTPUTFORMAT": "geojson",



            "SRSNAME": "urn:ogc:def:crs:OGC::CRS84",



            "BBOX": (



                f"{min_lon},{min_lat},"



                f"{max_lon},{max_lat},"



                "urn:ogc:def:crs:OGC::CRS84"



            ),



        },



        timeout=60,



    )



    response.raise_for_status()



    data = response.json()



    selected_features = []



    for feature in data.get("features", []):



        geometry = feature.get("geometry")



        if geometry is None:



            continue



        building_shape = shape(geometry)



        if building_shape.intersects(



            neighbourhood_shape



        ):

            properties = feature.get("properties", {}) or {}

            building_id = str(
                properties.get("identificatie")
                or properties.get("id")
                or feature.get("id")
                or f"building_{len(selected_features)}"
            )

            properties["building_id"] = building_id
            properties["name"] = f"Residential location {building_id}"
            properties["gama_type"] = "Residential"
            properties["source"] = "BAG"

            feature["properties"] = properties

            selected_features.append(feature)



    return {



        "type": "FeatureCollection",



        "features": selected_features,



    }



def classify_osm_poi(tags):



    """Translate OpenStreetMap tags to GAMA categories."""



    amenity = str(tags.get("amenity", "") or "")



    shop = str(tags.get("shop", "") or "")



    cuisine = str(tags.get("cuisine", "") or "").lower()



    butcher_type = str(tags.get("butcher", "") or "").lower()



    # Schools



    if amenity == "school":



        return "School"



    # Food service



    if amenity == "fast_food":



        return "Fastfood"



    if amenity == "restaurant":



        if "pancake" in cuisine:



            return "Pancake restaurant"



        return "Restaurant"



    if amenity in {"cafe", "bar", "pub"}:



        return "Café"



    if amenity == "ice_cream":



        return "Ice cream shop"



    if amenity == "fuel":



        return "Gas station"



    # Food retail



    shop_mapping = {



        "supermarket": "Supermarket",



        "convenience": "Mini mart",



        "bakery": "Bakery",



        "cheese": "Cheese store",



        "chocolate": "Chocolate shop",



        "confectionery": "Sweet shop",



        "alcohol": "Liquor store",



        "wine": "Liquor store",



        "tobacco": "Tobacconist",



        "pastry": "Pastry shop",



        "deli": "Delicacies shop",



        "health_food": "Reform/bio shop",



        "nuts": "Nut shop",



        "seafood": "Fish store",



        "greengrocer": "Vegetable store",



        "coffee": "Coffee/tea shop",



        "tea": "Coffee/tea shop",



        "chemist": "Drug store",



    }



    if shop == "butcher":



        if "poultry" in butcher_type:



            return "Poulterer"



        return "Butcher"



    return shop_mapping.get(shop)



def distance_metres(lat1, lon1, lat2, lon2):



    """Approximate distance between two WGS84 coordinates."""



    earth_radius = 6371000



    phi1 = math.radians(lat1)



    phi2 = math.radians(lat2)



    delta_phi = math.radians(lat2 - lat1)



    delta_lambda = math.radians(lon2 - lon1)



    a = (



        math.sin(delta_phi / 2) ** 2



        + math.cos(phi1)



        * math.cos(phi2)



        * math.sin(delta_lambda / 2) ** 2



    )



    return earth_radius * 2 * math.atan2(



        math.sqrt(a),



        math.sqrt(1 - a),



    )



def deduplicate_osm_pois(pois):



    """Remove likely duplicate OSM locations."""



    unique_pois = []



    for poi in pois:



        duplicate = False



        for existing in unique_pois:



            if poi["gama_type"] != existing["gama_type"]:



                continue



            poi_name = poi["name"].strip().lower()



            existing_name = existing["name"].strip().lower()



            # Named locations must have the same name.



            if (



                poi_name != "unnamed location"



                and existing_name != "unnamed location"



                and poi_name != existing_name



            ):



                continue



            distance = distance_metres(



                poi["latitude"],



                poi["longitude"],



                existing["latitude"],



                existing["longitude"],



            )



            # OSM can represent the same school or outlet as both



            # a point and a polygon/relation.



            if distance <= 60:



                duplicate = True



                break



        if not duplicate:



            unique_pois.append(poi)



    return unique_pois



@st.cache_data(show_spinner=False)



def load_osm_food_environment(



    neighbourhood_geometry,



    osm_file_mtime_ns,



):



    """



    Load schools and food outlets from the local OpenStreetMap GeoJSON



    and retain only locations inside the selected Amsterdam wijk.



    """



    if not LOCAL_OSM_FILE.exists():



        raise FileNotFoundError(



            "Local OpenStreetMap file not found at "



            f"{LOCAL_OSM_FILE}."



        )



    # osm_file_mtime_ns is intentionally part of the function signature.



    # It makes Streamlit invalidate this cache automatically when the



    # local GeoJSON file is replaced with a newer extract.



    _ = osm_file_mtime_ns



    with open(



        LOCAL_OSM_FILE,



        "r",



        encoding="utf-8",



    ) as file:



        osm_data = json.load(file)



    neighbourhood_shape = shape(



        neighbourhood_geometry



    )



    pois = []



    for feature_index, feature in enumerate(



        osm_data.get("features", [])



        ):



        geometry = feature.get("geometry")



        properties = feature.get("properties", {}) or {}



        if geometry is None:



            continue



        gama_type = classify_osm_poi(



            properties



        )



        if gama_type is None:



            continue



        try:



            osm_geometry = shape(



                geometry



            )



        except Exception:



            continue



        if osm_geometry.is_empty:



            continue



        if osm_geometry.geom_type == "Point":



            point = osm_geometry



        else:



            point = osm_geometry.representative_point()



        if not neighbourhood_shape.covers(point):



            continue



        osm_identifier = (



            properties.get("@id")



            or properties.get("id")



            or feature.get("id")



            or f"local_{feature_index}"



        )



        pois.append(



            {



                "osm_id": str(osm_identifier),



                "name": str(



                    properties.get(



                        "name",



                        "Unnamed location",



                    )



                    or "Unnamed location"



                ),



                "gama_type": gama_type,



                "latitude": float(point.y),



                "longitude": float(point.x),



                "source": "OpenStreetMap",



            }



        )



    return deduplicate_osm_pois(



        pois



    )




AMSTERDAM_BRT10_WFS_URL = (
    "https://api.data.amsterdam.nl/v1/wfs/brt10/"
)

RD_CRS = CRS.from_epsg(28992)
WGS84_TO_RD = Transformer.from_crs(
    "EPSG:4326",
    "EPSG:28992",
    always_xy=True,
)


@st.cache_data(ttl=86400, show_spinner=False)
def load_amsterdam_roads(neighbourhood_geometry):
    """
    Load BRT10 road centre lines intersecting the selected neighbourhood.

    The BGT ``kruinlijn`` is not a street centreline; it describes crest
    lines associated with terrain/road slopes and is therefore often absent.
    TOP10NL/BRT10 exposes dedicated road centre geometry (wegdeel hartlijnen),
    which is the appropriate line network for the GAMA street layer.
    """
    neighbourhood_shape = shape(neighbourhood_geometry)
    min_lon, min_lat, max_lon, max_lat = get_geometry_bounds(
        neighbourhood_geometry
    )

    # Prefer the dedicated road-centre geometry. If a neighbourhood happens
    # to have no heartlines in BRT10, fall back to the general road line
    # geometry rather than failing immediately.
    road_typenames = [
        "app:wegdeelhartlijnen-geometrie_lijn",
        "app:wegdelen-geometrie_lijn",
    ]

    for typename in road_typenames:
        response = requests.get(
            AMSTERDAM_BRT10_WFS_URL,
            params={
                "SERVICE": "WFS",
                "VERSION": "2.0.0",
                "REQUEST": "GetFeature",
                "TYPENAMES": typename,
                "OUTPUTFORMAT": "geojson",
                "SRSNAME": "urn:ogc:def:crs:OGC::CRS84",
                "COUNT": 10000,
                "BBOX": (
                    f"{min_lon},{min_lat},"
                    f"{max_lon},{max_lat},"
                    "urn:ogc:def:crs:OGC::CRS84"
                ),
            },
            timeout=90,
        )
        response.raise_for_status()
        data = response.json()

        selected_features = []
        for feature in data.get("features", []):
            geometry = feature.get("geometry")
            if geometry is None:
                continue

            try:
                road_shape = shape(geometry)
            except Exception:
                continue

            if road_shape.is_empty or not road_shape.intersects(
                neighbourhood_shape
            ):
                continue

            clipped = road_shape.intersection(neighbourhood_shape)
            if clipped.is_empty:
                continue

            selected_features.append(
                {
                    "type": "Feature",
                    "properties": {
                        **(feature.get("properties", {}) or {}),
                        "road_source_layer": typename,
                    },
                    "geometry": clipped.__geo_interface__,
                }
            )

        if selected_features:
            return {
                "type": "FeatureCollection",
                "features": selected_features,
                "source_layer": typename,
            }

    return {
        "type": "FeatureCollection",
        "features": [],
        "source_layer": None,
    }


def transform_wgs84_geometry_to_rd(geometry):
    """Transform a Shapely geometry from WGS84 lon/lat to EPSG:28992."""
    return shapely_transform(
        WGS84_TO_RD.transform,
        geometry,
    )


def write_shapefile_projection(base_path, crs=RD_CRS):
    """Write .prj and .cpg sidecars for a generated shapefile."""
    base_path = Path(base_path)
    base_path.with_suffix(".prj").write_text(
        crs.to_wkt(version="WKT1_ESRI"),
        encoding="utf-8",
    )
    base_path.with_suffix(".cpg").write_text(
        "UTF-8",
        encoding="utf-8",
    )


def iter_polygon_parts(geometry):
    """Yield Polygon/MultiPolygon parts from an arbitrary geometry."""
    if geometry.is_empty:
        return
    if geometry.geom_type in {"Polygon", "MultiPolygon"}:
        yield geometry
        return
    if geometry.geom_type == "GeometryCollection":
        for part in geometry.geoms:
            yield from iter_polygon_parts(part)


def iter_line_parts(geometry):
    """Yield LineString/MultiLineString parts from an arbitrary geometry."""
    if geometry.is_empty:
        return
    if geometry.geom_type in {"LineString", "MultiLineString"}:
        yield geometry
        return
    if geometry.geom_type == "GeometryCollection":
        for part in geometry.geoms:
            yield from iter_line_parts(part)


def create_amsterdam_gama_inputs(
    neighbourhood_id,
    neighbourhood_geometry,
    neighbourhood_buildings,
    school_pois,
    food_outlet_pois,
):
    """
    Build temporary GAMA-compatible shapefiles for an edited Amsterdam
    scenario. Buildings/locations, roads and boundary are all written in
    EPSG:28992 so distances remain metre-based.
    """
    scenario_folder = Path(
        tempfile.mkdtemp(
            prefix=f"amsterdam_{neighbourhood_id}_",
            dir=RUNTIME_DIR,
        )
    )

    buildings_base = scenario_folder / "amsterdam_locations"
    roads_base = scenario_folder / "amsterdam_roads"
    boundary_base = scenario_folder / "amsterdam_boundary"

    # -----------------------------------------------------------------
    # Locations / buildings
    # -----------------------------------------------------------------
    converted_types = {
        str(poi.get("building_id")): poi.get("gama_type")
        for poi in food_outlet_pois
        if poi.get("is_converted")
    }

    location_counts = {}
    with shapefile.Writer(
        str(buildings_base),
        shapeType=shapefile.POLYGON,
    ) as writer:
        writer.field("Nature", "C", size=50)
        writer.field("Name", "C", size=120)
        writer.field("Source", "C", size=40)

        # BAG buildings form the residential base. A converted building is
        # written once with its selected food-outlet category instead.
        for feature in neighbourhood_buildings.get("features", []):
            geometry = feature.get("geometry")
            if geometry is None:
                continue

            properties = feature.get("properties", {}) or {}
            building_id = str(properties.get("building_id", ""))
            category = converted_types.get(
                building_id,
                "Residential",
            )

            try:
                building_rd = transform_wgs84_geometry_to_rd(
                    shape(geometry)
                )
            except Exception:
                continue

            for polygon_part in iter_polygon_parts(building_rd):
                writer.shape(polygon_part.__geo_interface__)
                writer.record(
                    category,
                    str(properties.get("name", building_id))[:120],
                    (
                        "Scenario conversion"
                        if building_id in converted_types
                        else "BAG"
                    ),
                )
                location_counts[category] = (
                    location_counts.get(category, 0) + 1
                )

        # Existing schools are point POIs. Represent them as small polygons
        # so they can live in the same polygon shapefile expected by GAMA.
        for poi in school_pois:
            point_rd = transform_wgs84_geometry_to_rd(
                Point(
                    float(poi["longitude"]),
                    float(poi["latitude"]),
                )
            )
            school_polygon = point_rd.buffer(4.0)
            writer.shape(school_polygon.__geo_interface__)
            writer.record(
                "School",
                str(poi.get("name", "School"))[:120],
                str(poi.get("source", "OpenStreetMap"))[:40],
            )
            location_counts["School"] = (
                location_counts.get("School", 0) + 1
            )

        # Existing and edited OSM outlets are also represented by small
        # polygons. Converted residential buildings were already written
        # above, using their full BAG footprint, so skip their markers here.
        for poi in food_outlet_pois:
            if poi.get("is_converted"):
                continue

            category = str(poi.get("gama_type", "")).strip()
            if category not in FOOD_OUTLET_TYPES:
                continue

            point_rd = transform_wgs84_geometry_to_rd(
                Point(
                    float(poi["longitude"]),
                    float(poi["latitude"]),
                )
            )
            outlet_polygon = point_rd.buffer(4.0)
            writer.shape(outlet_polygon.__geo_interface__)
            writer.record(
                category,
                str(poi.get("name", category))[:120],
                str(poi.get("source", "OpenStreetMap"))[:40],
            )
            location_counts[category] = (
                location_counts.get(category, 0) + 1
            )

    write_shapefile_projection(buildings_base)

    # -----------------------------------------------------------------
    # Study-area boundary
    # -----------------------------------------------------------------
    boundary_rd = transform_wgs84_geometry_to_rd(
        shape(neighbourhood_geometry)
    )
    with shapefile.Writer(
        str(boundary_base),
        shapeType=shapefile.POLYGON,
    ) as writer:
        writer.field("ID", "C", size=80)
        for polygon_part in iter_polygon_parts(boundary_rd):
            writer.shape(polygon_part.__geo_interface__)
            writer.record(str(neighbourhood_id))
    write_shapefile_projection(boundary_base)

    # -----------------------------------------------------------------
    # Road network
    # -----------------------------------------------------------------
    road_features = load_amsterdam_roads(
        neighbourhood_geometry
    )
    road_count = 0
    with shapefile.Writer(
        str(roads_base),
        shapeType=shapefile.POLYLINE,
    ) as writer:
        writer.field("ID", "N", size=12, decimal=0)

        for feature in road_features.get("features", []):
            geometry = feature.get("geometry")
            if geometry is None:
                continue

            try:
                road_rd = transform_wgs84_geometry_to_rd(
                    shape(geometry)
                )
            except Exception:
                continue

            for line_part in iter_line_parts(road_rd):
                road_count += 1
                writer.shape(line_part.__geo_interface__)
                writer.record(road_count)

    write_shapefile_projection(roads_base)

    if road_count == 0:
        raise ValueError(
            "No BRT10 road centre/line features were found for the selected Amsterdam neighbourhood."
        )

    if location_counts.get("School", 0) == 0:
        raise ValueError(
            "No schools were found in the selected Amsterdam neighbourhood."
        )

    if location_counts.get("Residential", 0) == 0:
        raise ValueError(
            "No residential buildings remain in the selected Amsterdam scenario."
        )

    return {
        "buildings": str(buildings_base.with_suffix(".shp")),
        "roads": str(roads_base.with_suffix(".shp")),
        "boundary": str(boundary_base.with_suffix(".shp")),
        "location_counts": location_counts,
        "road_count": road_count,
    }


def normalize_building_type_field(



    shp_path,



    selected_field,



    value_mapping,



):



    """



    Create a temporary buildings shapefile whose selected type field is



    always called 'Nature' and contains the mapped GAMA categories.



    """



    original_path = Path(shp_path)



    output_base = original_path.with_name(



        original_path.stem + "_normalized"



    )



    with shapefile.Reader(shp_path) as reader:



        field_names = [



            field[0]



            for field in reader.fields[1:]



        ]



        selected_index = field_names.index(



            selected_field



        )



        writer = shapefile.Writer(



            str(output_base),



            shapeType=reader.shapeType,



        )



        try:



            for field in reader.fields[1:]:



                field_name = field[0]



                if field_name == selected_field:



                    # The mapped values are strings, even if the source



                    # municipality used numeric codes.



                    writer.field(



                        "Nature",



                        "C",



                        size=50,



                    )



                elif (



                    field_name == "Nature"



                    and selected_field != "Nature"



                ):



                    writer.field(



                        "Nature_old",



                        field[1],



                        size=field[2],



                        decimal=field[3],



                    )



                else:



                    writer.field(



                        field_name,



                        field[1],



                        size=field[2],



                        decimal=field[3],



                    )



            for shape_record in reader.iterShapeRecords():



                writer.shape(shape_record.shape)



                record = list(



                    shape_record.record



                )



                raw_value = record[selected_index]



                if (



                    raw_value is None



                    or str(raw_value).strip() == ""



                ):



                    cleaned_value = "<blank>"



                else:



                    cleaned_value = str(



                        raw_value



                    ).strip()



                mapped_value = value_mapping[



                    cleaned_value



                ]



                if mapped_value == IGNORE_CATEGORY:



                    mapped_value = "__IGNORE__"



                record[selected_index] = mapped_value



                writer.record(*record)



        finally:



            writer.close()



    for extension in [".prj", ".cpg"]:



        source = original_path.with_suffix(



            extension



        )



        destination = output_base.with_suffix(



            extension



        )



        if source.exists():



            shutil.copyfile(



                source,



                destination,



            )



    return str(



        output_base.with_suffix(".shp")



    )



def get_shapefile_crs(shp_path):



    prj_path = Path(shp_path).with_suffix(".prj")



    if not prj_path.exists():



        raise ValueError(



            f"No .prj file found for {Path(shp_path).name}."



        )



    wkt = prj_path.read_text(



        encoding="utf-8",



        errors="ignore",



    )



    return CRS.from_wkt(wkt)



def validate_crs(



    buildings_shapefile,



    roads_shapefile,



    boundary_shapefile,



):



    buildings_crs = get_shapefile_crs(



        buildings_shapefile



    )



    roads_crs = get_shapefile_crs(



        roads_shapefile



    )



    boundary_crs = get_shapefile_crs(



        boundary_shapefile



    )



    same_crs = (



        buildings_crs.equals(roads_crs)



        and buildings_crs.equals(boundary_crs)



    )



    return {



        "buildings": buildings_crs,



        "roads": roads_crs,



        "boundary": boundary_crs,



        "same_crs": same_crs,



    }



def get_geometry_type(shp_path):



    with shapefile.Reader(shp_path) as reader:



        shape_type = reader.shapeType



    polygon_types = {5, 15, 25}



    polyline_types = {3, 13, 23}



    point_types = {1, 11, 21}



    if shape_type in polygon_types:



        return "Polygon"



    if shape_type in polyline_types:



        return "Polyline"



    if shape_type in point_types:



        return "Point"



    return f"Other ({shape_type})"



# ---------------------------------------------------------------------



# SCENARIO PREVIEW



# ---------------------------------------------------------------------



def plot_polygon_shape(ax, shape, **kwargs):



    points = shape.points



    parts = list(shape.parts) + [len(points)]



    for index in range(len(parts) - 1):



        part = points[



            parts[index]:parts[index + 1]



        ]



        if part:



            xs = [point[0] for point in part]



            ys = [point[1] for point in part]



            ax.fill(



                xs,



                ys,



                **kwargs,



            )



def plot_line_shape(ax, shape, **kwargs):



    points = shape.points



    parts = list(shape.parts) + [len(points)]



    for index in range(len(parts) - 1):



        part = points[



            parts[index]:parts[index + 1]



        ]



        if part:



            xs = [point[0] for point in part]



            ys = [point[1] for point in part]



            ax.plot(



                xs,



                ys,



                **kwargs,



            )



def plot_scenario_preview(



    buildings_shapefile,



    roads_shapefile,



    boundary_shapefile,



):



    fig, ax = plt.subplots(figsize=(10, 8))



    with shapefile.Reader(boundary_shapefile) as reader:



        for shape in reader.shapes():



            plot_line_shape(



                ax,



                shape,



                linewidth=2,



                color="black",



            )



    with shapefile.Reader(roads_shapefile) as reader:



        for shape in reader.shapes():



            plot_line_shape(



                ax,



                shape,



                linewidth=0.5,



                color="lightgray",



            )



    with shapefile.Reader(buildings_shapefile) as reader:



        field_names = [



            field[0]



            for field in reader.fields[1:]



        ]



        type_index = field_names.index("Nature")



        for shape_record in reader.iterShapeRecords():



            building_type = str(



                shape_record.record[type_index]



            ).strip()



            if building_type == "School":



                color = "royalblue"



            elif building_type in [



                "Residential",



                "Nature",



            ]:



                color = "lightgray"



            elif building_type == "__IGNORE__":



                color = "white"



            else:



                color = "tomato"



            plot_polygon_shape(



                ax,



                shape_record.shape,



                facecolor=color,



                edgecolor="gray",



                linewidth=0.25,



            )



    ax.set_aspect("equal")



    ax.axis("off")



    ax.set_title(



        "Scenario preview",



        fontsize=14,



    )



    legend_items = [



        Patch(



            facecolor="royalblue",



            label="School",



        ),



        Patch(



            facecolor="lightgray",



            label="Residential",



        ),



        Patch(



            facecolor="tomato",



            label="Food outlet",



        ),



        Patch(



            facecolor="white",



            edgecolor="gray",



            label="Ignored",



        ),



        Line2D(



            [0],



            [0],



            color="lightgray",



            label="Road network",



        ),



        Line2D(



            [0],



            [0],



            color="black",



            linewidth=2,



            label="Study area",



        ),



    ]



    ax.legend(



        handles=legend_items,



        loc="upper right",



    )



    return fig



# ---------------------------------------------------------------------



# GAMA CONNECTION



# ---------------------------------------------------------------------



async def connect_to_gama_with_retry():



    """Connect to the Codespaces GAMA service, retrying during restarts."""



    loop = asyncio.get_running_loop()



    deadline = loop.time() + GAMA_CONNECT_RETRY_SECONDS



    last_error = None



    attempt = 0



    while True:



        attempt += 1



        websocket_context = None



        try:



            websocket_context = websockets.connect(



                GAMA_URI,



                open_timeout=5,



            )



            websocket = await websocket_context.__aenter__()



            hello_raw = await asyncio.wait_for(



                websocket.recv(),



                timeout=10,



            )



            hello = json.loads(hello_raw)



            if hello.get("type") != "ConnectionSuccessful":



                raise RuntimeError(



                    "GAMA returned an unexpected connection message: "



                    f"{hello}"



                )



            return websocket_context, websocket



        except Exception as exc:



            last_error = exc



            if websocket_context is not None:



                try:



                    await websocket_context.__aexit__(



                        type(exc),



                        exc,



                        exc.__traceback__,



                    )



                except Exception:



                    pass



            remaining = deadline - loop.time()



            if remaining <= 0:



                raise RuntimeError(



                    "Could not connect to the GAMA websocket server at "



                    f"'{GAMA_URI}' after retrying for "



                    f"{GAMA_CONNECT_RETRY_SECONDS} seconds. "



                    "The Codespaces 'gama' service may still be restarting. "



                    f"Last error: {type(last_error).__name__}: {last_error}"



                ) from last_error



            await asyncio.sleep(



                min(



                    GAMA_CONNECT_RETRY_INTERVAL_SECONDS,



                    remaining,



                )



            )





async def run_one_gama_simulation(

    websocket,

    exposure_radius,

    exposure_multiplier,

    wtp_upper_limit,

    lunch_duration,

    buildings_shapefile,

    roads_shapefile,

    boundary_shapefile,

):

    """Run one GAMA experiment using the original async play/CSV workflow."""

    OUTPUT.parent.mkdir(

        parents=True,

        exist_ok=True,

    )

    if OUTPUT.exists():

        OUTPUT.unlink()

    load_command = {

        "type": "load",

        "model": str(MODEL),

        "experiment": "web_experiment",

        "console": False,

        "parameters": [

            {

                "type": "shape_file",

                "value": buildings_shapefile,

                "name": "a2_Buildings_Strandeiland",

            },

            {

                "type": "file",

                "value": roads_shapefile,

                "name": "a1_Street_Strandeiland",

            },

            {

                "type": "shape_file",

                "value": boundary_shapefile,

                "name": "a3_Outline_Strandeiland",

            },

            {

                "type": "float",

                "value": exposure_radius,

                "name": "exposure_radius",

            },

            {

                "type": "float",

                "value": exposure_multiplier,

                "name": "exposure_multiplier",

            },

            {

                "type": "float",

                "value": wtp_upper_limit,

                "name": "wtp_upper_limit",

            },

            {

                "type": "float",

                "value": lunch_duration,

                "name": "current_lunch_duration",

            },

            {

                "type": "string",

                "value": str(OUTPUT),

                "name": "export_file_path",

            },

            {

                "type": "string",

                "value": "Nature",

                "name": "building_type_field",

            },

        ],

        "until": "time > 7 #days",

    }

    await websocket.send(json.dumps(load_command))

    load_response = json.loads(

        await asyncio.wait_for(

            websocket.recv(),

            timeout=30,

        )

    )

    if load_response.get("type") != "CommandExecutedSuccessfully":

        raise RuntimeError(

            "GAMA could not load the experiment: "

            f"{load_response}"

        )

    experiment_id = load_response["content"]

    # Keep the original, proven behaviour: start asynchronously and watch
    # the model's CSV output instead of waiting for SimulationEnded.
    play_command = {

        "type": "play",

        "exp_id": experiment_id,

        "sync": False,

    }

    await websocket.send(json.dumps(play_command))

    play_response = json.loads(

        await asyncio.wait_for(

            websocket.recv(),

            timeout=30,

        )

    )

    if play_response.get("type") != "CommandExecutedSuccessfully":

        raise RuntimeError(

            "GAMA could not start the experiment: "

            f"{play_response}"

        )

    loop = asyncio.get_running_loop()

    start_time = loop.time()

    while True:

        if OUTPUT.exists():

            with open(

                OUTPUT,

                "r",

                encoding="utf-8",

            ) as file:

                non_empty_lines = [

                    line

                    for line in file

                    if line.strip()

                ]

            if len(non_empty_lines) >= 2:

                break

        if (

            loop.time() - start_time

            > RUN_TIMEOUT_SECONDS

        ):

            raise TimeoutError(

                "The GAMA simulation did not produce a result CSV within "

                f"{RUN_TIMEOUT_SECONDS} seconds."

            )

        await asyncio.sleep(0.2)

    # Ask GAMA to stop/clean up this experiment before closing the client.
    stop_command = {

        "type": "stop",

        "exp_id": experiment_id,

    }

    try:

        await websocket.send(json.dumps(stop_command))

        await asyncio.wait_for(

            websocket.recv(),

            timeout=10,

        )

    except Exception:

        # The result is already complete. A failed cleanup response should
        # not discard a valid simulation result.

        pass

    with open(

        OUTPUT,

        newline="",

        encoding="utf-8",

    ) as file:

        reader = csv.DictReader(

            file,

            delimiter=";",

        )

        result = next(reader)

    return result



async def run_gama_batch(

    exposure_radius,

    exposure_multiplier,

    wtp_upper_limit,

    lunch_duration,

    buildings_shapefile,

    roads_shapefile,

    boundary_shapefile,

    number_of_runs,

    progress_callback=None,

):

    """Run repeated simulations with the proven one-connection-per-run flow."""

    results = []

    for run_index in range(number_of_runs):

        websocket_context, websocket = await connect_to_gama_with_retry()

        try:

            result = await run_one_gama_simulation(

                websocket,

                exposure_radius,

                exposure_multiplier,

                wtp_upper_limit,

                lunch_duration,

                buildings_shapefile,

                roads_shapefile,

                boundary_shapefile,

            )

        except TimeoutError:

            # A simulation timeout is not a websocket disconnect. Preserve the
            # real error so the UI reports the actual problem.

            raise

        except ConnectionClosed as exc:

            raise RuntimeError(

                "The GAMA websocket connection closed while running "

                f"simulation {run_index + 1}: {exc}"

            ) from exc

        finally:

            try:

                await websocket_context.__aexit__(

                    None,

                    None,

                    None,

                )

            except Exception:

                pass

        results.append(result)

        if progress_callback is not None:

            progress_callback(

                run_index + 1,

                number_of_runs,

            )

    return results



# ---------------------------------------------------------------------



# STREAMLIT PAGE



# ---------------------------------------------------------------------



st.set_page_config(



    page_title="Urban Food Environment Scenario Tool",



    layout="wide",



)



st.title(



    "Urban Food Environment Scenario Tool"



)



st.write(



    "Explore how different spatial configurations of the urban food "



    "environment may affect adolescents' lunch choices."



)



if "scenario_results" not in st.session_state:



    st.session_state.scenario_results = []



if "amsterdam_poi_edits" not in st.session_state:



    st.session_state.amsterdam_poi_edits = {}



if "amsterdam_building_conversions" not in st.session_state:

    st.session_state.amsterdam_building_conversions = {}



if "selected_amsterdam_poi" not in st.session_state:



    st.session_state.selected_amsterdam_poi = None



if "selected_amsterdam_neighbourhood_id" not in st.session_state:



    st.session_state.selected_amsterdam_neighbourhood_id = None



# ---------------------------------------------------------------------

# 1. STUDY AREA

# ---------------------------------------------------------------------



st.header("1. Study area")

study_area_source = st.radio(
    "Which food environment should this scenario use?",
    [
        "Amsterdam neighbourhood",
        "Uploaded food environment",
    ],
    horizontal=True,
)

selected_neighbourhood_name = None
neighbourhood_id = None
neighbourhood_geometry = None
neighbourhood_buildings = None
school_pois = []
food_outlet_pois = []

st.subheader("Approach 1: Amsterdam neighbourhood")



try:

    amsterdam_neighbourhoods = load_amsterdam_neighbourhoods()



    neighbourhood_names = [

        neighbourhood["name"]

        for neighbourhood in amsterdam_neighbourhoods

        if neighbourhood["name"]

    ]



    selected_neighbourhood_name = st.selectbox(

        "Select an Amsterdam neighbourhood",

        neighbourhood_names,

        index=None,

        placeholder="Choose a neighbourhood...",

    )



    if selected_neighbourhood_name:

        selected_neighbourhood = next(

            neighbourhood

            for neighbourhood in amsterdam_neighbourhoods

            if neighbourhood["name"] == selected_neighbourhood_name

        )



        neighbourhood_id = selected_neighbourhood["id"]



        if (

            st.session_state.selected_amsterdam_neighbourhood_id

            != neighbourhood_id

        ):

            st.session_state.selected_amsterdam_neighbourhood_id = (

                neighbourhood_id

            )

            st.session_state.selected_amsterdam_poi = None



        st.success(

            f"Selected neighbourhood: {selected_neighbourhood_name}"

        )

        st.caption(

            f"Neighbourhood ID: "

            f"{selected_neighbourhood.get('id', 'Unknown')}"

        )



        neighbourhood_geometry = (

            load_amsterdam_neighbourhood_geometry(

                neighbourhood_id

            )

        )



        neighbourhood_buildings = (

            load_amsterdam_buildings(

                neighbourhood_geometry

            )

        )



        osm_pois = []

        school_pois = []

        food_outlet_pois = []



        try:

            if not LOCAL_OSM_FILE.exists():

                raise FileNotFoundError(

                    f"Expected file: {LOCAL_OSM_FILE}"

                )



            osm_pois = load_osm_food_environment(

                neighbourhood_geometry,

                LOCAL_OSM_FILE.stat().st_mtime_ns,

            )



            school_pois = [

                poi

                for poi in osm_pois

                if poi["gama_type"] == "School"

            ]



            original_food_outlet_pois = [

                poi

                for poi in osm_pois

                if poi["gama_type"] != "School"

            ]



            edited_food_outlets = []



            for poi in original_food_outlet_pois:

                edited_poi = poi.copy()



                edit_key = (

                    f"{neighbourhood_id}::"

                    f"{poi['osm_id']}"

                )



                saved_edit = (

                    st.session_state.amsterdam_poi_edits.get(

                        edit_key

                    )

                )



                if saved_edit == "__REMOVE__":

                    continue



                if saved_edit:

                    edited_poi["gama_type"] = saved_edit

                    edited_poi["edited"] = True

                    edited_poi["display_color"] = [

                        140,

                        80,

                        200,

                        240,

                    ]

                else:

                    edited_poi["edited"] = False

                    edited_poi["display_color"] = [

                        217,

                        119,

                        87,

                        230,

                    ]



                edited_food_outlets.append(

                    edited_poi

                )



            converted_food_outlets = []

            for feature in neighbourhood_buildings["features"]:
                properties = feature.get("properties", {}) or {}
                building_id = str(properties.get("building_id"))
                conversion_key = (
                    f"{neighbourhood_id}::{building_id}"
                )
                converted_type = (
                    st.session_state.amsterdam_building_conversions.get(
                        conversion_key
                    )
                )

                if converted_type is None:
                    continue

                building_shape = shape(feature["geometry"])
                point = building_shape.representative_point()

                converted_food_outlets.append(
                    {
                        "osm_id": f"converted::{building_id}",
                        "building_id": building_id,
                        "conversion_key": conversion_key,
                        "name": f"Scenario {converted_type}",
                        "gama_type": converted_type,
                        "latitude": float(point.y),
                        "longitude": float(point.x),
                        "source": "Scenario conversion",
                        "is_converted": True,
                        "edited": True,
                        "display_color": [
                            140,
                            80,
                            200,
                            240,
                        ],
                    }
                )

            food_outlet_pois = (
                edited_food_outlets
                + converted_food_outlets
            )

            st.success(

                f"{len(school_pois)} schools and "

                f"{len(food_outlet_pois)} food outlets in the current scenario."

            )

            st.caption(

                "Food-environment data loaded from the local "

                "OpenStreetMap dataset."

            )



        except Exception as osm_error:

            st.warning(

                "The local OpenStreetMap food-environment data "

                f"could not be loaded: {osm_error}"

            )



        st.caption(

            f"{len(neighbourhood_buildings['features'])} "

            f"building polygons loaded."

        )



        neighbourhood_center = get_geometry_center(

            neighbourhood_geometry

        )



        neighbourhood_feature = {

            "type": "Feature",

            "properties": {

                "name": selected_neighbourhood_name

            },

            "geometry": neighbourhood_geometry,

        }



        available_residential_features = []

        for feature in neighbourhood_buildings["features"]:
            properties = feature.get("properties", {}) or {}
            building_id = str(properties.get("building_id"))
            conversion_key = (
                f"{neighbourhood_id}::{building_id}"
            )

            if (
                conversion_key
                in st.session_state.amsterdam_building_conversions
            ):
                continue

            available_residential_features.append(feature)

        available_residential_buildings = {
            "type": "FeatureCollection",
            "features": available_residential_features,
        }



        buildings_layer = pdk.Layer(

            "GeoJsonLayer",

            available_residential_buildings,

            id="buildings",

            pickable=True,

            auto_highlight=True,

            stroked=True,

            filled=True,

            get_fill_color=[210, 210, 210, 180],

            get_line_color=[120, 120, 120],

            line_width_min_pixels=0.5,

        )



        neighbourhood_layer = pdk.Layer(

            "GeoJsonLayer",

            neighbourhood_feature,

            id="neighbourhood",

            pickable=False,

            stroked=True,

            filled=True,

            get_fill_color=[70, 130, 180, 80],

            get_line_color=[30, 30, 30],

            line_width_min_pixels=2,

        )



        food_outlets_layer = pdk.Layer(

            "ScatterplotLayer",

            data=food_outlet_pois,

            id="food-outlets",

            get_position="[longitude, latitude]",

            get_fill_color="display_color",

            get_line_color=[120, 60, 40],

            get_radius=10,

            radius_min_pixels=5,

            stroked=True,

            pickable=True,

            auto_highlight=True,

        )



        schools_layer = pdk.Layer(

            "ScatterplotLayer",

            data=school_pois,

            id="schools",

            get_position="[longitude, latitude]",

            get_fill_color=[65, 105, 225, 230],

            get_line_color=[30, 50, 120],

            get_radius=12,

            radius_min_pixels=6,

            stroked=True,

            pickable=True,

            auto_highlight=True,

        )



        neighbourhood_map = pdk.Deck(

            layers=[

                buildings_layer,

                neighbourhood_layer,

                food_outlets_layer,

                schools_layer,

            ],

            initial_view_state=pdk.ViewState(

                latitude=neighbourhood_center["latitude"],

                longitude=neighbourhood_center["longitude"],

                zoom=13,

            ),

            map_style="light",

            tooltip={

                "html": (

                    "<b>{name}</b><br/>"

                    "{gama_type}<br/>"

                    "<small>{source}</small>"

                )

            },

        )



        map_event = st.pydeck_chart(

            neighbourhood_map,

            use_container_width=True,

            on_select="rerun",

            selection_mode="single-object",

            key=(

                f"amsterdam_scenario_map_"

                f"{neighbourhood_id}"

            ),

        )



        # Save the latest map selection.

        selected_objects = {}



        if map_event and map_event.selection:

            selected_objects = (

                map_event.selection.get(

                    "objects",

                    {},

                )

            )



        if selected_objects.get("food-outlets"):

            clicked_object = (

                selected_objects["food-outlets"][0]

            )



            if clicked_object.get("is_converted"):
                st.session_state.selected_amsterdam_poi = {
                    "building_id": clicked_object.get("building_id"),
                    "layer": "converted-food-outlets",
                }
            else:
                st.session_state.selected_amsterdam_poi = {

                    "osm_id": clicked_object.get("osm_id"),

                    "layer": "food-outlets",

                }



        elif selected_objects.get("schools"):

            clicked_object = (

                selected_objects["schools"][0]

            )



            st.session_state.selected_amsterdam_poi = {

                "osm_id": clicked_object.get("osm_id"),

                "layer": "schools",

            }

        elif selected_objects.get("buildings"):

            clicked_object = selected_objects["buildings"][0]



            properties = clicked_object.get(

                "properties",

                clicked_object,

            )



            st.session_state.selected_amsterdam_poi = {

                "building_id": properties.get("building_id"),

                "layer": "buildings",

            }



        # Re-find the selected object in the current edited data.

        selected_object = None

        selected_layer = None

        saved_selection = (

            st.session_state.selected_amsterdam_poi

        )



        if saved_selection:

            selected_layer = saved_selection.get("layer")

            selected_id = saved_selection.get("osm_id")



            if selected_layer == "food-outlets":

                selected_object = next(

                    (

                        poi

                        for poi in food_outlet_pois

                        if poi["osm_id"] == selected_id

                    ),

                    None,

                )



            elif selected_layer == "schools":

                selected_object = next(

                    (

                        poi

                        for poi in school_pois

                        if poi["osm_id"] == selected_id

                    ),

                    None,

                )

            elif selected_layer == "converted-food-outlets":
                selected_building_id = saved_selection.get("building_id")
                selected_object = next(
                    (
                        poi
                        for poi in food_outlet_pois
                        if poi.get("is_converted")
                        and str(poi.get("building_id"))
                        == str(selected_building_id)
                    ),
                    None,
                )

            elif selected_layer == "buildings":

                selected_building_id = saved_selection.get("building_id")



                selected_feature = next(

                    (

                        feature

                        for feature in neighbourhood_buildings["features"]

                        if str(

                            feature.get("properties", {}).get("building_id")

                        ) == str(selected_building_id)

                    ),

                    None,

                )



                if selected_feature:

                    selected_object = {

                        **selected_feature.get("properties", {}),

                        "geometry": selected_feature["geometry"],

                    }



        # Editor for the selected location.

        if selected_object:

            st.subheader("Selected location")



            location_name = selected_object.get(

                "name",

                "Unnamed location",

            )

            current_type = selected_object.get(

                "gama_type",

                "Unknown",

            )

            if selected_layer == "buildings":
                selected_building_id = selected_object.get("building_id")
                conversion_key = (
                    f"{neighbourhood_id}::{selected_building_id}"
                )
                current_type = (
                    st.session_state.amsterdam_building_conversions.get(
                        conversion_key,
                        "Residential",
                    )
                )



            st.write(

                "**Name:**",

                location_name,

            )

            st.write(

                "**Current model category:**",

                current_type,

            )

            st.write(

                "**Source:**",

                selected_object.get(

                    "source",

                    "Unknown",

                ),

            )



            if selected_layer == "food-outlets":

                selected_osm_id = selected_object["osm_id"]



                edit_key = (

                    f"{neighbourhood_id}::"

                    f"{selected_osm_id}"

                )

                widget_key = f"category_{edit_key}"



                default_index = (

                    FOOD_OUTLET_TYPES.index(current_type)

                    if current_type in FOOD_OUTLET_TYPES

                    else 0

                )



                new_type = st.selectbox(

                    "Change food outlet category",

                    FOOD_OUTLET_TYPES,

                    index=default_index,

                    key=widget_key,

                )



                edit_col1, edit_col2, edit_col3 = (

                    st.columns(3)

                )



                with edit_col1:

                    if st.button(

                        "Apply change",

                        key=f"apply_{edit_key}",

                        use_container_width=True,

                    ):

                        st.session_state.amsterdam_poi_edits[

                            edit_key

                        ] = new_type

                        st.rerun()



                with edit_col2:

                    if st.button(

                        "Remove outlet",

                        key=f"remove_{edit_key}",

                        use_container_width=True,

                    ):

                        st.session_state.amsterdam_poi_edits[

                            edit_key

                        ] = "__REMOVE__"

                        st.session_state.selected_amsterdam_poi = (

                            None

                        )

                        st.rerun()



                with edit_col3:

                    if st.button(

                        "Reset",

                        key=f"reset_{edit_key}",

                        use_container_width=True,

                    ):

                        st.session_state.amsterdam_poi_edits.pop(

                            edit_key,

                            None,

                        )

                        st.session_state.pop(

                            widget_key,

                            None,

                        )

                        st.rerun()



            elif selected_layer in {
                "buildings",
                "converted-food-outlets",
            }:
                selected_building_id = selected_object.get("building_id")
                conversion_key = (
                    f"{neighbourhood_id}::{selected_building_id}"
                )
                existing_conversion = (
                    st.session_state.amsterdam_building_conversions.get(
                        conversion_key
                    )
                )

                default_index = (
                    FOOD_OUTLET_TYPES.index(existing_conversion)
                    if existing_conversion in FOOD_OUTLET_TYPES
                    else 0
                )

                conversion_type = st.selectbox(
                    (
                        "Change converted food outlet category"
                        if existing_conversion
                        else "Convert residential location to"
                    ),
                    FOOD_OUTLET_TYPES,
                    index=default_index,
                    key=f"conversion_category_{conversion_key}",
                )

                if existing_conversion is None:
                    if st.button(
                        "Convert to food outlet",
                        key=f"convert_{conversion_key}",
                        use_container_width=True,
                    ):
                        st.session_state.amsterdam_building_conversions[
                            conversion_key
                        ] = conversion_type
                        st.session_state.selected_amsterdam_poi = {
                            "building_id": selected_building_id,
                            "layer": "converted-food-outlets",
                        }
                        st.rerun()
                else:
                    conversion_col1, conversion_col2 = st.columns(2)

                    with conversion_col1:
                        if st.button(
                            "Apply change",
                            key=f"change_conversion_{conversion_key}",
                            use_container_width=True,
                        ):
                            st.session_state.amsterdam_building_conversions[
                                conversion_key
                            ] = conversion_type
                            st.rerun()

                    with conversion_col2:
                        if st.button(
                            "Restore residential",
                            key=f"restore_{conversion_key}",
                            use_container_width=True,
                        ):
                            st.session_state.amsterdam_building_conversions.pop(
                                conversion_key,
                                None,
                            )
                            st.session_state.selected_amsterdam_poi = None
                            st.session_state.pop(
                                f"conversion_category_{conversion_key}",
                                None,
                            )
                            st.rerun()

            elif selected_layer == "schools":

                st.info(

                    "Schools are currently fixed and cannot "

                    "be edited."

                )



            if st.button(

                "Clear selection",

                key=(

                    f"clear_selection_"

                    f"{neighbourhood_id}"

                ),

            ):

                st.session_state.selected_amsterdam_poi = None

                st.rerun()



except Exception as exc:

    st.error(

        f"Could not load Amsterdam study-area data: {exc}"

    )



st.subheader("Approach 2: Upload your own food environment")

st.caption(



    "Upload one ZIP per GIS layer. Each ZIP should contain one "



    "shapefile with .shp, .shx, .dbf and .prj files."



)



uploaded_buildings = st.file_uploader(



    "Buildings / food environment",



    type=["zip"],



)



building_type_field = None



buildings_shapefile = None



value_mapping = {}



all_mapped = False



has_school = False



has_residential = False



if uploaded_buildings is not None:



    try:



        buildings_shapefile = prepare_shapefile(



            uploaded_buildings



        )



        building_fields = get_shapefile_fields(



            buildings_shapefile



        )



        building_type_field = st.selectbox(



            "Which column contains the location type?",



            building_fields,



        )



        unique_building_types = get_unique_values(



            buildings_shapefile,



            building_type_field,



        )



        building_value_counts = get_value_counts(



            buildings_shapefile,



            building_type_field,



        )



        st.markdown(



            "**Map the uploaded values to model categories**"



        )



        value_mapping = {}



        all_mapped = True



        mapping_options = [



            SELECT_CATEGORY,



            IGNORE_CATEGORY,



        ] + GAMA_TYPES



        for index, original_value in enumerate(



            unique_building_types



        ):



            if original_value in GAMA_TYPES:



                # Two non-model options appear before GAMA_TYPES.



                default_index = (



                    GAMA_TYPES.index(original_value)



                    + 2



                )



            else:



                default_index = 0



            selected_type = st.selectbox(



                f"{original_value} →",



                mapping_options,



                index=default_index,



                key=f"type_mapping_{index}",



            )



            value_mapping[



                original_value



            ] = selected_type



            if selected_type == SELECT_CATEGORY:



                all_mapped = False



        summary_counts = {}



        for (



            original_value,



            count,



        ) in building_value_counts.items():



            mapped_value = value_mapping[



                original_value



            ]



            if mapped_value == IGNORE_CATEGORY:



                summary_name = "Ignored"



            elif mapped_value == SELECT_CATEGORY:



                summary_name = "Not mapped"



            else:



                summary_name = mapped_value



            summary_counts[summary_name] = (



                summary_counts.get(



                    summary_name,



                    0,



                )



                + count



            )



        with st.expander(



            "Mapping summary",



            expanded=False,



        ):



            summary_table = [



                {



                    "Model category": category,



                    "Number of buildings": count,



                }



                for category, count in sorted(



                    summary_counts.items()



                )



            ]



            st.table(summary_table)



        mapped_categories = set(



            value_mapping.values()



        )



        has_school = (



            "School" in mapped_categories



        )



        has_residential = (



            "Residential" in mapped_categories



            or "Nature" in mapped_categories



        )



        if st.button("Clear selection"):



            st.session_state.selected_amsterdam_poi = None



            st.rerun()



    except Exception as error:



        st.error(



            f"Could not read buildings shapefile: {error}"



        )



uploaded_roads = st.file_uploader(



    "Road network",



    type=["zip"],



)



uploaded_boundary = st.file_uploader(



    "Study area boundary",



    type=["zip"],



)



# ---------------------------------------------------------------------



# 2. CONFIGURE SCENARIO



# ---------------------------------------------------------------------



st.header("2. Configure scenario")



scenario_name = st.text_input(



    "Scenario name",



    value=(



        f"Scenario "



        f"{len(st.session_state.scenario_results) + 1}"



    ),



)



settings_col1, settings_col2 = st.columns(2)



with settings_col1:



    exposure_radius = st.number_input(



        "Exposure radius (metres)",



        min_value=0.0,



        max_value=200.0,



        value=30.0,



        step=5.0,



    )



    exposure_multiplier = st.number_input(



        "Exposure multiplier",



        min_value=0.0,



        max_value=1.0,



        value=0.10,



        step=0.01,



        format="%.2f",



    )



with settings_col2:



    wtp_upper_limit = st.number_input(



        "WTP upper limit",



        min_value=0.0,



        max_value=1.0,



        value=0.35,



        step=0.05,



        format="%.2f",



    )



    lunch_duration = st.number_input(



        "Lunch duration (minutes)",



        min_value=5.0,



        max_value=60.0,



        value=30.0,



        step=5.0,



    )



# ---------------------------------------------------------------------



# 3. RUN SCENARIO



# ---------------------------------------------------------------------



st.header("3. Run scenario")



run_clicked = st.button(



    "Run scenario",



    type="primary",



)



if run_clicked:
    if not scenario_name.strip():
        st.error("Please enter a scenario name.")
    else:
        try:
            amsterdam_input_summary = None

            if study_area_source == "Amsterdam neighbourhood":
                if (
                    not selected_neighbourhood_name
                    or neighbourhood_id is None
                    or neighbourhood_geometry is None
                    or neighbourhood_buildings is None
                ):
                    raise ValueError(
                        "Please select an Amsterdam neighbourhood first."
                    )

                if not school_pois:
                    raise ValueError(
                        "No schools are available for the selected Amsterdam "
                        "neighbourhood. The scenario cannot run without a school."
                    )

                amsterdam_inputs = create_amsterdam_gama_inputs(
                    neighbourhood_id,
                    neighbourhood_geometry,
                    neighbourhood_buildings,
                    school_pois,
                    food_outlet_pois,
                )

                scenario_buildings_shapefile = amsterdam_inputs["buildings"]
                scenario_roads_shapefile = amsterdam_inputs["roads"]
                scenario_boundary_shapefile = amsterdam_inputs["boundary"]
                scenario_source_label = (
                    f"Amsterdam — {selected_neighbourhood_name}"
                )
                amsterdam_input_summary = amsterdam_inputs

            else:
                if (
                    uploaded_buildings is None
                    or uploaded_roads is None
                    or uploaded_boundary is None
                ):
                    raise ValueError(
                        "Please upload the buildings, roads and boundary files first."
                    )

                if not all_mapped:
                    raise ValueError(
                        "Please map all location types that occur in the uploaded "
                        "buildings file."
                    )

                if not has_school:
                    raise ValueError(
                        "The uploaded data must contain at least one location "
                        "mapped to School."
                    )

                if not has_residential:
                    raise ValueError(
                        "The uploaded data must contain at least one location "
                        "mapped to Residential or Nature."
                    )

                roads_shapefile = prepare_shapefile(
                    uploaded_roads
                )
                boundary_shapefile = prepare_shapefile(
                    uploaded_boundary
                )

                normalized_buildings_shapefile = (
                    normalize_building_type_field(
                        buildings_shapefile,
                        building_type_field,
                        value_mapping,
                    )
                )

                scenario_buildings_shapefile = (
                    normalized_buildings_shapefile
                )
                scenario_roads_shapefile = roads_shapefile
                scenario_boundary_shapefile = boundary_shapefile
                scenario_source_label = "Uploaded food environment"

            # ---------------------------------------------------------
            # Shared GIS validation for both study-area approaches.
            # ---------------------------------------------------------
            crs_check = validate_crs(
                scenario_buildings_shapefile,
                scenario_roads_shapefile,
                scenario_boundary_shapefile,
            )

            buildings_geometry = get_geometry_type(
                scenario_buildings_shapefile
            )
            roads_geometry = get_geometry_type(
                scenario_roads_shapefile
            )
            boundary_geometry = get_geometry_type(
                scenario_boundary_shapefile
            )

            with st.expander(
                "Validation details",
                expanded=False,
            ):
                st.write("Scenario source:", scenario_source_label)
                st.write("Buildings geometry:", buildings_geometry)
                st.write("Roads geometry:", roads_geometry)
                st.write("Boundary geometry:", boundary_geometry)
                st.write("Buildings CRS:", crs_check["buildings"].name)
                st.write("Roads CRS:", crs_check["roads"].name)
                st.write("Boundary CRS:", crs_check["boundary"].name)

                if amsterdam_input_summary is not None:
                    st.write(
                        "Amsterdam location counts:",
                        amsterdam_input_summary["location_counts"],
                    )
                    st.write(
                        "Amsterdam road segments:",
                        amsterdam_input_summary["road_count"],
                    )

            if buildings_geometry != "Polygon":
                raise ValueError(
                    "The buildings / locations layer must contain polygon geometries."
                )

            if roads_geometry != "Polyline":
                raise ValueError(
                    "The road network must contain line geometries."
                )

            if boundary_geometry != "Polygon":
                raise ValueError(
                    "The study area boundary must contain polygon geometries."
                )

            if not crs_check["same_crs"]:
                raise ValueError(
                    "The buildings, roads and boundary layers do not use the "
                    "same coordinate system."
                )

            st.success(
                f"GIS validation passed for {scenario_source_label}."
            )

            st.subheader("Scenario preview")
            scenario_figure = plot_scenario_preview(
                scenario_buildings_shapefile,
                scenario_roads_shapefile,
                scenario_boundary_shapefile,
            )
            st.pyplot(
                scenario_figure,
                use_container_width=True,
            )
            plt.close(scenario_figure)

            with st.expander(
                "Input files",
                expanded=False,
            ):
                st.write("Source:", scenario_source_label)
                st.write(
                    "Buildings / locations:",
                    Path(scenario_buildings_shapefile).name,
                )
                st.write(
                    "Roads:",
                    Path(scenario_roads_shapefile).name,
                )
                st.write(
                    "Boundary:",
                    Path(scenario_boundary_shapefile).name,
                )

            school_results = []
            healthy_results = []
            unhealthy_results = []

            progress_bar = st.progress(0)
            status_text = st.empty()

            def update_run_progress(completed_runs, total_runs):
                status_text.write(
                    f"Running simulation {completed_runs} of "
                    f"{total_runs}..."
                )
                progress_bar.progress(
                    completed_runs / total_runs
                )

            status_text.write(
                f"Connecting to GAMA and starting {NUMBER_OF_RUNS} "
                "simulations..."
            )

            batch_results = asyncio.run(
                run_gama_batch(
                    exposure_radius,
                    exposure_multiplier,
                    wtp_upper_limit,
                    lunch_duration,
                    scenario_buildings_shapefile,
                    scenario_roads_shapefile,
                    scenario_boundary_shapefile,
                    NUMBER_OF_RUNS,
                    progress_callback=update_run_progress,
                )
            )

            for result in batch_results:
                school_results.append(
                    int(result["School_Lunches"])
                )
                healthy_results.append(
                    int(result["Healthy_Lunches"])
                )
                unhealthy_results.append(
                    int(result["Unhealthy_Lunches"])
                )

            average_school = sum(school_results) / NUMBER_OF_RUNS
            average_healthy = sum(healthy_results) / NUMBER_OF_RUNS
            average_unhealthy = (
                sum(unhealthy_results) / NUMBER_OF_RUNS
            )

            scenario_result = {
                "Scenario": scenario_name.strip(),
                "Source": scenario_source_label,
                "Exposure radius": exposure_radius,
                "Exposure multiplier": exposure_multiplier,
                "WTP upper limit": wtp_upper_limit,
                "Lunch duration": lunch_duration,
                "On-campus": average_school,
                "Healthy": average_healthy,
                "Unhealthy": average_unhealthy,
            }

            st.session_state.scenario_results.append(
                scenario_result
            )

            status_text.empty()
            progress_bar.empty()

            st.success(
                f"{NUMBER_OF_RUNS} simulations completed."
            )

            st.subheader("Results")
            st.caption(
                f"Average number of lunch decisions across "
                f"{NUMBER_OF_RUNS} simulations."
            )

            result_col1, result_col2, result_col3 = st.columns(3)
            result_col1.metric(
                "On-campus lunches",
                f"{average_school:.1f}",
            )
            result_col2.metric(
                "Healthy outlet visits",
                f"{average_healthy:.1f}",
            )
            result_col3.metric(
                "Unhealthy outlet visits",
                f"{average_unhealthy:.1f}",
            )

        except Exception as error:
            st.error(
                f"Could not run scenario: {error}"
            )


# ---------------------------------------------------------------------



# 4. COMPARE SCENARIOS



# ---------------------------------------------------------------------



st.header("4. Compare scenarios")



if not st.session_state.scenario_results:



    st.info(



        "Run at least one scenario to start a comparison."



    )



else:



    comparison_df = pd.DataFrame(



        st.session_state.scenario_results



    )



    st.dataframe(



        comparison_df,



        use_container_width=True,



        hide_index=True,



    )



    st.subheader(



        "Lunch choices by scenario"



    )



    chart_data = comparison_df.set_index(



        "Scenario"



    )[



        [



            "On-campus",



            "Healthy",



            "Unhealthy",



        ]



    ]



    st.bar_chart(



        chart_data,



        use_container_width=True,



        color=[



            "#6B7280",



            "#2E8B57",



            "#D97757",



        ],



    )



    csv_data = comparison_df.to_csv(



        index=False



    ).encode("utf-8")



    action_col1, action_col2 = st.columns(2)



    with action_col1:



        st.download_button(



            label="Download scenario comparison",



            data=csv_data,



            file_name="scenario_comparison.csv",



            mime="text/csv",



            use_container_width=True,



        )



    with action_col2:



        if st.button(



            "Clear comparison",



            use_container_width=True,



        ):



            st.session_state.scenario_results = []



            st.rerun()


