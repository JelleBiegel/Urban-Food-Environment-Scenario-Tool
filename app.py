import asyncio
import csv
import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import shapefile
import streamlit as st
import websockets
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from pyproj import CRS

import requests
import pydeck as pdk
from shapely.geometry import Point, shape


# ---------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent

RUNTIME_DIR = PROJECT_ROOT / ".runtime"
RUNTIME_DIR.mkdir(exist_ok=True)

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

GAMA_URI = os.getenv("GAMA_URI", "ws://localhost:6868")
NUMBER_OF_RUNS = 5
RUN_TIMEOUT_SECONDS = 180

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
            selected_features.append(feature)

    return {
        "type": "FeatureCollection",
        "features": selected_features,
    }
OVERPASS_URLS = [
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]

def classify_osm_poi(tags):
    """Translate OpenStreetMap tags to GAMA categories."""

    amenity = tags.get("amenity", "")
    shop = tags.get("shop", "")
    cuisine = tags.get("cuisine", "").lower()
    butcher_type = tags.get("butcher", "").lower()

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

    # Shops
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

def run_overpass_query(query):
    """Try multiple public Overpass servers until one responds."""

    errors = []

    for url in OVERPASS_URLS:
        try:
            response = requests.post(
                url,
                data={"data": query},
                headers={
                    "User-Agent": (
                        "Urban-Food-Environment-Scenario-Tool/1.0"
                    ),
                    "Accept": "application/json",
                },
                timeout=45,
            )

            response.raise_for_status()

            return response.json()

        except requests.RequestException as exc:
            errors.append(
                f"{url}: {exc}"
            )

    raise RuntimeError(
        "OpenStreetMap data could not be retrieved from "
        "any available Overpass server."
    )
@st.cache_data(ttl=3600)
def load_osm_food_environment(neighbourhood_geometry):
    """Load schools and food outlets from OpenStreetMap."""

    neighbourhood_shape = shape(
        neighbourhood_geometry
    )

    min_lon, min_lat, max_lon, max_lat = (
        get_geometry_bounds(
            neighbourhood_geometry
        )
    )

    # Overpass uses south, west, north, east
    bbox = (
        f"{min_lat},{min_lon},"
        f"{max_lat},{max_lon}"
    )

    query = f"""
    [out:json][timeout:25];
    (
      nwr["amenity"~"^(school|restaurant|fast_food|cafe|ice_cream|pub|bar|fuel)$"]({bbox});
      nwr["shop"~"^(supermarket|convenience|bakery|butcher|cheese|chocolate|confectionery|alcohol|wine|tobacco|pastry|deli|health_food|nuts|seafood|greengrocer|coffee|tea|chemist)$"]({bbox});
    );
    out center qt;
    """

    data = run_overpass_query(query)



    pois = []

    for element in data.get("elements", []):
        tags = element.get("tags", {})

        gama_type = classify_osm_poi(tags)

        if gama_type is None:
            continue

        if element["type"] == "node":
            latitude = element.get("lat")
            longitude = element.get("lon")

        else:
            center = element.get("center", {})
            latitude = center.get("lat")
            longitude = center.get("lon")

        if latitude is None or longitude is None:
            continue

        point = Point(
            longitude,
            latitude,
        )

        if not neighbourhood_shape.covers(point):
            continue

        pois.append(
            {
                "osm_id": str(element.get("id")),
                "osm_type": element.get("type"),
                "name": tags.get(
                    "name",
                    "Unnamed location",
                ),
                "gama_type": gama_type,
                "latitude": latitude,
                "longitude": longitude,
                "source": "OpenStreetMap",
            }
        )

    return pois
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

async def run_gama(
    exposure_radius,
    exposure_multiplier,
    wtp_upper_limit,
    lunch_duration,
    buildings_shapefile,
    roads_shapefile,
    boundary_shapefile,
):
    """Run one GAMA simulation and return its CSV result row."""

    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if OUTPUT.exists():
        OUTPUT.unlink()

    async with websockets.connect(
        GAMA_URI
    ) as websocket:
        await websocket.recv()

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

        await websocket.send(
            json.dumps(load_command)
        )

        load_response = json.loads(
            await websocket.recv()
        )

        if (
            load_response.get("type")
            != "CommandExecutedSuccessfully"
        ):
            raise RuntimeError(
                "GAMA could not load the experiment: "
                f"{load_response}"
            )

        experiment_id = load_response[
            "content"
        ]

        play_command = {
            "type": "play",
            "exp_id": experiment_id,
            "sync": False,
        }

        await websocket.send(
            json.dumps(play_command)
        )

        await websocket.recv()

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
                    "The GAMA simulation did not "
                    "produce a result in time."
                )

            await asyncio.sleep(0.2)

        stop_command = {
            "type": "stop",
            "exp_id": experiment_id,
        }

        await websocket.send(
            json.dumps(stop_command)
        )

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


# ---------------------------------------------------------------------
# 1. STUDY AREA
# ---------------------------------------------------------------------

st.header("1. Study area")

st.subheader("Amsterdam neighbourhood prototype")

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

        st.success(
            f"Selected neighbourhood: {selected_neighbourhood_name}"
        )

        st.caption(
            f"Neighbourhood ID: "
            f"{selected_neighbourhood.get('id', 'Unknown')}"
        )
        neighbourhood_geometry = (
            load_amsterdam_neighbourhood_geometry(
                selected_neighbourhood["id"]
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
            osm_pois = load_osm_food_environment(
                neighbourhood_geometry
            )

            school_pois = [
                poi
                for poi in osm_pois
                if poi["gama_type"] == "School"
            ]

            food_outlet_pois = [
                poi
                for poi in osm_pois
                if poi["gama_type"] != "School"
            ]

            st.caption(
                f"{len(school_pois)} schools and "
                f"{len(food_outlet_pois)} food outlets loaded from OpenStreetMap."
            )

        except Exception:
            st.warning(
                "OpenStreetMap data could not be loaded right now. "
                "The neighbourhood and building data are still available. "
                "Refresh the page to retry."
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
        buildings_layer = pdk.Layer(
            "GeoJsonLayer",
            neighbourhood_buildings,
            pickable=True,
            stroked=True,
            filled=True,
            get_fill_color=[210, 210, 210, 180],
            get_line_color=[120, 120, 120],
            line_width_min_pixels=0.5,
        )
        neighbourhood_layer = pdk.Layer(
            "GeoJsonLayer",
            neighbourhood_feature,
            pickable=True,
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
            get_fill_color=[217, 119, 87, 230],
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

        st.pydeck_chart(
            neighbourhood_map,
            use_container_width=True,
        )

except Exception as exc:
    st.error(
        f"Could not load Amsterdam neighbourhoods: {exc}"
    )

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
    if (
        uploaded_buildings is None
        or uploaded_roads is None
        or uploaded_boundary is None
    ):
        st.error(
            "Please upload the buildings, roads and boundary files first."
        )

    elif not all_mapped:
        st.error(
            "Please map all location types that occur "
            "in the uploaded buildings file."
        )

    elif not has_school:
        st.error(
            "The uploaded data must contain at least one "
            "location mapped to School."
        )

    elif not has_residential:
        st.error(
            "The uploaded data must contain at least one "
            "location mapped to Residential or Nature."
        )

    elif not scenario_name.strip():
        st.error(
            "Please enter a scenario name."
        )

    else:
        try:
            roads_shapefile = prepare_shapefile(
                uploaded_roads
            )

            boundary_shapefile = prepare_shapefile(
                uploaded_boundary
            )

            crs_check = validate_crs(
                buildings_shapefile,
                roads_shapefile,
                boundary_shapefile,
            )

            buildings_geometry = get_geometry_type(
                buildings_shapefile
            )
            roads_geometry = get_geometry_type(
                roads_shapefile
            )
            boundary_geometry = get_geometry_type(
                boundary_shapefile
            )

            with st.expander(
                "Validation details",
                expanded=False,
            ):
                st.write(
                    "Buildings geometry:",
                    buildings_geometry,
                )
                st.write(
                    "Roads geometry:",
                    roads_geometry,
                )
                st.write(
                    "Boundary geometry:",
                    boundary_geometry,
                )

                st.write(
                    "Buildings CRS:",
                    crs_check["buildings"].name,
                )
                st.write(
                    "Roads CRS:",
                    crs_check["roads"].name,
                )
                st.write(
                    "Boundary CRS:",
                    crs_check["boundary"].name,
                )

            if buildings_geometry != "Polygon":
                raise ValueError(
                    "The buildings layer must contain polygon geometries."
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
                    "The buildings, roads and boundary layers "
                    "do not use the same coordinate system."
                )

            st.success(
                "GIS validation passed."
            )

            normalized_buildings_shapefile = (
                normalize_building_type_field(
                    buildings_shapefile,
                    building_type_field,
                    value_mapping,
                )
            )

            st.subheader("Scenario preview")

            scenario_figure = plot_scenario_preview(
                normalized_buildings_shapefile,
                roads_shapefile,
                boundary_shapefile,
            )

            st.pyplot(
                scenario_figure,
                use_container_width=True,
            )

            plt.close(
                scenario_figure
            )

            with st.expander(
                "Input files",
                expanded=False,
            ):
                st.write(
                    "Buildings:",
                    Path(buildings_shapefile).name,
                )
                st.write(
                    "Roads:",
                    Path(roads_shapefile).name,
                )
                st.write(
                    "Boundary:",
                    Path(boundary_shapefile).name,
                )

            school_results = []
            healthy_results = []
            unhealthy_results = []

            progress_bar = st.progress(0)
            status_text = st.empty()

            for run_index in range(
                NUMBER_OF_RUNS
            ):
                status_text.write(
                    f"Running simulation "
                    f"{run_index + 1} of "
                    f"{NUMBER_OF_RUNS}..."
                )

                result = asyncio.run(
                    run_gama(
                        exposure_radius,
                        exposure_multiplier,
                        wtp_upper_limit,
                        lunch_duration,
                        normalized_buildings_shapefile,
                        roads_shapefile,
                        boundary_shapefile,
                    )
                )

                school_results.append(
                    int(
                        result[
                            "School_Lunches"
                        ]
                    )
                )

                healthy_results.append(
                    int(
                        result[
                            "Healthy_Lunches"
                        ]
                    )
                )

                unhealthy_results.append(
                    int(
                        result[
                            "Unhealthy_Lunches"
                        ]
                    )
                )

                progress_bar.progress(
                    (run_index + 1)
                    / NUMBER_OF_RUNS
                )

            average_school = (
                sum(school_results)
                / NUMBER_OF_RUNS
            )

            average_healthy = (
                sum(healthy_results)
                / NUMBER_OF_RUNS
            )

            average_unhealthy = (
                sum(unhealthy_results)
                / NUMBER_OF_RUNS
            )

            scenario_result = {
                "Scenario": scenario_name.strip(),
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
                f"Average number of lunch decisions "
                f"across {NUMBER_OF_RUNS} simulations."
            )

            result_col1, result_col2, result_col3 = (
                st.columns(3)
            )

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
