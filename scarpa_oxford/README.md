# Oxford uomo cap-toe – modello 3D

Oxford classica (allacciatura chiusa, puntale riportato, 5 occhielli) costruita
sulla forma `forma_3d` (tg 42, tacco 25 mm). Ogni pezzo della tomaia è ritagliato
sulla superficie della forma lungo le linee di modello, così da poterlo poi
sviluppare in piano per i piani di taglio.

![Viste](output/anteprima_oxford.png)
![Esploso](output/esploso_oxford.png)

## Pezzi (per scarpa destra; quantità per paio = 2)

| Pezzo | Materiale | Spess. | Area su forma | Bordi |
|---|---|---|---|---|
| Puntale | vitello box | 1,3 | 65 cm² | linea puntale (a vista, doppia cucitura), filo forma |
| Mascherina | vitello box | 1,3 | 128 cm² | gola + cucitura sui quartieri (a vista, doppia), riporto 10 mm sotto il puntale, filo forma |
| Quartiere esterno / interno | vitello box | 1,3 | 118 cm² | bocca, occhielleria, cucitura posteriore, riporto 12 mm sotto la mascherina, filo forma |
| Bacchetta posteriore | vitello box | 1,3 | 12 cm² | bordi a vista, bocca, filo forma |
| Linguetta | vitello box | 1,4 | 49 cm² | bordo libero, attacco 14 mm sotto la mascherina |
| Fodera avampiede | vitello fodera | 0,8 | 234 cm² | riporto 8 mm sotto le fodere quartiere, filo forma |
| Fodera quartiere esterno / interno | vitello fodera | 0,8 | 88 cm² | bocca, occhielleria, cucitura posteriore, cucitura fodere (20 mm dietro la mascherina) |
| Contrafforte | termoplastico/cuoio | 1,6 | 67 cm² | bordo scarnito, filo forma |
| Rinforzo puntale | termoadesivo | 1,0 | 71 cm² | bordo scarnito (4 mm oltre la linea puntale), filo forma |
| Sottopiede | cuoio/fibra | 2,5 | 187 cm² | contorno del fondo forma |

Fondo: guardolo 360° (cuoio 3 mm), suola cuoio 5 mm (contorno a 4–6,5 mm dalla forma),
tacco 25 mm in 4 alzi più sopratacco in gomma 6 mm, petto tacco a 76 mm.

Ordine degli strati dalla forma verso l'esterno: sottopiede → fodera avampiede →
linguetta → fodere quartiere → contrafforte / rinforzo puntale → quartieri →
mascherina → puntale / bacchetta. I bordi di riporto sono scarniti nel 3D.

## Linee di modello principali (tg 42)

- Gola (fine allacciatura) a 156 mm dal tallone; mascherina che scende al filo forma a ~123 mm.
- Linea puntale inclinata: 219 mm dal tallone sul dorso, 211 mm al filo forma (puntale ≈ 61 mm).
- Bocca: altezza posteriore 59 mm sopra la seggetta, punto più basso 48 mm sotto i malleoli.
- Occhielleria: luce 0–9 mm, occhielli Ø 3,6 mm a 9 mm dal bordo, passo 10–11 mm.
- Le linee sono tabelle in testa a `genera_oxford.py`: modificandole si cambia il modello.

## File

| File | Contenuto |
|---|---|
| `output/oxford_42_dx.glb`, `_sx.glb` | scarpa completa, un nodo per pezzo (con cuciture, occhielli, lacci) |
| `output/camicie/<pezzo>.obj` | superficie del pezzo sulla forma fino al filo forma: base per lo sviluppo 2D |
| `output/pezzi.json` | materiale, spessore, quantità, area; bordi come polilinee 3D con tipo e margine; cuciture; posizioni occhielli; contorni di suola, guardolo e tacco |
| `output/visualizzatore.html` | visualizzatore interattivo (esploso, colori per pezzo, scheda pezzo) |

Per aprire il visualizzatore in locale: `cd output && python3 -m http.server`, poi
`http://localhost:8000/visualizzatore.html`.

## Verso i piani di taglio 2D

Ogni camicia è una superficie aperta in mm con i bordi già classificati in `pezzi.json`:

- `filo_forma` → aggiungere il margine di montaggio (16 mm);
- `riporto_*`, `fodera_riporto`, `linguetta_attacco`, `centro_sotto_mascherina` → sovrapposizioni già comprese nel pezzo;
- `bocca`, `occhielleria`, `mascherina`, `puntale`, `bacchetta` → bordi a vista, con le file di cucitura indicate;
- `cucitura_posteriore` → cucitura accostata, nessun margine.

## Rigenerare

```bash
pip install -r ../forma_3d/requirements.txt shapely triangle
python3 genera_oxford.py            # --stl per un STL per pezzo
python3 visualizzatore/impacchetta.py
cd anteprima && npm install && node shot.mjs && python3 componi.py
```

Il modello è costruito con regole geometriche: proporzioni e linee vanno
verificate da un modellista prima della produzione. La fodera della linguetta
non è modellata (stesso cartamodello della linguetta).
