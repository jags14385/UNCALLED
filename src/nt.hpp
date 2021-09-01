/* MIT License
 *
 * Copyright (c) 2018 Sam Kovaka <skovaka@gmail.com>
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in all
 * copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 * SOFTWARE.
 */

#ifndef _INCL_NT 
#define _INCL_NT 

#include <string>
#include <vector>
#include <cstdint>
#include <cmath>
#include "util.hpp"

#ifdef PYBIND
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/stl_bind.h>
#include <pybind11/numpy.h>
namespace py = pybind11;
#endif

#define BASE_COUNT 4

const char BASE_CHARS[] {'A', 'C', 'G', 'T', 'N'};

const u8 BASE_BYTES[] 
     {4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, //0-15 
      4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, //16-31
      4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, //32-47
      4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, //48-63
      4, 0, 4, 1, 4, 4, 4, 2, 4, 4, 4, 4, 4, 4, 4, 4, //64-79 (A,C,G)
      4, 4, 4, 4, 3, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, //80-95 (T)
      4, 0, 4, 1, 4, 4, 4, 2, 4, 4, 4, 4, 4, 4, 4, 4, //96-111 (a,c,g)
      4, 4, 4, 4, 3, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4};//112-127 (t)

const char BASE_COMP_C[] 
     {'N','N','N','N','N','N','N','N','N','N','N','N','N','N','N','N', //0-15  ga
      'N','N','N','N','N','N','N','N','N','N','N','N','N','N','N','N', //16-31 rb
      'N','N','N','N','N','N','N','N','N','N','N','N','N','N','N','N', //32-47 ag
      'N','N','N','N','N','N','N','N','N','N','N','N','N','N','N','N', //48-63 e!
      'N','T','N','G','N','N','N','C','N','N','N','N','N','N','N','N', //64-79 (A,C,G)
      'N','N','N','N','A','N','N','N','N','N','N','N','N','N','N','N', //80-95 (T)
      'N','t','N','g','N','N','N','c','N','N','N','N','N','N','N','N', //96-111 (a,c,g)
      'N','N','N','N','a','N','N','N','N','N','N','N','N','N','N','N'};//112-127 (t)

const u8 BASE_COMP_B[] {3, 2, 1, 0};

char base_to_char(u8 base);
u8 base_comp(u8 base);

//Binary k-mer representaiton
using kmer_t = u16;

//Pore model k-mer length
constexpr u8 KMER_LEN = 5;

//k-mer bitmask
constexpr kmer_t KMER_MASK = (1 << (2*KMER_LEN)) - 1;

//TODO eliminate
enum KmerLen {k2=2, k3=3, k4=4, k5=5};

//#define KMER_MASK(k) ( (1 << (2*k)) - 1 )

template <KmerLen k>
inline u16 kmer_count() {
    return (u16) pow((u16)BASE_COUNT, (u16)k);
}

template <KmerLen k>
u16 str_to_kmer(const std::string &kmer, u32 offs=0) {
    u16 index = BASE_BYTES[(u8) kmer[offs]];
    for (u8 i = 1; i < (u8) k; i++) {
        index = (index << 2) | BASE_BYTES[(u8) kmer[offs+i]];
    }
    return index;
}

template <KmerLen k>
u16 kmer_comp(u16 kmer) {
    return kmer ^ KMER_MASK;
}

template <KmerLen k>
u16 kmer_rev(u16 kmer) {
    kmer = ( (kmer >> 2 & 0x3333) | (kmer & 0x3333) << 2 );
    kmer = ( (kmer >> 4 & 0x0F0F) | (kmer & 0x0F0F) << 4 );
    kmer = ( (kmer >> 8 & 0x00FF) | (kmer & 0x00FF) << 8 );
    return kmer >> (2 * (8 - k));
}

template <KmerLen k>
u16 kmer_revcomp(u16 kmer) {
    return kmer_rev<k>(~kmer);
}

template <KmerLen KLEN>
std::vector<kmer_t> kmers_revcomp(const std::vector<u16> &kmers) {
    std::vector<kmer_t> rev;
    rev.reserve(kmers.size());
    for (auto k = kmers.rbegin(); k != kmers.rend(); k++) {
        rev.push_back(kmer_revcomp<KLEN>(*k));
    }
    return rev;
}

template <KmerLen k>
u8 kmer_head(u16 kmer) {
    return (u8) ((kmer >> (2*( (u8)k ) - 2)) & 0x3);
}

template <KmerLen k>
u16 kmer_neighbor(u16 kmer, u8 i) {
    return ((kmer << 2) & KMER_MASK) | i; 
}

template <KmerLen k>
u8 kmer_base(u16 kmer, u8 i) {
    return (u8) ((kmer >> (2 * ((u16)k-i-1))) & 0x3);
}

template <KmerLen K>
std::string kmer_to_str(u16 kmer) {
    std::string s(K, 'N');
    for (u8 i = 0; i < K; i++) {
        s[i] = BASE_CHARS[kmer_base<K>(kmer, i)];
    }
    return s;
}

template <KmerLen KLEN>
std::vector<kmer_t> pacseq_to_kmers(u8 *seq, u64 st, u64 en) {
    std::vector<kmer_t> ret;

    u64 pst = st >> 2,
        pen = ((en) >> 2)+1;

    u64 i = 0;
    u16 kmer = 0;
    u8 bst = (st&3), ben;

    for (u64 j = pst; j < pen; j++) {
        ben = j == pen-1 ? (en&3) : 4;
        for (u8 k = bst; k < ben; k++) {
            kmer = kmer_neighbor<KLEN>(kmer, (seq[j] >> ((k^3) << 1) ) & 3);
            if (++i >= KLEN) ret.push_back(kmer);
        }
        bst = 0;
    }

    return ret;
}

#ifdef PYBIND

#define PY_EVTD_METH(P, D) evdt.def(#P, &EventDetector::P, D);
#define PY_EVTD_PRM(P, D) prms.def_readwrite(#P, &EventDetector::Params::P, D);
#define PY_EVT_VAL(P, D) evt.def_readwrite(#P, &Event::P, D);
#define PY_DBG_VAL(P, D) dbg.def_readonly(#P, &Debug::P, D);

template <KmerLen K>
using kmerpy_t = std::array<char, K+1>;


template <KmerLen K>
u16 str_to_kmer(const kmerpy_t<K> &kmer, u32 offs) {
    auto s = std::string(kmer.data());
    return str_to_kmer<K>(s, offs);
}

template <KmerLen K>
kmerpy_t<K> kmer_to_arr(u16 kmer) {
    kmerpy_t<K> ret{0};
    for (size_t i = 0; i < K; i++) {
        ret[i] = BASE_CHARS[kmer_base<K>(kmer, i)];
    }
    return ret;
    //auto s = std::string(kmer.data());
    //return str_to_kmer<K>(s, offs);
}

PYBIND11_MAKE_OPAQUE(std::vector<kmer_t>);

template <KmerLen KLEN>
static void nt_pybind_defs(pybind11::module_ &m) {
	py::bind_vector<std::vector<kmer_t>>(m, "KmerArray", py::buffer_protocol());

	//PYBIND11_MAKE_OPAQUE(std::vector<kmer_t>);
    //py::class_<std::vector<kmer_t>>(m, "KmerArray", py::buffer_protocol())
    //    .def_buffer([](std::vector<kmer_t> &k) -> py::buffer_info {
    //    return py::buffer_info(
    //        k.data(),                
    //        sizeof(kmer_t), 
    //        py::format_descriptor<kmer_t>::format(),
    //        1,
    //        {k.size()},
	//		{sizeof(kmer_t)}
    //    );
    //});

    m.attr("K") = pybind11::cast(KMER_LEN);
    m.def("kmer_count", &kmer_count<KLEN>);

    m.def("str_to_kmer",   py::vectorize(static_cast< u16 (*) (const kmerpy_t<KLEN> &, u32)>(&str_to_kmer<KLEN>)), py::arg("kmer"), py::arg("offs")=0);

    m.def("_kmer_to_str",  &kmer_to_str<KLEN>);
    m.def("_kmer_to_arr",  py::vectorize(&kmer_to_arr<KLEN>));

    m.def("base_to_char", py::vectorize(&base_to_char)); 
    m.def("base_comp", py::vectorize(&base_comp));
    
    m.def("kmer_rev",      py::vectorize(&kmer_rev<KLEN>));
    m.def("kmer_comp",     py::vectorize(&kmer_comp<KLEN>));
    m.def("kmer_revcomp",  py::vectorize(&kmer_revcomp<KLEN>));
    m.def("kmer_head",     py::vectorize(&kmer_head<KLEN>));
    m.def("kmer_base",     py::vectorize(&kmer_base<KLEN>));
    m.def("kmer_neighbor", py::vectorize(&kmer_neighbor<KLEN>));

}
#endif

#endif