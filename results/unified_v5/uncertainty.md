# R3 workload-sensitivity uncertainty

Pooled seeds: seed01, seed02, seed03, seed04, seed05, seed06, seed07, seed08, seed09, seed10 (n=10). Bootstrap 95% CI of the mean per-seed effect; effect = strategy vs same-seed baseline.

### e2e_warm_us — async arm, layout orig

| workload | strategy | mean Δ% | 95% CI | sign | verdict |
|---|---|---:|---|---:|---|
| A | layers_5 | -4.7 | [-14.9, +4.5] | 6/10 | tie |
| A | layers_92 | -11.5 | [-17.1, -4.4] | 9/10 | robust |
| A | 2d | -26.9 | [-30.8, -22.2] | 10/10 | robust |
| A | 2e_K10 | -38.1 | [-52.0, -25.6] | 10/10 | robust |
| A | 2e_K500 | +50.4 | [+32.2, +69.9] | 10/10 | robust |
| A | 2f_slru | +769.4 | [+684.0, +904.3] | 10/10 | robust |
| B | layers_5 | -3.4 | [-13.6, +4.5] | 7/10 | directional |
| B | layers_92 | -13.5 | [-21.0, -1.7] | 9/10 | robust |
| B | 2d | -26.4 | [-32.7, -16.8] | 9/10 | robust |
| B | 2e_K10 | -24.2 | [-30.5, -14.7] | 9/10 | robust |
| B | 2e_K500 | +44.6 | [+29.2, +59.5] | 10/10 | robust |
| B | 2f_slru | +722.3 | [+642.6, +829.8] | 10/10 | robust |
| C | layers_5 | +4.7 | [+3.8, +5.7] | 10/10 | robust |
| C | layers_92 | -20.4 | [-21.5, -19.3] | 10/10 | robust |
| C | 2d | -35.7 | [-37.9, -33.6] | 10/10 | robust |
| C | 2e_K10 | -54.0 | [-66.0, -41.8] | 10/10 | robust |
| C | 2e_K500 | -29.6 | [-33.5, -25.8] | 10/10 | robust |
| C | 2f_slru | -4.5 | [-9.9, +0.8] | 7/10 | directional |

### first_query_us — async arm, layout orig

| workload | strategy | mean Δ% | 95% CI | sign | verdict |
|---|---|---:|---|---:|---|
| A | layers_5 | -13.7 | [-24.6, -3.8] | 8/10 | robust |
| A | layers_92 | -36.3 | [-40.0, -32.2] | 10/10 | robust |
| A | 2d | -37.9 | [-40.9, -34.7] | 10/10 | robust |
| A | 2e_K10 | -50.6 | [-63.5, -38.9] | 10/10 | robust |
| A | 2e_K500 | -53.0 | [-66.9, -38.8] | 10/10 | robust |
| A | 2f_slru | -88.1 | [-89.2, -86.2] | 10/10 | robust |
| B | layers_5 | -12.0 | [-21.9, -4.2] | 9/10 | robust |
| B | layers_92 | -36.9 | [-43.1, -27.3] | 9/10 | robust |
| B | 2d | -36.9 | [-42.6, -28.2] | 10/10 | robust |
| B | 2e_K10 | -37.1 | [-42.5, -28.9] | 10/10 | robust |
| B | 2e_K500 | -54.4 | [-67.5, -41.6] | 10/10 | robust |
| B | 2f_slru | -88.8 | [-89.9, -87.4] | 10/10 | robust |
| C | layers_5 | -3.3 | [-4.5, -2.0] | 9/10 | robust |
| C | layers_92 | -42.3 | [-44.5, -40.1] | 10/10 | robust |
| C | 2d | -43.6 | [-46.4, -40.9] | 10/10 | robust |
| C | 2e_K10 | -63.3 | [-75.8, -50.6] | 10/10 | robust |
| C | 2e_K500 | -80.5 | [-81.5, -79.6] | 10/10 | robust |
| C | 2f_slru | -89.8 | [-90.3, -89.3] | 10/10 | robust |

### e2e_us — async arm, layout orig

| workload | strategy | mean Δ% | 95% CI | sign | verdict |
|---|---|---:|---|---:|---|
| A | layers_5 | +24.6 | [+14.5, +33.4] | 8/10 | robust |
| A | layers_92 | +18.0 | [+9.1, +28.2] | 9/10 | robust |
| A | 2d | +3.2 | [-4.2, +11.4] | 7/10 | directional |
| A | 2e_K10 | -8.3 | [-22.9, +5.7] | 5/10 | tie |
| A | 2e_K500 | +80.5 | [+62.1, +100.5] | 10/10 | robust |
| A | 2f_slru | +799.8 | [+711.8, +938.9] | 10/10 | robust |
| B | layers_5 | +24.8 | [+14.0, +34.6] | 8/10 | robust |
| B | layers_92 | +15.2 | [+4.2, +30.4] | 8/10 | robust |
| B | 2d | +1.8 | [-7.6, +14.8] | 7/10 | directional |
| B | 2e_K10 | +5.1 | [-5.3, +18.5] | 7/10 | directional |
| B | 2e_K500 | +73.4 | [+55.4, +91.8] | 10/10 | robust |
| B | 2f_slru | +749.7 | [+667.7, +859.8] | 10/10 | robust |
| C | layers_5 | +29.2 | [+27.1, +31.5] | 10/10 | robust |
| C | layers_92 | +4.6 | [+2.7, +6.8] | 10/10 | robust |
| C | 2d | -9.9 | [-12.6, -6.4] | 9/10 | robust |
| C | 2e_K10 | -28.2 | [-38.7, -17.7] | 10/10 | robust |
| C | 2e_K500 | -4.1 | [-10.6, +2.7] | 6/10 | tie |
| C | 2f_slru | +20.7 | [+12.7, +29.5] | 10/10 | robust |

