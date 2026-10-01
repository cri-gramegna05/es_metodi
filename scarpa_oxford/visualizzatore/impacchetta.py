"""Crea output/visualizzatore.html (pagina completa) dal contenuto del visualizzatore.
Aprire con un server locale:  cd output && python3 -m http.server  ->  http://localhost:8000/visualizzatore.html"""
import os

QUI = os.path.dirname(os.path.abspath(__file__))
corpo = open(os.path.join(QUI, "contenuto.html"), encoding="utf-8").read()
testa, resto = corpo.split("</style>", 1)
pagina = ("<!doctype html>\n<html lang=\"it\">\n<head>\n<meta charset=\"utf-8\">\n"
          "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1, viewport-fit=cover\">\n"
          + testa + "</style>\n</head>\n<body>\n" + resto.strip() + "\n</body>\n</html>\n")
with open(os.path.join(QUI, "..", "output", "visualizzatore.html"), "w", encoding="utf-8") as f:
    f.write(pagina)
