import sys

sys.path.append("oswm_codebase")

from datetime import datetime
from functions import *

# from constants import *

import geopandas as gpd
import pandas as pd
import altair as alt


alt.data_transformers.disable_max_rows()

now = datetime.now()
dt_string = now.strftime("%d/%m/%Y %H:%M:%S")

default_color = alt.value("lightseagreen")


def get_count_df(
    input_df,
    fieldname,
    str_to_append="",
    #  " type"
):
    outfieldname = fieldname + str_to_append
    return (
        input_df[fieldname]
        .value_counts()
        .reset_index()
        .sort_values(by="count", ascending=False),
        outfieldname,
        # .rename(columns={"index": outfieldname, fieldname: "count"})
    )


def create_barchart(
    input_df,
    fieldname,
    title,
    str_to_append="",
    title_fontsize=24,
    tooltip="count",
    x_sort="-y",
    tooltip_list=["percent"],
):
    # bind = alt.selection_interval(bind='scales')
    # .add_selection(bind)

    data_to_plot, fieldname_v2 = get_count_df(input_df, fieldname, str_to_append)

    feat_count = float(data_to_plot["count"].sum())

    def compute_formatted_percent(featureval):
        return str(round((featureval / feat_count) * 100, 2)) + "%"

    data_to_plot["percent"] = data_to_plot["count"].apply(compute_formatted_percent)

    return (
        alt.Chart(data_to_plot, title=title)
        .mark_bar()
        .encode(
            x=alt.X(fieldname_v2, sort=x_sort),
            y="count",
            tooltip=tooltip_list,
        )
        .properties(width=650, height=300)
        .configure_title(fontSize=title_fontsize)
        .interactive()
    )


def create_barchartV2(
    input_gdf,
    fieldname,
    title,
    filter_out_opt="?",  # value to filter out
    filter_out_opt_text='Include "?" (Unknown)',
    str_to_append=" type",
    title_fontsize=24,
    len_field="length(km)",
    color_field="feature count",
    excluding_categories=[],
):
    import altair as alt

    # Create a modified fieldname for plotting
    fieldname_v2 = fieldname + str_to_append

    # add a dummy "count" if no len_field
    if not len_field:
        input_gdf = input_gdf.copy()  # to avoid fragmentation
        input_gdf["count"] = 1
        len_field = "count"

    if excluding_categories:
        input_gdf = input_gdf[~input_gdf["category"].isin(excluding_categories)]

    # Define the fields to plot
    if color_field == "feature count":
        fields_to_plot = [fieldname, len_field]
    else:
        fields_to_plot = [color_field, fieldname, len_field]

    # aggregation fields:
    if color_field == "feature count":
        agg_fields = {fieldname: "count", len_field: "sum"}
    else:
        agg_fields = {color_field: "sum", fieldname: "count", len_field: "sum"}

    # Aggregate the data for plotting
    data_to_plot = (
        input_gdf[fields_to_plot]
        .groupby([fieldname])
        .agg(agg_fields)
        .rename(columns={fieldname: "feature count"})
        .reset_index()
        .rename(columns={fieldname: fieldname_v2})
    )

    # Create an interactive selection for filtering (boolean checkbox)
    # if filter_out_opt: # TODO: implement the option for no filter
    filter_checkbox = alt.binding_checkbox(name=filter_out_opt_text)
    selection = alt.param(
        name="include_filter_out_opt", bind=filter_checkbox, value=True
    )
    # else:
    #     selection = alt.param(name="empty")

    if color_field == "feature count":
        tooltip_fields = [fieldname_v2, len_field, "feature count"]
    else:
        tooltip_fields = [color_field, fieldname_v2, len_field, "feature count"]

        # avoiding dupes:
        tooltip_fields = list(set(tooltip_fields))

        # another workaround, geez:
        if "feature count" and "count" in tooltip_fields:
            tooltip_fields.remove("count")

    # Create the bar chart with conditional filtering
    chart = (
        alt.Chart(data_to_plot, title=title)
        .mark_bar()
        .encode(
            x=alt.X(fieldname_v2, sort="-y"),
            y=len_field,
            tooltip=tooltip_fields,
            color=color_field,
        )
        .properties(width=650, height=300)
        .configure_title(fontSize=title_fontsize)
        .add_params(selection)
        .transform_filter(
            f"include_filter_out_opt || datum['{fieldname_v2}'] != '{filter_out_opt}'"
        )
        .interactive()
    )

    return chart


def print_relevant_columnames(
    input_df, not_include=("score", "geometry", "type", "id")
):
    print(
        *[
            f"{column}, "
            for column in input_df.columns
            if not any(word in column for word in not_include)
        ]
    )


def return_weblink(string_id, type="way"):
    return f"<a href=https://www.openstreetmap.org/{type}/{string_id}>{string_id}</a>"


def get_year_surveydate(featuredate):
    if featuredate:
        return featuredate.split("-")[0]


def create_double_mat_and_bar(
    input_df,
    title,
    xs="surface",
    ys="smoothness",
    scolor=None,
    xh="count()",
    yh1="surface",
    yh2="smoothness",
    hcolor=None,
    fontsize=24,
    # tooltip_fields: list = ["element_type", "id"], # deprecated, as there's generally too much data
):

    # preselect only the needed columns:
    """
    Creates a double scatter-bar chart for visualizing two different features
    of a given GeoDataFrame (or Pandas DataFrame).

    Parameters
    ----------
    input_df : GeoPandas GeoDataFrame or Pandas DataFrame
        The DataFrame containing the data to be plotted.
    title : str
        The title of the plot.
    xs, ys : str
        The column names of the two features to be plotted in the scatter plot.
    scolor : str or None
        The color for the scatter plot. If None, defaults to 'lightseagreen'.
    xh, yh1, yh2 : str
        The column names for the x and y axes of the histograms.
    hcolor : str or None
        The color for the histograms. If None, defaults to 'lightseagreen'.
    fontsize : int
        The font size for the title.


    Returns
    -------
    An Altair chart object.
    """
    needed_columns = [xs, ys, xh, yh1, yh2, hcolor, scolor]

    # remove None, and any one with "()":
    needed_columns = [column for column in needed_columns if column]
    needed_columns = [column for column in needed_columns if "()" not in column]
    needed_columns = list(set(needed_columns))

    # only keep the needed columns:
    input_df = input_df[needed_columns].copy()

    interval = alt.selection_interval()

    if not hcolor:
        hcolor = default_color

    if not scolor:
        scolor = default_color

    scatter = (
        alt.Chart(input_df, title=title)
        .mark_point()
        # .mark_rect() # MAYBE? TODO: how to make it have a different color than the histogram
        .encode(
            x=xs,
            y=ys,
            color=scolor,
            tooltip=alt.Tooltip(["count()"], title="count:"),
        )
        .properties(
            width=600,
            # height=350,
        )
        .add_params(interval)
    )

    hist_base = (
        alt.Chart(input_df)
        .mark_bar()
        .encode(
            x=alt.X(xh, title=xh.replace("()", "").title() + " (selection)"),
            color=hcolor,
            tooltip=alt.Tooltip(["count()"], title="count:"),
        )
        .properties(
            width=300,
            height=220,
        )
        .transform_filter(
            interval,
        )
    )

    # if hcolor:
    #      hist_base.encode(color=hcolor)

    # extra encoding rules
    encoding_base = {}

    # if hcolor:
    #     encoding_base["color"] = hcolor

    encoding_h1 = encoding_base.copy()
    encoding_h1["y"] = yh1

    encoding_h2 = encoding_base.copy()
    encoding_h2["y"] = yh2

    # define the histograms
    # hist = hist_base.encode(**encoding_h1) | hist_base.encode(**encoding_h2)
    hist = alt.hconcat(
        hist_base.encode(**encoding_h1),
        hist_base.encode(**encoding_h2),
        # title="selection",
    )

    # return (scatter & hist).configure_title(fontSize=fontsize, align="center")
    return alt.vconcat(scatter, hist).configure_title(fontSize=fontsize, align="center")


def create_linked_boxplot_histogram(
    df,
    column,
    boxplot_title,
    # tooltip_fields: list = [], # deprecated, as there's generally too much data
    color_field=None,
    hist_title="",
    maxbins=10,
    width=400,
    height=100,
    color_share_y_boxplot=True,
):

    # Ensure tooltip_fields is a list
    # if tooltip_fields is None:
    #     tooltip_fields = []
    # elif not isinstance(tooltip_fields, list):
    #     raise ValueError("tooltip_fields must be a list of column names.")

    # Include the main column and color_field in the necessary columns
    necessary_columns = [column]  # + tooltip_fields
    if color_field and color_field not in necessary_columns:
        necessary_columns.append(color_field)

    # Filter the DataFrame to include only necessary columns
    df_filtered = df[necessary_columns].copy()

    # Define tooltip encoding
    # tooltip_encoding = []
    # for field in tooltip_fields:
    #     if pd.api.types.is_numeric_dtype(df[field]):
    #         field_type = "Q"
    #     elif pd.api.types.is_datetime64_any_dtype(df[field]):
    #         field_type = "T"
    #     else:
    #         field_type = "N"
    #     tooltip_encoding.append(alt.Tooltip(f"{field}:{field_type}", title=field))

    # Determine the type of the color field
    if color_field:
        if pd.api.types.is_numeric_dtype(df[color_field]):
            color_type = "Q"  # Quantitative
        elif pd.api.types.is_datetime64_any_dtype(df[color_field]):
            color_type = "T"  # Temporal
        else:
            color_type = "N"  # Nominal
        color_encoding = alt.Color(
            f"{color_field}:{color_type}", legend=alt.Legend(title=color_field)
        )
    else:
        color_encoding = alt.value(
            "steelblue"
        )  # Default color if no color_field is specified

    # Create a selection for interactivity, bind it to scales
    selection = alt.selection_interval(encodings=["x"], bind="scales", name="brush")

    box_encoding = {
        "x": alt.X(f"{column}:Q", scale=alt.Scale(zero=False)),
        "color": color_encoding,
        "tooltip": alt.Tooltip(column),
    }

    if color_field and color_share_y_boxplot:
        box_encoding["y"] = alt.Y(f"{color_field}:{color_type}")

    # Create a boxplot that responds to the selection
    boxplot = (
        alt.Chart(df_filtered)
        .mark_boxplot()
        .encode(**box_encoding)
        .transform_filter(selection)  # Filter the boxplot based on the selection
        .properties(title=boxplot_title, width=width, height=height)
    )

    # Create a histogram with the selection
    hist = (
        alt.Chart(df_filtered)
        .mark_bar()
        .encode(
            alt.X(f"{column}:Q", bin=alt.Bin(maxbins=maxbins)),
            y="count()",
            color=color_encoding,
            # tooltip=tooltip_encoding, # It's buggy
            tooltip=alt.Tooltip("count()", title="count"),
        )
        .add_params(selection)  # Add the selection to the histogram
        # .properties(title=hist_title, width=400, height=200)
    )

    # Combine both charts: boxplot above histogram
    combined_chart = alt.vconcat(boxplot, hist).resolve_scale(
        x="shared"
    )  # Share the x-axis scale

    return combined_chart


def create_rev_date(row):
    try:
        return datetime(
            year=int(row["rev_year"]),
            month=int(row["rev_month"]),
            day=int(row["rev_day"]),
        )
    except ValueError:
        # Handle invalid dates, you can return None or a specific default date
        return datetime(
            default_missing_year, default_missing_month, default_missing_day
        )


global_insertions = {
    "<head>": """

    <head>

    <link rel="stylesheet" href="https://kauevestena.github.io/oswm_codebase/assets/styles/stats_styles.css">
    <script src="https://kauevestena.github.io/oswm_codebase/assets/webscripts/stats_funcs.js"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/4.7.0/css/font-awesome.min.css">


    <title>OSWM Dashboard</title>

    <link rel="icon" type="image/x-icon" href="https://kauevestena.github.io/oswm_codebase/assets/homepage/favicon_homepage.png">

    """,
}

global_exclusions = [{"points": ["<style>", "</style>"], "multiline": True}]

dashboard_main_page_insertions = {
    "<body>": """
    <body>
    <h1 style="text-align: center;">Welcome to the OSWM Node Dashboard!</h1>
    <div style="text-align: center; padding: 5px;">
        <img src="https://kauevestena.github.io/oswm_codebase/assets/homepage/project_logo.png" alt="OSWM Project Logo">
    </div>
    <h3 style="text-align: center; font-weight: normal;"><b>Select a category of data</b> or the aggregated on "All Data Charts"<br><br>Or click the blue button to go back to the node homepage!<br><br>Most <b>charts are interactive</b>, so try out some pan and zoom!<br></form></h3>

    <h4 style="text-align: center; font-weight: normal;">They're made with the amazing Altair library!<br> so <b>you can click on the 3 dots on the upper right corner</b>,<br> to export to different formats and edit on the Vega Editor!</h4>


    </body>"""
}
