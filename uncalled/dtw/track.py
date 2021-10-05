#!/usr/bin/env python3

import sys, os
import numpy as np
import argparse
from collections import defaultdict, namedtuple
import re
import time
from typing import NamedTuple
from matplotlib.colors import Normalize
import pandas as pd
import copy
import sqlite3

import scipy.stats
from sklearn.decomposition import PCA

import matplotlib.pyplot as plt

from ..pafstats import parse_paf, PafEntry
from ..argparse import Opt, ref_coords
from .. import nt, PoreModel, config, index 
from ..index import load_index, RefCoord

KMER_LAYER       = "kmer"
CURRENT_LAYER    = "current"
DWELL_LAYER      = "dwell"
MODEL_DIFF_LAYER = "model_diff"
DEFAULT_LAYERS = [CURRENT_LAYER, DWELL_LAYER, MODEL_DIFF_LAYER]

LayerMeta = namedtuple("LayerMeta", ["type", "label", "derived"])

LAYER_META = {
    "start"   : LayerMeta(int, "Sample Start", False),
    "length"  : LayerMeta(int, "Sample Length", False),
    "current" : LayerMeta(float, "Current (pA)", False),
    "kmer"    : LayerMeta(int, "Reference K-mer", True),
    "mref"    : LayerMeta(int, "Mirrored Packed Ref. Coord.", False),
    "dwell"   : LayerMeta(float, "Dwell Time (ms/nt)", True),
    "model_diff" : LayerMeta(float, "Model pA Difference", True),
}

LAYERS = {
    "dtw" : {
        "start" : LayerMeta(int, "Sample Start", False),
        "length" : LayerMeta(int, "Sample Length", False),
        "current" : LayerMeta(float, "Current (pA)", False),
        "dwell" : LayerMeta(float, "Dwell Time (ms/nt)", True),
        "model_diff" : LayerMeta(float, "Model pA Difference", True)},
    "bcaln" : { 
        "sample" : LayerMeta(int, "Sample Start", False),
        "bp" : LayerMeta(int, "Basecaller Base Index", False),
        "err" : LayerMeta(str, "Basecalled Alignment Error", False)}
}

def parse_layers(layers):
    if isinstance(layers, str):
        layers = layers.split(",")

    ret = list()

    for layer in layers:
        spl = layer.split(".")
        if len(spl) == 2:
            group,layer = spl
        elif len(spl) == 1:
            group = "dtw"
            layer = spl[0]
        else:
            raise ValueError("Invalid layer specifier \"%s\", must contain at most one \".\"" % layer)

        if not group in LAYERS:
            raise ValueError("Invalid layer group \"%s\". Options: %s" % (group, LAYERS.keys()))

        group_layers = LAYERS[group]

        if not layer in group_layers:
            raise ValueError("Invalid layer \"%s\". Options: %s" % (group, group_layers.keys()))

        ret.append( (group, layer) )

class AlnTrack:

    #TODO get rid of htis
    CMP_LAYERS = ["current", "dwell"]

    def __init__(self, db, track_id, name, desc, groups, conf):
        self.db = db
        #self.index = index
        self.id = track_id
        self.name = name
        self.desc = desc
        self.groups = groups.split(",")
        self.conf = conf

        self.read_ids = set()

        self.mat = None
        self.coords = None
        self.layers = None

        self.model = PoreModel(self.conf.pore_model) 

    def _group_layers(self, group, layers):
        return pd.concat({group : layers}, names=["group", "layer"], axis=1)
        
    def add_layer_group(self, group, df, aln_id=None):
        aln_id = self._default_id(aln_id)
        df = self._group_layers(group, df)#pd.concat({group : layers}, names=["group", "layer"], axis=1)

        df.index = pd.MultiIndex.from_product(
                        [df.index, [aln_id]], 
                        names=["mref", "aln_id"])

        self.db.write_layers(df)

        if self.layers is None:
            self.layers = df
        else:
            self.layers = pd.concat([self.layers, df], axis=1)

    def aln_ref_coord(self, aln_id):
        return RefCoord(*self.alignments[["ref_name","ref_start","ref_end","fwd"]].loc[aln_id])

    #def _aln_coords(self, aln_id):
    #    #ref_coord = RefCoord(
    #    #    *self.alignments[["ref_name","ref_start","ref_end","fwd"]].loc[aln_id])
    #    return self.index.get_coord_space(self.aln_ref_coord(aln_id), self.conf.is_rna, kmer_shift=0)

    def _default_id(self, aln_id):
        if aln_id is None:
            if len(self.alignments) == 1:
                return self.alignments.index[0]
            raise ValueError("Must specify aln_id for Track with more than one alignment loaded")
        return aln_id


    def set_layers(self, layers):
        if layers is not None:
            self.prms.layers = layers
        self.layer_idxs = {layer : i for i,layer in enumerate(self.prms.layers)}

    #TODO parse mm2 every time to enable changing bounds
    #eventually use some kind of tabix-like indexing
    def set_data(self, coords, alignments, layers, load_mat=False):
        self.coords = coords
        self.layers = layers#pd.concat(layers, names=["group", "layer"], axis=1)

        self.alignments = alignments
        self.alignments.sort_values(["fwd", "ref_start"], inplace=True)

        if self.coords.kmers is not None:
            mrefs = self.layers.index.get_level_values("mref")
            if self.coords.stranded:
                self.kmers = self.coords.kmers[mrefs]
            else:
                self.kmers = pd.concat(self.coords.kmers)[mrefs]

        self.has_fwd = np.any(self.alignments['fwd'])
        self.has_rev = not np.all(self.alignments['fwd'])

    def load_mat(self):

        df = self.layers.copy()
        df["aln_id"] = df.index.get_level_values("aln_id")
        df.index = self.coords.mref_to_ref_index(df.index.get_level_values("mref"), multi=False)
        df = df.reset_index()

        self.mat = df.pivot(index="aln_id", columns=["ref"]) \
                     .rename_axis(("group","layer","ref"), axis=1) \
                     .sort_index(axis=1, level="ref")

        self.mat = self.mat.reindex(self.alignments.index, copy=False)

        self.width = len(self.coords.refs)
        self.height = len(self.alignments)

    #@property
    #def kmers(self):
    #    if self.coords.stranded:
    #        return self.coords.kmers[self.layers.index.get_level_values("mref")]
    #    return self.coords.kmers[True][self.layers.index.get_level_values("mref")]


    def sort_coord(self, layer, ref):
        order = (-self.mat[layer,ref].fillna(0)).argsort()
        self.sort(order)

    def sort(self, order):
        self.mat = self.mat.iloc[order]
        self.alignments = self.alignments.iloc[order]

    def calc_ks(self, track_b):
        ks_stats = np.zeros((len(self.CMP_LAYERS), self.width))

        for i,l in enumerate(AlnTrack.CMP_LAYERS):
            for j,rf in enumerate(self.coords.mrefs[True]):
                a = self.layers["dtw",l].loc[rf]
                b = track_b.layers["dtw",l].loc[rf]
                ks = scipy.stats.mstats.ks_2samp(a,b,mode="asymp")
                ks_stats[i][j] = ks[0]

        return ks_stats

    def calc_pca(self, layer, ref_start, ref_end, n_components=2):
        x = self[layer,:,ref_start:ref_end].T
        pc = PCA(n_components=n_components).fit_transform(x)
        data = {"read_id" : self.alignments["id"]}
        for c in range(n_components):
            data["pc%d" % (c+1)] = pc[:,c]
        return pd.DataFrame(data).set_index("read_id")
    
    
    def sort_pca(self, layer, ref_start, ref_end):
        pc = self.calc_pca(layer, ref_start, ref_end, 1)
        self.sort(pc["pc1"].argsort())


    def __getitem__(self, key):
        if isinstance(key, str):
            #key = self.layer_idxs[key]
            return self.mat[key]
        if len(key) == 3:
            return self.mat[key[0],key[2]][key[1]]
        return self.mat[key[0]][key[1]]
    
    @property
    def kmer(self):
        return self.mat[self.KMER_LAYER]

    @property
    def pa(self):
        return self.mat[self.PA_LAYER]
    
    @property
    def dwell(self):
        return self.mat[self.DWELL_LAYER]
    
    @property
    def pa_diff(self):
        return self.mat[self.PA_DIFF_LAYER]

