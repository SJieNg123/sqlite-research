# The unified_v6 matrix, in one place, sourced by both the gate and the driver so
# they cannot disagree about what is being run.
#
# v6 = v5 plus the one coverage gap v5 left: the 2f_topN (Dump-N) family outside orig.
# v5 ran Dump-N on orig only, on the reasoning that no claim needed it elsewhere. That
# turned out to be wrong for the database-size paragraph (main.tex:553), whose
# "Skel+500 from -31% to +35%" clause cannot be checked without Dump-500 at 1gb. Rather
# than run those cells as an addendum, which would put them in a different machine state
# and forfeit absolute comparability with everything else, v6 re-runs the whole matrix.
#
# Family A (headline, orig): every cell the paper's Tables 3-6 need, plus the C_hit
#   control, plus the two coalesced delivery arms.
# Family B (delivery order, orig): lp_sorted/lp_shuf differ from 2f_slru ONLY in pread
#   order, so they run pread-only with no coalesced arm -- coalescing sorts offsets and
#   would silently make the two identical. run_experiment.py refuses the combination.
# Family C (layout and size): now 12 strategies, the 8 structural/ablation arms v5 ran
#   plus the 4 Dump-N budgets. Inputs come from tools/gen_freqdump_layouts.sh.
#
# The coalesced arms still run on orig only: hint geometry is what they vary, the layout
# axis does not vary it, and every layout/size claim is stated under the plain async arm.
# learned_markov also stays orig-only: it needs LOSO training per layout and no claim in
# the paper places it outside orig, so adding it would be cost without a consumer.

WL_A="A,B,C,C_hit"
STRATS_A="layers_5,layers_92,2d,2e_K10,2e_K500,2f_top14,2f_top28,2f_top100,2f_top500,2f_slru,leaf_freq_K10,leaf_rand_K10,learned_markov_14,learned_markov_28"

STRATS_LP="lp_sorted,lp_shuf"

WL_C="A,B,C"
DBS_C="vacuum ta 1gb"
STRATS_C="layers_5,layers_92,2d,2e_K10,2e_K500,2f_top14,2f_top28,2f_top100,2f_top500,2f_slru,leaf_freq_K10,leaf_rand_K10"

# Reps. Unchanged from v5 and from every prior batch, so the shared cells stay
# protocol-identical and v5 -> v6 reproduction is a clean check.
PREAD_REPS=5
ASYNC_REPS=10
BASELINE_REPS=10
WIN_REPS=10       # coalesced, hint cut to the readahead window -> the strong baseline
BULK_REPS=5       # coalesced, one uncapped hint per range -> the naive version
