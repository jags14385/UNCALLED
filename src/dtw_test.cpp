#include <iostream>
#include <math.h>
#include <unordered_map>

#include "event_profiler.hpp"
#include "normalizer.hpp"
#include "models.inl"
#include "fast5_reader.hpp"
#include "bwa_index.hpp"
#include "dtw.hpp"
#include "dtw_banded.hpp"

//const std::string CONF_DIR(std::getenv("UNCALLED_CONF")),
//                  DEF_MODEL = CONF_DIR + "/r94_5mers.txt",
//                  DEF_CONF = CONF_DIR + "/defaults.toml";
//
//bool load_conf(int argc, char** argv, Conf &conf);


typedef struct {
    std::string rd_name, rf_name;
    u32 rd_st, rd_en;
    u64 rf_st, rf_en;
    bool fwd;
} Query;

std::unordered_map<std::string, Query> 
    load_queries(const std::string &fname, 
                 Fast5Reader &fast5s) {

    std::unordered_map<std::string, Query> queries;

    if (fname.empty()) {
        std::cerr << "Must specify query file\n";
        return queries;
    }
    
    std::ifstream infile(fname);

    if (!infile.is_open()) {
        std::cerr << "Error: failed to open query file\n";
        return queries;
    }

    Query q;
    char strand;
    while (!infile.eof()) {
        infile >> q.rd_name >> q.rd_st >> q.rd_en
               >> q.rf_name >> q.rf_st >> q.rf_en
               >> strand;
        q.fwd = strand == '+';

        queries[q.rd_name] = q;
        fast5s.add_read(q.rd_name);
    }

    return queries;
}

int main(int argc, char** argv) {
    Timer t;

    std::string index_prefix  = std::string(argv[1]), 
                fast5_fname   = std::string(argv[2]),
                query_fname = std::string(argv[3]);

    std::string out_prefix = "";
    if (argc > 4) {
        out_prefix = std::string(argv[4]);
    }

    auto model = pmodel_r94_dna_templ;

    auto dtwp = DTW_RAW_GLOB;
    dtwp.dw = dtwp.vw = dtwp.hw = 1;
    //1,1,1};         //d,v,h

    EventDetector evdt;
    EventProfiler evpr;

    BwaIndex<KLEN> idx(index_prefix);
    idx.load_pacseq();

    Fast5Reader fast5s;
    fast5s.add_fast5(fast5_fname);

    bool create_events = true;

    auto queries = load_queries(query_fname, fast5s);

    while (!fast5s.empty()) {
        //Get next read and corrasponding query
        auto read = fast5s.pop_read();
        //std::cout << read.get_id() << "\n";
        //std::cerr << "aligning " << read.get_id() << "\n";
        //std::cerr.flush();

        Query q = queries[read.get_id()];

        std::vector<u16> kmers = idx.get_kmers(q.rf_name, q.rf_st, q.rf_en);
        if (!q.fwd) kmers = kmers_revcomp<KLEN>(kmers);

        float read_mean = 0;
        for (u16 k : kmers) {
            read_mean += model.get_mean(k);
        }
        read_mean /= kmers.size();
        float read_stdv = 0;
        for (u16 k : kmers) {
            read_stdv += pow(model.get_mean(k) - read_mean, 2);
        }
        read_stdv = sqrt(read_stdv / kmers.size());
        Normalizer norm(read_mean, read_stdv);

        //Normalizer norm(model.get_means_mean(), model.get_means_stdv());

        //Get raw signal
        auto &full_raw = read.get_signal();
        std::vector<float> signal;
        if (q.rd_st != 0 || q.rd_en != 0) {
            u32 en = q.rd_en == 0 ? read.size() : q.rd_en;
            signal.reserve(en - q.rd_st);

            for (u32 i = q.rd_st; i < en; i++) {
                signal.push_back(full_raw[i]);
            }
        } else {
            signal = full_raw;
        }

        //Create events if needed
        if (create_events) {
            auto events = evdt.get_events(signal);
            auto mask = evpr.get_full_mask(events);
            signal.clear();

            for (u32 i = 0; i < events.size(); i++) {
                if (mask[i]) signal.push_back(events[i].mean);
            }
            
            norm.set_signal(signal);

        } else {
            norm.set_signal(signal);
        }

        //Normalize
        signal.clear();
        signal.reserve(norm.unread_size());
        while (!norm.empty()) signal.push_back(norm.pop());

        //Takes up too much space :(
        if (signal.size() > 50000) {
            std::cerr << "Skipping " << read.get_id() << "\n";
            continue;
        }

        u32 band_width = 400;

        std::vector<bool> rmoves;
        for (size_t i = 0; i < signal.size()+kmers.size(); i++) {
            rmoves.push_back((i % 3) == 0);
        }

        //BandedDTW dtw(signal, kmers, rmoves, band_width, model);
        DTWp dtw(signal, kmers, model, dtwp);

        //if (!out_prefix.empty()) {
        //    std::string path_fname = out_prefix+read.get_id()+".txt";
        //    std::ofstream out(path_fname);
        //    for (auto &t : dtw.get_path()) {
        //        out << t.ref << "\t" << t.qry << "\n";
        //    }
        //    out.close();
        //}

        std::cout << read.get_id() << "\t"
                  << dtw.mean_score() << "\t"
                  << (t.lap()/1000) << "\n";
        std::cout.flush();


    }

    idx.destroy();

    return 0;
}
