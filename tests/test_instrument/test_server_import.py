def test_import_opus_server_entrypoint():
    import importlib

    module = importlib.import_module("src.instrument.main")
    assert hasattr(module, "main") or hasattr(module, "run_server_main")
