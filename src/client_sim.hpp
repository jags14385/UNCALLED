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

#ifndef _INCL_SIM_POOL
#define _INCL_SIM_POOL

#include <unordered_map>
#include <deque>
#include "util.hpp"
#include "read_buffer.hpp" 
#include "fast5_reader.hpp" 
#include "config.hpp" 

class ClientSim {
    public:
    ClientSim(Config &c);

    bool run();
    std::vector< std::pair<u16, ReadBuffer> > get_read_chunks();
    void stop_receiving_read(u16 channel, u32 number);
    u32 unblock_read(u16 channel, u32 number);
    bool is_running();
    float get_runtime();

    bool load_from_files(const std::string &prefix);

    void add_intv(u16 ch, u16 i, u32 st, u32 en);
    void add_gap(u16 ch, u16 i, u32 len);
    void add_delay(u16 ch, u16 i, u32 len);
    void add_read(u16 ch, const std::string &id, u32 offs);
    void add_fast5(const std::string &fname);
    void load_fast5s();

    private:

    bool load_itvs(const std::string &fname);
    bool load_gaps(const std::string &fname);
    bool load_delays(const std::string &fname);
    bool load_reads(const std::string &fname);


    u32 get_number(u16 channel);
    float get_time();

    typedef struct {
        u16 ch;
        u32 i, offs;
    } ReadLoc;
    std::unordered_map< std::string, ReadLoc >  read_locs;

    class ScanIntv {

        //private:
        public:
        u16 channel_, intv_;
        u32 start_time_;
        bool active_;
        std::vector<u32> gaps_, delays_;
        std::deque<u32> active_bounds_;
        u32 g_, d_;

        ScanIntv(u16 channel, u16 intv_) :
            channel_(channel),
            intv_(intv_),
            start_time_(UINT_MAX),
            active_(false),
            g_(0), d_(0) {}

        void set_active(u32 st, u32 en) {
            if (st == 0) {
                active_ = true;
            } else {
                active_bounds_.push_back(st);
            }

            active_bounds_.push_back(en);
        }

        void start(u32 t) {
            start_time_ = t;
        }

        u32 intv_time(u32 t) {
            return t-start_time_;
        }

        u32 get_end() const {
            if (active_bounds_.empty()) return 0;
            return active_bounds_.back();
        }

        bool is_active(u32 t) {
            while (!active_bounds_.empty() && intv_time(t) >= active_bounds_.front()) {
                active_bounds_.pop_front();
                active_ = !active_;
                std::cerr << "switch "
                          << active_ << " "
                          << channel_ << " "
                          << intv_ << " "
                          << t << "\n";
            }

            return active_;
        }

        void add_gap(u32 gap) {
            gaps_.push_back(gap);
        }

        u32 next_gap() {
            if (gaps_.empty()) {
                if (active_) {
                    active_ = false;
                    active_bounds_.pop_front();
                }
                return 0;
            }
            u32 gap = gaps_[g_];
            g_ = (g_+1) % gaps_.size();
            return gap;
        }

        void add_delay(u32 delay) {
            delays_.push_back(delay);
        }

        u32 next_delay() {
            if (delays_.empty()) {
                return 0;//not ideal?
            }

            u32 delay = delays_[d_];
            d_ = (d_+1) % delays_.size();
            return delay;
        }
    };

    class SimRead {
        //private:
        public:
        std::vector<ReadBuffer> chunks_;
        u8 c_;
        u32 start_, end_, duration_, number_;

        SimRead() :
            c_(0),
            start_(0),
            end_(0),
            duration_(0),
            number_(0) {}

        void load_read(const ReadBuffer &read, u32 offs) {
            duration_ = read.size();
            read.get_chunks(chunks_, false, offs);
            number_ = read.get_number();
        }

        void start(u32 t) {
            start_ = t;
            end_ = start_ + duration_;
            u64 i = start_;
            for (auto &ch : chunks_) {
                ch.set_start(i);
                i += ch.size();
            }
            c_ = 0;
        }

        bool started(u64 t) {
            return start_ != 0 && start_ <= t;
        }

        bool chunk_ready(u32 t) {
            return started(t) && 
                   c_ < chunks_.size() && 
                   t >= chunks_[c_].get_end();
        }

        u32 get_number() {
            return number_;
        }

        ReadBuffer pop_chunk() {
            assert(c_ < chunks_.size());
            return chunks_[c_++];
        }

        u64 get_end() {
            return end_;
        }

        bool ended(u64 t) {
            return started(t) && t >= end_;
        }

        void stop_receiving() {
            c_ = chunks_.size();
        }

        void unblock(u32 t, u32 delay) {
            end_ = min(t + delay, start_ + duration_);
        }
    };

    class SimChannel {
        //private:
        public:
        u16 channel_;
        std::deque<ScanIntv> intvs_; //intervals
        std::vector<SimRead> reads_;
        u32 r_; //read index
        u32 extra_gap_;
        u32 read_count_;
        bool is_active_;

        SimChannel(u16 channel) : 
            channel_(channel), 
            r_(0), 
            read_count_(0),
            is_active_(false) {}

        bool is_dead() {
            return intvs_.empty();
        }

        bool is_active(u32 t) {
            if (is_dead()) return false;

            if (intvs_[0].is_active(t)) {
                if (!is_active_) {
                    reads_[r_].start(t + intvs_[0].next_gap());
                    is_active_ = true;
                }
                
            } else if (is_active_) {
                r_ = (r_+1) % reads_.size();
                is_active_ = false;
            }

            return is_active_;
        }

        bool start(u32 t) {
            if (!is_dead()) {
                extra_gap_ = 0;
                intvs_[0].start(t);
            }

            return is_active(t);
        }

        u32 reserve_read() {
            return read_count_++;
        }

        void load_read(u32 i, u32 offs, const ReadBuffer &read) {
            if (reads_.size() < read_count_) {
                reads_.resize(read_count_);
            }

            reads_[i].load_read(read, offs);
        }

        void add_delay(u32 i, u32 delay) {
            while (i >= intvs_.size()) {
                intvs_.emplace_back(channel_, intvs_.size());
            }
            intvs_[i].add_delay(delay);
        }

        void add_gap(u32 i, u32 gap) {
            while (i >= intvs_.size()) {
                intvs_.emplace_back(channel_, intvs_.size());
            }
            intvs_[i].add_gap(gap);
        }

        void set_active(u32 i, u32 start, u32 end) {
            while (i >= intvs_.size()) {
                intvs_.emplace_back(channel_, intvs_.size());
            }
            intvs_[i].set_active(start, end);
        }

        bool chunk_ready(u32 t) {
            if (!intvs_[0].is_active(t)) return false;
            assert (!reads_.empty());

            u32 end = reads_[r_].get_end();
            while (t >= end) {
                r_ = (r_+1) % reads_.size();

                reads_[r_].start(end + intvs_[0].next_gap() + extra_gap_);
                extra_gap_ = 0;
                end = reads_[r_].get_end();
            }

            return reads_[r_].chunk_ready(t);
        }

        ReadBuffer next_chunk(u32 t) {
            assert(chunk_ready(t));
            return reads_[r_].pop_chunk();
        }

        u32 read_number() {
            return reads_[r_].get_number();
        }

        bool intv_ended(u32 t) {
            return is_dead() || intvs_[0].get_end() <= t;
        }

        void next_intv(u32 t) {
            intvs_.pop_front();
            if (!is_dead()) intvs_[0].start(t);
        }

        void stop_receiving_read() {
            reads_[r_].stop_receiving();
        }

        u32 unblock(u32 t, u32 ej_time) {
            u32 delay = intvs_[0].next_delay();
            reads_[r_].unblock(t, delay);
            extra_gap_ = ej_time;
            return delay;
        }
    };

    friend bool operator< (const SimRead &r1, const SimRead &r2);

    SimParams PRMS;
    Fast5Iter fast5s_;
    float time_coef_; //TODO: make const?
    u32 ej_time_, ej_delay_, scan_time_, scan_start_; //start_samp_, end_samp_, 


    bool is_running_, in_scan_;

    Timer timer_;
    
    std::vector<SimChannel> channels_;

    #ifdef PYBIND

    #define PY_SIM_METH(P) c.def(#P, &ClientSim::P);
    #define PY_SIM_PROP(P) c.def_property(#P, &ClientSim::get_##P, &ClientSim::set_##P);
    #define PY_SIM_RPROP(P) c.def_property_readonly(#P, &ClientSim::P);
    #define PY_SIM_PRM(P) prm.def_readwrite(#P, &SimParams::P);

    public:

    static void pybind_defs(pybind11::class_<ClientSim> &c) {
        c.def(pybind11::init<Config &>());
        PY_SIM_METH(run);
        PY_SIM_METH(get_runtime);
        PY_SIM_METH(get_read_chunks);
        PY_SIM_METH(stop_receiving_read);
        PY_SIM_METH(unblock_read);
        PY_SIM_METH(add_intv);
        PY_SIM_METH(add_gap);
        PY_SIM_METH(add_delay);
        PY_SIM_METH(add_read);
        PY_SIM_METH(add_fast5);
        PY_SIM_METH(load_fast5s);

        PY_SIM_RPROP(is_running);

        pybind11::class_<SimParams> prm(c, "Params");
        PY_SIM_PRM(ctl_seqsum)
        PY_SIM_PRM(unc_seqsum)
        PY_SIM_PRM(unc_paf)
        PY_SIM_PRM(sim_speed)
        PY_SIM_PRM(scan_time)
        PY_SIM_PRM(scan_intv_time)
        PY_SIM_PRM(ej_time)
        PY_SIM_PRM(min_ch_reads)

    }

    #endif
};

bool operator< (const ClientSim::SimRead &r1, const ClientSim::SimRead &r2);
#endif
