
# introduced gases
p_co_m1m2m3_50tube = 0.304 # torr

p_co_m1m2 =  0.0  # torr
p_co_m1m2m3 = 0.0  # torr
p_co_m1m2_50tube = 0.089  # torr
p_co_m3 = 1.162
p_co2_50tube = 0.0  # torr
p_o2_m3 = 0.0 # torr
p_h2_m3 = 0.0
T_cell = 298  # K

# # pre-adsorbed gases
# p_h2o_m1m2m3_i = 0.495  # torr
# p_h2o_tot_f = 0.440 # torr


# manifold volumes
v_valve = 0.000152  # L
v_cell = 0.03381  # L, excludes valve stem
v_m1m2 = 0.078862  # m1+m2 (L)
v_m1m2m3 = 0.11116  # m1+m2+m3 (L)
v_50tube = 0.05643  # 50 mL tube (L), includes valve stem
v_flask = 1.004  # L, not measured as of 09/24/2024
v_m3 = v_m1m2m3 - v_m1m2 - v_valve 
v_tot = v_m1m2m3 + v_cell + v_valve + v_50tube

R = 62.363577  # L Torr K-1 mol-1
T = 298  # K


# calculated values
n_co_m1m2m3_50tube_i = (p_co_m1m2m3_50tube * (v_m1m2m3 + v_50tube)) / (R*T)
p_calc_co_cell = (p_co_m1m2m3_50tube * (v_m1m2m3 + v_50tube)) / (v_tot)
n_calc_co_cell = (p_calc_co_cell * v_tot) / (R*T)


# # calculated values with flask
# n_co_m1m2m3_50tube_i = (p_co_m1m2m3_50tube * (v_m1m2m3 + v_50tube + v_flask)) / (R*T)
# p_calc_co_cell = (p_co_m1m2m3_50tube * (v_m1m2m3 + v_50tube + v_flask)) / (v_tot + v_flask)
# n_calc_co_cell = (p_calc_co_cell * v_tot) / (R*T)

# n_co_m1m2m3_50tube_i = (p_co_m1m2m3_50tube * (v_m1m2m3 + v_50tube)) / (R*T)
# p_calc_co_cell = (p_co_m1m2m3_50tube * (v_m1m2m3 + v_50tube)) / (v_tot)
# n_calc_co_cell = (p_calc_co_cell * v_tot) / (R*T)

# n_co_m1m2_50tube_i = (p_co_m1m2_50tube * (v_m1m2 + v_50tube)) / (R*T)
# p_calc_co_cell = (p_co_m1m2_50tube * (v_m1m2 + v_50tube)) / (v_tot)
# n_calc_co_cell = (p_calc_co_cell * v_tot) / (R*T)

# n_co_m3_i = (p_co_m3 * (v_m3)) / (R*T)
# p_calc_13co_cell = (p_co_m3 * (v_m3)) / (v_tot)
# n_calc_13co_cell = (p_calc_13co_cell * v_tot) / (R*T)

# # co-adsorbate calculations
# n_co_m1m2_i = (p_co_m1m2 * (v_m1m2)) / (R*T)
# p_calc_co_cell = (p_co_m1m2 * (v_m1m2)) / (v_tot)
# n_calc_co_cell = (p_calc_co_cell * v_tot) / (R*T)

# n_co_m1m2m3_i = (p_co_m1m2m3 * (v_m1m2m3)) / (R*T)
# p_calc_co_cell = (p_co_m1m2m3 * (v_m1m2m3)) / (v_tot)
# n_calc_co_cell = (p_calc_co_cell * v_tot) / (R*T)

# n_co2_50tube_i = (p_co2_50tube * (v_50tube - v_valve)) / (R*T) # check v_valve calcs again
# p_calc_co2_cell = (p_co2_50tube * (v_50tube - v_valve)) / (v_tot)
# n_calc_co2_cell = (p_calc_co2_cell * v_tot) / (R*T)

# n_o2_m3_i = (p_o2_m3 * v_m3) / (R*T)
# p_calc_o2_cell = (p_o2_m3 * v_m3) / (v_tot)
# n_calc_o2_cell = (p_calc_o2_cell * v_tot) / (R*T)

# n_h2_m3_i = (p_h2_m3 * v_m3) / (R*T)
# p_calc_h2_cell = (p_h2_m3 * v_m3) / (v_tot)
# n_calc_h2_cell = (p_calc_h2_cell * v_tot) / (R*T)

# # calculations for bulk admittance of water
# p_calc_h2o_tot = (p_h2o_m1m2m3_i * v_m1m2m3) / (v_tot)
# n_calc_h2o_tot = (p_calc_h2o_tot * v_tot) / (R*T)
# p_calc_h2o_ads = p_calc_h2o_tot - p_h2o_tot_f
# n_calc_h2o_ads = p_calc_h2o_ads * v_tot / (R*T)

# # calculations for aliquot admittance of water
# p_meas_h2o_ads = p_h2o_m1m2m3_i - p_h2o_tot_f
# n_calc_h2o_ads = p_meas_h2o_ads * v_m1m2m3 / (R*T)

parameters = [
    {
        "name": "Pd_load",
        "description": "Weight percentage of Pd used in the experiment.",
        "value": "0.03387"
    },
    {
        "name": "Pd_density",
        "description": "Surface density of Pd in inverse nanometers squared.",
        "value": "0.0354"
    },
    {
        "name": "CeO2_SA",
        "description": "Surface area of CeO2 in square meters per gram.",
        "value": "54"
    },
    {
        "name": "V_cell",
        "description": "Volume of the cell in liters.",
        "value": str(v_tot)
    },
    {
        "name": "P_cell_CO",
        "description": "Initial calculated pressure of carbon monoxide in cell in Torr.",
        "value": str(p_calc_co_cell)
    },
    # {
    #     "name": "P_cell_13CO",
    #     "description": "Initial calculated pressure of carbon monoxide in cell in Torr.",
    #     "value": str(p_calc_13co_cell)
    # },
    # {
    #     "name": "P_cell_H2",
    #     "description": "Initial pressure of hydrogen in cell in Torr.",
    #     "value": str(p_calc_h2_cell)
    # },
    # {
    #     "name": "P_cell_13CO",
    #     "description": "Initial pressure of labeled carbon monoxide in cell in Torr.",
    #     "value": str(p_calc_co2_cell)
    # },
    {
        "name": "T_cell",
        "description": "Temperature of cell in Kelvin.",
        "value": str(T_cell)
    },
    # {
    #     "name": "n_ads_H2O",
    #     "description": "Amount of water adsorbed on Pd/CeO2 in moles.",
    #     "value": str(n_calc_h2o_ads)
    # },
    {
        "name": "Pretreatment Parameters",
        "description": "Parameters for pretreatment steps...",
        "subparameters": [
            {
                "name": "Pre-temperature_1",
                "description": "Temperature for pretreatment step 1 in" +
                " Kelvin.",
                "value": "673"
            },
            {
                "name": "Pre-time_1",
                "description": "Duration of pretreatment step 1 in hours.",
                "value": "2.0"
            },
            {
                "name": "Pre_pressure_1",
                "description": "Pressure during pretreatment in Torr.",
                "value": "0.0004"
            },
            {
                "name": "Pre-condition_1",
                "description": "Condition for pretreatment step 1.",
                "value": "evacuation"
            },
            {
                "name": "Pre-temperature_2",
                "description": "Temperature for pretreatment step 2 in" +
                " Kelvin.",
                "value": "673"
            },
            {
                "name": "Pre-time_2",
                "description": "Duration of pretreatment step 2 in hours.",
                "value": "2.0"
            },
            {
                "name": "Pre-pressure_2",
                "description": "Pressure during pretreatment in Torr.",
                "value": "3.9" #, 2.5"
            },
            {
                "name": "Pre-condition_2",
                "description": "Condition for pretreatment step 2.",
                "value": "oxygen" #, water"
            },
            {
                "name": "Pre-temperature_3",
                "description": "Temperature for pretreatment step 3 in" +
                " Kelvin.",
                "value": "673"
            },
            {
                "name": "Pre-time_3",
                "description": "Duration of pretreatment step 3 in hours.",
                "value": "0.50"
            },
            {
                "name": "Pre-pressure_3",
                "description": "Pressure during pretreatment in Torr.",
                "value": "0.0004"
            },
            {
                "name": "Pre-condition_3",
                "description": "Condition for pretreatment step 3.",
                "value": "evacuation"
            },
            # {
            #     "name": "Pre-temperature_4",
            #     "description": "Temperature for pretreatment step 4 in" +
            #     " Kelvin.",
            #     "value": "673"
            # },
            # {
            #     "name": "Pre-time_4",
            #     "description": "Duration of pretreatment step 4 in hours.",
            #     "value": "2.0"
            # },
            # {
            #     "name": "Pre-pressure_4",
            #     "description": "Pressure during pretreatment in Torr.",
            #     "value": "3.9"
            # },
            # {
            #     "name": "Pre-condition_4",
            #     "description": "Condition for pretreatment step 4.",
            #     "value": "water"
            # },
            # {
            #     "name": "Pre-temperature_5",
            #     "description": "Temperature for pretreatment step 5 in" +
            #     " Kelvin.",
            #     "value": "673"
            # },
            # {
            #     "name": "Pre-time_5",
            #     "description": "Duration of pretreatment step 5 in hours.",
            #     "value": "0.5"
            # },
            # {
            #     "name": "Pre-pressure_5",
            #     "description": "Pressure during pretreatment in Torr.",
            #     "value": "0.0004"
            # },
            # {
            #     "name": "Pre-condition_5",
            #     "description": "Condition for pretreatment step 5.",
            #     "value": "evacuation"
            # },
            # {
            #     "name": "Pre-temperature_6",
            #     "description": "Temperature for pretreatment step 6 in" +
            #     " Kelvin.",
            #     "value": "423"
            # },
            # {
            #     "name": "Pre-time_6",
            #     "description": "Duration of pretreatment step 6 in hours.",
            #     "value": "0.5"
            # },
            # {
            #     "name": "Pre-pressure_6",
            #     "description": "Pressure during pretreatment in Torr.",
            #     "value": "0.83"
            # },
            # {
            #     "name": "Pre-condition_6",
            #     "description": "Condition for pretreatment step 6.",
            #     "value": "water"
            # },
            # {
            #     "name": "Pre-temperature_7",
            #     "description": "Temperature for pretreatment step 7 in" +
            #     " Kelvin.",
            #     "value": "423"
            # },
            # {
            #     "name": "Pre-time_7",
            #     "description": "Duration of pretreatment step 7 in hours.",
            #     "value": "0.1"
            # },
            # {
            #     "name": "Pre-pressure_7",
            #     "description": "Pressure during pretreatment in Torr.",
            #     "value": "0.0004"
            # },
            # {
            #     "name": "Pre-condition_7",
            #     "description": "Condition for pretreatment step 7.",
            #     "value": "evacuation"
            # },
            
            # Add more subparameters as needed
        ]
    }
]

# Create and write to the README file
opus_filename = '20241029_170101_NN2053_04PdCe_3'
folder = 'NN2053_04PdCe_COAds//'
save_dir = ('C://Data//OpusReadParams//' + folder + opus_filename +
            '_README.md')
with open(save_dir, "w") as readme_file:
    for parameter in parameters:
        readme_file.write(f"## {parameter['name']}\n")
        readme_file.write(f"- Description: {parameter['description']}\n")

        if 'value' in parameter:
            readme_file.write(f"- Value: {parameter['value']}\n")

        if 'subparameters' in parameter:
            for subparameter in parameter['subparameters']:
                readme_file.write(f"  - **{subparameter['name']}**\n")
                readme_file.write(
                    f"    - Description: {subparameter['description']}\n")
                readme_file.write(f"    - Value: {subparameter['value']}\n")

            readme_file.write("\n")
