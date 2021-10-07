import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np

from .sigplot import Sigplot

from ... import config, nt

from ...dtw.track import LAYER_META
from ...index import str_to_coord
from ...dtw.track_io import TrackIO, parse_layers, LAYERS
from ...argparse import Opt, comma_split
from ...fast5 import parse_read_ids
from ...sigproc import ProcRead

track_colors = ["#AA0DFE", "#1CA71C", "#6A76FC"]

class DotplotParams(config.ParamGroup):
    _name = "dotplot"
DotplotParams._def_params(
    ("tracks", None, None, "DTW aligment tracks"),
    ("layers", ["model_diff"], None, ""),
    ("track_colors", ["#AA0DFE", "#1CA71C", "#6A76FC"], list, ""),
)

class Dotplot:
    def __init__(self, *args, **kwargs):
        self.conf, self.prms = config._init_group("dotplot", *args, **kwargs)
        self.tracks = self.prms.tracks #TODO do this better
        self.prms.layers = list(parse_layers(self.prms.layers))

        column_widths=[5]+[1]*len(self.prms.layers)

        self.fig = make_subplots(
            rows=2, cols=len(column_widths), 
            row_heights=[1,3],
            column_widths=column_widths,
            vertical_spacing=0.01,
            horizontal_spacing=0.01,
            shared_xaxes=True,
            shared_yaxes=True)

        Sigplot(self.tracks, track_colors=self.prms.track_colors, conf=self.conf).plot(self.fig)

        hover_df = dict()

        for i,track in enumerate(self.tracks):

            track_df = list()
            
            for aln_id, aln in track.alignments.iterrows():
                layers = track.layers.xs(aln_id, level="aln_id")
                dtw = layers["dtw"]
                refs = layers["ref","coord"]


                df = layers["dtw"][["middle","current","dwell","model_diff"]].set_index(layers["ref","coord"])
                
                track_df.append(df)

                self.fig.add_trace(go.Scatter(
                    x=dtw["start"], y=refs,
                    name=track.name,
                    legendgroup=track.desc,
                    line={"color":self.prms.track_colors[i], "width":2, "shape" : "hv"},
                    hoverinfo="skip",
                ), row=2, col=1)

                for j,layer in enumerate(self.prms.layers):
                    self.fig.add_trace(go.Scatter(
                        x=dtw[layer[1]], y=refs-0.5, #TODO try vhv
                        name=track.name, 
                        line={
                            "color" : self.prms.track_colors[i], 
                            "width":2, "shape" : "hv"},
                        legendgroup=track.desc, showlegend=False,
                    ), row=2, col=j+2)

            hover_df[track.name] = pd.concat(track_df)

        hover_df = pd.concat(hover_df, axis=1)
        hover_coords = hover_df.xs("middle", axis=1, level=1).mean(axis=1)
        hoverdata = hover_df.drop("middle", axis=1, level=1).to_numpy()

        hover_rows = [
            track.coords.ref_name + ":%{y:,d}"
        ]
        labels = [
            "Current (pA): ", 
            "Dwell (ms): ", 
            "Model pA Diff: "]
        for i,label in enumerate(labels):
            s = "<b>"+label+"</b>"
            #s = "<b style=\"font-family:mono\">"+label+"</b>"
            fields = list()
            for j in range(len(self.tracks)):
                fields.append(
                    '<span style="color:%s;float:right">%%{customdata[%d]:.2f}</span>' % 
                    (self.prms.track_colors[j], j*3+i))
            hover_rows.append(s + ", ".join(fields))

        self.fig.add_trace(go.Scatter(
            x=hover_coords, y=hover_coords.index,
            mode="markers", marker={"size":0,"color":"rgba(0,0,0,0)"},
            name="",
            customdata=hoverdata,
            hovertemplate="<b>"+"<br>".join(hover_rows)+"</b>",
            hoverlabel={"bgcolor":"rgba(255,255,255,1)"},
            showlegend=False
        ), row=2,col=1)
            #customdata=hoverdata.to_numpy(),


        if track.coords.fwd == self.conf.is_rna:
            self.fig.update_yaxes(autorange="reversed", row=2, col=1)
            self.fig.update_yaxes(autorange="reversed", row=2, col=2)

        self.fig.update_yaxes(row=2, col=1,
            title_text="Reference (%s)" % aln["ref_name"])

        for i,layer in enumerate(self.prms.layers):
            self.fig.update_xaxes(row=2, col=i+2,
                title_text=LAYERS[layer[0]][layer[1]].label)

        axis_kw = dict(
            showspikes=True,
            spikemode="across",
            spikecolor="darkgray",
            spikethickness=1)

        self.fig.update_xaxes(**axis_kw)
        self.fig.update_yaxes(**axis_kw)
        #self.fig.update_yaxes(showspikes=True)

        self.fig.update_xaxes(
            title_text="Raw Sample", 
            tickformat="d", 
            #showspikes=True,
            row=2, col=1)

        self.fig.update_layout(
            #hovermode="x unified",
            hoverdistance=20,
            dragmode="pan", 
            legend={"bgcolor" : "#e6edf6"})#, scroll_zoom=True)


OPTS = (
    Opt("input", "track_io", nargs="+"),
    Opt(("-o", "--out-prefix"), type=str, default=None, help="If included will output images with specified prefix, otherwise will display interactive plot."),
    Opt(("-f", "--out-format"), default="svg", help="Image output format. Only has an effect with -o option.", choices={"pdf", "svg", "png"}),
    Opt(("-R", "--ref-bounds"), "track_io", type=str_to_coord),
    Opt(("-l", "--read-filter"), "track_io", type=parse_read_ids),
    Opt(("-L", "--layers"), "dotplot", type=comma_split),
)

def main(conf):
    """plot a dotplot"""
    conf.track_io.layers = ["ref.coord", "start", "length", "middle", "current", "dwell"] + conf.dotplot.layers
    io = TrackIO(conf=conf)

    for read_id, tracks in io.iter_reads():
        print(read_id)
        fig = Dotplot(tracks, conf=io.conf).fig

        fig.write_html(conf.out_prefix + read_id + ".html", config={"scrollZoom" : True, "displayModeBar" : True})
