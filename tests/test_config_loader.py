from odw2json.config_loader import load_app_config, load_lookup, load_registry


def test_registry_has_three_doctypes():
    reg = load_registry()
    assert set(reg) == {"odwolanie", "pelnomocnictwo", "przelew"}


def test_template_shape_and_isolation():
    cfg = load_registry()["odwolanie"]
    t = cfg.template()
    assert list(t) == ["OdwolanieKIO", "Odwolujacy", "Zamawiajacy", "ZamowieniePubliczne"]
    t["OdwolanieKIO"]["data"] = "x"
    assert cfg.template()["OdwolanieKIO"]["data"] is None


def test_lookup_czynnosc_powod():
    lk = load_lookup("czynnosc_powod")
    assert lk[9] == "Decyzja o unieważnieniu postępowania"


def test_app_config_unknown_output():
    assert load_app_config()["unknown_output"] in {"none", "empty_file"}
