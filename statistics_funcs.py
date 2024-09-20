from datetime import datetime
from functions import *

# from constants import *

import geopandas as gpd
import pandas as pd
import altair as alt

alt.data_transformers.disable_max_rows()

now = datetime.now()
dt_string = now.strftime("%d/%m/%Y %H:%M:%S")


def get_count_df(input_df, fieldname, str_to_append=" type"):
    outfieldname = fieldname + str_to_append
    return (
        input_df[fieldname]
        .value_counts()
        .reset_index()
        .rename(columns={"index": outfieldname, fieldname: "count"})
        .sort_values(by="count", ascending=False),
        outfieldname,
    )


def create_barchart(
    input_df,
    fieldname,
    title,
    str_to_append=" type",
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
    tooltip_fields=["element_type", "id"],
):

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
        .add_selection(interval)
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


# 'Surface x Smoothness'
