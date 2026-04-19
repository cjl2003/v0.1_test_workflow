# Formal EC Summary

- Canonical implementation netlist: `TT mapped.v`
- Translated-formal-spec run: `FAIL:UNMATCH` with asserts `79/987/0/0/1066`
- TT pre_mapped.v sanity run: `FAIL:UNMATCH` with asserts `66/998/0/0/1064`

## Findings
- FormalEC could not consume the original `rtl/mac16.sv` directly under the sample Verilog-2000 read flow, so a local Verilog-2000-compatible formal-spec proxy was generated for diagnosis.
- That translated-spec run still failed with large unmatched state.
- A second sanity run using TT `pre_mapped.v` versus TT `mapped.v` also failed, so the remaining issue is in proof setup / compare mapping rather than SSH reachability or missing mapped netlists.

## Evidence
- Windows package contains `logs/formal_console.log`, `logs/formal_pre_console.log`, `formal/run_out/cec.match`, `formal/run_out/compare.point`, `formal/pre_run/cec.match`, and `formal/pre_run/compare.point`.
