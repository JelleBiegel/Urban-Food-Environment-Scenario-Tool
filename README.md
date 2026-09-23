# Urban Food Environment Scenario Tool

This repository contains the code for an Agent-Based Model (ABM) developed to explore how different spatial configurations of the urban food environment may affect adolescents' food outlet choices.

The model simulates a complete school week five times. In each simulation run, 100 adolescents make one lunch decision per school day.

The ABM is written in GAMA using the GAML modelling language. The model code can be adapted or extended based on the user's own research questions, assumptions or ambitions.

In addition, this repository contains a Streamlit-based frontend application that allows users to configure and run the model without directly working in GAMA. The application communicates with GAMA in headless mode. This makes it possible to use the ABM through a browser-based interface, including on devices where installing GAMA locally may not be possible.

## Required GIS data

To use the model, the user needs three ZIP folders containing shapefiles for:

- Building polygons
- Road network
- Geographical boundary of the study area

### Building polygons

The building polygon shapefile must contain at least one attribute column describing the function or nature of each building, for example:

- Residential / living
- School
- Restaurant
- Fast-food outlet

Within the frontend application, the values in this attribute can be mapped to the building and food outlet categories used by the ABM.

The shapefile must contain at least:

- One school
- One residential building

Mixed-use building polygons are currently not supported by the model.

### Road network

The road network must consist of polylines with sufficient topological quality.

Road segments that represent a continuous road or path must be properly connected to each other. Disconnected road segments may prevent agents from finding a valid route through the network.

### Study area boundary

The boundary shapefile must cover the complete study area.

It is not a problem if the boundary contains a margin around the actual area of interest.

All uploaded shapefiles must use the same Coordinate Reference System (CRS). The application checks this automatically and will prevent the model from running if the coordinate systems do not match.

# Using the tool in GitHub Codespaces

GitHub Codespaces can be used to run the tool without installing the required software locally.

After opening the repository in a Codespace, the Streamlit application must be started manually.

In the Codespaces terminal, run:

```bash
python -m streamlit run app.py --server.address 0.0.0.0 --server.port 8505
```

**# Codespaces troubleshooting: blank page**
During testing, GitHub Codespaces occasionally retained a stale port-forwarding state after restarting a Codespace. In this situation, the Streamlit server may be running correctly while the previously used forwarded port displays a blank page.
If this happens, start Streamlit using another unused port, for example:
python -m streamlit run app.py --server.address 0.0.0.0 --server.port 8506
Then open port 8506 from the Ports tab.
This behaviour appears to be related to Codespaces port forwarding rather than the scenario tool itself.

## Running a scenario

**1. Upload building polygons**
First, upload a ZIP folder containing the building polygon shapefile.
The application will ask which attribute field contains the building or land-use categories.
The unique values in this field can then be assigned to the categories used by the ABM through dropdown menus.
For categories that are not relevant to the model, select:
Ignore / not used
The uploaded building data must contain at least one school and one residential building.

**2. Upload the road network and study area boundary**
Next, upload the ZIP folders containing:
The road network
The geographical boundary of the study area
The application checks whether the uploaded shapefiles use the same Coordinate Reference System.
If their spatial reference systems do not match, the scenario cannot be run.

**3. Configure model parameters**
Several ABM parameters can be changed through the frontend.
For example:
Visual exposure radius
Determines the distance within which agents can be visually exposed to food outlets.
Exposure multiplier
Determines how strongly exposure to food outlets influences adolescents' probability of leaving the school campus during lunch.
Willingness to pay
Lunch break duration
These settings allow users to explore how different modelling assumptions affect the simulated outcomes.

**4. Run the scenario**
After configuring the inputs and parameters, click:

_Run scenario_

The model runs five simulations of a complete school week.
The application reports the average number of lunch decisions resulting in:

- On-campus lunches
- Visits to healthy food outlets
- Visits to unhealthy food outlets

Multiple spatial scenarios can be run and compared within the application.
The comparison results can also be downloaded as a CSV file.
**Interpretation**
The model is intended as an exploratory scenario tool.
Its results should be interpreted as simulated outcomes under the assumptions represented in the ABM, rather than as direct predictions of real-world adolescent behaviour.


