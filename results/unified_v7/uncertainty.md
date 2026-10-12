# R3 workload-sensitivity uncertainty

Pooled seeds: seed01, seed02, seed03, seed04, seed05, seed06, seed07, seed08, seed09, seed10 (n=10). Bootstrap 95% CI of the mean per-seed effect; effect = strategy vs same-seed baseline.

### e2e_warm_us — async arm, layout orig

| workload | strategy | mean Δ% | 95% CI | sign | verdict |
|---|---|---:|---|---:|---|
| A | layers_5 | -7.9 | [-18.3, +1.1] | 6/10 | tie |
| A | layers_92 | -14.4 | [-19.7, -7.9] | 9/10 | robust |
| A | 2d | -27.6 | [-31.7, -22.9] | 10/10 | robust |
| A | 2e_K10 | -39.3 | [-52.7, -27.1] | 10/10 | robust |
| A | 2e_K500 | +76.2 | [+36.6, +133.6] | 10/10 | robust |
| A | 2f_slru | +751.1 | [+667.2, +880.4] | 10/10 | robust |
| B | layers_5 | -1.5 | [-12.8, +7.2] | 8/10 | directional |
| B | layers_92 | -12.9 | [-20.1, -0.2] | 9/10 | robust |
| B | 2d | -26.3 | [-32.3, -16.6] | 9/10 | robust |
| B | 2e_K10 | -24.4 | [-30.9, -13.8] | 9/10 | robust |
| B | 2e_K500 | +45.6 | [+27.6, +62.7] | 10/10 | robust |
| B | 2f_slru | +728.1 | [+642.9, +844.3] | 10/10 | robust |
| C | layers_5 | +3.9 | [+2.2, +5.5] | 9/10 | robust |
| C | layers_92 | -21.7 | [-23.1, -20.2] | 10/10 | robust |
| C | 2d | -36.7 | [-39.3, -34.2] | 10/10 | robust |
| C | 2e_K10 | -56.5 | [-67.7, -44.8] | 10/10 | robust |
| C | 2e_K500 | -31.0 | [-34.5, -28.0] | 10/10 | robust |
| C | 2f_slru | -5.9 | [-11.2, -1.0] | 6/10 | robust |

### first_query_us — async arm, layout orig

| workload | strategy | mean Δ% | 95% CI | sign | verdict |
|---|---|---:|---|---:|---|
| A | layers_5 | -16.3 | [-26.9, -6.7] | 9/10 | robust |
| A | layers_92 | -38.2 | [-42.0, -34.4] | 10/10 | robust |
| A | 2d | -37.9 | [-41.3, -34.3] | 10/10 | robust |
| A | 2e_K10 | -51.3 | [-64.0, -39.9] | 10/10 | robust |
| A | 2e_K500 | -24.8 | [-62.8, +35.5] | 9/10 | directional |
| A | 2f_slru | -88.3 | [-89.4, -86.5] | 10/10 | robust |
| B | layers_5 | -9.6 | [-20.9, -0.9] | 7/10 | robust |
| B | layers_92 | -36.0 | [-41.9, -26.1] | 9/10 | robust |
| B | 2d | -36.3 | [-41.8, -27.8] | 10/10 | robust |
| B | 2e_K10 | -36.2 | [-42.1, -27.0] | 9/10 | robust |
| B | 2e_K500 | -55.5 | [-67.6, -44.1] | 10/10 | robust |
| B | 2f_slru | -88.6 | [-89.8, -87.0] | 10/10 | robust |
| C | layers_5 | -3.6 | [-5.1, -2.2] | 10/10 | robust |
| C | layers_92 | -42.9 | [-45.0, -40.8] | 10/10 | robust |
| C | 2d | -44.1 | [-46.9, -41.2] | 10/10 | robust |
| C | 2e_K10 | -65.1 | [-76.5, -53.2] | 10/10 | robust |
| C | 2e_K500 | -80.8 | [-81.8, -79.9] | 10/10 | robust |
| C | 2f_slru | -89.9 | [-90.4, -89.4] | 10/10 | robust |

### e2e_us — async arm, layout orig

| workload | strategy | mean Δ% | 95% CI | sign | verdict |
|---|---|---:|---|---:|---|
| A | layers_5 | +17.3 | [+8.0, +25.2] | 7/10 | robust |
| A | layers_92 | +10.9 | [+3.3, +20.6] | 8/10 | robust |
| A | 2d | -2.5 | [-8.9, +5.2] | 7/10 | directional |
| A | 2e_K10 | -13.8 | [-29.1, +0.7] | 6/10 | tie |
| A | 2e_K500 | +101.5 | [+61.0, +158.5] | 10/10 | robust |
| A | 2f_slru | +776.4 | [+690.1, +909.3] | 10/10 | robust |
| B | layers_5 | +23.5 | [+12.7, +33.1] | 8/10 | robust |
| B | layers_92 | +11.6 | [+2.4, +27.1] | 9/10 | robust |
| B | 2d | -2.2 | [-9.6, +10.1] | 9/10 | directional |
| B | 2e_K10 | -0.4 | [-8.2, +12.7] | 9/10 | directional |
| B | 2e_K500 | +69.6 | [+50.4, +88.7] | 10/10 | robust |
| B | 2f_slru | +752.1 | [+665.0, +870.8] | 10/10 | robust |
| C | layers_5 | +26.4 | [+23.9, +29.1] | 10/10 | robust |
| C | layers_92 | +1.2 | [-0.5, +3.2] | 6/10 | tie |
| C | 2d | -14.2 | [-16.3, -11.9] | 10/10 | robust |
| C | 2e_K10 | -34.2 | [-44.5, -23.0] | 10/10 | robust |
| C | 2e_K500 | -9.2 | [-14.4, -4.5] | 9/10 | robust |
| C | 2f_slru | +16.8 | [+10.1, +22.9] | 10/10 | robust |

