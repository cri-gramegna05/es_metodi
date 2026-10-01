"""Compone le anteprime PNG in due tavole per il README."""
import os
from PIL import Image

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "png")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "output")


def tavola(nomi, colonne, uscita, scala=0.5):
    ims = [Image.open(os.path.join(D, n)) for n in nomi]
    w, h = ims[0].size
    righe = (len(ims) + colonne - 1) // colonne
    t = Image.new("RGB", (w * colonne, h * righe), (244, 241, 236))
    for i, im in enumerate(ims):
        t.paste(im, ((i % colonne) * w, (i // colonne) * h))
    t = t.resize((int(t.width * scala), int(t.height * scala)), Image.LANCZOS)
    t.save(os.path.join(OUT, uscita), optimize=True)


tavola(["v_esterno.png", "v_trequarti.png", "v_interno.png", "v_retro.png"], 2, "anteprima_oxford.png")
tavola(["esploso_tomaia.png", "esploso_interno.png"], 1, "esploso_oxford.png", scala=0.6)
