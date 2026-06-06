from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parent
EDGE_PATH = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
HTML_PATH = ROOT / "outputs" / "thailand_ghcn_2026_map.html"
PDF_PATH = ROOT / "outputs" / "thailand_ghcn_2026_map_A4.pdf"


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=str(EDGE_PATH),
            headless=True,
        )
        page = browser.new_page(viewport={"width": 1587, "height": 1123})
        page.goto(HTML_PATH.as_uri(), wait_until="networkidle")
        page.add_style_tag(
            content="""
                @page { size: A4 landscape; margin: 8mm; }
                html, body { margin: 0; padding: 0; background: white; }
                .plotly-graph-div { width: 100% !important; height: 100vh !important; }
            """
        )
        page.wait_for_timeout(1500)
        page.pdf(
            path=str(PDF_PATH),
            format="A4",
            landscape=True,
            print_background=True,
            margin={"top": "8mm", "right": "8mm", "bottom": "8mm", "left": "8mm"},
        )
        browser.close()

    print(f"Saved PDF: {PDF_PATH}")


if __name__ == "__main__":
    main()
