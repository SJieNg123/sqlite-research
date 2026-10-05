# unified_v7 matrix, shared by tools/run_unified_v7.sh and tools/check_unified_v7_inputs.sh.
# Families A to C repeat unified_v6 (tools/unified_v6_matrix.sh) except that family C now
# also runs the window-chunked arm. Families D and E are new.
WL_A="A,B,C,C_hit"
STRATS_A="layers_5,layers_92,2d,2e_K10,2e_K500,2f_top14,2f_top28,2f_top100,2f_top500,2f_slru,leaf_freq_K10,leaf_rand_K10,learned_markov_14,learned_markov_28"
STRATS_LP="lp_sorted,lp_shuf"
WL_C="A,B,C"
DBS_C="vacuum ta 1gb"
STRATS_C="layers_5,layers_92,2d,2e_K10,2e_K500,2f_top14,2f_top28,2f_top100,2f_top500,2f_slru,leaf_freq_K10,leaf_rand_K10"
# family D: Dump-15, the matched budget for Skel+10 on Tail-Hit (results/matched_budget/PREREG.md)
WL_D="C_hit"
STRATS_D="2f_top15"
# family E: the profile-free whole-file baselines (results/pilot_whole_file_delivery)
WL_E="A,B,C,C_hit"
STRATS_E="whole_file"
PREAD_REPS=5
ASYNC_REPS=10
BASELINE_REPS=10
WIN_REPS=10       # coalesced, hint cut to the readahead window -> the strong baseline
BULK_REPS=5       # coalesced, one uncapped hint per range -> the naive version
POPULATE_REPS=10  # synchronous MAP_POPULATE of the whole file (family E only)
