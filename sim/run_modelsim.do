transcript on

set root_dir [file normalize [pwd]]
set work_dir [file join $root_dir sim modelsim_work]

if {[file exists $work_dir]} {
    file delete -force $work_dir
}

vlib $work_dir
vmap work $work_dir

vlog -sv [file join $root_dir rtl mac16.sv] [file join $root_dir tb tb_mac16.sv]
vsim -c work.tb_mac16
run -all
quit -f
