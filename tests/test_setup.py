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


def test_setup_without_a_terminal_asks_for_tv_host(tmp_path, monkeypatch, capsys):
    """No input (an agent, `</dev/null`): a clear message, no traceback, no file."""
    def no_input(prompt=""):
        raise EOFError
    monkeypatch.setattr("builtins.input", no_input)
    monkeypatch.setattr(setup, "lan_address", lambda: "10.0.0.10")
    monkeypatch.setattr(setup, "find_tvs", lambda near: [("10.0.0.20", "Frame")])
    out = tmp_path / "local.toml"
    assert setup.main(["--config", str(out)]) == 1
    err = capsys.readouterr().err
    assert "--tv-host" in err and "10.0.0.20" in err
    assert not out.exists()
