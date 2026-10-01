#!/usr/bin/env python3
"""Relazione PDF: dalla forma ai piani di taglio dell'Oxford tg 42.

Uso: python3 relazione/figure.py && python3 relazione/genera_relazione.py
"""

import json
import os

import matplotlib
from PIL import Image as PILImage
from reportlab.graphics.shapes import Circle, Drawing, Line, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Frame, Image, KeepTogether, NextPageTemplate,
                                PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle)

QUI = os.path.dirname(os.path.abspath(__file__))
RADICE = os.path.join(QUI, "..")
OUT = os.path.join(RADICE, "output")
FIG = os.path.join(QUI, "figure")
PNG3D = os.path.join(RADICE, "anteprima", "png")
FORMA = os.path.join(RADICE, "..", "forma_3d", "output")
LINK_3D = "https://claude.ai/artifact/B81qbzvuF4gzVuD9ijHMzx"

# --- caratteri e colori ------------------------------------------------------
TTF = os.path.join(os.path.dirname(matplotlib.__file__), "mpl-data", "fonts", "ttf")
pdfmetrics.registerFont(TTFont("Corpo", os.path.join(TTF, "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont("Corpo-B", os.path.join(TTF, "DejaVuSans-Bold.ttf")))
pdfmetrics.registerFont(TTFont("Corpo-I", os.path.join(TTF, "DejaVuSans-Oblique.ttf")))
pdfmetrics.registerFontFamily("Corpo", normal="Corpo", bold="Corpo-B", italic="Corpo-I")

INCHIOSTRO = colors.HexColor("#1f2329")
CUOIO = colors.HexColor("#5a3420")
GRIGIO = colors.HexColor("#5d6773")
LINEA = colors.HexColor("#d8cfc4")
FONDO_TAB = colors.HexColor("#f3eee8")

S = {
    "corpo": ParagraphStyle("corpo", fontName="Corpo", fontSize=9.4, leading=14, textColor=INCHIOSTRO,
                            spaceAfter=6, alignment=TA_LEFT),
    "h1": ParagraphStyle("h1", fontName="Corpo-B", fontSize=17, leading=21, textColor=CUOIO,
                         spaceBefore=4, spaceAfter=10, keepWithNext=1),
    "h2": ParagraphStyle("h2", fontName="Corpo-B", fontSize=11.5, leading=15, textColor=INCHIOSTRO,
                         spaceBefore=10, spaceAfter=5, keepWithNext=1),
    "didascalia": ParagraphStyle("did", fontName="Corpo-I", fontSize=7.8, leading=10.5,
                                 textColor=GRIGIO, spaceBefore=3, spaceAfter=10),
    "cella": ParagraphStyle("cella", fontName="Corpo", fontSize=8.2, leading=11, textColor=INCHIOSTRO),
    "cella_b": ParagraphStyle("cellab", fontName="Corpo-B", fontSize=8.2, leading=11, textColor=INCHIOSTRO),
    "punto": ParagraphStyle("punto", fontName="Corpo", fontSize=9.4, leading=14, textColor=INCHIOSTRO,
                            leftIndent=12, bulletIndent=2, spaceAfter=3),
    "nota": ParagraphStyle("nota", fontName="Corpo", fontSize=8.6, leading=12.5, textColor=GRIGIO,
                           spaceAfter=6),
}
LARGH = A4[0] - 40 * mm


def P(t, st="corpo"):
    return Paragraph(t, S[st])


def punti(voci):
    return [Paragraph(v, S["punto"], bulletText="•") for v in voci]


def ritaglia(nome_file, sfondo=None, togli_titolo=False):
    """Toglie i bordi vuoti di un'immagine (e l'etichetta in alto a sinistra dei render)."""
    im = PILImage.open(nome_file).convert("RGB")
    if togli_titolo:
        bg = im.getpixel((3, 3))
        im.paste(bg, (0, 0, 260, 40))
    bg = sfondo or im.getpixel((2, 2))
    diff = PILImage.new("RGB", im.size, bg)
    from PIL import ImageChops
    bbox = ImageChops.difference(im, diff).convert("L").point(lambda v: 255 if v > 12 else 0).getbbox()
    if bbox:
        pad = 12
        bbox = (max(bbox[0] - pad, 0), max(bbox[1] - pad, 0), min(bbox[2] + pad, im.width),
                min(bbox[3] + pad, im.height))
        im = im.crop(bbox)
    out = os.path.join(FIG, "_" + os.path.basename(nome_file))
    im.save(out)
    return out


def immagine(path, larghezza, ritaglio=True, togli_titolo=False):
    p = ritaglia(path, togli_titolo=togli_titolo) if ritaglio else path
    w, h = PILImage.open(p).size
    return Image(p, width=larghezza, height=larghezza * h / w)


def figura(path, larghezza, didascalia=None, ritaglio=True, togli_titolo=False):
    el = [immagine(path, larghezza, ritaglio, togli_titolo)]
    if didascalia:
        el.append(P(didascalia, "didascalia"))
    return KeepTogether(el)


def tabella(righe, larghezze, intestazione=True, allinea_dx=()):
    dati = []
    for i, r in enumerate(righe):
        st = "cella_b" if (intestazione and i == 0) else "cella"
        dati.append([c if not isinstance(c, str) else P(c, st) for c in r])
    t = Table(dati, colWidths=larghezze, repeatRows=1 if intestazione else 0)
    stile = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
             ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINEA),
             ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
             ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
    if intestazione:
        stile += [("BACKGROUND", (0, 0), (-1, 0), FONDO_TAB), ("LINEBELOW", (0, 0), (-1, 0), 0.8, CUOIO)]
    for c in allinea_dx:
        stile.append(("ALIGN", (c, 0), (c, -1), "RIGHT"))
    t.setStyle(TableStyle(stile))
    return t


def campione(tipo):
    """Piccolo disegno del segno grafico usato sui cartamodelli."""
    d = Drawing(18 * mm, 5 * mm)
    y = 2.5 * mm
    spec = {"taglio": ("#111111", 1.2, None), "montaggio": ("#1f5fae", 1.0, [1, 2]),
            "cucitura": ("#b03a2e", 0.9, [4, 2]), "scarnitura": ("#7d7d7d", 0.9, [6, 2, 1, 2]),
            "riferimento": ("#1e8449", 1.1, None), "asse": ("#7d3c98", 0.9, [8, 2, 2, 2])}
    if tipo in spec:
        c, w, da = spec[tipo]
        d.add(Line(1 * mm, y, 17 * mm, y, strokeColor=colors.HexColor(c), strokeWidth=w,
                   strokeDashArray=da))
    elif tipo == "tacche":
        d.add(Line(1 * mm, y - 1.5 * mm, 17 * mm, y - 1.5 * mm, strokeColor=colors.black, strokeWidth=1.1))
        d.add(Line(9 * mm, y - 1.5 * mm, 9 * mm, y + 1.5 * mm, strokeColor=colors.black, strokeWidth=1.1))
    elif tipo == "fori":
        for x in (4, 9, 14):
            d.add(Circle(x * mm, y, 1.3 * mm, strokeColor=colors.black, fillColor=None, strokeWidth=0.8))
    elif tipo == "testo":
        d.add(String(1 * mm, y - 1.2 * mm, "Abc  →", fontName="Corpo", fontSize=8))
    return d


def numero(v, dec=1):
    return f"{v:.{dec}f}".replace(".", ",")


# --- pagine -------------------------------------------------------------------

def piede(canvas, doc):
    canvas.saveState()
    canvas.setFont("Corpo", 7.5)
    canvas.setFillColor(GRIGIO)
    canvas.drawString(20 * mm, 10 * mm, "Oxford cap-toe uomo tg 42 · Dalla forma ai piani di taglio")
    canvas.drawRightString(A4[0] - 20 * mm, 10 * mm, f"{doc.page}")
    canvas.setStrokeColor(LINEA)
    canvas.setLineWidth(0.4)
    canvas.line(20 * mm, 14 * mm, A4[0] - 20 * mm, 14 * mm)
    canvas.restoreState()


def copertina(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(colors.HexColor("#f4f1ec"))
    canvas.rect(0, 0, A4[0], A4[1], stroke=0, fill=1)
    canvas.setFillColor(CUOIO)
    canvas.rect(0, A4[1] - 8 * mm, A4[0], 8 * mm, stroke=0, fill=1)
    canvas.setFillColor(INCHIOSTRO)
    canvas.setFont("Corpo-B", 30)
    canvas.drawString(20 * mm, A4[1] - 45 * mm, "Oxford cap-toe uomo")
    canvas.setFont("Corpo", 30)
    canvas.drawString(20 * mm, A4[1] - 58 * mm, "taglia 42")
    canvas.setFillColor(CUOIO)
    canvas.setFont("Corpo-B", 15)
    canvas.drawString(20 * mm, A4[1] - 74 * mm, "Dalla forma ai piani di taglio")
    canvas.setFillColor(GRIGIO)
    canvas.setFont("Corpo", 10)
    canvas.drawString(20 * mm, A4[1] - 82 * mm, "Relazione sul lavoro svolto · 1 ottobre 2026")
    img = ritaglia(os.path.join(PNG3D, "v_trequarti.png"), togli_titolo=True)
    w, h = PILImage.open(img).size
    lw = A4[0] - 30 * mm
    canvas.drawImage(img, 15 * mm, 62 * mm, width=lw, height=lw * h / w)
    canvas.setFillColor(INCHIOSTRO)
    canvas.setFont("Corpo", 9)
    y = 44 * mm
    for t in ("1  La forma da montaggio",
              "2  La scarpa 3D e la divisione in pezzi",
              "3  I piani di taglio 2D: sviluppo, margini, segni, verifiche, file"):
        canvas.drawString(20 * mm, y, t)
        y -= 6 * mm
    canvas.restoreState()


def contenuto():
    rie = json.load(open(os.path.join(OUT, "piani_2d", "riepilogo.json"), encoding="utf-8"))
    forma = json.load(open(os.path.join(FORMA, "forma_uomo_42_tacco25_misure.json"), encoding="utf-8"))
    pz = {p["nome"]: p for p in rie["pezzi"]}
    cons = rie["consumi_per_materiale"]
    ctr = rie["controllo_cuciture"]
    st = []

    # 1. Sintesi -------------------------------------------------------------
    st += [P("In sintesi", "h1"),
           P("Il lavoro si è svolto in tre passaggi, ognuno costruito sul precedente:"),
           *punti(["<b>La forma</b>: una forma da montaggio uomo in taglia 42, destra e sinistra, "
                   "disegnata con le proporzioni di una classica forma da uomo.",
                   "<b>La scarpa 3D</b>: una Oxford con puntale riportato, costruita sulla forma e divisa "
                   "negli stessi pezzi che si tagliano in produzione.",
                   "<b>I piani di taglio 2D</b>: ogni pezzo è stato steso in piano e completato con margini, "
                   "cuciture e segni. Il risultato sono 17 cartamodelli in scala 1:1."]),
           Spacer(1, 6)]
    vit, fod = cons["vitello box"], cons["pelle fodera"]
    max_diff = max(abs(c["differenza_mm"]) for c in ctr)
    st.append(tabella([
        ["Risultato", "Valore"],
        ["Cartamodelli", "17: 12 di tomaia, fodere e rinforzi, la fodera della linguetta e 4 del fondo"],
        ["Formati", "PDF da stampare su A3 al 100%; DXF e SVG in scala 1:1"],
        ["Bordi da cucire insieme", f"differenze tra i due bordi al massimo di {numero(max_diff)} mm"],
        ["Deformazione dello sviluppo", "sotto l'1% sui fianchi, circa il 3% sui pezzi della punta"],
        ["Vitello box per paio", f"{numero(vit['netto_dm2'])} dm² netti, {numero(vit['lordo_dm2'])} dm² con sfrido"],
        ["Pelle fodera per paio", f"{numero(fod['netto_dm2'])} dm² netti, {numero(fod['lordo_dm2'])} dm² con sfrido"],
    ], [45 * mm, LARGH - 45 * mm]))
    st += [Spacer(1, 10),
           P("I capitoli 1 e 2 riassumono brevemente forma e scarpa 3D. Il capitolo 3 spiega in dettaglio "
             "come sono stati ottenuti i piani di taglio, cosa c'è disegnato su ogni cartamodello, come sono "
             "stati controllati e come si usano i file.")]

    # 2. Forma -----------------------------------------------------------------
    st += [PageBreak(), P("1. La forma", "h1"),
           P("È una forma da montaggio uomo in taglia 42 francese (punto Paris, 6,67 mm per numero), "
             "destra e sinistra. È stata costruita da proporzioni standard: il profilo del fondo con "
             "tacco e slancio di punta, il profilo del dorso e una serie di sezioni dal tallone alla punta, "
             "con la punta leggermente spostata verso l'interno come in una forma reale. Sul cono c'è il foro "
             "per il perno della macchina da montaggio."),
           tabella([["Misura", "Valore"],
                    ["Lunghezza", f"{numero(forma['lunghezza_mm'], 0)} mm"],
                    ["Larghezza pianta / tallone", f"{numero(forma['larghezza_pianta_mm'])} / "
                                                   f"{numero(forma['larghezza_tallone_mm'])} mm"],
                    ["Giro pianta / giro collo", f"{numero(forma['giro_pianta_mm'], 0)} / "
                                                 f"{numero(forma['giro_collo_mm'], 0)} mm"],
                    ["Altezza totale", f"{numero(forma['altezza_totale_mm'], 0)} mm"],
                    ["Tacco / slancio di punta", "25 / 12 mm"],
                    ["Foro per il perno", "Ø 11 × 45 mm"]],
                   [60 * mm, 50 * mm], allinea_dx=(1,)),
           Spacer(1, 8),
           figura(os.path.join(FORMA, "anteprima_42_dx.png"), LARGH * 0.92,
                  "Figura 1. La forma destra nelle sei viste principali."),
           P("La forma non deriva da una scansione: proporzioni e calzata vanno verificate dal modellista. "
             "Il giro pianta di 252 mm corrisponde a una calzata piuttosto abbondante.", "nota")]

    # 3. Scarpa 3D -------------------------------------------------------------
    st += [PageBreak(), P("2. La scarpa 3D", "h1"),
           P("Il modello è una Oxford classica: allacciatura chiusa (i quartieri sono cuciti sotto la "
             "mascherina), puntale riportato con doppia cucitura, 5 occhielli, bacchetta sulla cucitura "
             "del tallone, guardolo a giro completo, suola in cuoio e tacco di 25 mm in 4 alzi con "
             "sopratacco in gomma."),
           figura(os.path.join(OUT, "anteprima_oxford.png"), LARGH * 0.62,
                  "Figura 2. La scarpa destra: lato esterno, tre quarti, lato interno e retro."),
           ]
    testo_3d = [P("Le linee di modello", "h2"),
                P("Come fa il modellista sul nastro, le linee sono state disegnate direttamente sulla forma:"),
                *punti(["<b>bocca</b>: 59 mm sopra la seggetta al tallone, punto più basso 48 mm, sotto i "
                        "malleoli;",
                        "<b>gola</b>, cioè la fine dell'allacciatura: a 156 mm dal tallone;",
                        "<b>mascherina</b>: dalla gola scende fino al filo forma a circa 123 mm dal tallone;",
                        "<b>puntale</b>: a 219 mm dal tallone sul dorso (puntale di circa 61 mm), inclinato "
                        "verso il fondo;",
                        "<b>occhielleria</b>: luce da 0 mm alla gola a 9 mm in alto, 5 occhielli;",
                        "<b>contrafforte</b>, più lungo sul lato interno, e <b>rinforzo puntale</b>, che arriva "
                        "4 mm oltre la linea del puntale."]),
                P("I pezzi", "h2"),
                P("Ogni pezzo è la parte di superficie della forma chiusa dalle sue linee, comprese le parti "
                  "che finiscono sotto un altro pezzo (i riporti). Per ogni pezzo questa superficie, che qui "
                  "chiamiamo <b>camicia</b>, è stata conservata: è il punto di partenza dei piani di taglio."),
                P("Dal piede verso l'esterno gli strati sono: sottopiede, fodera avampiede, linguetta, fodere "
                  "quartiere, contrafforte e rinforzo puntale, quartieri, mascherina, puntale e bacchetta.")]
    esploso = [immagine(os.path.join(OUT, "esploso_oxford.png"), 58 * mm),
               P("Figura 3. Esploso: sopra i pezzi esterni della tomaia, sotto fodere, rinforzi e sottopiede.",
                 "didascalia")]
    st += [Table([[testo_3d, esploso]], colWidths=[LARGH - 62 * mm, 62 * mm],
                 style=[("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("RIGHTPADDING", (0, 0), (0, 0), 8)]),
           P(f"La scarpa si può ruotare ed esplodere nel visualizzatore 3D: "
             f'<link href="{LINK_3D}" color="#2c64a8">{LINK_3D}</link>', "nota")]

    # 4. Piani 2D ----------------------------------------------------------------
    st += [PageBreak(), P("3. I piani di taglio 2D", "h1"),
           P("3.1 Dalla forma al piano", "h2"),
           P("Nel metodo tradizionale si ricopre la forma di nastro, si disegnano le linee, si stacca il "
             "nastro e lo si stende sul cartoncino. Qui si è fatto lo stesso, ma pezzo per pezzo: la camicia "
             "di ogni pezzo è stata stesa in piano cercando di non allungare né accorciare nessun tratto "
             "della sua superficie."),
           figura(os.path.join(FIG, "camicia_piano.png"), LARGH,
                  "Figura 4. Il quartiere esterno sulla forma (in blu) e lo stesso pezzo steso in piano, "
                  "con margini e segni."),
           P("Una superficie che curva in una sola direzione, come il fianco del quartiere, si stende quasi "
             "senza deformarsi. Una superficie che curva in due direzioni insieme, come la punta, non si può "
             "stendere senza piccole differenze: è lo stesso motivo per cui in montaggio la pelle in punta "
             "va tirata al centro e ripresa verso i bordi."),
           P("<b>La scelta fatta.</b> Le lunghezze dei bordi che si cuciono tra loro (linea del puntale, bordo "
             "della mascherina, cucitura posteriore, cucitura delle fodere, bocca, occhielleria) sono state "
             "tenute uguali a quelle sulla forma. Le piccole differenze inevitabili sono state lasciate "
             "all'interno del pezzo e verso il margine di montaggio, dove il montaggio le assorbe."),
           figura(os.path.join(FIG, "deformazione.png"), LARGH,
                  "Figura 5. Dove il pezzo in piano differisce dalla forma. Bianco: nessuna differenza. "
                  "Rosso: in piano il pezzo è più grande e la pelle va ripresa. Blu: in piano è più piccolo e "
                  "la pelle va tirata. Nel puntale il centro va tirato e il bordo ripreso, come in montaggio."),
           ]
    def err(n):
        return numero(pz[n]["errore_sviluppo_pct"])
    st += [KeepTogether([
        P("Differenza media tra le lunghezze sulla forma e quelle in piano, per pezzo:"),
        tabella([["Pezzi", "Differenza media", "Perché"],
                 ["Quartieri, fodere quartiere, bacchetta, sottopiede",
                  f"{err('sottopiede')}–{err('fodera_quartiere_interno')}%", "fianchi quasi piatti"],
                 ["Mascherina, linguetta", f"{err('mascherina')}–{err('linguetta')}%", "curvatura del collo piede"],
                 ["Contrafforte, fodera avampiede", f"{err('contrafforte')}–{err('fodera_avampiede')}%",
                  "avvolgono tallone e punta"],
                 ["Puntale, rinforzo puntale", f"{err('rinforzo_puntale')}–{err('puntale')}%",
                  "punta curva in due direzioni"]],
                [72 * mm, 32 * mm, LARGH - 104 * mm], allinea_dx=(1,))])]

    st += [P("3.2 Convenzioni di disegno", "h2"),
           *punti(["Scala 1:1, misure in millimetri.",
                   "Ogni cartamodello è della <b>scarpa destra</b>, visto dal lato esterno (lato fiore). "
                   "Per la sinistra si usa lo stesso cartamodello rovesciato: per questo il cartiglio "
                   "riporta «2 per paio (dx + sx speculare)».",
                   "Tallone a sinistra e punta a destra. I pezzi del fianco (quartieri, fodere quartiere, "
                   "contrafforte, bacchetta) hanno la bocca in alto, quindi il quartiere interno ha la punta "
                   "a sinistra. Il sottopiede è visto dall'alto, dal lato del piede.",
                   "La freccia del <b>verso del tiro</b> va dal tallone alla punta: è la direzione in cui la "
                   "pelle deve cedere meno. Sulla bacchetta è verticale."])]

    st += [P("3.3 Margini e riporti", "h2"),
           P("Ogni bordo del pezzo è stato classificato in base a cosa gli succede in giunteria e in "
             "montaggio. Il margine aggiunto dipende dal tipo di bordo:"),
           tabella([["Bordo", "Dove", "Margine"],
                    ["Filo forma", "puntale, mascherina, quartieri, bacchetta", "+16 mm di montaggio"],
                    ["Filo forma", "fodere, contrafforte", "+14 mm"],
                    ["Filo forma", "rinforzo puntale", "+10 mm"],
                    ["Riporto sotto la mascherina", "quartieri", "già compreso: 12 mm, scarnito 8 mm"],
                    ["Riporto sotto il puntale", "mascherina", "già compreso: 10 mm, scarnito 8 mm"],
                    ["Attacco sotto la mascherina", "linguetta", "già compreso: 14 mm, scarnito 4 mm"],
                    ["Sormonto delle fodere", "fodera avampiede sotto le fodere quartiere",
                     "già compreso: 8 mm, scarnito 6 mm"],
                    ["Bocca e occhielleria", "quartieri", "0: bordo a vista, tagliato a vivo"],
                    ["Bocca e occhielleria", "fodere quartiere", "+3 mm, da rifilare dopo la cucitura"],
                    ["Cucitura posteriore", "quartieri e fodere quartiere", "0: accostata a zig-zag, "
                                                                            "coperta dalla bacchetta"],
                    ["Contorno", "sottopiede", "0: segue il fondo forma"]],
                   [44 * mm, 62 * mm, LARGH - 106 * mm])]
    angolo = immagine(os.path.join(FIG, "angolo.png"), 86 * mm)
    st += [Spacer(1, 6), Table([[
        [P("<b>Gli angoli.</b> Dove il margine di montaggio incontra un bordo che non ha margine, per "
           "esempio il bordo della mascherina o la cucitura posteriore, il margine si chiude sul "
           "prolungamento di quel bordo, come si traccia a mano. Così non restano scalini né sporgenze, e "
           "la tacca del bordo cade sulla linea di taglio."),
         P("Figura 6. Angolo della mascherina tra bordo a vista e margine di montaggio.", "didascalia")],
        angolo]], colWidths=[LARGH - 92 * mm, 92 * mm],
        style=[("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0)])]

    st += [P("3.4 Cosa c'è disegnato sul cartamodello", "h2"),
           tabella([["Segno", "Significato"],
                    [campione("taglio"), "<b>Linea di taglio</b>, comprensiva dei margini."],
                    [campione("montaggio"), "<b>Filo forma</b>: dove la tomaia arriva sul fondo della forma "
                                            "e comincia il margine di montaggio. Serve anche da riferimento in "
                                            "montaggio."],
                    [campione("cucitura"), "<b>Cucitura</b>: doppia a 1,6 e 3,6 mm su puntale e mascherina; a "
                                           "2 mm su bocca e occhielleria; a 1,5 mm sulla bacchetta. Circa 3 "
                                           "punti per cm."],
                    [campione("scarnitura"), "<b>Limite della scarnitura</b>, con la larghezza scritta: 8 mm sui "
                                             "riporti di quartieri e mascherina, 6 mm sulle fodere, 10 mm su "
                                             "contrafforte e rinforzo puntale, 4 mm sulla linguetta."],
                    [campione("riferimento"), "<b>Linea di sovrapposizione</b>: dove appoggia il bordo del pezzo "
                                              "che sta sopra. Mascherina e bacchetta sui quartieri, puntale "
                                              "sulla mascherina, mascherina e occhielleria sulla linguetta, "
                                              "fodere quartiere sulla fodera avampiede."],
                    [campione("asse"), "<b>Asse della forma</b>, sui pezzi centrali: puntale, mascherina, "
                                       "linguetta, fodera avampiede, rinforzo, contrafforte, bacchetta, "
                                       "sottopiede, suola, tacco."],
                    [campione("tacche"), "<b>Tacche</b> sul contorno di taglio, agli estremi dell'asse e delle "
                                         "linee di sovrapposizione: servono ad allineare i pezzi in giunteria."],
                    [campione("fori"), "<b>Fori occhielli</b>: 5 per lato, Ø 3,6 mm, a 9 mm dal bordo, passo "
                                       "10–11 mm. Sulle fodere quartiere sono segnati come riferimento, da "
                                       "forare insieme alla tomaia."],
                    [campione("testo"), "<b>Cartiglio</b> (nome, modello, materiale, quantità) e freccia del "
                                        "verso del tiro."]],
                   [24 * mm, LARGH - 24 * mm]),
           Spacer(1, 8),
           figura(os.path.join(FIG, "quartiere_annotato.png"), LARGH * 0.8,
                  "Figura 7. Il cartamodello del quartiere esterno con i suoi segni.")]

    st += [Spacer(1, 4), P("3.5 Il fondo", "h2"),
           *punti([f"<b>Suola</b>: segue la curva del fondo forma (enfranchimento e slancio di punta). Sviluppata "
                   f"lungo questa curva è lunga {numero(pz['suola']['ingombro_mm'][0])} mm contro 287,6 mm della "
                   "sua impronta in pianta: 3,6 mm in più, che si perderebbero tagliandola sulla sola impronta. "
                   "Sono segnati l'asse e il petto del tacco, a 76 mm dal tallone.",
                   "<b>Alzi del tacco</b>: 4 per tacco, 8 per paio, con il contorno del tacco. Il primo, sotto la "
                   "suola, va lavorato a cuneo per seguire la curva della seggetta. <b>Sopratacco</b> in gomma "
                   "di 6 mm con lo stesso contorno.",
                   f"<b>Guardolo</b> a giro completo: striscia 12 × {numero(pz['guardolo']['ingombro_mm'][0], 0)} mm, "
                   "compresa una giunta di 10 mm al tallone.",
                   "<b>Sottopiede</b>: il contorno del fondo forma, senza margine."]),
           figura(os.path.join(FIG, "suola.png"), LARGH * 0.85,
                  "Figura 8. Profilo della suola: la sua lunghezza lungo la curva è maggiore della proiezione "
                  "in pianta.")]

    st += [P("3.6 I 17 cartamodelli", "h2"),
           figura(os.path.join(FIG, "cartamodelli.png"), LARGH * 0.85,
                  "Figura 9. Tutti i cartamodelli alla stessa scala (ridotta). Il guardolo è accorciato.")]
    righe = [["Pezzo", "Materiale", "mm", "Q.tà/paio", "Ingombro mm", "Area cm²"]]
    for p in rie["pezzi"]:
        righe.append([p["titolo"], p["materiale"].rsplit(" ", 2)[0] if p["materiale"][-2:] == "mm"
                      else p["materiale"], numero(p["spessore_mm"], 1), str(p["quantita_paio"]),
                      f"{p['ingombro_mm'][0]:.0f} × {p['ingombro_mm'][1]:.0f}", numero(p["area_cm2"])])
    st.append(tabella(righe, [40 * mm, 48 * mm, 12 * mm, 18 * mm, 27 * mm, LARGH - 145 * mm],
                      allinea_dx=(2, 3, 4, 5)))

    st += [P("3.7 Verifiche", "h2"),
           P("Prima della consegna sono stati confrontati, in piano, i bordi che in giunteria si cuciono tra "
             "loro. Le due cuciture posteriori sono identiche; gli altri accoppiamenti differiscono di pochi "
             "millimetri su lunghezze di 130–185 mm, una differenza che si recupera facendo lavorare la pelle "
             "in giunteria."),
           tabella([["Bordi a confronto", "A mm", "B mm", "Differenza"]] +
                   [[c["controllo"].capitalize(), numero(c["a_mm"]), numero(c["b_mm"]),
                     f"{numero(abs(c['differenza_mm']))} mm ({numero(abs(c['differenza_pct']))}%)"]
                    for c in ctr],
                   [86 * mm, 20 * mm, 20 * mm, LARGH - 126 * mm], allinea_dx=(1, 2, 3)),
           Spacer(1, 4),
           P("A e B sono, nell'ordine, i due bordi indicati nella prima colonna (per esempio il bordo del "
             "puntale e la linea del puntale disegnata sulla mascherina).", "nota"),
           P("3.8 Consumi stimati per paio", "h2"),
           P("Somma delle aree dei cartamodelli, con margini, moltiplicata per la quantità per paio. Lo sfrido "
             "è una stima: 20% sul vitello, 15% sulla fodera, 10% sugli altri materiali."),
           tabella([["Materiale", "Netto dm²", "Con sfrido dm²"]] +
                   [[k, numero(v["netto_dm2"]), numero(v["lordo_dm2"])] for k, v in cons.items()],
                   [80 * mm, 30 * mm, 34 * mm], allinea_dx=(1, 2))]

    st += [P("3.9 I file e come usarli", "h2"),
           tabella([["File", "Uso"],
                    ["Piani di taglio (PDF)", "Prima pagina: tavola riassuntiva. Poi un foglio A3 per pezzo. "
                                              "Stampare al 100% senza adattamento e controllare il quadrato di "
                                              "50 × 50 mm. Il guardolo non entra nel foglio: usare DXF o SVG."],
                    ["DXF, uno per pezzo e uno complessivo", "Per CAD, plotter e macchine da taglio. Ogni segno sta "
                                                             "su un proprio livello (TAGLIO, MONTAGGIO, CUCITURA, "
                                                             "SCARNITURA, RIFERIMENTO, ASSE, TACCHE, FORI, TESTO): "
                                                             "per esempio si possono mandare al taglio solo TAGLIO "
                                                             "e FORI."],
                    ["SVG, uno per pezzo", "Stesso contenuto, per i programmi di grafica."],
                    ["Riepilogo", "Aree, ingombri, consumi e verifiche in un unico file di dati."],
                    ["Visualizzatore 3D", f'<link href="{LINK_3D}" color="#2c64a8">scarpa 3D interattiva</link>, '
                                          "con esploso e scheda di ogni pezzo."]],
                   [50 * mm, LARGH - 50 * mm]),
           Spacer(1, 4),
           P("I file dei piani di taglio sono nella cartella <i>scarpa_oxford/output/piani_2d</i> del "
             "repository.", "nota")]

    # 5. Limiti -------------------------------------------------------------------
    st += [KeepTogether([P("4. Limiti e prossimi passi", "h1"),
           *punti(["Le proporzioni della forma e le linee di modello sono standard e non vengono da un modello "
                   "esistente: vanno riviste dal modellista.",
                   "Prima di tagliare la pelle conviene una prova su forma con i cartamodelli in carta o tela, "
                   "poi un paio campione.",
                   "Margini (16, 14 e 10 mm), rifilatura delle fodere (3 mm) e sfrido sono valori correnti che ho "
                   "scelto io: vanno adattati alle abitudini della vostra produzione.",
                   "La fodera della linguetta ha lo stesso contorno della linguetta.",
                   "Tutto è in taglia 42: lo sviluppo delle altre taglie è ancora da fare."])])]
    return st


def main():
    out = os.path.join(QUI, "relazione_oxford_42.pdf")
    doc = BaseDocTemplate(out, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                          topMargin=18 * mm, bottomMargin=20 * mm,
                          title="Oxford cap-toe uomo tg 42 - Dalla forma ai piani di taglio",
                          author="Claude", subject="Relazione sul lavoro svolto")
    cornice = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="corpo")
    doc.addPageTemplates([PageTemplate(id="copertina", frames=[cornice], onPage=copertina),
                          PageTemplate(id="corpo", frames=[cornice], onPage=piede)])
    doc.build([NextPageTemplate("corpo"), PageBreak()] + contenuto())
    print(out)


if __name__ == "__main__":
    main()
