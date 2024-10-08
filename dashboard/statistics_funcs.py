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
    str_to_append=" type",
    title_fontsize=24,
    len_field="length(km)",
):

    # bind = alt.selection_interval(bind='scales')
    # .add_selection(bind)

    fieldname_v2 = fieldname + str_to_append

    data_to_plot = (
        input_gdf[[len_field, fieldname]]
        .groupby([fieldname])
        .agg({fieldname: "count", len_field: "sum"})
        .rename(columns={fieldname: "feature count"})
        .reset_index()
        .rename(columns={fieldname: fieldname_v2})
    )

    return (
        alt.Chart(data_to_plot, title=title)
        .mark_bar()
        .encode(
            x=alt.X(fieldname_v2, sort="-y"),
            y=len_field,
            tooltip=len_field,
            color="feature count",
        )
        .properties(width=650, height=300)
        .configure_title(fontSize=title_fontsize)
        .interactive()
    )


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


def double_scatter_bar(
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
    tooltip_fields: list = ["element_type", "id"],
):

    # preselect only the needed columns:
    needed_columns = tooltip_fields + [xs, ys, xh, yh1, yh2, hcolor, scolor]

    # remove None, and any one with "()":
    needed_columns = [column for column in needed_columns if column]
    needed_columns = [column for column in needed_columns if "()" not in column]
    needed_columns = list(set(needed_columns))

    # only keep the needed columns:
    input_df = input_df[needed_columns].copy()

    interval = alt.selection_interval()

    default_color = alt.value("lightseagreen")

    if not hcolor:
        hcolor = default_color

    if not scolor:
        scolor = default_color

    scatter = (
        alt.Chart(input_df, title=title)
        .mark_point()
        .encode(
            x=xs,
            y=ys,
            color=scolor,
            tooltip=alt.Tooltip(tooltip_fields),
        )
        .properties(
            width=600,
            height=350,
        )
        .add_params(interval)
    )

    hist_base = (
        alt.Chart(input_df)
        .mark_bar()
        .encode(
            x=xh,
            color=hcolor,
            tooltip=alt.Tooltip(tooltip_fields),
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

    hist = hist_base.encode(y=yh1) | hist_base.encode(y=yh2)

    return (scatter & hist).configure_title(fontSize=fontsize, align="center")


def create_linked_boxplot_histogram(
    df,
    column,
    boxplot_title,
    tooltip_fields=None,
    color_field=None,
    hist_title="",
    maxbins=10,
    width=400,
    height=100,
):

    # Ensure tooltip_fields is a list
    if tooltip_fields is None:
        tooltip_fields = []
    elif not isinstance(tooltip_fields, list):
        raise ValueError("tooltip_fields must be a list of column names.")

    # Include the main column and color_field in the necessary columns
    necessary_columns = [column] + tooltip_fields
    if color_field and color_field not in necessary_columns:
        necessary_columns.append(color_field)

    # Filter the DataFrame to include only necessary columns
    df_filtered = df[necessary_columns].copy()

    # Define tooltip encoding
    tooltip_encoding = []
    for field in tooltip_fields:
        if pd.api.types.is_numeric_dtype(df[field]):
            field_type = "Q"
        elif pd.api.types.is_datetime64_any_dtype(df[field]):
            field_type = "T"
        else:
            field_type = "N"
        tooltip_encoding.append(alt.Tooltip(f"{field}:{field_type}", title=field))

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

    # Create a boxplot that responds to the selection
    boxplot = (
        alt.Chart(df_filtered)
        .mark_boxplot()
        .encode(
            x=alt.X(f"{column}:Q", scale=alt.Scale(zero=False)),
            color=color_encoding,
            tooltip=tooltip_encoding,
        )
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
