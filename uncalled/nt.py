from collections import Sequence
import numpy as np 

from _uncalled._nt import *
from _uncalled._nt import _kmer_to_arr, _kmer_to_str

KMERS = np.arange(kmer_count())

def kmer_array(kmer):
    arr = np.array(kmer)
    if arr.dtype.type in {np.str_, np.bytes_}:

        #TODO add option to fully check BP validity
        if not np.all(np.char.str_len(arr) == K):
            raise RuntimeError("All k-mers must be %d bases long" % nt.K)

        return str_to_kmer(arr)
    return arr

def kmer_to_str(kmer, dtype=str):
    if isinstance(kmer, (Sequence, np.ndarray)):
        return _kmer_to_arr(kmer).astype(dtype)
    return dtype(_kmer_to_str(kmer))

KMER_STRS = kmer_to_str(KMERS)