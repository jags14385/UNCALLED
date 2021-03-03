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

#ifndef _INCL_READ_SEED_TRACKER
#define _INCL_READ_SEED_TRACKER

#include <set>
#include <vector>
#include <iostream>
#include <algorithm>
#include "util.hpp"
#include "range.hpp"
//typedef struct {
//    float min_mean_conf = 6.00;
//    float min_top_conf = 1.85;
//} TrackerParams;


class SeedCluster {

    //TODO: privatize
    public:

    u64 ref_st_;
    Range ref_en_;
    u32 evt_st_,
        evt_en_,
        total_len_;

    #ifdef PYDEBUG
    u32 id_;
    #endif

    SeedCluster(Range ref_st, u32 evt_st);
    //SeedCluster(const SeedCluster &r);
    SeedCluster();
    u64 ref_start_base() const;
    u8 update(SeedCluster &new_seed);
    void print(std::ostream &out, bool newline, bool print_all) const;
    Range ref_range() const;
    bool is_valid();

    friend bool operator< (const SeedCluster &q1, const SeedCluster &q2);
    friend std::ostream &operator<< (std::ostream &out, const SeedCluster &a);
};

const SeedCluster NULL_ALN = SeedCluster();

bool operator< (const SeedCluster &q1, const SeedCluster &q2);
std::ostream &operator<< (std::ostream &out, const SeedCluster &a);

class SeedTracker {
    public:

    typedef struct {
        u32 min_map_len;
        float min_mean_conf;
        float min_top_conf;
    } Params;
    static const Params PRMS_DEF;

    Params PRMS;

    std::set<SeedCluster> seed_clusters_;
    std::multiset<u32> all_lens_;
    SeedCluster max_map_;

    float len_sum_;

    SeedTracker();
    SeedTracker(Params params);

    //SeedCluster add_seed(SeedCluster sg);
    const SeedCluster &add_seed(u64 ref_en, u32 ref_len, u32 evt_st);
    SeedCluster get_final();
    SeedCluster get_best();
    float get_top_conf();
    float get_mean_conf();
    bool empty();

    void reset();

    std::vector<SeedCluster> get_alignments(u8 min_len);

    bool check_ratio(const SeedCluster &s, float ratio);
    bool check_map_conf(u32 seed_len, float mean_len, float second_len);

    void print(std::ostream &out, u16 max_out);

    #ifdef PYBIND

    #define PY_SEED_TRACKER_METH(P) c.def(#P, &SeedTracker::P);
    #define PY_SEED_TRACKER_RPROP(P) c.def_property_readonly(#P, &SeedTracker::get_##P);
    #define PY_SEED_TRACKER_PRM(P) p.def_readwrite(#P, &SeedTracker::Params::P);

    static void pybind_defs(pybind11::class_<SeedTracker> &c) {
        c.def(pybind11::init());
        c.def(pybind11::init<Params>());
        PY_SEED_TRACKER_METH(empty);

        pybind11::class_<Params> p(c, "Params");
        PY_SEED_TRACKER_PRM(min_map_len)
        PY_SEED_TRACKER_PRM(min_mean_conf)
        PY_SEED_TRACKER_PRM(min_top_conf)
    }
    #endif
};


#endif
