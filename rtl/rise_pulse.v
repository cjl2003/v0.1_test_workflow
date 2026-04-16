// rise_pulse emits a one-cycle pulse for sampled 0->1 transitions.
// Reset release establishes a new baseline: if level_in is already high when
// rst_n is released, that high level is not treated as a new rising edge.
// pulse_out only asserts after reset once level_in is sampled low first and
// then sampled high on a later clock edge.
module rise_pulse (
    input  wire clk,
    input  wire rst_n,
    input  wire level_in,
    output reg  pulse_out
);
    reg level_d;
    reg primed;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            level_d   <= 1'b0;
            primed    <= 1'b0;
            pulse_out <= 1'b0;
        end else begin
            // Detect only fresh 0->1 samples after the reset baseline is armed.
            pulse_out <= primed & level_in & ~level_d;
            level_d   <= level_in;
            primed    <= 1'b1;
        end
    end
endmodule
