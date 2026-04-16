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

    task check_after_posedge(input bit expected, input [127:0] step_name);
        begin
            @(posedge clk);
            #1;
            expect_pulse(expected, step_name);
        end
    endtask

    initial begin
        clk = 1'b0;
        rst_n = 1'b0;
        level_in = 1'b0;

        repeat (2) begin
            check_after_posedge(1'b0, "during reset");
        end

        rst_n = 1'b1;
        check_after_posedge(1'b0, "after reset release with input low");

        level_in = 1'b1;
        check_after_posedge(1'b1, "single pulse on rising edge");

        check_after_posedge(1'b0, "no repeated pulse while input stays high");

        level_in = 1'b0;
        check_after_posedge(1'b0, "no pulse on falling edge");

        level_in = 1'b1;
        check_after_posedge(1'b1, "second pulse on next rising edge");

        check_after_posedge(1'b0, "pulse returns low after one cycle");

        rst_n = 1'b0;
        level_in = 1'b1;
        check_after_posedge(1'b0, "during second reset with input high");

        rst_n = 1'b1;
        check_after_posedge(1'b0, "no pulse when input stays high across reset release");
        check_after_posedge(1'b0, "still no pulse while reset baseline stays high");

        level_in = 1'b0;
        check_after_posedge(1'b0, "drop low after reset release");

        level_in = 1'b1;
        check_after_posedge(1'b1, "pulse still appears on a fresh rise after reset");

        $display("PASS: rise_pulse_tb");
        $finish;
    end
endmodule
