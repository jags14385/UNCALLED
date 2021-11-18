import plotly.express as px
import pandas as pd
import numpy as np

import dash
from dash import html, dcc, dash_table
from dash.dependencies import Input, Output, State
import sys

from .trackplot import Trackplot, PLOT_LAYERS
from .dotplot import Dotplot
from .. import config
from ..index import str_to_coord
from ..dtw.tracks import Tracks
from ..dtw.aln_track import LAYERS, parse_layer
from ..argparse import Opt, comma_split


OPTS = (
    Opt("input", "tracks", nargs="+"),
    Opt("ref_bounds", "tracks", type=str_to_coord),
    #Opt("layer", "trackplot", default="current", nargs="?"),
    Opt(("-r", "--refstats"), "tracks", default=None, type=comma_split),
    Opt(("-f", "--full-overlap"), "tracks", action="store_true"),
    Opt(("-o", "--outfile"), "trackplot"),
)

def main(conf):
    """Interactive signal alignment genome browser"""
    conf.tracks.load_mat = True
    conf.tracks.refstats_layers.append("cmp.mean_ref_dist")
    conf.dotplot.layers=["model_diff"]
    sys.stderr.write("Loading tracks...\n")
    tracks = Tracks(conf=conf)
    sys.stderr.write("Starting server...\n")
    browser(tracks, conf)

def _icon_btn(icon, name=None, panel="", hide=False):
    style={"display" : "none" if hide else "inline-block"}
    if name is not None:
        href = f"javascript:{name}('{panel}')"
        id=f"{panel}-{name}"
    else:
        href = "javascript:void()"
        id=""

    return html.A(icon, id=id, className="material-icons w3-padding-24", href=href, style=style)

def _panel(title, name, content, settings=None, hide=False):
    style={"display" : "none" if hide else "block"}

    ret = [html.Header(
        id=f"{name}-header", 
        className="w3-display-container w3-deep-purple", 
        style={"height":"40px"},
        children = [
            html.Div(
                html.H5(html.B(title)),
                className="w3-padding w3-display-left"),
            
            html.Div(children=[
                _icon_btn("settings", "toggle_settings", name),
                #_icon_btn("arrow_drop_down"),
                #_icon_btn("arrow_drop_up"),
                _icon_btn("remove", "minimize", name),
                _icon_btn("add", "maximize", name, hide=True),
            ], className="w3-display-right w3-padding"),
    ])]

    if settings is not None:
        ret.append(html.Div(
            settings, 
            id=f"{name}-settings", 
            style={"display" : "none"},
            className="w3-container w3-pale-blue"))
        
    ret.append(
        html.Div(content, id=f"{name}-body", className="w3-container"))

    return html.Div(
        html.Div(ret, id=f"{name}-card", className="w3-card"),
        id=f"{name}-panel", className="w3-panel", style=style)

def browser(tracks, conf):
    external_stylesheets = [
        "https://fonts.googleapis.com/icon?family=Material+Icons",
        "https://www.w3schools.com/w3css/4/w3.css",
    ]

    app = dash.Dash(__name__, external_stylesheets=external_stylesheets)
    app.title = "Uncalled4 Browser"

    layer_opts = [
        {"label" : LAYERS[group][layer].label, "value" : f"{group}.{layer}"}
        for group,layer in tracks.aln_layers(PLOT_LAYERS)]

    app.layout = html.Div(children=[
        html.Div(
            html.H3(html.B("Uncalled4 Genome Browser")), 
            className="w3-container w3-deep-purple"),

        html.Div([
            html.Div(
                _panel("Trackplot", "trackplot", 
                    content=[
                        dcc.Dropdown(
                            options=layer_opts,
                            value=layer_opts[0]["value"], 
                            clearable=False, multi=False,
                            className="w3-padding",
                            id="trackplot-layer"),
                        dcc.Graph(#[dcc.Loading(type="circle"),
                            id="trackplot",
                            config = {"scrollZoom" : True, "displayModeBar" : True})
                    ], settings=[
                        html.P("blah blah blah")
                ])
            , className="w3-half"),

            html.Div([
                _panel("Selection", "selection",
                        html.Table([], id="info-table")),

                _panel("Dotplot", "dotplot",
                    dcc.Graph(
                        id="dotplot",
                        config = {"scrollZoom" : True, "displayModeBar" : True}
                    ), hide=True,
                ),
            ], className="w3-half"),

        ]),
        html.Div(style={"display" : "none"}, id="selected-read"),
        html.Div(style={"display" : "none"}, id="selected-ref"),
    ])

    @app.callback(
        Output("trackplot", "figure"),
        Output("info-table", "children"),
        Output("selection-panel", "style"),
        Output("selected-ref", "children"),
        Output("selected-read", "children"),
        Input("trackplot-layer", "value"),
        Input("trackplot", "clickData"))
    def update_trackplot(layer, click):
        table = list()
        ref = aln = read = None
        card_style = {"display" : "none"}
        if click is not None:
            coord = click["points"][0]
            ref = coord["x"]

            if coord["curveNumber"] < len(tracks):
                track = tracks.alns[coord["curveNumber"]]
                aln = track.alignments.iloc[coord["y"]]
                read = aln["read_id"]

                layers = track.layers.loc[(ref, aln.name)]["dtw"]

                table.append(html.Tr(html.Td(html.B("%s:%d" % (tracks.coords.ref_name, ref)), colSpan=2)))
                table.append(html.Tr(html.Td([html.B("Read "), read], colSpan=2)))
                for l in ["current", "dwell", "model_diff"]:
                    table.append(html.Tr([
                        html.Td(html.B(LAYERS["dtw"][l].label)), 
                        html.Td("%.3f"%layers[l], style={"text-align":"right"})]))

                card_style = {"display" : "block"}

        layer, = parse_layer(layer)

        fig = Trackplot(
            tracks, [("mat", layer)], 
            select_ref=ref, select_read=read, 
            conf=conf).fig
        fig.update_layout(uirevision=True)

        return fig, table, card_style, ref, read

    @app.callback(
        Output("dotplot", "figure"),
        Output("dotplot-panel", "style"),
        #State("selected-read", "children"),
        #Input("dotplot-btn", "n_clicks"))
        Input("trackplot", "clickData"))
    def update_trackplot(click):
        #if n_clicks is None:
        #    print("Nothing")
        #    return {}, {"display" : "hidden"}

        if click is None: 
            return {}, {"display" : "hidden"}
        coord = click["points"][0]
        if coord["curveNumber"] >= len(tracks): 
            return {}, {"display" : "hidden"}
        ref = coord["x"]

        track = tracks.alns[coord["curveNumber"]]
        aln = track.alignments.iloc[coord["y"]]
        read = aln["read_id"]

        fig = Dotplot(tracks, select_ref=ref, conf=tracks.conf).plot(read)
        #fig.update_layout(uirevision=True)

        return fig, {"display" : "block"}

    app.run_server(debug=True)
