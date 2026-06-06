# Model improvement notes

- log transform of 4/6 params was helpful
- grouping was helpful
- random split was helpful b/c started sampling longer times lately
- using previous targets was helpful


# Current Best:

## Test Metrics:
  pfo-sec_q0_au: RMSE=0.043684, R²=0.5744
  pfo-sec_q_e_au: RMSE=0.306630, R²=0.6972
  pfo-sec_q_inf_au: RMSE=0.017978, R²=-0.1072
  pfo-sec_k_a_s-1: RMSE=0.000125, R²=-0.1778
  pfo-sec_k_s_s-1: RMSE=0.004596, R²=-0.3134
  pfo-sec_k_p_s-1: RMSE=0.000105, R²=-0.1276
  Aggregate: RMSE=0.062186, R²=0.0909

## Baseline Metrics (training mean):
  pfo-sec_q0_au: RMSE=0.068917, R²=-0.0592
  pfo-sec_q_e_au: RMSE=0.583298, R²=-0.0959
  pfo-sec_q_inf_au: RMSE=0.017979, R²=-0.1073
  pfo-sec_k_a_s-1: RMSE=0.000131, R²=-0.3018
  pfo-sec_k_s_s-1: RMSE=0.004599, R²=-0.3150
  pfo-sec_k_p_s-1: RMSE=0.000105, R²=-0.1317
  Aggregate: RMSE=0.112505, R²=-0.1685