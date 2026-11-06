from curator.config import Settings, load


def test_missing_file_gives_defaults(tmp_path):
    assert load(tmp_path / "none.toml") == Settings()


def test_loads_values_and_resolves_relative_paths(tmp_path):
    f = tmp_path / "c.toml"
    f.write_text('[tv]\nhost="10.0.0.9"\ntoken_file="t.txt"\n[web]\nport=9000\n[storage]\ndata_dir="d"\n')
    s = load(f, base=tmp_path)
    assert s.tv_host == "10.0.0.9" and s.web_port == 9000
    assert s.token_file == tmp_path / "t.txt" and s.data_dir == tmp_path / "d"
    assert s.db_path == tmp_path / "d" / "curator.sqlite3"
