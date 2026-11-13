from curator import config, setup


def test_setup_writes_a_config_without_questions(tmp_path):
    out = tmp_path / "local.toml"
    assert setup.main(["--tv-host", "10.0.0.20", "--bind", "10.0.0.10", "--config", str(out)]) == 0
    s = config.load(out, base=tmp_path)
    assert (s.tv_host, s.web_bind, s.web_port) == ("10.0.0.20", "10.0.0.10", 8080)


def test_setup_keeps_an_existing_file(tmp_path):
    out = tmp_path / "local.toml"
    out.write_text("keep")
    assert setup.main(["--tv-host", "10.0.0.20", "--config", str(out)]) == 1
    assert out.read_text() == "keep"
