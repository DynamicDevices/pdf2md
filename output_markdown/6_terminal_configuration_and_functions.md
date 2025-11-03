# 6 Terminal Configuration and Functions

## 6.1 Pin Diagram – RGZ Package (Top View)


![Figure 6-1: RGZ (7-mm × 7-mm)
 Pinout, 0.5-mm Pitch (Top View)](./images/page_6_diagram.png)

**Figure 6-1: RGZ (7-mm × 7-mm) Pinout, 0.5-mm Pitch (Top View)**

This diagram shows the top view of the 48-pin RGZ QFN package for the CC1312R7 device. The pins are numbered counter-clockwise starting from the top-left corner.

*   **Left Side (Pins 1-12):**
    *   1: RF_P
    *   2: RF_N
    *   3: RX_TX
    *   4: X32K_Q1
    *   5: X32K_Q2
    *   6: DIO_1
    *   7: DIO_2
    *   8: DIO_3
    *   9: DIO_4
    *   10: DIO_5
    *   11: DIO_6
    *   12: DIO_7

*   **Bottom Side (Pins 13-24):**
    *   13: VDDS2
    *   14: DIO_8
    *   15: DIO_9
    *   16: DIO_10
    *   17: DIO_11
    *   18: DIO_12
    *   19: DIO_13
    *   20: DIO_14
    *   21: DIO_15
    *   22: VDDS3
    *   23: DCOUPL
    *   24: JTAG_TMSC

*   **Right Side (Pins 25-36):**
    *   25: JTAG_TCKC
    *   26: DIO_16
    *   27: DIO_17
    *   28: DIO_18
    *   29: DIO_19
    *   30: DIO_20
    *   31: DIO_21
    *   32: DIO_22
    *   33: DCDC_SW
    *   34: VDDS_DCDC
    *   35: RESET_N
    *   36: DIO_23

*   **Top Side (Pins 37-48):**
    *   37: DIO_24
    *   38: DIO_25
    *   39: DIO_26
    *   40: DIO_27
    *   41: DIO_28
    *   42: DIO_29
    *   43: DIO_30
    *   44: VDDS
    *   45: VDDR
    *   46: X48M_N
    *   47: X48M_P
    *   48: VDDR_RF

The following I/O pins marked in Figure 6-1 in **bold** have high-drive capabilities:
*   Pin 10, DIO_5
*   Pin 11, DIO_6
*   Pin 12, DIO_7
*   Pin 24, JTAG_TMSC
*   Pin 26, DIO_16
*   Pin 27, DIO_17

The following I/O pins marked in Figure 6-1 in *italics* have analog capabilities:
*   Pin 36, DIO_23
*   Pin 37, DIO_24
*   Pin 38, DIO_25
*   Pin 39, DIO_26
*   Pin 40, DIO_27
*   Pin 41, DIO_28
*   Pin 42, DIO_29
*   Pin 43, DIO_30