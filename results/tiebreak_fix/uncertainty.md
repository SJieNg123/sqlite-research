# R3 workload-sensitivity uncertainty

Pooled seeds: seed01, seed02, seed03, seed04, seed05, seed06, seed07, seed08, seed09, seed10 (n=10). Bootstrap 95% CI of the mean per-seed effect; effect = strategy vs same-seed baseline.

### e2e_warm_us — async arm, layout orig

| workload | strategy | mean Δ% | 95% CI | sign | verdict |
|---|---|---:|---|---:|---|
| A | 2e_K10 | -37.9 | [-52.1, -25.0] | 10/10 | robust |
| A | 2e_K500 | +78.0 | [+37.4, +136.9] | 10/10 | robust |
| A | 2f_slru | +758.6 | [+676.2, +883.8] | 10/10 | robust |
| B | 2e_K10 | -25.1 | [-31.6, -14.7] | 9/10 | robust |
| B | 2e_K500 | +43.1 | [+26.0, +59.7] | 10/10 | robust |
| B | 2f_slru | +731.3 | [+649.0, +846.5] | 10/10 | robust |
| C | 2e_K10 | -55.4 | [-67.2, -43.4] | 10/10 | robust |
| C | 2e_K500 | -31.8 | [-35.4, -28.3] | 10/10 | robust |
| C | 2f_slru | -10.0 | [-14.7, -5.7] | 10/10 | robust |

### first_query_us — async arm, layout orig

| workload | strategy | mean Δ% | 95% CI | sign | verdict |
|---|---|---:|---|---:|---|
| A | 2e_K10 | -49.6 | [-63.1, -37.4] | 10/10 | robust |
| A | 2e_K500 | -22.2 | [-62.1, +40.4] | 9/10 | directional |
| A | 2f_slru | -88.2 | [-89.4, -86.4] | 10/10 | robust |
| B | 2e_K10 | -36.5 | [-42.5, -27.4] | 9/10 | robust |
| B | 2e_K500 | -55.7 | [-67.8, -44.5] | 10/10 | robust |
| B | 2f_slru | -88.6 | [-89.8, -87.1] | 10/10 | robust |
| C | 2e_K10 | -63.9 | [-76.0, -51.6] | 10/10 | robust |
| C | 2e_K500 | -80.8 | [-81.8, -79.9] | 10/10 | robust |
| C | 2f_slru | -90.0 | [-90.4, -89.6] | 10/10 | robust |

### e2e_us — async arm, layout orig

| workload | strategy | mean Δ% | 95% CI | sign | verdict |
|---|---|---:|---|---:|---|
| A | 2e_K10 | -20.0 | [-35.1, -5.9] | 9/10 | robust |
| A | 2e_K500 | +95.8 | [+53.8, +155.1] | 10/10 | robust |
| A | 2f_slru | +776.4 | [+692.4, +903.8] | 10/10 | robust |
| B | 2e_K10 | -7.6 | [-15.8, +5.9] | 9/10 | directional |
| B | 2e_K500 | +61.1 | [+42.0, +80.4] | 10/10 | robust |
| B | 2f_slru | +749.2 | [+664.6, +867.7] | 10/10 | robust |
| C | 2e_K10 | -39.3 | [-50.4, -27.7] | 10/10 | robust |
| C | 2e_K500 | -15.1 | [-19.7, -10.7] | 10/10 | robust |
| C | 2f_slru | +5.2 | [+0.3, +9.9] | 7/10 | robust |

