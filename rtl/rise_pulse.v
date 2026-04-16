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
            pulse_out <= primed & level_in & ~level_d;
            level_d   <= level_in;
            primed    <= 1'b1;
        end
    end
endmodule
