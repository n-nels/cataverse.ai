# Model improvement notes

- log transform of 4/6 params was helpful, box-cox was even better
- grouping was helpful
- random split was helpful b/c started sampling longer times lately
- using previous targets was helpful


# Current Best:

Test Metrics:
  pfo-sec_q0_au: RMSE=0.040941, R²=0.6262
  pfo-sec_q_e_au: RMSE=0.296985, R²=0.7159
  pfo-sec_q_inf_au: RMSE=0.017979, R²=-0.1073
  pfo-sec_k_a_s-1: RMSE=0.000094, R²=0.3390
  pfo-sec_k_s_s-1: RMSE=0.004410, R²=-0.2089
  pfo-sec_k_p_s-1: RMSE=0.000096, R²=0.0501
  Aggregate: RMSE=0.060084, R²=0.2358

Baseline Metrics (training mean):
  pfo-sec_q0_au: RMSE=0.068917, R²=-0.0592
  pfo-sec_q_e_au: RMSE=0.583298, R²=-0.0959
  pfo-sec_q_inf_au: RMSE=0.017979, R²=-0.1073
  pfo-sec_k_a_s-1: RMSE=0.000119, R²=-0.0713
  pfo-sec_k_s_s-1: RMSE=0.004598, R²=-0.3143
  pfo-sec_k_p_s-1: RMSE=0.000103, R²=-0.0906
  Aggregate: RMSE=0.112502, R²=-0.1231