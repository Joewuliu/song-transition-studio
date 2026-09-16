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


def test_configured_origins_can_still_resolve_to_a_wildcard_only_if_explicitly_set(
    monkeypatch,
) -> None:
    # get_allowed_origins() itself applies no filtering beyond trimming —
    # it is the operator's responsibility not to configure "*"; this test
    # just documents that the function doesn't silently rewrite an
    # explicit "*" into something safer, so a misconfiguration is visible
    # rather than hidden.
    monkeypatch.setenv(config.FRONTEND_ORIGINS_ENV_VAR, "*")
    assert config.get_allowed_origins() == ["*"]
