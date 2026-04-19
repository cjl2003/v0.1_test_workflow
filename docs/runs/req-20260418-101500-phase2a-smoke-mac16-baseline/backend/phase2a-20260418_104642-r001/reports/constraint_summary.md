# Constraint Summary

- Constraint file: `inputs/sdc/mac16.sdc`
- Clock: 1.000 ns on `clk`
- Input delay: 0.100 ns on `inA inB in_ready mode`
- Output delay: 0.100 ns on `sum_out carry out_ready`
- False path: `rst_n`

All three synthesis corners loaded constraints successfully and emitted post-synthesis SDC plus timing/constraint reports.
The baseline timing result is still failing at 1 GHz in all three corners, with SS worst among TT/SS/FF.
