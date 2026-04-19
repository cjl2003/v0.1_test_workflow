# Phase-2A Backend Summary

- Request Id: `req-20260418-101500-phase2a-smoke-mac16-baseline`
- Run Id: `phase2a-20260418_104642-r001`
- Version: `r001`
- Tag: `not-created`
- Commit: `pending`

## Gate Status
- Synthesis: `pass`
- Mapped Netlist: `present`
- Constraints: `loaded`
- Formal EC: `failed`

## Baseline Metrics
- Power: `TT=1.246e-02  6.353e-03  1.881e-02( 99.99%)  1.855e-06(  0.01%)  1.881e-02(100.00%); SS=9.182e-03  4.628e-03  1.381e-02( 99.77%)  3.137e-05(  0.23%)  1.384e-02(100.00%); FF=1.550e-02  6.960e-03  2.246e-02( 99.99%)  2.190e-06(  0.01%)  2.247e-02(100.00%)`
- Area: `TT=26905.68; SS=26814.24; FF=22349.88`
- Timing: `TT: WNS=-0.849442, TNS=-271.654297, Paths=894.000000; SS: WNS=-2.208038, TNS=-1234.247559, Paths=1031.000000; FF: WNS=-0.238153, TNS=-54.578938, Paths=299.000000`

## Short Notes
Synthesis completed on all three required PVT corners and produced a canonical TT mapped.v. Formal EC did not pass. The first direct RTL-oriented attempt required a Verilog-2000-compatible formal-spec proxy because FormalEC could not parse the original SystemVerilog source. That translated-spec run ended with FAIL:UNMATCH (79/987/0/0/1066). A second sanity run using TT pre_mapped.v vs TT mapped.v also ended with FAIL:UNMATCH (66/998/0/0/1064), so the remaining blocker is in the Formal proof setup or compare mapping, not in SSH connectivity or synthesis artifact generation.
