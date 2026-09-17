# R3 workload-sensitivity uncertainty

Pooled seeds: seed01, seed02, seed03, seed04, seed05, seed06, seed07, seed08, seed09, seed10 (n=10). Bootstrap 95% CI of the mean per-seed effect; effect = strategy vs same-seed baseline.

### e2e_warm_us — async arm, layout orig

| workload | strategy | mean Δ% | 95% CI | sign | verdict |
|---|---|---:|---|---:|---|
| A | layers_5 | -4.8 | [-15.5, +5.2] | 6/10 | tie |
| A | 2d | -27.3 | [-30.9, -23.0] | 10/10 | robust |
| A | 2e_K10 | -37.5 | [-52.2, -24.3] | 10/10 | robust |
| A | 2e_K500 | +86.9 | [+37.3, +161.1] | 10/10 | robust |
| A | 2f_slru | +766.9 | [+676.5, +903.1] | 10/10 | robust |
| B | layers_5 | -1.8 | [-12.1, +6.1] | 8/10 | directional |
| B | 2d | -25.6 | [-32.9, -15.9] | 9/10 | robust |
| B | 2e_K10 | -26.0 | [-31.7, -17.4] | 9/10 | robust |
| B | 2e_K500 | +43.7 | [+27.2, +59.1] | 10/10 | robust |
| B | 2f_slru | +721.8 | [+640.8, +827.4] | 10/10 | robust |
| C | layers_5 | +4.1 | [+3.1, +5.1] | 10/10 | robust |
| C | 2d | -36.7 | [-39.4, -34.1] | 10/10 | robust |
| C | 2e_K10 | -55.5 | [-67.5, -43.3] | 10/10 | robust |
| C | 2e_K500 | -31.0 | [-33.8, -28.3] | 10/10 | robust |
| C | 2f_slru | -9.6 | [-14.4, -5.0] | 9/10 | robust |

### first_query_us — async arm, layout orig

| workload | strategy | mean Δ% | 95% CI | sign | verdict |
|---|---|---:|---|---:|---|
| A | layers_5 | -13.4 | [-24.6, -2.9] | 8/10 | robust |
| A | 2d | -37.7 | [-40.6, -34.6] | 10/10 | robust |
| A | 2e_K10 | -49.4 | [-63.1, -37.0] | 10/10 | robust |
| A | 2e_K500 | -13.6 | [-61.6, +65.0] | 9/10 | directional |
| A | 2f_slru | -88.0 | [-89.3, -86.2] | 10/10 | robust |
| B | layers_5 | -9.8 | [-20.0, -1.6] | 7/10 | robust |
| B | 2d | -36.9 | [-42.9, -28.4] | 10/10 | robust |
| B | 2e_K10 | -37.3 | [-42.4, -30.1] | 10/10 | robust |
| B | 2e_K500 | -55.4 | [-67.8, -44.0] | 10/10 | robust |
| B | 2f_slru | -88.7 | [-89.8, -87.2] | 10/10 | robust |
| C | layers_5 | -3.2 | [-4.4, -2.1] | 10/10 | robust |
| C | 2d | -44.1 | [-47.1, -41.1] | 10/10 | robust |
| C | 2e_K10 | -64.0 | [-76.2, -51.6] | 10/10 | robust |
| C | 2e_K500 | -80.6 | [-81.5, -79.8] | 10/10 | robust |
| C | 2f_slru | -90.0 | [-90.4, -89.5] | 10/10 | robust |

### e2e_us — async arm, layout orig

| workload | strategy | mean Δ% | 95% CI | sign | verdict |
|---|---|---:|---|---:|---|
| A | layers_5 | +13.9 | [+3.7, +23.2] | 7/10 | robust |
| A | 2d | -8.1 | [-13.5, +0.0] | 9/10 | directional |
| A | 2e_K10 | -18.3 | [-34.9, -2.2] | 9/10 | robust |
| A | 2e_K500 | +105.8 | [+55.1, +179.9] | 10/10 | robust |
| A | 2f_slru | +786.2 | [+693.6, +926.0] | 10/10 | robust |
| B | layers_5 | +17.2 | [+7.3, +25.4] | 8/10 | robust |
| B | 2d | -7.1 | [-15.6, +5.1] | 9/10 | directional |
| B | 2e_K10 | -6.9 | [-14.6, +4.4] | 9/10 | directional |
| B | 2e_K500 | +63.5 | [+45.0, +81.5] | 10/10 | robust |
| B | 2f_slru | +740.8 | [+657.7, +849.4] | 10/10 | robust |
| C | layers_5 | +21.5 | [+20.8, +22.4] | 10/10 | robust |
| C | 2d | -18.9 | [-20.9, -16.7] | 10/10 | robust |
| C | 2e_K10 | -37.7 | [-48.5, -26.5] | 10/10 | robust |
| C | 2e_K500 | -13.5 | [-17.0, -10.1] | 10/10 | robust |
| C | 2f_slru | +7.1 | [+1.4, +12.7] | 6/10 | robust |

