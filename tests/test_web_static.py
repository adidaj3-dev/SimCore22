"""
Guards for the front end. There's no compiler or bundler, so a typo that would blank a page
(an import of a name that isn't exported, a misspelled CSS variable, raw HTML built from data)
is caught here instead of on a bay screen.
"""
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from simcore22.web.app import STATIC_DIR, create_app

JS_DIR = STATIC_DIR / "js"
CSS_DIR = STATIC_DIR / "css"


@pytest.fixture(scope="module")
def client():
    return TestClient(create_app(demo=True))


# ------------------------------------------------------------------ pages / assets

@pytest.mark.parametrize("path", ["/live", "/admin"])
def test_pages_are_served_as_html_and_revalidate(client, path):
    response = client.get(path)
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/html")
    assert response.headers["cache-control"] == "no-cache"   # an update must show without a hard refresh
    assert '<script type="module"' in response.text


def test_root_goes_to_the_player_app(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code in (302, 307) and response.headers["location"] == "/app"


@pytest.mark.parametrize("page", ["live.html", "admin.html"])
def test_every_asset_a_page_references_exists_and_is_served(client, page):
    html = (STATIC_DIR / page).read_text(encoding="utf-8")
    assets = re.findall(r'(?:href|src)="(/static/[^"]+)"', html)
    assert assets, "page references no assets?"
    for url in assets:
        response = client.get(url)
        assert response.status_code == 200, f"{page} references {url}, which is not served"
        assert response.headers["cache-control"] == "no-cache"


def test_every_stylesheet_and_script_is_reachable_over_http(client):
    for folder, kind in ((CSS_DIR, "css"), (JS_DIR, "js")):
        for file in folder.iterdir():
            assert client.get(f"/static/{kind}/{file.name}").status_code == 200


def test_api_docs_are_available_for_partners(client):
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").json()["info"]["title"] == "SimCore22"


# ----------------------------------------------------------- JS import / export

def _exports(source: str) -> set:
    names = set(re.findall(r"export\s+(?:async\s+)?(?:function|const|let|class)\s+(\w+)", source))
    for block in re.findall(r"export\s*\{([^}]*)\}", source):
        names |= {part.split(" as ")[-1].strip() for part in block.split(",") if part.strip()}
    return names


def _imports(source: str):
    for names, module in re.findall(r"import\s*\{([^}]*)\}\s*from\s*'(\./[\w.]+)'", source):
        yield [n.split(" as ")[0].strip() for n in names.split(",") if n.strip()], module


@pytest.mark.parametrize("file", sorted(JS_DIR.glob("*.js")), ids=lambda f: f.name)
def test_every_imported_name_is_really_exported(file):
    """A missing export is a SyntaxError that silently blanks the whole page."""
    for names, module in _imports(file.read_text(encoding="utf-8")):
        target = JS_DIR / module[2:]
        assert target.exists(), f"{file.name} imports {module}, which doesn't exist"
        missing = [n for n in names if n not in _exports(target.read_text(encoding="utf-8"))]
        assert not missing, f"{file.name} imports {missing} from {module}, which doesn't export them"


@pytest.mark.parametrize("file", sorted(JS_DIR.glob("*.js")), ids=lambda f: f.name)
def test_no_unused_imports(file):
    source = file.read_text(encoding="utf-8")
    for names, _ in _imports(source):
        for name in names:
            uses = len(re.findall(rf"\b{re.escape(name)}\b", source))
            assert uses >= 2, f"{file.name}: '{name}' is imported but never used"


# ------------------------------------------------------------------------ CSS

def test_every_css_variable_that_is_used_is_defined():
    defined, used = set(), set()
    for css in CSS_DIR.glob("*.css"):
        text = css.read_text(encoding="utf-8")
        defined |= set(re.findall(r"(--[\w-]+)\s*:", text))
        used |= set(re.findall(r"var\((--[\w-]+)", text))
    for js in JS_DIR.glob("*.js"):  # a few (row height, row offset) are set by the scripts at run time
        defined |= set(re.findall(r"setProperty\(\s*'(--[\w-]+)'", js.read_text(encoding="utf-8")))
    assert not (used - defined), f"CSS uses undefined variables: {sorted(used - defined)}"


def test_both_themes_define_the_same_colors():
    tokens = (CSS_DIR / "tokens.css").read_text(encoding="utf-8")
    dark, light = tokens.split(':root[data-theme="light"]')
    dark_colors = set(re.findall(r"(--[\w-]+)\s*:\s*(?:#|rgba?\()", dark))
    light_colors = set(re.findall(r"(--[\w-]+)\s*:\s*(?:#|rgba?\()", light))
    assert dark_colors - light_colors == set(), f"light theme is missing: {sorted(dark_colors - light_colors)}"


# ----------------------------------------------------------------- HTML safety

def test_data_is_never_turned_into_html():
    """
    Player names, courses etc. come from the log and could contain anything. The only places
    allowed to build HTML from a string are the static icon/logo constants.
    """
    offenders = []
    for file in JS_DIR.glob("*.js"):
        for number, line in enumerate(file.read_text(encoding="utf-8").splitlines(), start=1):
            if file.name == "dom.js" and ("el.innerHTML = value" in line or "innerHTML = " in line and "key === 'html'" in line):
                continue
            if re.search(r"innerHTML\s*=|\bhtml\s*:", line) and not re.search(r"ICONS|LOGO", line):
                offenders.append(f"{file.name}:{number}: {line.strip()}")
    assert not offenders, "raw HTML from a non-constant:\n" + "\n".join(offenders)


def test_no_external_resources_so_a_bay_works_offline():
    for file in list(STATIC_DIR.glob("*.html")) + list(CSS_DIR.glob("*.css")) + list(JS_DIR.glob("*.js")):
        urls = re.findall(r"""(?:src|href)=["'](https?://[^"']+)|url\(["']?(https?://[^)"']+)""", file.read_text(encoding="utf-8"))
        external = [u for pair in urls for u in pair if u]
        assert not external, f"{file.name} loads from the internet: {external}"


def test_scripts_use_only_the_public_api_paths_that_exist(client):
    """Every /api/... path written in the JS must be a real endpoint."""
    paths = set()
    for file in JS_DIR.glob("*.js"):
        paths |= set(re.findall(r"""['"`](/api/[\w/]+)""", file.read_text(encoding="utf-8")))
    known = {route.path.split("{")[0].rstrip("/") for route in client.app.routes}
    for path in paths:
        assert path.rstrip("/") in known, f"JS calls {path}, which the server doesn't define"


def test_demo_flag_exists_on_everything_the_ui_uses_to_label_demo_data(client):
    """The UI decides 'this is demo data' from these two fields; they must stay."""
    assert client.get("/api/leaderboard").json()["demo"] is True
    assert client.get("/api/engine").json()["demo"] is True


def test_static_directory_is_inside_the_package():
    assert STATIC_DIR == Path(__file__).resolve().parents[1] / "simcore22" / "web" / "static"
