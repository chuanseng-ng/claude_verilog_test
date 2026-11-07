# Innovus native SPEF (test) vs StarRC tuned nom (ref), b5h (capTable RC) and b5g (tech-LEF RC)
## b5h
nets ref=35088 test=34758 common=34758 only_ref=330 only_test=0
gate population (ref total C > 1 fF): 32272 nets
| quantity (b5h) | nets | median | p5 | p95 | r (lin) | r (log-log) | outside +-10 % |
|---|---|---|---|---|---|---|---|
| total C | 32272 | 1.056 | 0.898 | 1.181 | 0.9985 | 0.9987 | 10272 (31.8 %) |
| ground C | 32272 | 1.870 | 1.308 | 4.177 | 0.9512 | 0.9676 | 32149 (99.6 %) |
| total R (nets with R>0 both) | 32272 | 1.014 | 0.999 | 1.025 | 0.9863 | 0.9893 | 1090 (3.4 %) |
coupling share per net (cc/total), nets with ref C > 1 fF: median ref 0.442 test 0.000 (diff -44.2 points), p25/p75 ref 0.352/0.554 test 0.000/0.000
total design (all nets): C ref 941.1 pF, test 1039.0 pF, ratio 1.104 | ground C 419.2 vs 1039.0 pF (2.479) | coupling C 261.0 vs 0.0 pF (0.000) | sum R 6.08e+06 vs 5.97e+06 ohm (0.982)
coupling fraction of total C: ref 0.555 test 0.000
## b5g (tech-LEF RC)
nets ref=35893 test=35563 common=35563 only_ref=330 only_test=0
gate population (ref total C > 1 fF): 33239 nets
| quantity (b5g) | nets | median | p5 | p95 | r (lin) | r (log-log) | outside +-10 % |
|---|---|---|---|---|---|---|---|
| total C | 33239 | 1.132 | 0.889 | 1.410 | 0.9963 | 0.9970 | 21576 (64.9 %) |
| ground C | 33239 | 1.312 | 0.797 | 2.074 | 0.9798 | 0.9784 | 28010 (84.3 %) |
| total R (nets with R>0 both) | 33239 | 0.797 | 0.634 | 0.983 | 0.9734 | 0.9862 | 25398 (76.4 %) |
coupling share per net (cc/total), nets with ref C > 1 fF: median ref 0.449 test 0.376 (diff -7.3 points), p25/p75 ref 0.360/0.565 test 0.213/0.532
total design (all nets): C ref 974.0 pF, test 1217.3 pF, ratio 1.250 | ground C 428.7 vs 552.7 pF (1.289) | coupling C 272.7 vs 332.3 pF (1.219) | sum R 6.26e+06 vs 5.43e+06 ohm (0.868)
coupling fraction of total C: ref 0.560 test 0.546
