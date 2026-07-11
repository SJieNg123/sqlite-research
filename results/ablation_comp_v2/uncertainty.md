# R3 workload-sensitivity uncertainty

Pooled seeds: seed01, seed02, seed03, seed04, seed05, seed06, seed07, seed08, seed09, seed10 (n=10). Bootstrap 95% CI of the mean per-seed effect; effect = strategy vs same-seed baseline.

### e2e_warm_us — async arm, layout orig

| workload | strategy | mean Δ% | 95% CI | sign | verdict |
|---|---|---:|---|---:|---|
| C | 2d | -35.9 | [-38.0, -33.8] | 10/10 | robust |
| C | 2e_K10 | -54.5 | [-66.6, -42.2] | 10/10 | robust |
| C | 2f_slru | -7.1 | [-11.8, -2.5] | 8/10 | robust |

### first_query_us — async arm, layout orig

| workload | strategy | mean Δ% | 95% CI | sign | verdict |
|---|---|---:|---|---:|---|
| C | 2d | -43.3 | [-45.8, -40.9] | 10/10 | robust |
| C | 2e_K10 | -63.1 | [-75.4, -50.6] | 10/10 | robust |
| C | 2f_slru | -89.6 | [-90.1, -89.2] | 10/10 | robust |

### e2e_us — async arm, layout orig

| workload | strategy | mean Δ% | 95% CI | sign | verdict |
|---|---|---:|---|---:|---|
| C | 2d | -19.0 | [-21.2, -17.0] | 10/10 | robust |
| C | 2e_K10 | -37.4 | [-48.8, -25.5] | 10/10 | robust |
| C | 2f_slru | +10.0 | [+4.4, +15.7] | 8/10 | robust |

