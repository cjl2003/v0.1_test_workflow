module mac16 (
    input  logic clk,
    input  logic rst_n,
    input  logic mode,
    input  logic in_ready,
    input  logic inA,
    input  logic inB,
    output logic sum_out,
    output logic carry,
    output logic out_ready
);

    localparam int IN_BITS      = 16;
    localparam int OUT_BITS     = 24;
    localparam int FIFO_DEPTH   = 16;
    localparam int PTR_W        = $clog2(FIFO_DEPTH);
    localparam int COUNT_W      = $clog2(FIFO_DEPTH + 1);
    localparam int OUT_CNT_W    = $clog2(OUT_BITS + 1);

    localparam logic [PTR_W-1:0]   FIFO_LAST      = FIFO_DEPTH - 1;
    localparam logic [COUNT_W-1:0] FIFO_DEPTH_VAL = FIFO_DEPTH;
    localparam logic [OUT_CNT_W-1:0] OUT_BITS_VAL = OUT_BITS;

    typedef enum logic [1:0] {
        CTRL_RUN,
        CTRL_WAIT_DRAIN,
        CTRL_SWAP_MODE
    } ctrl_state_t;

    integer idx;

    // ============================================================
    // 1. 串行输入收帧
    // ============================================================
    logic [IN_BITS-1:0] inA_shift;
    logic [IN_BITS-1:0] inB_shift;
    logic [4:0]         in_bit_cnt;

    logic               frame_done;
    logic [IN_BITS-1:0] frame_a;
    logic [IN_BITS-1:0] frame_b;
    logic               frame_mode;

    // ============================================================
    // 2. 单一帧 FIFO
    //    每帧把 A/B/mode 一起存起来，后面只按 FIFO 头处理。
    // ============================================================
    logic [IN_BITS-1:0] frameA_fifo [0:FIFO_DEPTH-1];
    logic [IN_BITS-1:0] frameB_fifo [0:FIFO_DEPTH-1];
    logic               frameMode_fifo [0:FIFO_DEPTH-1];
    logic [PTR_W-1:0]   frame_wr_ptr;
    logic [PTR_W-1:0]   frame_rd_ptr;
    logic [COUNT_W-1:0] frame_count;

    logic               frame_head_valid;
    logic [IN_BITS-1:0] frame_head_a;
    logic [IN_BITS-1:0] frame_head_b;
    logic               frame_head_mode;
    logic               frame_mode_mismatch;
    logic               frame_can_accept;
    logic               frame_push;
    logic               do_process_head;

    // ============================================================
    // 3. mode 相关算术状态
    //    mode0 记住上一帧乘积，mode1 记住低 24 位累加值。
    // ============================================================
    logic        active_mode;
    logic        history_valid;
    logic [31:0] mode0_prev_product;
    logic [23:0] mode1_accum_low24;
    logic        carry_sticky;

    logic [31:0] raw_product;
    logic [32:0] mode0_sum_ext;
    logic [24:0] mode1_sum_ext;
    logic [23:0] calc_result_low24;
    logic        calc_overflow;

    // ============================================================
    // 4. mode 切换控制
    //    只看 FIFO 头的 mode，不再直接看外部 mode 引脚做即时切换。
    // ============================================================
    ctrl_state_t ctrl_state;
    logic        old_outputs_drained;

    // ============================================================
    // 5. 结果 FIFO + 串行输出
    // ============================================================
    logic [OUT_BITS-1:0] result_fifo [0:FIFO_DEPTH-1];
    logic                result_carry_fifo [0:FIFO_DEPTH-1];
    logic [PTR_W-1:0]    result_wr_ptr;
    logic [PTR_W-1:0]    result_rd_ptr;
    logic [COUNT_W-1:0]  result_count;

    logic [OUT_BITS-1:0] out_shift_reg;
    logic [OUT_CNT_W-1:0] out_bits_left;
    logic                 out_busy;
    logic                 result_pop_load;
    logic                 result_can_accept;

    function automatic logic [PTR_W-1:0] ptr_inc(input logic [PTR_W-1:0] ptr);
        if (ptr == FIFO_LAST) begin
            ptr_inc = '0;
        end else begin
            ptr_inc = ptr + 1'b1;
        end
    endfunction

    // 空闲时 sum_out 必须为 0，out_ready 只在输出窗口拉高。
    assign sum_out   = out_busy ? out_shift_reg[OUT_BITS-1] : 1'b0;
    assign out_ready = out_busy;
    assign carry     = carry_sticky;

    // 先把本周期的组合动作算清楚，时序块只负责更新寄存器。
    always @* begin
        frame_head_valid = (frame_count != '0);
        frame_head_a     = '0;
        frame_head_b     = '0;
        frame_head_mode  = active_mode;

        if (frame_head_valid) begin
            frame_head_a    = frameA_fifo[frame_rd_ptr];
            frame_head_b    = frameB_fifo[frame_rd_ptr];
            frame_head_mode = frameMode_fifo[frame_rd_ptr];
        end

        old_outputs_drained = (!out_busy) && (result_count == '0);

        result_pop_load  = (!out_busy) && (result_count != '0);
        result_can_accept = (result_count != FIFO_DEPTH_VAL) || result_pop_load;

        frame_mode_mismatch = frame_head_valid && (frame_head_mode != active_mode);
        do_process_head     = (ctrl_state == CTRL_RUN) &&
                              frame_head_valid &&
                              !frame_mode_mismatch &&
                              result_can_accept;

        frame_can_accept = (frame_count != FIFO_DEPTH_VAL) || do_process_head;
        frame_push       = frame_done && frame_can_accept;

        raw_product      = '0;
        mode0_sum_ext    = '0;
        mode1_sum_ext    = '0;
        calc_result_low24 = '0;
        calc_overflow     = 1'b0;

        if (do_process_head) begin
            raw_product   = {16'd0, frame_head_a} * {16'd0, frame_head_b};
            mode0_sum_ext = {1'b0, mode0_prev_product} + {1'b0, raw_product};
            mode1_sum_ext = {1'b0, mode1_accum_low24} + {1'b0, raw_product[OUT_BITS-1:0]};

            if (!history_valid) begin
                calc_result_low24 = raw_product[OUT_BITS-1:0];
                calc_overflow     = |raw_product[31:OUT_BITS];
            end else if (!active_mode) begin
                calc_result_low24 = mode0_sum_ext[OUT_BITS-1:0];
                calc_overflow     = |mode0_sum_ext[32:OUT_BITS];
            end else begin
                calc_result_low24 = mode1_sum_ext[OUT_BITS-1:0];
                calc_overflow     = (|raw_product[31:OUT_BITS]) || mode1_sum_ext[24];
            end
        end
    end

    // ------------------------------
    // 1. 串行输入收帧
    // ------------------------------
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            inA_shift  <= '0;
            inB_shift  <= '0;
            in_bit_cnt <= '0;
            frame_done <= 1'b0;
            frame_a    <= '0;
            frame_b    <= '0;
            frame_mode <= 1'b0;
        end else begin
            frame_done <= 1'b0;

            if (in_ready) begin
                if (in_bit_cnt == '0) begin
                    frame_mode <= mode;
                end

                if (in_bit_cnt == IN_BITS - 1) begin
                    frame_done <= 1'b1;
                    frame_a    <= {inA_shift[IN_BITS-2:0], inA};
                    frame_b    <= {inB_shift[IN_BITS-2:0], inB};

                    inA_shift  <= '0;
                    inB_shift  <= '0;
                    in_bit_cnt <= '0;
                end else begin
                    inA_shift  <= {inA_shift[IN_BITS-2:0], inA};
                    inB_shift  <= {inB_shift[IN_BITS-2:0], inB};
                    in_bit_cnt <= in_bit_cnt + 1'b1;
                end
            end
        end
    end

    // ------------------------------
    // 2/3/4/5. 主控制、算术、结果输出
    // ------------------------------
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            active_mode        <= 1'b0;
            history_valid      <= 1'b0;
            mode0_prev_product <= '0;
            mode1_accum_low24  <= '0;
            carry_sticky       <= 1'b0;

            ctrl_state         <= CTRL_RUN;

            frame_wr_ptr       <= '0;
            frame_rd_ptr       <= '0;
            frame_count        <= '0;

            result_wr_ptr      <= '0;
            result_rd_ptr      <= '0;
            result_count       <= '0;

            out_shift_reg      <= '0;
            out_bits_left      <= '0;
            out_busy           <= 1'b0;

            for (idx = 0; idx < FIFO_DEPTH; idx = idx + 1) begin
                frameA_fifo[idx]      <= '0;
                frameB_fifo[idx]      <= '0;
                frameMode_fifo[idx]   <= 1'b0;
                result_fifo[idx]      <= '0;
                result_carry_fifo[idx] <= 1'b0;
            end
        end else begin
            // --------------------------
            // 4. mode 切换状态机
            // --------------------------
            case (ctrl_state)
                CTRL_RUN: begin
                    if (frame_mode_mismatch) begin
                        ctrl_state <= CTRL_WAIT_DRAIN;
                    end
                end

                CTRL_WAIT_DRAIN: begin
                    if (old_outputs_drained) begin
                        ctrl_state <= CTRL_SWAP_MODE;
                    end
                end

                CTRL_SWAP_MODE: begin
                    ctrl_state         <= CTRL_RUN;
                    active_mode        <= frame_head_mode;
                    history_valid      <= 1'b0;
                    mode0_prev_product <= '0;
                    mode1_accum_low24  <= '0;
                    carry_sticky       <= 1'b0;
                end

                default: begin
                    ctrl_state <= CTRL_RUN;
                end
            endcase

            // --------------------------
            // 2. 单一帧 FIFO
            // --------------------------
            if (frame_push) begin
                frameA_fifo[frame_wr_ptr]    <= frame_a;
                frameB_fifo[frame_wr_ptr]    <= frame_b;
                frameMode_fifo[frame_wr_ptr] <= frame_mode;
                frame_wr_ptr                 <= ptr_inc(frame_wr_ptr);
            end

            if (do_process_head) begin
                frame_rd_ptr <= ptr_inc(frame_rd_ptr);
            end

            case ({frame_push, do_process_head})
                2'b10: frame_count <= frame_count + 1'b1;
                2'b01: frame_count <= frame_count - 1'b1;
                default: frame_count <= frame_count;
            endcase

            // --------------------------
            // 3. 算术状态
            // --------------------------
            if (do_process_head) begin
                history_valid <= 1'b1;

                if (!active_mode) begin
                    mode0_prev_product <= raw_product;
                end else begin
                    mode1_accum_low24 <= calc_result_low24;
                end
            end

            // --------------------------
            // 5. 结果 FIFO + 串行输出
            // --------------------------
            if (do_process_head) begin
                result_fifo[result_wr_ptr]       <= calc_result_low24;
                result_carry_fifo[result_wr_ptr] <= calc_overflow;
                result_wr_ptr                    <= ptr_inc(result_wr_ptr);
            end

            if (result_pop_load) begin
                out_shift_reg <= result_fifo[result_rd_ptr];
                out_bits_left <= OUT_BITS_VAL;
                out_busy      <= 1'b1;
                result_rd_ptr <= ptr_inc(result_rd_ptr);

                if (result_carry_fifo[result_rd_ptr]) begin
                    carry_sticky <= 1'b1;
                end
            end else if (out_busy) begin
                if (out_bits_left == 1) begin
                    out_shift_reg <= '0;
                    out_bits_left <= '0;
                    out_busy      <= 1'b0;
                end else begin
                    out_shift_reg <= {out_shift_reg[OUT_BITS-2:0], 1'b0};
                    out_bits_left <= out_bits_left - 1'b1;
                    out_busy      <= 1'b1;
                end
            end

            case ({do_process_head, result_pop_load})
                2'b10: result_count <= result_count + 1'b1;
                2'b01: result_count <= result_count - 1'b1;
                default: result_count <= result_count;
            endcase
        end
    end

endmodule
