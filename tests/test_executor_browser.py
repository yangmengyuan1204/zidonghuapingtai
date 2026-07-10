from app.executors.browser import _browser_executable_candidates


def test_browser_candidates_include_nested_playwright_executable(tmp_path, monkeypatch):
    executable = tmp_path / "chromium" / "chrome-win" / "chrome.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"")
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path))

    candidates = _browser_executable_candidates()

    assert str(executable) in candidates
