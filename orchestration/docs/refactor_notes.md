# refactor notes
- [] session.py has start_pressure_log() and start_mass_spec_log(), weird.
- [] let's shut heat lines off on final evac. Just put them as args for each function. If introducing pre-gas, true, if evac, false.
- [] src.experiments/adsorption.py, line 109; should be argument with default
- [] finalize.py; may consider doing post opus acquisition things here as well for early script exit
- [] should round dp, gives huge floating
- [] need to add process_pressure.py & analyze
- [] would then need to build auto pipeline to graph
- [] setup.py, line 57; If you want confirmation that all devices connected, you'd need to add logger calls inside DeviceManager.connect(). But functionally, if it didn't raise an exception, the connections succeeded.
