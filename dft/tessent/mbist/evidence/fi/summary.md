| Fault class | LVMARCHCMINUS | SMARCH | SMARCHCHKB | SMARCHCHKBCI | SMARCHCHKBCIL | LVCHECKERBOARD1X1 |
|---|---|---|---|---|---|---|
| AFalias | 6/6 | 6/6 | 6/6 | 6/6 | 6/6 | 4/6 |
| AFmulti | 6/6 | 6/6 | 6/6 | 6/6 | 6/6 | 4/6 |
| AFnone | 6/6 | 6/6 | 6/6 | 6/6 | 6/6 | 6/6 |
| CFid | 40/40 | 40/40 | 40/40 | 40/40 | 40/40 | 8/40 |
| CFid (intra-word) | 4/8 | 4/8 | 6/8 | 6/8 | 6/8 | 0/8 |
| CFin | 20/20 | 20/20 | 20/20 | 20/20 | 20/20 | 8/20 |
| CFin (intra-word) | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 | 0/4 |
| CFst | 40/40 | 40/40 | 40/40 | 40/40 | 40/40 | 20/40 |
| CFst (intra-word) | 4/8 | 4/8 | 8/8 | 8/8 | 8/8 | 4/8 |
| P1STUCK | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| SAF | 28/28 | 28/28 | 28/28 | 28/28 | 28/28 | 28/28 |
| TF | 28/28 | 28/28 | 28/28 | 28/28 | 28/28 | 28/28 |
| WMASK | 8/16 | 8/16 | 8/16 | 8/16 | 8/16 | 8/16 |
| **all** | **196/212** | **196/212** | **202/212** | **202/212** | **202/212** | **120/212** |

| Fault class | MARCH_CM | CKBD | LANE | FULL |
|---|---|---|---|---|
| AFalias | 3/3 | 3/3 | 3/3 | 3/3 |
| AFmulti | 3/3 | 3/3 | 3/3 | 3/3 |
| AFnone | 3/3 | 3/3 | 3/3 | 3/3 |
| CFid | 20/20 | 20/20 | 5/20 | 20/20 |
| CFid (intra-word) | 2/4 | 2/4 | 2/4 | 4/4 |
| CFin | 10/10 | 10/10 | 5/10 | 10/10 |
| CFin (intra-word) | 2/2 | 2/2 | 2/2 | 2/2 |
| CFst | 20/20 | 20/20 | 15/20 | 20/20 |
| CFst (intra-word) | 2/4 | 2/4 | 2/4 | 4/4 |
| SAF | 14/14 | 14/14 | 14/14 | 14/14 |
| TF | 14/14 | 14/14 | 14/14 | 14/14 |
| WMASK | 4/8 | 4/8 | 8/8 | 8/8 |
| **all** | **97/105** | **97/105** | **76/105** | **105/105** |

Retention (Tessent, 200 us pause):
- mem sr, RET decay 5000 clk (> back-to-back March gap, < 8000-clk pause), P_RETENTION: 2 miscompares (DETECTED)
- mem sr, RET decay 5000 clk (> back-to-back March gap, < 8000-clk pause), P_MARCHCM: 0 miscompares (not detected)
- mem sr, RET decay 200000 clk (> pause), P_RETENTION: 0 miscompares (not detected)
- mem sr, RET decay 200000 clk (> pause), P_MARCHCM: 0 miscompares (not detected)
- mem wm, RET decay 5000 clk (> back-to-back March gap, < 8000-clk pause), P_RETENTION: 2 miscompares (DETECTED)
- mem wm, RET decay 5000 clk (> back-to-back March gap, < 8000-clk pause), P_MARCHCM: 0 miscompares (not detected)
- mem wm, RET decay 200000 clk (> pause), P_RETENTION: 0 miscompares (not detected)
- mem wm, RET decay 200000 clk (> pause), P_MARCHCM: 0 miscompares (not detected)
