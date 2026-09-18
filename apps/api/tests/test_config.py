from app import config


def test_falls_back_to_localhost_when_env_var_unset(monkeypatch) -> None:
    monkeypatch.delenv(config.FRONTEND_ORIGINS_ENV_VAR, raising=False)
    assert config.get_allowed_origins() == [config.DEFAULT_FRONTEND_ORIGIN]


def test_falls_back_to_localhost_when_env_var_empty(monkeypatch) -> None:
    monkeypatch.setenv(config.FRONTEND_ORIGINS_ENV_VAR, "   ")
    assert config.get_allowed_origins() == [config.DEFAULT_FRONTEND_ORIGIN]


def test_single_configured_origin_is_used_verbatim(monkeypatch) -> None:
    monkeypatch.setenv(config.FRONTEND_ORIGINS_ENV_VAR, "https://app.example.com")
    assert config.get_allowed_origins() == ["https://app.example.com"]


def test_multiple_origins_are_split_trimmed_and_empty_entries_dropped(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        config.FRONTEND_ORIGINS_ENV_VAR,
        " https://app.example.com , https://staging.example.com ,,",
    )
    assert config.get_allowed_origins() == [
        "https://app.example.com",
        "https://staging.example.com",
    ]


def test_default_origin_is_never_a_wildcard() -> None:
    assert config.DEFAULT_FRONTEND_ORIGIN != "*"


def test_a_wildcard_origin_is_rejected_and_falls_back_to_the_default(
    monkeypatch,
) -> None:
    # "*" is never valid here — allow_credentials=True is set on
    # CORSMiddleware, and browsers reject a wildcard origin combined with
    # credentials anyway. Since it's the only configured entry, nothing
    # usable remains and the safe localhost default is used.
    monkeypatch.setenv(config.FRONTEND_ORIGINS_ENV_VAR, "*")
    assert config.get_allowed_origins() == [config.DEFAULT_FRONTEND_ORIGIN]


def test_a_malformed_entry_is_dropped_but_valid_siblings_are_kept(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        config.FRONTEND_ORIGINS_ENV_VAR,
        "https://app.example.com,not a url,https://app.example.com/some/path,ftp://bad.example.com",
    )
    assert config.get_allowed_origins() == ["https://app.example.com"]


def test_get_max_upload_bytes_defaults_when_unset(monkeypatch) -> None:
    monkeypatch.delenv(config.MAX_UPLOAD_BYTES_ENV_VAR, raising=False)
    assert config.get_max_upload_bytes() == config.DEFAULT_MAX_UPLOAD_BYTES


def test_get_max_upload_bytes_honors_a_valid_override(monkeypatch) -> None:
    monkeypatch.setenv(config.MAX_UPLOAD_BYTES_ENV_VAR, "12345")
    assert config.get_max_upload_bytes() == 12345


def test_get_max_upload_bytes_falls_back_on_non_integer(monkeypatch) -> None:
    monkeypatch.setenv(config.MAX_UPLOAD_BYTES_ENV_VAR, "not-a-number")
    assert config.get_max_upload_bytes() == config.DEFAULT_MAX_UPLOAD_BYTES


def test_get_max_upload_bytes_falls_back_on_non_positive_value(monkeypatch) -> None:
    monkeypatch.setenv(config.MAX_UPLOAD_BYTES_ENV_VAR, "0")
    assert config.get_max_upload_bytes() == config.DEFAULT_MAX_UPLOAD_BYTES
