`timescale 1ns/1ps

module rise_pulse_tb;
    reg clk;
    reg rst_n;
    reg level_in;
    wire pulse_out;

    rise_pulse dut (
        .clk(clk),
        .rst_n(rst_n),
        .level_in(level_in),
        .pulse_out(pulse_out)
    );

    always #5 clk = ~clk;

    task expect_pulse(input bit expected, input [127:0] step_name);
        begin
            if (pulse_out !== expected) begin
                $display("FAIL: %0s expected pulse_out=%0d got %0d", step_name, expected, pulse_out);
                $fatal(1);
            end
        end
    endtask

    initial begin
        clk = 1'b0;
        rst_n = 1'b0;
        level_in = 1'b0;

        repeat (2) @(posedge clk);
        expect_pulse(1'b0, "during reset");

        rst_n = 1'b1;
        @(posedge clk);
        expect_pulse(1'b0, "after reset release with input low");

        level_in = 1'b1;
        @(posedge clk);
        expect_pulse(1'b1, "single pulse on rising edge");

        @(posedge clk);
        expect_pulse(1'b0, "no repeated pulse while input stays high");

        level_in = 1'b0;
        @(posedge clk);
        expect_pulse(1'b0, "no pulse on falling edge");

        level_in = 1'b1;
        @(posedge clk);
        expect_pulse(1'b1, "second pulse on next rising edge");

        @(posedge clk);
        expect_pulse(1'b0, "pulse returns low after one cycle");

        $display("PASS: rise_pulse_tb");
        $finish;
    end
endmodule
