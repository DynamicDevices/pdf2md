# 7 Specifications

## 7.1 Absolute Maximum Ratings
over operating free-air temperature range (unless otherwise noted) (1) (2)

| Parameter                                                                | MIN    | MAX                 | UNIT |
| :----------------------------------------------------------------------- | :----- | :------------------ | :--- |
| VDDS, Supply voltage                                                     | –0.3   | 4.1                 | V    |
| Voltage on any digital pin (4)                                           | –0.3   | VDDS + 0.3, max 4.1 | V    |
| Voltage on crystal oscillator pins, X32K_Q1, X32K_Q2, X48M_N and X48M_P | –0.3   | VDDR + 0.3, max 2.25 | V    |
| V in, Voltage on ADC input                                               |        |                     |      |
| Voltage scaling enabled                                                  | –0.3   | VDDS                | V    |
| Voltage scaling disabled, internal reference                             | –0.3   | 1.49                | V    |
| Voltage scaling disabled, VDDS as reference                              | –0.3   | VDDS / 2.9          | V    |
| Input level, RF pins (RF_P and RF_N)                                     |        | 10                  | dBm  |
| T stg, Storage temperature                                               | –40    | 150                 | °C   |

(1) Stresses beyond those listed under Absolute Maximum Ratings may cause permanent damage to the device. These are stress ratings only, and functional operation of the device at these or any other conditions beyond those indicated under Recommended Operating Conditions is not implied. Exposure to absolute-maximum-rated conditions for extended periods may affect device reliability.
(2) All voltage values are with respect to ground, unless otherwise noted.
(3) VDDS_DCDC, VDDS2 and VDDS3 must be at the same potential as VDDS.
(4) Including analog capable DIOs.

## 7.2 ESD Ratings

| Parameter                                               | VALUE     | UNIT |
| :------------------------------------------------------ | :-------- | :--- |
| V ESD, Electrostatic discharge                          |           |      |
| Human body model (HBM), per ANSI/ESDA/JEDEC JS-001 (1)  |           |      |
| All pins                                                | ±2000     | V    |
| Charged device model (CDM), per ANSI/ESDA/JEDEC JS-002 (2) |           |      |
| All pins                                                | ±500      | V    |

(1) JEDEC document JEP155 states that 500-V HBM allows safe manufacturing with a standard ESD control process
(2) JEDEC document JEP157 states that 250-V CDM allows safe manufacturing with a standard ESD control process

## 7.3 Recommended Operating Conditions
over operating free-air temperature range (unless otherwise noted)

| Parameter                                                                      | MIN | MAX | UNIT |
| :----------------------------------------------------------------------------- | :-- | :-- | :--- |
| Operating ambient temperature (1) (3)                                          | –40 | 105 | °C   |
| Operating junction temperature (1) (3)                                         | –40 | 115 | °C   |
| Operating supply voltage (VDDS)                                                | 1.8 | 3.8 | V    |
| Operating supply voltage (VDDS), boost mode VDDR = 1.95 V, +14 dBm RF output power | 2.1 | 3.8 | V    |
| Rising supply voltage slew rate                                                | 0   | 100 | mV/µs |
| Falling supply voltage slew rate (2)                                           | 0   | 20  | mV/µs |

(1) Operation at or near maximum operating temperature for extended durations will result in a reduction in lifetime.
(2) For small coin-cell batteries, with high worst-case end-of-life equivalent source resistance, a 22-µF VDDS input capacitor must be used to ensure compliance with this slew rate.
(3) For thermal resistance characteristics refer to Section 7.8.