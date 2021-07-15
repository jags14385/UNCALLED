#!/usr/bin/env python

# MIT License
#
# Copyright (c) 2018 Sam Kovaka <skovaka@gmail.com>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from __future__ import division
import sys                         
import os
import numpy as np
import uncalled as unc
from bisect import bisect_left, bisect_right
from typing import NamedTuple

_index_cache = dict()

def load_index(prefix, load_pacseq=True, load_bwt=False):
    idx = _index_cache.get(prefix, None)
    if idx is None:
        idx = unc.BwaIndex(prefix, load_pacseq, load_bwt)
        _index_cache[prefix] = idx
    else:
        if load_pacseq and not idx.pacseq_loaded():
            idx.load_pacseq()
        if load_bwt and not idx.bwt_loaded():
            idx.load_index()
    return idx

#Index parameter group
class IndexParams(unc.config.ParamGroup):
    _name = "index"
IndexParams._def_params(
    ("fasta_filename", None, str, "FASTA file to index"),
    ("index_prefix", None, str, "Index output prefix. Will use input fasta filename by default"),
    ("no_bwt", False, bool, "Will only generate the pacseq if specified, which is much faster to build. Can only be used with DTW subcommands (NOT map, sim, or realtime)"),
    ("max_sample_dist", 100, int, "Maximum average sampling distance between reference alignments."),
    ("min_samples", 50000, int, "Minimum number of alignments to produce (approximate, due to deterministically random start locations),"),
    ("max_samples", 1000000, int, "Maximum number of alignments to produce (approximate, due to deterministically random start locations),"),
    ("kmer_len", 5, int, "Model k-mer length"),
    ("matchpr1", 0.6334, float, "Minimum event match probability"),
    ("matchpr2", 0.9838, float, "Maximum event match probability"),
    ("pathlen_percentile", 0.05, float, ""),
    ("max_replen", 100, int, ""),
    ("probs", None, str, "Find parameters with specified target probabilites (comma separated)"),
    ("speeds", None, str, "Find parameters with specified speed coefficents (comma separated)"),
)

from uncalled.config import Opt
BWA_OPTS = (
    Opt("bwa_prefix", "mapper"),
    Opt(("-p", "--idx-preset"), "mapper"),
)

OPTS = (
    Opt("fasta_filename", "index"),
    Opt(("-o", "--index-prefix"), "index"),
    Opt("--no-bwt", "index", action="store_true"),
    Opt(("-s", "--max-sample-dist"), "index"),
    Opt("--min-samples", "index"),
    Opt("--max-samples", "index"),
    Opt(("-1", "--matchpr1"), "index"),
    Opt(("-2", "--matchpr2"), "index"),
    Opt(("-f", "--pathlen-percentile"), "index"),
    Opt(("-m", "--max-replen"), "index"),
    Opt("--probs", "index"),
    Opt("--speeds", "index"),
)

def main(conf):
    """Builds an UNCALLED index from a FASTA reference"""

    prms = conf.index

    if prms.index_prefix is None or len(prms.index_prefix) == 0:
        prms.index_prefix = prms.fasta_filename

    bwa_built = True

    for suff in unc.index.UNCL_SUFFS:
        if not os.path.exists(prms.index_prefix + suff):
            bwa_built = False
            break

    if bwa_built:
        sys.stderr.write("Using previously built BWA index.\nNote: to fully re-build the index delete files with the \"%s.*\" prefix.\n" % prms.index_prefix)
    else:
        unc.BwaIndex.create(prms.fasta_filename, prms.index_prefix, prms.no_bwt)
        
        if prms.no_bwt: 
            sys.stderr.write("Pacseq built\n")
            return

    sys.stderr.write("Initializing parameter search\n")
    p = unc.index.IndexParameterizer(prms)

    p.add_preset("default", tgt_speed=115)

    if prms.probs != None:
        for tgt in prms.probs.split(","):
            sys.stderr.write("Writing 'prob_%s' parameters\n" % tgt)
            try:
                p.add_preset("prob_%s" % tgt, tgt_prob=float(tgt))
            except Exception as e:
                sys.stderr.write("Failed to add 'prob_%s'\n" % tgt)

    if prms.speeds != None:
        for tgt in prms.speeds.split(","):
            sys.stderr.write("Writing 'speed_%s' parameters\n" % tgt)
            try:
                p.add_preset("speed_%s" % tgt, tgt_speed=float(tgt))
            except:
                sys.stderr.write("Failed to add 'speed_%s'\n" % tgt)

    p.write()

    sys.stderr.write("Done\n")

#TODO move to BwaIndex?
UNCL_SUFF = ".uncl"
AMB_SUFF = ".amb"
ANN_SUFF = ".ann"
BWT_SUFF = ".bwt"
PAC_SUFF = ".pac" 
SA_SUFF = ".sa"
NOBWT_SUFFS = [ANN_SUFF, AMB_SUFF, PAC_SUFF]
UNCL_SUFFS = NOBWT_SUFFS + [UNCL_SUFF, PAC_SUFF, SA_SUFF]

def check_prefix(path, no_bwt=False):
    if no_bwt:
        suffs = NOBWT_SUFFS
    else:
        suffs = UNCL_SUFFS

    for suff in suffs:
        fname = path+suff
        if not os.path.exists(fname):
            raise FileNotFoundError("could not find index file \"%s\"" % fname)
    return True

ROOT_DIR = os.path.dirname(os.path.realpath(__file__))


def power_fn(xmax, ymin, ymax, exp, N=100):
    dt = 1.0/N
    t = np.arange(0, 1+dt, dt)

    return t*xmax, (t**exp) * (ymax-ymin) + ymin

class IndexParameterizer:
    #MODEL_THRESHS_FNAME = os.path.join(ROOT_DIR, "conf/r94_5mers_rna_threshs.txt")
    MODEL_THRESHS_FNAME = os.path.join(ROOT_DIR, "config/r94_5mers_threshs.txt")

    def __init__(self, params):
        self.prms = params

        self.out_fname = self.prms.index_prefix + UNCL_SUFF

        self.pck1 = self.prms.matchpr1
        self.pck2 = self.prms.matchpr2

        self.calc_map_stats()
        self.get_model_threshs()

        self.functions = dict()

    def calc_map_stats(self):

        ann_in = open(self.prms.index_prefix + ANN_SUFF)
        header = ann_in.readline()
        ref_len = int(header.split()[0])
        ann_in.close()

        approx_samps = ref_len / self.prms.max_sample_dist
        if approx_samps < self.prms.min_samples:
            sample_dist = int(np.ceil(ref_len/self.prms.min_samples))
        elif approx_samps > self.prms.max_samples:
            sample_dist = int(np.floor(ref_len/self.prms.max_samples))
        else:
            sample_dist = self.prms.max_sample_dist

        fmlens = unc.self_align(self.prms.index_prefix, sample_dist)
        path_kfmlens = [p[self.prms.kmer_len-1:] if len(p) >= self.prms.kmer_len else [1] for p in fmlens]

        max_pathlen = 0
        all_pathlens = [len(p) for p in path_kfmlens if len(p) <= self.prms.max_replen]
        gt1_counts = np.zeros(max(all_pathlens))
        for l in all_pathlens:
            for i in range(l):
                gt1_counts[i] += 1

        max_pathlen = np.flatnonzero(gt1_counts / len(all_pathlens) <= self.prms.pathlen_percentile)[0]
        max_fmexp = int(np.log2(max([p[0] for p in path_kfmlens])))+1
        fm_path_mat = np.zeros((max_fmexp, max_pathlen))

        for p in path_kfmlens:
            for i in range(min(max_pathlen, len(p))):
                fm_path_mat[int(np.log2(p[i])), i] += 1
            for i in range(len(p), max_pathlen):
                fm_path_mat[0, i] += 1

        mean_fm_locs = list()
        for f in range(max_fmexp):
            loc_weights = fm_path_mat[f] / np.sum(fm_path_mat[f])
            mean_fm_locs.append(np.sum([i*loc_weights[i] for i in range(max_pathlen)]))
        self.fm_locs = np.array(mean_fm_locs)

        mean_loc_fms = list()
        for p in range(max_pathlen):
            fm_weights = fm_path_mat[:,p] / np.sum(fm_path_mat[:,p])
            mean_loc_fms.append(np.sum([i*fm_weights[i] for i in range(max_fmexp)]))
        self.loc_fms = np.array(mean_loc_fms)

        self.speed_denom = np.sum(self.loc_fms)

        self.prms_locs = np.arange(np.round(self.fm_locs[0]))
        self.all_locs = np.arange(max_pathlen)

    def get_model_threshs(self, fname=MODEL_THRESHS_FNAME):
        prob_thresh_in = open(fname)
        threshs = list()
        freqs = list()
        counts = list()
        for line in prob_thresh_in:
            thresh, freq, count = line.split()
            threshs.append(float(thresh))
            freqs.append(float(freq))
            counts.append(float(count))

        self.model_ekms = np.flip(np.array(threshs),0)
        self.model_pcks = np.flip(np.array(freqs),0)
        self.model_counts = np.flip(np.array(counts),0)

    def get_fn_speed(self, fn_locs, fn_pcks):
        pcks = np.interp(self.all_locs, fn_locs, fn_pcks)
        counts = np.interp(pcks, self.model_pcks, self.model_counts)
        speed = np.dot(counts, self.loc_fms) / (self.speed_denom)
        return speed

    def get_fn_prob(self, fn_locs, fn_pcks):
        return np.prod(np.interp(self.prms_locs, fn_locs, fn_pcks))

    def add_preset(self, name, tgt_prob=None, tgt_speed=None, exp_st=2, init_fac=2, eps=0.00001):

        exp = exp_st
        exp_min, exp_max = (None, None)

        pdelta = None

        pck1 = self.pck1
        pck2 = self.pck2

        sys.stderr.write("Computing %s parameters\n" % name)

        while True:
            fn_locs,fn_pcks = power_fn(self.fm_locs[0], pck1, pck2, exp)

            if tgt_prob is not None:
                delta = self.get_fn_prob(fn_locs, fn_pcks) - tgt_prob
            elif tgt_speed is not None:
                delta = self.get_fn_speed(fn_locs, fn_pcks) - tgt_speed

            if abs(delta) <= eps:
                break
            
            if delta == pdelta:
                #This works well for small references
                #TODO: check for larger references
                sys.stderr.write("Maxed out %s parameters\n" % name)
                break
            pdelta = delta

            if delta < 0:
                exp_max = exp
            else:
                exp_min = exp
            
            pexp = exp

            if exp_max == None:
                exp *= init_fac
            elif exp_min == None:
                exp /= init_fac
            else:
                exp = exp_min + ((exp_max - exp_min) / 2.0)

            #for floating point rounding errors
            if exp == pexp:
                break

        fm_pcks = np.interp(self.fm_locs, fn_locs, fn_pcks)
        fm_ekms = np.interp(fm_pcks, self.model_pcks, self.model_ekms)
        prob = self.get_fn_prob(fn_locs, fn_pcks)
        speed = self.get_fn_speed(fn_locs, fn_pcks)

        #while len(fm_ekms) > 2 and fm_ekms[-1] == fm_ekms[-2]:
        #    fm_ekms = fm_ekms[:-1]

        sys.stderr.write("Writing %s parameters\n" % name)
        self.functions[name] = (fm_ekms, prob, speed)

    def write(self):
        params_out = open(self.out_fname, "w")
        
        for name, fn in self.functions.items():
            ekms, prob, speed = fn
            params_out.write("%s\t%s\t%.5f\t%.3f\n" % (name, ",".join(map(str,ekms)), prob, speed))

        params_out.close()

