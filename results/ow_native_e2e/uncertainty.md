# R3 workload-sensitivity uncertainty

Pooled seeds: seed01, seed02, seed03, seed04, seed05, seed06, seed07, seed08, seed09, seed10 (n=10). Bootstrap 95% CI of the mean per-seed effect; effect = strategy vs same-seed baseline.

### e2e_warm_us — async arm, layout orig

| workload | strategy | mean Δ% | 95% CI | sign | verdict |
|---|---|---:|---|---:|---|
| A | 2d | -6.4 | [-11.5, +0.9] | 8/10 | directional |
| A | 2e_K10 | -4.0 | [-14.8, +8.0] | 8/10 | directional |
| A | 2f_slru | +3259.4 | [+3100.6, +3534.8] | 10/10 | robust |
| B | 2d | -6.8 | [-15.0, +6.8] | 9/10 | directional |
| B | 2e_K10 | +3.7 | [-5.3, +13.1] | 5/10 | tie |
| B | 2f_slru | +3021.8 | [+2846.9, +3226.4] | 10/10 | robust |
| C | 2d | -22.0 | [-30.9, -12.3] | 9/10 | robust |
| C | 2e_K10 | -36.4 | [-45.3, -27.4] | 10/10 | robust |
| C | 2f_slru | +269.3 | [+243.2, +294.1] | 10/10 | robust |

### first_query_us — async arm, layout orig

| workload | strategy | mean Δ% | 95% CI | sign | verdict |
|---|---|---:|---|---:|---|
| A | 2d | -32.5 | [-36.6, -27.1] | 10/10 | robust |
| A | 2e_K10 | -38.4 | [-48.0, -28.8] | 10/10 | robust |
| A | 2f_slru | -73.6 | [-74.7, -71.7] | 10/10 | robust |
| B | 2d | -30.4 | [-38.0, -17.9] | 9/10 | robust |
| B | 2e_K10 | -27.4 | [-35.4, -19.2] | 10/10 | robust |
| B | 2f_slru | -75.3 | [-76.9, -73.3] | 10/10 | robust |
| C | 2d | -38.0 | [-46.0, -28.9] | 10/10 | robust |
| C | 2e_K10 | -57.0 | [-65.3, -48.3] | 10/10 | robust |
| C | 2f_slru | -70.7 | [-75.8, -65.0] | 10/10 | robust |

### e2e_us — async arm, layout orig

| workload | strategy | mean Δ% | 95% CI | sign | verdict |
|---|---|---:|---|---:|---|
| A | 2d | +51.6 | [+33.7, +68.0] | 10/10 | robust |
| A | 2e_K10 | +51.7 | [+29.0, +75.3] | 9/10 | robust |
| A | 2f_slru | +3298.3 | [+3129.4, +3583.6] | 10/10 | robust |
| B | 2d | +27.6 | [+10.9, +46.2] | 9/10 | robust |
| B | 2e_K10 | +31.7 | [+18.4, +47.9] | 10/10 | robust |
| B | 2f_slru | +3045.7 | [+2867.0, +3251.0] | 10/10 | robust |
| C | 2d | +1.6 | [-12.8, +19.7] | 6/10 | tie |
| C | 2e_K10 | -13.3 | [-26.2, +0.7] | 7/10 | directional |
| C | 2f_slru | +294.0 | [+262.5, +325.5] | 10/10 | robust |

