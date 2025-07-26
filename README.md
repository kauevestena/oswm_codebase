# OSWM Codebase

This repository holds the code that is used to create the static data for each node of project OpenSidewalkMap or OSWM for short.

OSWM is a decentered and modular project, leveraging OpenStreetMap data for sidewalk data management.

Project's main repository: https://github.com/kauevestena/opensidewalkmap

OSWM organization: https://github.com/opensidewalkmap/

## Project Overview

The OSWM codebase is a data processing pipeline that takes OpenStreetMap (OSM) data as input and generates a set of data files and a web map that can be used to assess sidewalk accessibility. The pipeline performs the following steps:

1.  **Data Fetching:** Downloads OSM data for a specified area.
2.  **Data Filtering and Adaptation:** Cleans and processes the data, removing invalid or irrelevant features.
3.  **Data Enrichment:** Adds additional information to the data, such as versioning and scoring.
4.  **Data Quality Checks:** Performs a series of quality checks on the data to identify potential issues.
5.  **Web Map Generation:** Generates an interactive web map that visualizes the sidewalk data.
6.  **Statistics Generation:** Generates a set of statistics about the sidewalk data.

## Project Structure

The project is organized into the following directories:

*   `assets/`: Contains static assets for the web map and homepage.
*   `dashboard/`: Contains the code for generating the statistics dashboard.
*   `data_quality/`: Contains the code for performing data quality checks.
*   `demos/`: Contains demos and examples.
*   `deprecated/`: Contains deprecated code.
*   `generation/`: Contains the code for generating the web map and other outputs.
*   `other/`: Contains miscellaneous files.
*   `routing/`: Contains the code for the routing demo.
*   `tests/`: Contains the unit tests.
*   `webmap/`: Contains the code for the web map.
*   `workflows/`: Contains the GitHub Actions workflows.

## Local Development

To set up a local development environment, follow these steps:

1.  Clone the repository:

    ```
    git clone https://github.com/kauevestena/oswm_codebase
    ```

2.  Create a virtual environment and activate it:

    ```
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  Install the required dependencies:

    ```
    pip install -r requirements.txt
    ```

4.  Create a `config.py` file in the root directory of the project. You can use the `other/templates/config.py` file as a template.

5.  Run the data processing pipeline:

    ```
    python3 getting_data.py
    python3 filtering_adapting_data.py
    ```

## Running the Tests

To run the unit tests, run the following command from the root directory of the project:

```
python3 -m unittest discover tests
```
