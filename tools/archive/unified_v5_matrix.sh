# The unified_v5 matrix, in one place, sourced by both the gate and the driver so
# they cannot disagree about what is being run.
#
# Family A (headline, orig): every cell the paper's Tables 3-6 need, plus the C_hit
#   control that currently sits in its own batch, plus the two coalesced delivery arms.
#   = unified_v4's 11 strategies + layers_92 (quoted in the guidance paragraph and the
#   layout comparison) + the two learned_markov budgets.
# Family B (delivery order, orig): lp_sorted/lp_shuf differ from 2f_slru ONLY in pread
#   order, so they run pread-only with no coalesced arm -- coalescing sorts offsets and
#   would silently make the two identical. run_experiment.py refuses the combination.
# Family C (layout and size): the structural strategies the layout paragraph
#   (main.tex:505) and the database-size paragraph quote. The 2f_topN and learned_markov
#   arms have no inputs outside orig and no claim needs them there.
#
# The coalesced arms run on orig only: hint geometry is what they vary, the layout axis
# does not vary it, and every layout/size claim is stated under the plain async arm.

WL_A="A,B,C,C_hit"
STRATS_A="layers_5,layers_92,2d,2e_K10,2e_K500,2f_top14,2f_top28,2f_top100,2f_top500,2f_slru,leaf_freq_K10,leaf_rand_K10,learned_markov_14,learned_markov_28"

STRATS_LP="lp_sorted,lp_shuf"

WL_C="A,B,C"
DBS_C="vacuum ta 1gb"
STRATS_C="layers_5,layers_92,2d,2e_K10,2e_K500,2f_slru,leaf_freq_K10,leaf_rand_K10"

# Reps. pread/async/baseline are the study defaults every prior batch used, so the
# shared cells stay protocol-identical to unified_v4.
PREAD_REPS=5
ASYNC_REPS=10
BASELINE_REPS=10
WIN_REPS=10       # coalesced, hint cut to the readahead window -> the strong baseline
BULK_REPS=5       # coalesced, one uncapped hint per range -> the naive version
