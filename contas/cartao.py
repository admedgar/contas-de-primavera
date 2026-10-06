"""Imagem de pré-visualização (og.png, 1200×630) com os números REAIS coletados (não a estimativa). Usa Pillow se disponível."""
from __future__ import annotations

from pathlib import Path

CORES = {"fundo": (11, 92, 122), "texto": (255, 255, 255), "suave": (205, 228, 238), "faixa": (8, 70, 94)}
FONTES = ["/System/Library/Fonts/Helvetica.ttc", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
          "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
          "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]


def _fonte(ImageFont, tam):
    for f in FONTES:
        if Path(f).exists():
            try:
                return ImageFont.truetype(f, tam)
            except OSError:
                continue
    return ImageFont.load_default(tam)     # Pillow ≥ 10.1: fonte vetorial embutida


def reais_curto(c: int) -> str:
    v = c / 100
    if v >= 1e9:
        return f"R$ {v / 1e9:.2f} bilhões".replace(".", ",")
    if v >= 1e6:
        return f"R$ {v / 1e6:.1f} milhões".replace(".", ",")
    return f"R$ {v:,.0f}".replace(",", ".")


def gerar(caminho: Path, titulo: str, valor_centavos: int, medida: str, data_br: str, por_habitante_centavos=None, rodape="") -> bool:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return False
    W, H = 1200, 630
    img = Image.new("RGB", (W, H), CORES["fundo"])
    d = ImageDraw.Draw(img)
    d.rectangle([0, H - 90, W, H], fill=CORES["faixa"])
    f = lambda t: _fonte(ImageFont, t)
    d.text((60, 50), "Contas de Primavera", font=f(40), fill=CORES["suave"])
    d.text((60, 130), titulo, font=f(46), fill=CORES["texto"])
    d.text((60, 215), reais_curto(valor_centavos), font=f(118), fill=CORES["texto"])
    d.text((60, 365), f"{medida} · valor coletado em {data_br}", font=f(38), fill=CORES["suave"])
    if por_habitante_centavos:
        d.text((60, 430), f"R$ {por_habitante_centavos / 100:,.0f} por habitante no ano".replace(",", "."), font=f(38), fill=CORES["texto"])
    d.text((60, H - 70), rodape or "Dados do Portal da Transparência oficial · projeto independente", font=f(28), fill=CORES["suave"])
    caminho = Path(caminho); caminho.parent.mkdir(parents=True, exist_ok=True)
    img.save(caminho, "PNG", optimize=True)
    return True
