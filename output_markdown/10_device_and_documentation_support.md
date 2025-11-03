# 10 Device and Documentation Support

TI offers an extensive line of development tools. Tools and software to evaluate the performance of the device, generate code, and develop solutions are listed as follows.

## 10.1 Device Nomenclature

To designate the stages in the product development cycle, TI assigns prefixes to all part numbers and/or date-code. Each device has one of three prefixes/identifications: X, P, or null (no prefix) (for example, XCC1312R7 is in preview; therefore, an X prefix/identification is assigned).

Device development evolutionary flow:

*   **X**: Experimental device that is not necessarily representative of the final device's electrical specifications and may not use production assembly flow.
*   **P**: Prototype device that is not necessarily the final silicon die and may not necessarily meet final electrical specifications.
*   **null** (no prefix): Production version of the silicon die that is fully qualified.

Production devices have been characterized fully, and the quality and reliability of the device have been demonstrated fully. TI's standard warranty applies.

Predictions show that prototype devices (X or P) have a greater failure rate than the standard production devices. Texas Instruments recommends that these devices not be used in any production system because their expected end-use failure rate still is undefined. Only qualified production devices are to be used.

TI device nomenclature also includes a suffix with the device family name. This suffix indicates the package type (for example, `RGZ`).

For orderable part numbers of `CC1312R7` devices in the RGZ (7-mm x 7-mm) package type, see the *Package Option Addendum* of this document, the Device Information in [Section 3](#), the TI website (www.ti.com), or contact your TI sales representative.

![Figure 10-1: Device Nomenclature](./images/page_45.png)

**Figure 10-1: Device Nomenclature**
This figure illustrates the structure of a Texas Instruments SimpleLink™ Ultra-Low-Power Wireless MCU part number, using `CC1312R74T0RGZR` as an example. Each segment of the part number denotes specific device characteristics:

*   **Prefix (Implicit before CC1312)**:
    *   `X`: Experimental device
    *   `Blank` (no prefix): Qualified device
*   **CC1312**: Represents the SimpleLink™ Ultra-Low-Power Wireless MCU device family.
*   **R** (after CC1312): Indicates the Configuration.
    *   `R`: Regular
    *   `P`: +20 dBm PA included
*   **7**: Represents the Flash Size.
    *   `7`: 704 kB
*   **4**: Represents the SRAM Size.
    *   `4`: 144kB
*   **T**: Indicates the Temperature Range.
    *   `T`: 105 °C Ambient
*   **0**: Represents the Product Revision (the example shows '0', which might indicate the initial revision or a placeholder).
*   **RGZ**: Indicates the Package Type.
    *   `RGZ`: 48-pin VQFN (Very Thin Quad Flatpack No-Lead)
*   **R** (at the end): An orderable part number suffix.
    *   `R`: Large Reel

## 10.2 Tools and Software

The CC1312R7 device is supported by a variety of software and hardware development tools.

### Development Kit

**CC1312R LaunchPad™ Development Kit**
The CC1312R7 LaunchPad™ Development Kit enables development of high-performance Sub-1 GHz wireless applications that benefit from low-power operation. The kit features the CC1312R7 Sub-1 GHz SimpleLink Wireless MCU. The kit works with the LaunchPad ecosystem, easily enabling additional functionality like sensors, display, and more.