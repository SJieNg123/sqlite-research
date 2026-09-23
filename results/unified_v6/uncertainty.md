# R3 workload-sensitivity uncertainty

Pooled seeds: seed01, seed02, seed03, seed04, seed05, seed06, seed07, seed08, seed09, seed10 (n=10). Bootstrap 95% CI of the mean per-seed effect; effect = strategy vs same-seed baseline.

### e2e_warm_us — async arm, layout orig

| workload | strategy | mean Δ% | 95% CI | sign | verdict |
|---|---|---:|---|---:|---|
| A | layers_5 | -4.6 | [-15.1, +5.0] | 6/10 | tie |
| A | layers_92 | -12.6 | [-18.0, -5.8] | 9/10 | robust |
| A | 2d | -27.1 | [-30.7, -23.1] | 10/10 | robust |
| A | 2e_K10 | -37.5 | [-52.1, -24.5] | 10/10 | robust |
| A | 2e_K500 | +80.6 | [+40.8, +137.2] | 10/10 | robust |
| A | 2f_slru | +769.6 | [+680.8, +906.6] | 10/10 | robust |
| B | layers_5 | -0.9 | [-10.6, +6.7] | 8/10 | directional |
| B | layers_92 | -13.3 | [-20.8, -1.9] | 9/10 | robust |
| B | 2d | -26.2 | [-33.2, -15.9] | 9/10 | robust |
| B | 2e_K10 | -24.7 | [-30.8, -15.2] | 9/10 | robust |
| B | 2e_K500 | +42.2 | [+26.1, +57.7] | 10/10 | robust |
| B | 2f_slru | +723.6 | [+648.6, +825.6] | 10/10 | robust |
| C | layers_5 | +4.8 | [+3.5, +6.2] | 10/10 | robust |
| C | layers_92 | -21.5 | [-23.2, -19.6] | 10/10 | robust |
| C | 2d | -36.8 | [-39.8, -33.5] | 10/10 | robust |
| C | 2e_K10 | -57.1 | [-68.2, -45.7] | 10/10 | robust |
| C | 2e_K500 | -31.8 | [-35.0, -28.9] | 10/10 | robust |
| C | 2f_slru | -9.2 | [-13.3, -4.9] | 9/10 | robust |

### first_query_us — async arm, layout orig

| workload | strategy | mean Δ% | 95% CI | sign | verdict |
|---|---|---:|---|---:|---|
| A | layers_5 | -13.1 | [-24.0, -3.1] | 8/10 | robust |
| A | layers_92 | -36.6 | [-40.0, -32.9] | 10/10 | robust |
| A | 2d | -37.6 | [-40.4, -34.3] | 10/10 | robust |
| A | 2e_K10 | -49.5 | [-63.1, -37.2] | 10/10 | robust |
| A | 2e_K500 | -21.4 | [-61.0, +40.1] | 9/10 | directional |
| A | 2f_slru | -88.1 | [-89.3, -86.2] | 10/10 | robust |
| B | layers_5 | -8.9 | [-18.9, -1.1] | 7/10 | robust |
| B | layers_92 | -35.8 | [-42.1, -26.8] | 9/10 | robust |
| B | 2d | -36.1 | [-42.6, -26.8] | 9/10 | robust |
| B | 2e_K10 | -36.2 | [-41.6, -28.0] | 10/10 | robust |
| B | 2e_K500 | -54.5 | [-67.5, -42.0] | 10/10 | robust |
| B | 2f_slru | -88.7 | [-89.8, -87.3] | 10/10 | robust |
| C | layers_5 | -2.7 | [-4.1, -1.2] | 8/10 | robust |
| C | layers_92 | -42.5 | [-45.0, -39.9] | 10/10 | robust |
| C | 2d | -44.0 | [-47.3, -40.5] | 10/10 | robust |
| C | 2e_K10 | -65.7 | [-76.8, -54.2] | 10/10 | robust |
| C | 2e_K500 | -81.2 | [-82.0, -80.4] | 10/10 | robust |
| C | 2f_slru | -90.4 | [-90.8, -90.1] | 10/10 | robust |

### e2e_us — async arm, layout orig

| workload | strategy | mean Δ% | 95% CI | sign | verdict |
|---|---|---:|---|---:|---|
| A | layers_5 | +20.5 | [+10.5, +29.2] | 8/10 | robust |
| A | layers_92 | +12.5 | [+5.0, +22.7] | 9/10 | robust |
| A | 2d | -0.9 | [-7.0, +7.3] | 6/10 | tie |
| A | 2e_K10 | -11.2 | [-28.3, +5.8] | 7/10 | directional |
| A | 2e_K500 | +106.9 | [+64.8, +164.9] | 10/10 | robust |
| A | 2f_slru | +795.6 | [+703.7, +937.7] | 10/10 | robust |
| B | layers_5 | +23.5 | [+15.2, +30.5] | 9/10 | robust |
| B | layers_92 | +11.2 | [+1.8, +25.1] | 7/10 | robust |
| B | 2d | -1.9 | [-10.6, +11.0] | 7/10 | directional |
| B | 2e_K10 | -0.6 | [-8.4, +11.4] | 7/10 | directional |
| B | 2e_K500 | +66.3 | [+47.9, +84.3] | 10/10 | robust |
| B | 2f_slru | +748.0 | [+670.4, +852.8] | 10/10 | robust |
| C | layers_5 | +27.0 | [+25.2, +28.8] | 10/10 | robust |
| C | layers_92 | +0.1 | [-1.4, +1.6] | 6/10 | tie |
| C | 2d | -15.1 | [-17.3, -12.9] | 10/10 | robust |
| C | 2e_K10 | -35.6 | [-46.0, -24.8] | 10/10 | robust |
| C | 2e_K500 | -10.2 | [-14.5, -6.3] | 10/10 | robust |
| C | 2f_slru | +12.1 | [+6.5, +17.7] | 9/10 | robust |

