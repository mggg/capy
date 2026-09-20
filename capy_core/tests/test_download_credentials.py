import pytest

from capy_core.download import download_geographies, download_population_tables


@pytest.mark.parametrize(
    "downloader", [download_geographies, download_population_tables]
)
@pytest.mark.parametrize("file_exists", [False, True])
def test_configured_credentials_override_environment_with_fallback(
    tmp_path, monkeypatch, downloader, file_exists
):
    monkeypatch.setenv("IPUMS_API_KEY", "environment-ipums-key")
    monkeypatch.setenv("CENSUS_API_KEY", "environment-census-key")
    env_file = tmp_path / "credentials.env"
    if file_exists:
        env_file.write_text('IPUMS_API_KEY="file-ipums-key"\n', encoding="utf-8")

    downloader.load_dotenv(env_file)

    expected_ipums_key = "file-ipums-key" if file_exists else "environment-ipums-key"
    assert downloader.require_env("IPUMS_API_KEY") == expected_ipums_key
    assert downloader.require_env("CENSUS_API_KEY") == "environment-census-key"
