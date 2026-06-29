# R3 workload-sensitivity uncertainty

Pooled seeds: seed01, seed02, seed03, seed04, seed05, seed06, seed07, seed08, seed09, seed10 (n=10). Bootstrap 95% CI of the mean per-seed effect; effect = strategy vs same-seed baseline.

### e2e_warm_us — async arm, layout orig

| workload | strategy | mean Δ% | 95% CI | sign | verdict |
|---|---|---:|---|---:|---|
| A | 2d | -26.8 | [-30.9, -22.0] | 10/10 | robust |
| A | 2e_K10 | -37.8 | [-52.5, -24.5] | 10/10 | robust |
| B | 2d | -26.1 | [-33.6, -14.0] | 9/10 | robust |
| B | 2e_K10 | -25.9 | [-32.4, -14.9] | 9/10 | robust |
| C | 2d | -36.0 | [-38.0, -33.9] | 10/10 | robust |
| C | 2e_K10 | -72.8 | [-74.2, -71.5] | 10/10 | robust |

### first_query_us — async arm, layout orig

| workload | strategy | mean Δ% | 95% CI | sign | verdict |
|---|---|---:|---|---:|---|
| A | 2d | -37.1 | [-40.6, -33.6] | 10/10 | robust |
| A | 2e_K10 | -49.7 | [-63.4, -37.4] | 10/10 | robust |
| B | 2d | -35.9 | [-42.9, -25.0] | 9/10 | robust |
| B | 2e_K10 | -37.2 | [-43.2, -27.7] | 9/10 | robust |
| C | 2d | -43.3 | [-45.6, -40.9] | 10/10 | robust |
| C | 2e_K10 | -81.2 | [-82.2, -80.3] | 10/10 | robust |

### e2e_us — async arm, layout orig

| workload | strategy | mean Δ% | 95% CI | sign | verdict |
|---|---|---:|---|---:|---|
| A | 2d | -7.7 | [-12.9, -1.3] | 9/10 | robust |
| A | 2e_K10 | -18.6 | [-33.8, -4.2] | 8/10 | robust |
| B | 2d | -7.8 | [-16.9, +7.2] | 9/10 | directional |
| B | 2e_K10 | -7.5 | [-15.7, +6.4] | 9/10 | directional |
| C | 2d | -19.5 | [-20.8, -18.3] | 10/10 | robust |
| C | 2e_K10 | -55.7 | [-58.8, -52.9] | 10/10 | robust |

