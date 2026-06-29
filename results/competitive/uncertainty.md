# R3 workload-sensitivity uncertainty

Pooled seeds: seed01, seed02, seed03, seed04, seed05, seed06, seed07, seed08, seed09, seed10 (n=10). Bootstrap 95% CI of the mean per-seed effect; effect = strategy vs same-seed baseline.

### e2e_warm_us — async arm, layout orig

| workload | strategy | mean Δ% | 95% CI | sign | verdict |
|---|---|---:|---|---:|---|
| A | 2e_K10 | -38.2 | [-52.9, -25.1] | 10/10 | robust |
| A | 2f_slru | +762.3 | [+674.2, +899.4] | 10/10 | robust |
| B | 2e_K10 | -23.8 | [-31.4, -11.9] | 9/10 | robust |
| B | 2f_slru | +730.0 | [+644.3, +847.9] | 10/10 | robust |
| C | 2e_K10 | -72.5 | [-73.8, -71.2] | 10/10 | robust |
| C | 2f_slru | -11.7 | [-16.7, -6.5] | 9/10 | robust |

### first_query_us — async arm, layout orig

| workload | strategy | mean Δ% | 95% CI | sign | verdict |
|---|---|---:|---|---:|---|
| A | 2e_K10 | -50.0 | [-63.5, -37.8] | 10/10 | robust |
| A | 2f_slru | -88.2 | [-89.4, -86.4] | 10/10 | robust |
| B | 2e_K10 | -35.1 | [-42.0, -24.7] | 9/10 | robust |
| B | 2f_slru | -88.7 | [-89.9, -87.1] | 10/10 | robust |
| C | 2e_K10 | -80.9 | [-81.8, -80.0] | 10/10 | robust |
| C | 2f_slru | -90.1 | [-90.5, -89.7] | 10/10 | robust |

### e2e_us — async arm, layout orig

| workload | strategy | mean Δ% | 95% CI | sign | verdict |
|---|---|---:|---|---:|---|
| A | 2e_K10 | -18.3 | [-34.7, -2.3] | 9/10 | robust |
| A | 2f_slru | +782.1 | [+692.0, +922.6] | 10/10 | robust |
| B | 2e_K10 | -5.3 | [-14.3, +9.6] | 9/10 | directional |
| B | 2f_slru | +749.0 | [+661.9, +869.7] | 10/10 | robust |
| C | 2e_K10 | -55.1 | [-57.9, -52.3] | 10/10 | robust |
| C | 2f_slru | +5.7 | [-0.3, +11.9] | 7/10 | directional |

