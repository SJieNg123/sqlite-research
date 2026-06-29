# S1 three-lever ablation — lever decomposition

Effect = strategy median vs **same-seed baseline** median, mean over seeds, bootstrap 95% CI. `leaf_freq` vs `leaf_rand` (same page-type, same count) isolates the access-frequency signal; `2d` isolates page-type; orig-vs-ta the layout-clustering lever.

#### layout orig — async arm (cross-seed mean Δ% vs baseline, 95% CI)

| workload | arm | lever isolated | pages | first-query Δ% | e2e_warm Δ% |
|---|---|---|---:|---|---|
| A | `2d` | (ii) page-type · interior-only | 18 | -37% [-41,-34] (robust) | -27% [-31,-22] (robust) |
| A | `leaf_rand_K10` | control · random leaves (= freq count) | 10 | +0% [-2,+3] (tie) | +10% [+7,+12] (robust) |
| A | `leaf_freq_K10` | (iii) access-frequency · hot leaves | 10 | -13% [-26,-1] (robust) | -4% [-18,+8] (directional) |
| A | `2e_K10` | (ii)+(iii) combined | 28 | -50% [-63,-37] (robust) | -38% [-52,-25] (robust) |
| A | `leaf_rand_K500` | control · random leaves (= freq count) | 500 | -3% [-7,+1] (directional) | +99% [+87,+116] (robust) |
| A | `leaf_freq_K500` | (iii) access-frequency · hot leaves | 500 | +21% [-26,+98] (directional) | +114% [+62,+191] (robust) |
| A | `2e_K500` | (ii)+(iii) combined | 518 | -17% [-62,+58] (directional) | +81% [+34,+151] (robust) |
| B | `2d` | (ii) page-type · interior-only | 18 | -36% [-43,-25] (robust) | -26% [-34,-14] (robust) |
| B | `leaf_rand_K10` | control · random leaves (= freq count) | 10 | -2% [-3,-1] (robust) | +7% [+6,+8] (robust) |
| B | `leaf_freq_K10` | (iii) access-frequency · hot leaves | 10 | -3% [-4,-2] (robust) | +6% [+5,+7] (robust) |
| B | `2e_K10` | (ii)+(iii) combined | 28 | -37% [-43,-28] (robust) | -26% [-32,-15] (robust) |
| C | `2d` | (ii) page-type · interior-only | 4 | -43% [-46,-41] (robust) | -36% [-38,-34] (robust) |
| C | `leaf_rand_K10` | control · random leaves (= freq count) | 10 | -2% [-3,-1] (robust) | +6% [+5,+7] (robust) |
| C | `leaf_freq_K10` | (iii) access-frequency · hot leaves | 10 | -40% [-43,-37] (robust) | -32% [-35,-28] (robust) |
| C | `2e_K10` | (ii)+(iii) combined | 14 | -81% [-82,-80] (robust) | -73% [-74,-72] (robust) |

#### layout ta — async arm (cross-seed mean Δ% vs baseline, 95% CI)

| workload | arm | lever isolated | pages | first-query Δ% | e2e_warm Δ% |
|---|---|---|---:|---|---|
| A | `2d` | (ii) page-type · interior-only | 43 | -37% [-44,-30] (robust) | -24% [-33,-16] (robust) |
| A | `leaf_rand_K10` | control · random leaves (= freq count) | 10 | -2% [-3,+0] (directional) | +8% [+6,+9] (robust) |
| A | `leaf_freq_K10` | (iii) access-frequency · hot leaves | 10 | -12% [-25,-0] (robust) | -3% [-17,+9] (directional) |
| A | `2e_K10` | (ii)+(iii) combined | 53 | -48% [-63,-34] (robust) | -34% [-51,-18] (robust) |
| A | `leaf_rand_K500` | control · random leaves (= freq count) | 500 | +1% [-2,+5] (directional) | +108% [+94,+122] (robust) |
| A | `leaf_freq_K500` | (iii) access-frequency · hot leaves | 500 | +3% [-25,+42] (tie) | +99% [+75,+130] (robust) |
| A | `2e_K500` | (ii)+(iii) combined | 543 | -51% [-66,-35] (robust) | +39% [+20,+57] (robust) |
| B | `2d` | (ii) page-type · interior-only | 40 | -36% [-44,-28] (robust) | -22% [-32,-13] (robust) |
| B | `leaf_rand_K10` | control · random leaves (= freq count) | 10 | -1% [-3,+0] (directional) | +8% [+6,+10] (robust) |
| B | `leaf_freq_K10` | (iii) access-frequency · hot leaves | 10 | -1% [-3,+3] (directional) | +9% [+6,+13] (robust) |
| B | `2e_K10` | (ii)+(iii) combined | 50 | -37% [-44,-30] (robust) | -22% [-31,-14] (robust) |
| C | `2d` | (ii) page-type · interior-only | 48 | -44% [-45,-43] (robust) | -31% [-32,-29] (robust) |
| C | `leaf_rand_K10` | control · random leaves (= freq count) | 10 | -2% [-3,-1] (robust) | +7% [+5,+8] (robust) |
| C | `leaf_freq_K10` | (iii) access-frequency · hot leaves | 10 | -32% [-36,-29] (robust) | -24% [-28,-20] (robust) |
| C | `2e_K10` | (ii)+(iii) combined | 58 | -80% [-81,-79] (robust) | -65% [-67,-64] (robust) |

