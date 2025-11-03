# 9 Application, Implementation, and Layout

Note
Information in the following Applications section is not part of the TI component specification, and TI does not warrant its accuracy or completeness. TI's customers are responsible for determining suitability of components for their purposes. Customers should validate and test their design implementation to confirm system functionality.

For general design guidelines and hardware configuration guidelines, refer to CC13xx/CC26xx Hardware Configuration and PCB Design Considerations Application Report.

## 9.1 Reference Designs

The following reference designs should be followed closely when implementing designs using the CC1312R7 device.
Special attention must be paid to RF component placement, decoupling capacitors and DCDC regulator components, as well as ground connections for all of these.

**CC1312-R7EM-XD7793 Design Files**
The differential CC1312-R7EM-XD7793 reference design provides schematic, layout and production files for the characterization board used for deriving the performance number found in this document.

**LP-CC1312R7 Design Files**
The CC1312R7 LaunchPad Design Files contain detailed schematics and layouts to build application specific boards using the CC1312R7 device.

**LP-CC1352P7-4 Design Files**
Detailed schematics and layouts for the multi-band CC1352P7 LaunchPad evaluation board featuring 2.4 GHz RF matching optimized for 10 dBm operation on the 20 dBm PA output and up to 13 dBm TX power at 433 MHz. For evaluation of 20 dBm operation at 2.4 GHz the BOM can be modified as described in the schematics available in the Design Files.
For CC1312R7, the sub-1 GHz RF circuitry can be used for 433 MHz operation while the 2.4 GHz and 20 dBm RF circuitry can be disregarded.

**Sub-1 GHz and 2.4 GHz Antenna Kit for LaunchPad™ Development Kit and SensorTag**
The antenna kit allows real-life testing to identify the optimal antenna for your application. The antenna kit includes 16 antennas for frequencies from 169 MHz to 2.4 GHz, including:
* PCB antennas
* Helical antennas
* Chip antennas
* Dual-band antennas for 868 MHz and 915 MHz combined with 2.4 GHz

The antenna kit includes a JSC cable to connect to the Wireless MCU LaunchPad Development Kits and SensorTags.

## 9.2 Junction Temperature Calculation

This section shows the different techniques for calculating the junction temperature under various operating conditions. For more details, see Semiconductor and IC Package Thermal Metrics.

There are three recommended ways to derive the junction temperature from other measured temperatures:

1. From package temperature:
   `T J = ψ JT × P + T case` (1)
2. From board temperature:
   `T J = ψ JB × P + T board` (2)