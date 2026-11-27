// replay_main.cpp -- C++ harness of the scan replay (bead j41m.19).  Same protocol as the intent of replay_tb.sv, but a separate
// compile unit: the Verilated gate netlist (replay_top) takes ~45 min to build, a harness change takes seconds.
//
// usage: Vreplay +dir=<vec dir> +mode=pat|flush +tap=0|1 +fault=<k> +npat=N +dbg=1
// Entry (TM 14.14): pin mode = scan_mode_i=1, TAP in reset (the ATPG cut's conditions); TAP mode = scan_mode from IR=SCAN with
// SCAN_SEL.PARALLEL=1, shift pins still scan_*.  3 wipe edges + spare with scan_en=0, then scan_en=1.
// Output: one `RESULT ...` line parsed by run_replay.py.
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <string>
#include <vector>

#include "Vreplay_top.h"
#include "verilated.h"

#include "params_h.h"  // generated: NPAT L N_PI N_PO PIW POW CH0..CH7 (replay_vectors.py)

static Vreplay_top* d;
static int dbg = 0;

static int tms1 = 5, trstn = 3, dump_n = 0, dump = -1, bypass = 1, freeval = 1, flushones = 0, seen_en_drop = -1;
// The free pseudo-inputs of the cut (unscanned latches/flops, replay_netlist.py `free`) cannot be set by scan.  The one in the
// fabric is the clock-switch enable latch en_b_q (dft_clk_switch.sv): in pin mode it settles to 1 and its value never reaches a
// data endpoint of the cut (pattern_map.py cone check), so the pattern's value is replaced by `freeval` (default 1).
static void force_free() {
    for (int b = N_PI - NFREE; b < N_PI; b++) {
        if (freeval) d->pi_vec[b / 32] |= 1u << (b % 32); else d->pi_vec[b / 32] &= ~(1u << (b % 32));
    }
}
static void ev() { d->eval(); }
// fsel[nbyp-1:0] is the what-if "shift-phase conditioning": stuck-at-1 on the wipe-done pin of the AND that makes dft_scan_en
// (bit 0) and of the six scan_out_o AND gates (bits 1..6), and on the 80 gate outputs that drive the async reset pins of
// scanned flops (bits 7..86; shifted data would otherwise pulse those resets).  The scan-entry edge-detect flops are scan flops, so without it the
// shifted data drops crypto_wipe_done, hence scan_en and the scan-out gating (see README).  It is ON during shift phases only;
// entry and capture run on the real gate.  +bypass=0 turns it off.
static int nbyp = 87;
static void set_bypass(int on) {
    if (!bypass) return;
    for (int b = 0; b < nbyp; b++) {
        if (on) d->fsel[b / 32] |= 1u << (b % 32); else d->fsel[b / 32] &= ~(1u << (b % 32));
    }
    ev();
}
static void sclk() { d->scan_clk_i = 1; ev(); d->scan_clk_i = 0; ev(); }
static void tck(int tms, int tdi) { d->tms_i = tms; d->tdi_i = tdi; ev(); d->tck_i = 1; ev(); d->tck_i = 0; ev(); }
static void tap_ir(int v) {
    tck(1, 0); tck(1, 0); tck(0, 0); tck(0, 0);
    for (int b = 0; b < 4; b++) tck(b == 3, (v >> b) & 1);
    tck(1, 0); tck(0, 0);
}
static void tap_dr3(int v) {
    tck(1, 0); tck(0, 0); tck(0, 0);
    for (int b = 0; b < 3; b++) tck(b == 2, (v >> b) & 1);
    tck(1, 0); tck(0, 0);
}
static void show(const char* tag, int t) {
    if (dbg)
        printf("DBG %s t=%d en=%d si=%02x so=%02x dbg=%02x (mode,en,wipe,test_clk,core,cpu) dbg2=%06x (c0f0 clk,sce,q; c0f1; c5f0; c5f1)\n", tag, t,
               d->scan_en_i, d->scan_in_i, d->scan_out_o, d->dbg_o, (unsigned)d->dbg2_o);
}

static void enter_scan(int tap) {
    d->scan_en_i = 0;
    if (tap) {
        d->scan_mode_i = 0; d->trst_ni = 0; ev();
        for (int i = 0; i < trstn; i++) tck(1, 0);
        d->trst_ni = 1; ev();
        for (int i = 0; i < tms1; i++) tck(1, 0);
        tck(0, 0);
        tap_ir(3); tap_dr3(1);
        tap_ir(4);
        for (int i = 0; i < 12; i++) sclk();
    } else {
        d->trst_ni = 0; d->scan_mode_i = 1; ev();
        for (int i = 0; i < 5; i++) sclk();
    }
    show("entered", 0);
}

static std::vector<uint32_t> rd32(const std::string& f) {
    std::vector<uint32_t> v; std::ifstream in(f); std::string s;
    while (in >> s) v.push_back((uint32_t)strtoul(s.c_str(), nullptr, 16));
    return v;
}

int main(int argc, char** argv) {
    std::string dir = ".", mode = "pat"; int tap = 0, fault = -1, npat = NPAT;
    for (int i = 1; i < argc; i++) {
        if (!strncmp(argv[i], "+dir=", 5)) dir = argv[i] + 5;
        else if (!strncmp(argv[i], "+mode=", 6)) mode = argv[i] + 6;
        else if (!strncmp(argv[i], "+tap=", 5)) tap = atoi(argv[i] + 5);
        else if (!strncmp(argv[i], "+fault=", 7)) fault = atoi(argv[i] + 7);
        else if (!strncmp(argv[i], "+npat=", 6)) npat = atoi(argv[i] + 6);
        else if (!strncmp(argv[i], "+dbg=", 5)) dbg = atoi(argv[i] + 5);
        else if (!strncmp(argv[i], "+freeval=", 9)) freeval = atoi(argv[i] + 9);
        else if (!strncmp(argv[i], "+dump=", 6)) dump = atoi(argv[i] + 6);
        else if (!strncmp(argv[i], "+tms1=", 6)) tms1 = atoi(argv[i] + 6);
        else if (!strncmp(argv[i], "+trstn=", 7)) trstn = atoi(argv[i] + 7);
        else if (!strncmp(argv[i], "+nbyp=", 6)) nbyp = atoi(argv[i] + 6);
        else if (!strncmp(argv[i], "+bypass=", 8)) bypass = atoi(argv[i] + 8);
        else if (!strncmp(argv[i], "+ones=", 6)) flushones = atoi(argv[i] + 6);
    }
    Verilated::commandArgs(argc, argv);
    d = new Vreplay_top;
    d->scan_rst_ni = 1; d->clk_i = 0; d->cpu_clk_i = 0; d->scan_in_i = 0;
    for (int i = 0; i < 8; i++) d->fsel[i] = 0;
    if (fault >= 0) d->fsel[fault / 32] |= 1u << (fault % 32);
    for (int i = 0; i < PIW; i++) d->pi_vec[i] = 0;
    force_free();
    ev();
    int chlen[8] = {CH0, CH1, CH2, CH3, CH4, CH5, CH6, CH7};
    long mism_so = 0, mism_po = 0; int first_so_pat = -1, first_po_pat = -1; unsigned so_chain_mask = 0;
    if (mode == "tapid") {  // TAP sanity: IDCODE after reset must read 0x15C01001 (TM 15.3), then IR=SCAN must raise scan_mode
        d->scan_mode_i = 0; d->trst_ni = 0; ev();
        for (int i = 0; i < trstn; i++) tck(1, 0);
        d->trst_ni = 1; ev();
        for (int i = 0; i < tms1; i++) tck(1, 0);
        tck(0, 0);
        tck(1, 0); tck(0, 0); tck(0, 0);  // Select-DR, Capture-DR, Shift-DR
        unsigned id = 0;
        for (int b = 0; b < 32; b++) { id |= (unsigned)(d->tdo_o & 1) << b; tck(b == 31, 0); }
        tck(1, 0); tck(0, 0);
        printf("TAPID idcode=0x%08x\n", id);
        if (dbg > 1) {  // brute force: which written IR value raises scan_mode?
            for (int v = 0; v < 16; v++) { tap_ir(v); printf("TAPSWEEP IR=%d dbg=%02x\n", v, d->dbg_o); }
            return 0;
        }
        // read back the IR through Capture-IR/Shift-IR: TDO shows the captured/current IR (LSB first)
        for (int pass = 0; pass < 3; pass++) {
            int v = pass == 0 ? 3 : (pass == 1 ? 4 : 4);
            tck(1, 0); tck(1, 0); tck(0, 0); tck(0, 0);  // Select-DR, Select-IR, Capture-IR, Shift-IR
            unsigned cap = 0;
            for (int b = 0; b < 4; b++) { cap |= (unsigned)(d->tdo_o & 1) << b; tck(b == 3, (v >> b) & 1); }
            tck(1, 0); tck(0, 0);  // Update-IR, RTI
            printf("TAPID pass %d wrote IR=%d, captured old IR bits=0x%x, dbg=%02x\n", pass, v, cap, d->dbg_o);
            for (int i = 0; i < 6; i++) tck(0, 0);
            printf("TAPID   after 6 idle TCK: dbg=%02x\n", d->dbg_o);
        }
        return 0;
    }
    enter_scan(tap);
    set_bypass(1);

    if (mode == "flush") {
        int tot = L + 40;
        int chain_first[8] = {0}, chain_cnt[8] = {0};
        std::vector<int> hist(tot);
        d->scan_en_i = 1; ev();
        for (int t = 0; t < tot; t++) {
            int b = flushones ? 1 : (t >> 1) & 1;
            hist[t] = b ? 0xff : 0x00;
            d->scan_in_i = hist[t]; ev();
            if (t < 6 || (t >= L - 2 && t < L + 6)) show("flush", t);
            if (seen_en_drop < 0 && !((d->dbg_o >> 1) & 1)) { seen_en_drop = t; printf("DFT_SCAN_EN dropped to 0 at shift edge %d (dbg=%02x)\n", t, d->dbg_o); }
            for (int k = 0; k < 6; k++)
                if (t >= chlen[k] && (((d->scan_out_o >> k) & 1) != ((hist[t - chlen[k]] >> k) & 1))) { mism_so++; so_chain_mask |= 1u << k; if (!chain_first[k]) chain_first[k] = t + 1; chain_cnt[k]++;
                    if (dump == k && chain_cnt[k] <= 60) printf("MIS chain %d t=%d got=%d exp=%d dbg=%02x\n", k, t, (d->scan_out_o >> k) & 1, (hist[t - chlen[k]] >> k) & 1, d->dbg_o); }
            sclk();
        }
        for (int k = 0; k < 6; k++) printf("FLUSHCHAIN %d len=%d mismatches=%d first_t=%d\n", k, chlen[k], chain_cnt[k], chain_first[k] - 1);
    } else {
        auto pi = rd32(dir + "/pi.hex"), po = rd32(dir + "/po.hex");
        auto rd8 = [&](const char* n) { auto w = rd32(dir + "/" + n); return w; };
        auto ld = rd8("ld.hex"), ex = rd8("ex.hex"), mk = rd8("mk.hex");
        auto shift = [&](int lp, int up) {
            for (int c = 0; c < L; c++) {
                d->scan_in_i = lp >= 0 ? ld[lp * L + c] : 0; ev();
                if (up >= 0) {
                    unsigned diff = (d->scan_out_o ^ ex[up * L + c]) & mk[up * L + c];
                    if (diff) {
                        if (!mism_so) { first_so_pat = up; }
                        mism_so++; so_chain_mask |= diff;
                        if (dump >= 0 && dump_n < 5000) for (int k = 0; k < 6; k++) if ((diff >> k) & 1) { dump_n++; printf("UM pat=%d chain=%d pos=%d got=%d\n", up, k, chlen[k] - 1 - c, (d->scan_out_o >> k) & 1); }
                    }
                }
                sclk();
            }
        };
        for (int p = 0; p < npat; p++) {
            set_bypass(1);
            d->scan_en_i = 1; ev();
            shift(p, p - 1);
            set_bypass(0);
            d->scan_en_i = 0;
            for (int w = 0; w < PIW; w++) d->pi_vec[w] = pi[p * PIW + w];
            force_free();
            ev();
            bool bad = false;
            for (int w = 0; w < POW; w++) {
                uint32_t m = (w == POW - 1 && (N_PO % 32)) ? ((1u << (N_PO % 32)) - 1) : 0xffffffffu;
                if ((d->po_vec[w] ^ po[p * POW + w]) & m) bad = true;
            }
            if (bad) {
                if (!mism_po) first_po_pat = p;
                mism_po++;
                if (dump >= 0) for (int b = 0; b < N_PO; b++) if (((d->po_vec[b / 32] ^ po[p * POW + b / 32]) >> (b % 32)) & 1) printf("PM pat=%d po=%d\n", p, b);
            }
            sclk();
        }
        set_bypass(1);
        d->scan_en_i = 1; ev();
        shift(-1, npat - 1);
    }
    printf("RESULT mode=%s tap=%d fault=%d npat=%d so_mismatch=%ld first_so_pat=%d first_so_chains=0x%x po_mismatch=%ld first_po_pat=%d\n",
           mode.c_str(), tap, fault, npat, mism_so, first_so_pat, so_chain_mask, mism_po, first_po_pat);
    delete d;
    return 0;
}
