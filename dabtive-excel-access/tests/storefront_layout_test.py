from pathlib import Path


def main() -> None:
    css = (Path(__file__).resolve().parents[1] / "app" / "static" / "style.css").read_text()
    marker = "v0.5.1 — desktop storefront is full-width"
    assert marker in css
    tail = css[css.index(marker):]
    assert ".storefront-page{padding:0" in tail
    assert ".storefront-card{width:100%;max-width:none" in tail
    assert "border-radius:0" in tail
    assert "box-shadow:none" in tail
    print("STOREFRONT LAYOUT TEST OK")


if __name__ == "__main__":
    main()
