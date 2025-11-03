# 8 Detailed Description

## 8.1 Overview
Section 3.1 shows the core modules of the CC1312R7 device.

## 8.2 System CPU
The CC1312R7 SimpleLink™ Wireless MCU contains an Arm® Cortex®-M4F system CPU, which runs the application and the higher layers of radio protocol stacks.
The system CPU is the foundation of a high-performance, low-cost platform that meets the system requirements of minimal memory implementation, and low-power consumption, while delivering outstanding computational performance and exceptional system response to interrupts.
Its features include the following:

*   ARMv7-M architecture optimized for small-footprint embedded applications
*   Arm Thumb®-2 mixed 16- and 32-bit instruction set delivers the high performance expected of a 32-bit Arm core in a compact memory size
*   Fast code execution permits increased sleep mode time
*   Deterministic, high-performance interrupt handling for time-critical applications
*   Single-cycle multiply instruction and hardware divide
*   Hardware division and fast digital-signal-processing oriented multiply accumulate
*   Saturating arithmetic for signal processing
*   IEEE 754-compliant single-precision Floating Point Unit (FPU)
*   Memory Protection Unit (MPU) for safety-critical applications
*   Full debug with data matching for watchpoint generation
    *   Data Watchpoint and Trace Unit (DWT)
    *   JTAG Debug Access Port (DAP)
    *   Flash Patch and Breakpoint Unit (FPB)
*   Trace support reduces the number of pins required for debugging and tracing
    *   Instrumentation Trace Macrocell Unit (ITM)
    *   Trace Port Interface Unit (TPIU) with asynchronous serial wire output (SWO)
*   Optimized for single-cycle flash memory access
*   Tightly connected to 8-KB 4-way random replacement cache for minimal active power consumption and wait states
*   Ultra-low-power consumption with integrated sleep modes
*   48 MHz operation
*   1.25 DMIPS per MHz