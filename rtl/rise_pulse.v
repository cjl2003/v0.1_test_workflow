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
            // The first sampled high level after reset release is treated as
            // the new baseline and does not emit a pulse. A pulse is only
            // generated after reset once the input is observed low and then
            // rises to high on a later clock edge.
            pulse_out <= primed & level_in & ~level_d;
            level_d   <= level_in;
            primed    <= 1'b1;
        end
    end
endmodule
