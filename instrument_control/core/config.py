
"""Configuration and constants for the instrument control system."""

# Physical constants
R = 62.363577  # L Torr K-1 mol-1
t_mfld = 298  # K, manifold temperature

# Manifold volumes (in liters)
v_vessel = 0.0119913  # Calibrated vessel
v_valve = 0.000152    # Valve stem volume
v_cell = 0.03381      # Excludes valve stem
v_m1m2 = 0.078862     # m1+m2
v_m1m2m3 = 0.11116    # m1+m2+m3
v_50tube = 0.05643    # 50 mL tube (includes valve stem)
v_flask = 1.004       # Flask (not measured as of 09/24/2024)
v_m3 = v_m1m2m3 - v_m1m2 - v_valve
v_tot = v_m1m2m3 + v_cell + v_valve + v_50tube

# Experiment parameters
notebook = 'nn1120-3'
metal = "pd"
support = "ceo2"
mass = 0.0164  # g (8 mg quartz wool)
metal_load = 0.04983  # wt.%
support_sa = 54  # Surface area in m²/g
metal_density = (metal_load / 100) * (1 / 106.42) * (6.023e23) * (1 / support_sa) * (1e-9**2)

# Device IDs
chiller_id = "80068F39DE57BDF8D6EA6F2AB145251E223AF901"
variac_id = "80068C02EA20EFE6A7149420FAA20DB5223A54AA"
variac_id_vsl = "8006CF042D478C8A62FE5B07A53B29B8223A2135" # 50 mL tube

# pnnl-devices network password
# HJ^5%zy5WYXB#CbTv%TFZcJNM