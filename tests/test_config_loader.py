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
    assert load_app_config()["unknown_output"] in {"none", "empty_file", "empty_object"}


def test_classify_config_defaults_are_backward_compatible():
    from odw2json.config_loader import ClassifyConfig

    c = ClassifyConfig(strong=["a"])
    assert c.title == [] and c.patterns == [] and c.required_any == []
    assert (c.min_score, c.min_margin, c.header_chars) == (3.0, 0.0, 600)
    assert (c.weights.strong, c.weights.weak, c.weights.negative, c.weights.title) == (2.0, 1.0, -3.0, 4.0)


def test_shipped_classify_configs_load_with_new_fields():
    reg = load_registry()
    assert reg["przelew"].classify.required_any
    assert reg["przelew"].classify.patterns
    assert all(c.classify.title for c in reg.values())
