`timescale 1ps/1ps

module tb_mac16;

    localparam int CLK_HALF_PS = 500;
    localparam int IN_BITS     = 16;
    localparam int OUT_BITS    = 24;
    localparam int FRAME_COUNT = 6;
    localparam int TIMEOUT_CYC = 5000;

    logic clk;
    logic rst_n;
    logic mode;
    logic in_ready;
    logic inA;
    logic inB;
    logic sum_out;
    logic carry;
    logic out_ready;

    logic [15:0] input_a [0:FRAME_COUNT-1];
    logic [15:0] input_b [0:FRAME_COUNT-1];
    logic [23:0] exp_data [0:FRAME_COUNT-1];
    logic        exp_carry [0:FRAME_COUNT-1];
    logic [1:0]  exp_segment [0:FRAME_COUNT-1];

    logic        scenario_running;
    logic        capture_active;
    logic [23:0] captured_word;
    integer      captured_bits;
    integer      got_count;
    integer      exp_count;
    logic        failed;

    logic        carry_has_gone_high;
    logic        carry_clear_expected;

    integer idx;
    integer wait_idx;

    mac16 dut (
        .clk      (clk),
        .rst_n    (rst_n),
        .mode     (mode),
        .in_ready (in_ready),
        .inA      (inA),
        .inB      (inB),
        .sum_out  (sum_out),
        .carry    (carry),
        .out_ready(out_ready)
    );

    // 1GHz 时钟，500ps 半周期。
    initial begin
        clk = 1'b0;
        forever #CLK_HALF_PS clk = ~clk;
    end

`ifdef TB_ENABLE_VCD
    // 只在调试时导出波形，默认关闭。
    initial begin
        $dumpfile("sim/mac16_tb.vcd");
        $dumpvars(0, tb_mac16);
    end
`endif

    // 题目给定的 6 组输入向量。
    initial begin
        input_a[0] = 16'd2;
        input_a[1] = 16'd8;
        input_a[2] = 16'd14;
        input_a[3] = 16'd116;
        input_a[4] = 16'd1546;
        input_a[5] = 16'd20698;

        input_b[0] = 16'd6;
        input_b[1] = 16'd30;
        input_b[2] = 16'd71;
        input_b[3] = 16'd828;
        input_b[4] = 16'd1152;
        input_b[5] = 16'd728;
    end

    task automatic clear_capture_state;
        begin
            capture_active = 1'b0;
            captured_word  = '0;
            captured_bits  = 0;
        end
    endtask

    task automatic clear_carry_monitor_state;
        begin
            carry_has_gone_high = 1'b0;
            carry_clear_expected = 1'b0;
        end
    endtask

    task automatic begin_scenario;
        begin
            got_count        = 0;
            exp_count        = FRAME_COUNT;
            scenario_running = 1'b1;
            clear_capture_state();
            clear_carry_monitor_state();
        end
    endtask

    task automatic end_scenario;
        begin
            scenario_running = 1'b0;
            clear_capture_state();
            clear_carry_monitor_state();
        end
    endtask

    task automatic load_mode0_expected;
        begin
            exp_data[0]  = 24'd12;
            exp_data[1]  = 24'd252;
            exp_data[2]  = 24'd1234;
            exp_data[3]  = 24'd97042;
            exp_data[4]  = 24'd1877040;
            exp_data[5]  = 24'd71920;

            exp_carry[0] = 1'b0;
            exp_carry[1] = 1'b0;
            exp_carry[2] = 1'b0;
            exp_carry[3] = 1'b0;
            exp_carry[4] = 1'b0;
            exp_carry[5] = 1'b1;

            exp_segment[0] = 2'd0;
            exp_segment[1] = 2'd0;
            exp_segment[2] = 2'd0;
            exp_segment[3] = 2'd0;
            exp_segment[4] = 2'd0;
            exp_segment[5] = 2'd0;
        end
    endtask

    task automatic load_mode1_expected;
        begin
            exp_data[0]  = 24'd12;
            exp_data[1]  = 24'd252;
            exp_data[2]  = 24'd1246;
            exp_data[3]  = 24'd97294;
            exp_data[4]  = 24'd1878286;
            exp_data[5]  = 24'd169214;

            exp_carry[0] = 1'b0;
            exp_carry[1] = 1'b0;
            exp_carry[2] = 1'b0;
            exp_carry[3] = 1'b0;
            exp_carry[4] = 1'b0;
            exp_carry[5] = 1'b1;

            exp_segment[0] = 2'd0;
            exp_segment[1] = 2'd0;
            exp_segment[2] = 2'd0;
            exp_segment[3] = 2'd0;
            exp_segment[4] = 2'd0;
            exp_segment[5] = 2'd0;
        end
    endtask

    task automatic load_switch_0_to_1_expected;
        begin
            exp_data[0]  = 24'd12;
            exp_data[1]  = 24'd252;
            exp_data[2]  = 24'd1234;
            exp_data[3]  = 24'd96048;
            exp_data[4]  = 24'd1877040;
            exp_data[5]  = 24'd167968;

            exp_carry[0] = 1'b0;
            exp_carry[1] = 1'b0;
            exp_carry[2] = 1'b0;
            exp_carry[3] = 1'b0;
            exp_carry[4] = 1'b0;
            exp_carry[5] = 1'b1;

            exp_segment[0] = 2'd0;
            exp_segment[1] = 2'd0;
            exp_segment[2] = 2'd0;
            exp_segment[3] = 2'd1;
            exp_segment[4] = 2'd1;
            exp_segment[5] = 2'd1;
        end
    endtask

    task automatic load_switch_1_to_0_expected;
        begin
            exp_data[0]  = 24'd12;
            exp_data[1]  = 24'd252;
            exp_data[2]  = 24'd1246;
            exp_data[3]  = 24'd96048;
            exp_data[4]  = 24'd1877040;
            exp_data[5]  = 24'd71920;

            exp_carry[0] = 1'b0;
            exp_carry[1] = 1'b0;
            exp_carry[2] = 1'b0;
            exp_carry[3] = 1'b0;
            exp_carry[4] = 1'b0;
            exp_carry[5] = 1'b1;

            exp_segment[0] = 2'd0;
            exp_segment[1] = 2'd0;
            exp_segment[2] = 2'd0;
            exp_segment[3] = 2'd1;
            exp_segment[4] = 2'd1;
            exp_segment[5] = 2'd1;
        end
    endtask

    task automatic load_switch_0_to_1_to_0_expected;
        begin
            exp_data[0]  = 24'd12;
            exp_data[1]  = 24'd252;
            exp_data[2]  = 24'd994;
            exp_data[3]  = 24'd97042;
            exp_data[4]  = 24'd1780992;
            exp_data[5]  = 24'd71920;

            exp_carry[0] = 1'b0;
            exp_carry[1] = 1'b0;
            exp_carry[2] = 1'b0;
            exp_carry[3] = 1'b0;
            exp_carry[4] = 1'b0;
            exp_carry[5] = 1'b1;

            exp_segment[0] = 2'd0;
            exp_segment[1] = 2'd0;
            exp_segment[2] = 2'd1;
            exp_segment[3] = 2'd1;
            exp_segment[4] = 2'd2;
            exp_segment[5] = 2'd2;
        end
    endtask

    // 连续送入一整帧，输入位序固定为 MSB first。
    task automatic drive_frame_continuous(input logic [15:0] a, input logic [15:0] b);
        integer bit_idx;
        begin
            for (bit_idx = IN_BITS - 1; bit_idx >= 0; bit_idx = bit_idx - 1) begin
                @(negedge clk);
                in_ready = 1'b1;
                inA      = a[bit_idx];
                inB      = b[bit_idx];
            end
        end
    endtask

    // 在帧边界停住输入，便于切 mode。
    task automatic stop_input_stream;
        begin
            @(negedge clk);
            in_ready = 1'b0;
            inA      = 1'b0;
            inB      = 1'b0;
        end
    endtask

    // 插入若干空拍，仍保持输入空闲。
    task automatic idle_cycles(input integer n);
        integer gap_idx;
        begin
            in_ready = 1'b0;
            inA      = 1'b0;
            inB      = 1'b0;
            for (gap_idx = 0; gap_idx < n; gap_idx = gap_idx + 1) begin
                @(negedge clk);
            end
        end
    endtask

    task automatic set_mode_between_frames(input logic new_mode);
        begin
            mode = new_mode;
        end
    endtask

    // 复位保持 2 个周期，并检查 carry 已清零。
    task automatic do_reset(input logic reset_mode);
        begin
            rst_n    = 1'b0;
            mode     = reset_mode;
            in_ready = 1'b0;
            inA      = 1'b0;
            inB      = 1'b0;
            end_scenario();

            @(posedge clk);
            @(posedge clk);
            @(negedge clk);

            rst_n = 1'b1;

            @(negedge clk);
            if (carry !== 1'b0) begin
                failed = 1'b1;
`ifdef TB_DEBUG
                $display("DBG carry not cleared by reset");
`endif
            end
        end
    endtask

    task automatic check_result(input logic [23:0] actual_word, input logic actual_carry);
        integer result_idx;
        begin
            result_idx = got_count;

            if (result_idx >= exp_count) begin
                failed = 1'b1;
`ifdef TB_DEBUG
                $display("DBG extra result: got_count=%0d actual=%0d carry=%0b", result_idx, actual_word, actual_carry);
`endif
            end else begin
                if (actual_word !== exp_data[result_idx]) begin
                    failed = 1'b1;
`ifdef TB_DEBUG
                    $display("DBG data mismatch idx=%0d exp=%0d act=%0d", result_idx, exp_data[result_idx], actual_word);
`endif
                end

                if (actual_carry !== exp_carry[result_idx]) begin
                    failed = 1'b1;
`ifdef TB_DEBUG
                    $display("DBG carry mismatch idx=%0d exp=%0b act=%0b", result_idx, exp_carry[result_idx], actual_carry);
`endif
                end

                if ((result_idx < (exp_count - 1)) && (exp_segment[result_idx] != exp_segment[result_idx + 1])) begin
                    carry_clear_expected = 1'b1;
                end

                got_count = result_idx + 1;
            end
        end
    endtask

    // 等待当前场景的全部结果收齐。
    task automatic wait_for_all_results;
        integer cycle_cnt;
        begin
            cycle_cnt = 0;
            while ((got_count < exp_count) && !failed && (cycle_cnt < TIMEOUT_CYC)) begin
                @(negedge clk);
                cycle_cnt = cycle_cnt + 1;
            end

            if (got_count != exp_count) begin
                failed = 1'b1;
`ifdef TB_DEBUG
                $display("DBG timeout or missing results: got=%0d exp=%0d", got_count, exp_count);
`endif
            end

            if (capture_active) begin
                failed = 1'b1;
`ifdef TB_DEBUG
                $display("DBG capture still active when scenario finished");
`endif
            end
        end
    endtask

    // 监视器只跟随 out_ready 窗口，不依赖固定 latency。
    always @(negedge clk) begin
        if (!rst_n || !scenario_running) begin
            clear_capture_state();
            clear_carry_monitor_state();
        end else begin
            // 空闲窗口必须输出 0，避免串行尾巴残留。
            if ((out_ready === 1'b0) && (sum_out !== 1'b0)) begin
                failed = 1'b1;
`ifdef TB_DEBUG
                $display("DBG sum_out not zero while idle");
`endif
            end

            // carry 一旦拉高，就必须一直保持，直到 reset 或 mode 段切换清零。
            if (carry === 1'b1) begin
                carry_has_gone_high = 1'b1;
            end

            if (carry_clear_expected) begin
                if ((out_ready === 1'b0) && (carry === 1'b0)) begin
                    carry_has_gone_high = 1'b0;
                    carry_clear_expected = 1'b0;
                end else if (!capture_active && (out_ready === 1'b1) && carry_has_gone_high) begin
                    failed = 1'b1;
`ifdef TB_DEBUG
                    $display("DBG new mode output started before carry cleared");
`endif
                end
            end else if (carry_has_gone_high && (carry !== 1'b1)) begin
                failed = 1'b1;
`ifdef TB_DEBUG
                $display("DBG carry lost sticky behavior");
`endif
            end

            // 只有在 out_ready 有效窗口内才采样串行输出。
            if (!capture_active) begin
                if (out_ready === 1'b1) begin
                    capture_active = 1'b1;
                    captured_word  = {23'd0, sum_out};
                    captured_bits  = 1;
                end
            end else begin
                if (out_ready !== 1'b1) begin
                    failed = 1'b1;
`ifdef TB_DEBUG
                    $display("DBG out_ready dropped early after %0d bits", captured_bits);
`endif
                    clear_capture_state();
                end else begin
                    captured_word = {captured_word[22:0], sum_out};
                    captured_bits = captured_bits + 1;

                    if (captured_bits == OUT_BITS) begin
                        check_result(captured_word, carry);
                        clear_capture_state();
                    end
                end
            end
        end
    end

    initial begin
        failed           = 1'b0;
        scenario_running = 1'b0;
        capture_active   = 1'b0;
        captured_word    = '0;
        captured_bits    = 0;
        got_count        = 0;
        exp_count        = FRAME_COUNT;
        carry_has_gone_high = 1'b0;
        carry_clear_expected = 1'b0;
        rst_n            = 1'b1;
        mode             = 1'b0;
        in_ready         = 1'b0;
        inA              = 1'b0;
        inB              = 1'b0;

        // 场景 1：mode = 0，连续输入。
        load_mode0_expected();
        do_reset(1'b0);
        begin_scenario();
        for (idx = 0; idx < FRAME_COUNT; idx = idx + 1) begin
            drive_frame_continuous(input_a[idx], input_b[idx]);
        end
        stop_input_stream();
        wait_for_all_results();
        idle_cycles(2);

        // 场景 2：mode = 1，组间留 1 个空拍。
        load_mode1_expected();
        do_reset(1'b1);
        begin_scenario();
        for (idx = 0; idx < FRAME_COUNT; idx = idx + 1) begin
            drive_frame_continuous(input_a[idx], input_b[idx]);
            stop_input_stream();
            if (idx != FRAME_COUNT - 1) begin
                idle_cycles(1);
            end
        end
        wait_for_all_results();
        idle_cycles(2);

        // 场景 3：mode 0 -> 1，在第 3 帧后切换，只留 1 个空拍。
        load_switch_0_to_1_expected();
        do_reset(1'b0);
        begin_scenario();
        for (idx = 0; idx < 3; idx = idx + 1) begin
            drive_frame_continuous(input_a[idx], input_b[idx]);
        end
        stop_input_stream();
        set_mode_between_frames(1'b1);
        for (idx = 3; idx < FRAME_COUNT; idx = idx + 1) begin
            drive_frame_continuous(input_a[idx], input_b[idx]);
        end
        stop_input_stream();
        wait_for_all_results();
        idle_cycles(2);

        // 场景 4：mode 1 -> 0，在第 3 帧后切换，只留 1 个空拍。
        load_switch_1_to_0_expected();
        do_reset(1'b1);
        begin_scenario();
        for (idx = 0; idx < 3; idx = idx + 1) begin
            drive_frame_continuous(input_a[idx], input_b[idx]);
        end
        stop_input_stream();
        set_mode_between_frames(1'b0);
        for (idx = 3; idx < FRAME_COUNT; idx = idx + 1) begin
            drive_frame_continuous(input_a[idx], input_b[idx]);
        end
        stop_input_stream();
        wait_for_all_results();
        idle_cycles(2);

        // 场景 5：mode 0 -> 1 -> 0，在第 2 帧和第 4 帧后切换。
        load_switch_0_to_1_to_0_expected();
        do_reset(1'b0);
        begin_scenario();
        for (idx = 0; idx < 2; idx = idx + 1) begin
            drive_frame_continuous(input_a[idx], input_b[idx]);
        end
        stop_input_stream();
        set_mode_between_frames(1'b1);
        for (idx = 2; idx < 4; idx = idx + 1) begin
            drive_frame_continuous(input_a[idx], input_b[idx]);
        end
        stop_input_stream();
        set_mode_between_frames(1'b0);
        for (idx = 4; idx < FRAME_COUNT; idx = idx + 1) begin
            drive_frame_continuous(input_a[idx], input_b[idx]);
        end
        stop_input_stream();
        wait_for_all_results();
        idle_cycles(2);
        end_scenario();

        if (failed) begin
            $display("Simulation Failed");
        end else begin
            $display("Simulation Passed");
        end
        $finish(0);
    end

endmodule
