# MIGRATION.md — Hardware Validation Checklist

This document provides a step-by-step checklist for validating the new v2 architecture against physical hardware. Follow each section in order.

## Pre-Validation Setup

### 1. Environment Preparation
- [ ] Switch to physical workstation with hardware access
- [ ] Ensure all serial devices are connected:
  - MKS pressure gauge (COM8)
  - Watlow IR temperature controller (COM6)
  - Extrel mass spectrometer (COM5)
- [ ] Ensure NI USB-6009 is connected for actuator control
- [ ] Ensure network connection to OPUS spectrometer (130.20.216.127:5555)
- [ ] Verify Kasa smart plugs are online (chiller, variac, variac_vsl)

### 2. Configuration Verification
- [ ] Verify `config/devices.yaml` has correct COM ports
- [ ] Verify `config/sample.yaml` has current sample information
- [ ] Verify `config/paths.yaml` has correct data directories
- [ ] Verify `config/system.yaml` has correct physical constants

### 3. Code Preparation
- [ ] Replace `main.py` with `main_v2.py`:
  ```bash
  cp main.py main_legacy.py
  cp main_v2.py main.py
  ```
- [ ] Or run v2 directly: `python main_v2.py`

## Hardware Connection Tests

### 4. Basic Device Communication
- [ ] Test MKS pressure gauge connection:
  ```python
  from src.hardware.connections import DeviceManager
  from src.config_loader import load_config
  config = load_config()
  devices = DeviceManager(config.hardware)
  devices.connect()
  print(devices.pressure.read())  # Should return pressure reading
  ```
- [ ] Test Watlow temperature controller:
  ```python
  print(devices.temperature.read_temperature())  # Should return temperature
  ```
- [ ] Test Extrel mass spectrometer:
  ```python
  print(devices.mass_spec.read_registers(address=1, count=2))  # Should return register values
  ```
- [ ] Test NI USB-6009 analog outputs:
  ```python
  devices.analog_io.write("v16", 1.0)  # Should close valve (1.0V = closed)
  ```
- [ ] Test OPUS spectrometer connection:
  ```python
  devices.spectrometer.connect("tcp://130.20.216.127:5555")
  ```

### 5. Safety System Verification
- [ ] Verify valve default state is closed (1.0V):
  ```python
  # All actuators should be at 1.0V (closed)
  for actuator_id in config.hardware.actuator.device_map:
      devices.analog_io.write(actuator_id, 1.0)
  ```
- [ ] Verify TurboPump safety check:
  - Attempt to open TurboPump without roughing first
  - Should fail with safety error
- [ ] Verify MassSpec safety check:
  - Attempt to open MassSpec with high cell pressure
  - Should fail with safety error

## Experiment Sequence Validation

### 6. Adsorption Experiment Validation
Run the following sequence and verify each step:

#### 6.1 Clean Surface Sequence
```python
from src.experiments.adsorption_v2 import AdsorptionExperiment
from src.experiments.session import ExperimentSession

# Initialize experiment
session = ExperimentSession(sample=config.sample, volumes=config.system, paths=config.paths)
ads_exp = AdsorptionExperiment(session=session, devices=devices, gas_controller=gas_controller, temp=temp_controller, spec=spec_controller)

# Run clean surface sequence
ads_exp.chiller_variac_state(chiller_cmd=True, variac_cmd=True, variac_vsl_cmd=True)
ads_exp.heat_under_evacuation(pumpType='RoughPump', targetTemp=400, holdTime=0.0, rampRate=20)
ads_exp.heat_under_evacuation(pumpType='TurboPump', targetTemp=400, holdTime=2.0, rampRate=0)
```

**Verify:**
- [ ] Chiller turns on
- [ ] Variac turns on
- [ ] RoughPump valve opens
- [ ] Temperature ramps to 400°C at 20°C/min
- [ ] Pressure decreases during evacuation
- [ ] TurboPump valve opens after roughing
- [ ] Temperature holds at 400°C for 2 hours

#### 6.2 Oxidize Surface Sequence
```python
ads_exp.supply_gas_to_mfld(gas='O2', targetPressure=5.0)
ads_exp.introduce_pretreatment_gas_to_cell(targetTemp=500, holdTime=2)
ads_exp.heat_under_evacuation(pumpType='TurboPump', targetTemp=500, holdTime=0.5, rampRate=0)
```

**Verify:**
- [ ] O2 valve opens
- [ ] Manifold pressure increases to calculated value
- [ ] Cell pressure increases after gas admission
- [ ] Temperature ramps to 500°C
- [ ] Temperature holds for 2 hours
- [ ] Pressure stabilizes during hold
- [ ] Evacuation removes O2 after pretreatment

#### 6.3 Adsorption Monitoring Sequence
```python
ads_exp.cool_cell(targetTemp=45, holdTime=0, variac_cmd=False)
ads_exp.chiller_variac_state(chiller_cmd=False, variac_cmd=False, variac_vsl_cmd=False)
ads_exp.supply_gas_to_mfld(gas='13CO', targetPressure=1.0)
ads_exp.acquire_spectra(repeat=[10,5,15,30], delay=[60,300,600,1800], all_fileids=True, do_bckg=True, do_fit=True)
```

**Verify:**
- [ ] Temperature cools to 45°C
- [ ] Chiller turns off
- [ ] 13CO valve opens
- [ ] Manifold pressure increases to calculated value
- [ ] Cell pressure increases after gas admission
- [ ] OPUS acquires background spectrum
- [ ] OPUS acquires spectra at specified intervals
- [ ] Pressure log file is created
- [ ] Temperature log file is created
- [ ] Data files are copied to share drive

### 7. Isotopic Exchange Calibration Validation
Run the following sequence and verify each step:

#### 7.1 Isotopic Exchange Main Sequence
```python
from src.experiments.isotopic_exchange_v2 import IsotopicExchangeCalibration

iso_exp = IsotopicExchangeCalibration(session=session, devices=devices, gas_controller=gas_controller, temp=temp_controller, spec=spec_controller)

# Run isotopic exchange
iso_exp.isoX_calib_main(xchgTime=[2,4,6,8,9,10,11,12,14,16], sleepTime=2)
```

**Verify:**
- [ ] Each exchange cycle runs correctly
- [ ] Pressure stabilizes before each measurement
- [ ] OPUS acquires spectra at correct times
- [ ] 13CO is delivered between cycles
- [ ] Sleep intervals are respected
- [ ] All data files are created

#### 7.2 Mass Spectrometer Calibration
```python
iso_exp.massSpec_calibration(targets=[2e-10, 4e-10, 6e-10, 1.5e-9, 5e-9])
```

**Verify:**
- [ ] Dilution calculations are correct
- [ ] Pressure measurements match expected values
- [ ] Calibration data is logged to CSV
- [ ] Final calibration file is copied to share drive

## Data Validation

### 8. File Output Verification
- [ ] Verify pressure log files are created with correct format:
  - Columns: timestamp, p_mfld, p_cell, t_cell, amount_adsorbed, conversion
  - Data is logged at 5-second intervals
- [ ] Verify temperature log files are created:
  - Columns: timestamp, temperature
  - Data is logged at 5-second intervals
- [ ] Verify OPUS data files are created:
  - Files are saved in correct directory
  - File naming follows convention
- [ ] Verify README files are created:
  - Contains experiment parameters
  - Contains sample information
- [ ] Verify files are copied to share drive:
  - Peak fit files in `X:\peakFit`
  - Pressure data in `X:\pressureData`
  - MS calibrations in `X:\ms_calibrations`

### 9. Data Integrity Verification
- [ ] Pressure readings are within expected ranges:
  - Manifold pressure: 0-10 Torr
  - Cell pressure: 0-10 Torr
- [ ] Temperature readings are within expected ranges:
  - Room temperature to 700°C
- [ ] Timing is accurate:
  - Hold times match specified values
  - Ramp rates match specified values
  - Sleep intervals are correct

## Error Handling Validation

### 10. Error Condition Tests
- [ ] Test serial communication failure:
  - Disconnect MKS pressure gauge
  - Attempt to read pressure
  - Should handle error gracefully
- [ ] Test OPUS communication timeout:
  - Disconnect from OPUS spectrometer
  - Attempt to acquire spectra
  - Should timeout and reconnect
- [ ] Test safety limit violation:
  - Attempt to open TurboPump with high manifold pressure
  - Should fail with safety error
- [ ] Test file system errors:
  - Attempt to write to read-only directory
  - Should handle error gracefully

## Performance Validation

### 11. Timing Verification
- [ ] Valve operations complete within 5 seconds
- [ ] Pressure readings complete within 2 seconds
- [ ] Temperature readings complete within 2 seconds
- [ ] OPUS commands complete within 10 seconds
- [ ] Gas delivery dithering works correctly

### 12. Resource Usage
- [ ] Memory usage is stable during long experiments
- [ ] CPU usage is reasonable during idle periods
- [ ] File handles are properly closed
- [ ] Serial connections are properly managed

## Final Validation

### 13. Full Experiment Run
- [ ] Run complete adsorption experiment end-to-end
- [ ] Run complete isotopic exchange calibration end-to-end
- [ ] Verify all data files are created correctly
- [ ] Verify no exceptions or errors occur
- [ ] Verify experiment results are physically reasonable

### 14. Comparison with Legacy
- [ ] Run same experiment with legacy `main.py`
- [ ] Compare pressure readings (should match within 0.01 Torr)
- [ ] Compare temperature readings (should match within 1°C)
- [ ] Compare timing (should match within 1 second)
- [ ] Compare data file formats (should be identical)

## Post-Validation

### 15. Cleanup
- [ ] If validation successful:
  - Delete legacy packages: `core/`, `devices/`, `operations/`, `utils/`
  - Delete legacy experiment files: `adsorption.py`, `isotopic_exchange.py`, `parameters.py`
  - Rename v2 files to final names:
    - `adsorption_v2.py` → `adsorption.py`
    - `isotopic_exchange_v2.py` → `isotopic_exchange.py`
    - `main_v2.py` → `main.py`
  - Update imports in all files
  - Update documentation
- [ ] If validation fails:
  - Document the failure in `docs/validation_issues.md`
  - Fix the issue in new code
  - Re-run validation from failed step
  - Do not delete legacy code until all issues are resolved

### 16. Documentation Update
- [ ] Update `README.md` with new architecture information
- [ ] Update `AGENTS.md` files with new dependencies
- [ ] Update `docs/directory_structure.md` to remove legacy markers
- [ ] Create `docs/architecture.md` explaining new design

## Troubleshooting

### Common Issues
1. **Serial connection failures**: Check COM ports in `devices.yaml`
2. **OPUS timeout**: Check network connection to spectrometer
3. **Safety check failures**: Verify pressure readings are accurate
4. **File permission errors**: Check directory permissions
5. **Timing issues**: Verify system clock is accurate

### Debug Commands
```python
# Enable debug logging
import logging
logging.basicConfig(level=logging.DEBUG)

# Check device connections
devices.connect()
print(f"Pressure: {devices.pressure.read()}")
print(f"Temperature: {devices.temperature.read_temperature()}")

# Check configuration
config = load_config()
print(f"COM ports: {config.hardware.mks.port}, {config.hardware.watlow_ir.port}")
```

## Validation Sign-off

- [ ] All hardware connection tests pass
- [ ] All safety system tests pass
- [ ] All experiment sequences run without errors
- [ ] All data files are created correctly
- [ ] Performance meets requirements
- [ ] Results match legacy system within tolerance

**Validated by:** _________________ **Date:** _________

**Notes:**
_______________________________________________________________
_______________________________________________________________
