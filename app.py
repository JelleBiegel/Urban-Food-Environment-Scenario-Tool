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


# ---------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent

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
        tempfile.mkdtemp(prefix="food_environment_")
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
