"""Convierte los .svg en .png con el Chrome del sistema (Playwright)."""
import pathlib, re
from playwright.sync_api import sync_playwright
AQUI = pathlib.Path(__file__).resolve().parent
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CHROME, headless=True)
    for f in sorted(AQUI.glob('*.svg')):
        svg = f.read_text(encoding='utf-8')
        w, h = map(int, re.search(r'width="(\d+)" height="(\d+)"', svg).groups())
        pg = b.new_page(viewport={'width': w, 'height': h}, device_scale_factor=1.5)
        pg.set_content('<body style="margin:0">' + svg + '</body>')
        pg.screenshot(path=str(f.with_suffix('.png')))
        pg.close()
        print('PNG', f.stem, w, h)
    b.close()
