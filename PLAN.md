# Schermetto: piano di riprogettazione

Sostituire `UsbMonitor.exe` (TURZX) con un'app Python nostra, a pagine, dove aggiungere una pagina
(meteo, borsa, media player, ...) voglia dire aggiungere **un file**.

## 1. Cosa abbiamo scoperto

| Cosa | Valore |
|---|---|
| Dispositivo | Turing Smart Screen 3.5" **Revision A** ("UsbMonitor") |
| USB | `VID 1A86`, `PID 5722`, seriale `USB35INCHIPSV2` |
| Porta | **COM8** (gli script vecchi usavano COM3) |
| Risoluzione | 320x480 (portrait), ruotabile a 480x320 |
| Formato pixel | RGB565 little-endian, **raw** (niente JPEG) |
| Baud | 115200 (CDC USB: il valore conta poco, il limite è il firmware) |

Gli script in `C:\Program Files\PROGRAMMA_SCHERMETTO\` (`turing_*.py`) **non possono funzionare**:
usano header `EF BE ...` + JPEG o `EE A1 ...`, che non sono il protocollo di questo schermo, e la porta
sbagliata. Da riutilizzare solo le idee: lettura media da Windows (SMTC/winsdk) con copertina, e la
pagina con copertina sfocata.

### Protocollo Rev A (verificato sul codice di riferimento `mathoudebine/turing-smart-screen-python`)

Ogni comando = 6 byte con coordinate impacchettate a 10 bit:

```
b0 = x >> 2
b1 = ((x & 3) << 6) | (y >> 4)
b2 = ((y & 15) << 4) | (ex >> 6)
b3 = ((ex & 63) << 2) | (ey >> 8)
b4 = ey & 255
b5 = comando
```

| Comando | Codice | Note |
|---|---|---|
| HELLO | 69 | 6 byte `0x45`; risposta `01 01 01 01 01 01` = UsbMonitor 3.5" |
| RESET | 101 | la porta COM può cambiare, riaprire dopo ~5 s |
| CLEAR | 102 | va fatto in portrait |
| SCREEN_OFF / ON | 108 / 109 | |
| SET_BRIGHTNESS | 110 | x = 255 - (pct * 2.55); 0 = massima luminosità |
| SET_ORIENTATION | 121 | pacchetto da 16 byte: i 6 sopra + `orient+100`, width(2B BE), height(2B BE) |
| DISPLAY_BITMAP | 197 | (x0,y0,x1,y1) poi i pixel RGB565 LE, inviati a blocchi di `width*8` byte |

Orientamenti: 0 portrait, 1 reverse portrait, 2 landscape, 3 reverse landscape.

Licenza: la repo di riferimento è GPL-3. Reimplementiamo il protocollo (≈80 righe) invece di copiarne il
codice, così la nostra app resta libera da vincoli.

## 2. Architettura

```
schermetto/
  main.py               avvio: config → driver → loop
  config.toml           porta, orientamento, luminosità, pagine attive e loro impostazioni
  screen.py             driver Rev A (open/autodetect, hello, orientation, brightness, bitmap, reconnect)
  sources/              chi raccoglie i dati (task asyncio, ognuno col suo intervallo)
    system.py           CPU, RAM, disco, rete (psutil)
    media.py            brano, artista, posizione, copertina (Windows SMTC via winsdk)
    weather.py          Open-Meteo (gratuito, senza chiave API)
    stocks.py           quotazioni (Yahoo chart endpoint; alternativa Stooq)
  pages/                una pagina = un file, scoperta automaticamente
    clock.py
    system.py
    media.py
    weather.py
    stocks.py
  assets/               font (TTF) e icone
  preview.py            renderizza le pagine in PNG senza schermo (per sviluppare)
```

### Flusso dati

```
sources/*  --(scrivono)-->  state: dict condiviso  --(leggono)-->  pagina attiva
                                                                     │ render(state) -> PIL.Image
                                                                     ▼
                                    diff col frame precedente (ImageChops.difference().getbbox())
                                                                     ▼
                                    screen.show(crop, x, y)   ← invia SOLO il rettangolo cambiato
```

Il diff è la scelta che rende l'app fluida: un frame intero sono 307 KB e su Rev A un full refresh
richiede circa un secondo; un orologio che cambia ne manda pochi KB.

### Contratto di una pagina

```python
# pages/weather.py
from PIL import Image, ImageDraw

name = "weather"
interval = 60          # ogni quanti secondi ridisegnare
needs = ["weather"]    # quali source avviare (solo se la pagina è attiva)

def render(state, size, cfg) -> Image.Image:
    img = Image.new("RGB", size, "black")
    d = ImageDraw.Draw(img)
    w = state.get("weather")
    d.text((20, 20), f"{w['temp']}°C" if w else "...", fill="white")
    return img
```

Niente classi base né registri: `main.py` importa ogni file in `pages/` e usa `name`, `interval`,
`needs`, `render`. Aggiungere una pagina = copiare un file e abilitarlo in `config.toml`.
Le source hanno lo stesso schema: `name`, `interval`, `async def fetch(cfg) -> dict`.

### Navigazione tra pagine

- Rotazione automatica ogni N secondi (configurabile, disattivabile).
- Hotkey globali (`keyboard`, come negli script vecchi): `ctrl+shift+→/←`.
- Priorità media: quando parte un brano si passa alla pagina media (opzionale da config).

### Config d'esempio

```toml
port = "AUTO"            # o "COM8"
orientation = "portrait"
brightness = 40
rotate_seconds = 15

pages = ["clock", "system", "media", "weather", "stocks"]

[weather]
lat = 45.46
lon = 9.19
city = "Milano"

[stocks]
tickers = ["AAPL", "NVDA", "BTC-USD"]
```

### Dipendenze

Già presenti nel `.venv` del vecchio programma, quindi nessuna novità: `pyserial`, `Pillow`, `psutil`,
`winsdk`, `requests`, `keyboard`. Config con `tomllib` (standard da Python 3.11).
RGB565 con `img.tobytes("raw", "BGR;16")` di Pillow, senza numpy (da verificare in Fase 0).

## Stato (10/11/2026)

- [x] Fase 0: protocollo verificato sullo schermo (full frame 1,95 s, rettangolo piccolo 38 ms)
- [x] Fase 1-3: driver, loop con diff, pagine clock/system/media/claude/weather/stocks, hotkey, `preview.py`, `test_core.py`
- [x] App impostazioni `settings.py` (Tkinter): generale, pagine (ordine + impostazioni + cerca città), tema
      (colori, font, scala, sfondi per pagina, duplica/rinomina/elimina/importa/esporta, anteprima), servizio
- [x] Modifiche applicate dal vivo (main.py rilegge `config.json` e `themes/<tema>/theme.json` ogni secondo)
- [x] Tray, avvio automatico al login (registro HKCU\...\Run), avvia/ferma, spegnimento con PC bloccato
- [x] Statusline Claude configurata in `~/.claude/settings.json` (badge ponytail incluso)
- [x] Pagine a widget: `widgets.py` (17 tipi), `layout.py`, `layouts/<id>.json` con layout verticale e
      orizzontale; editor drag & drop in `editor.py` (scheda Pagine), fonti dati nella scheda Dati
- [ ] Verificare i nomi dei campi della statusline (costo, rate_limits) sul primo JSON reale in `~/.schermetto/claude/`

### Campi utilizzabili nei widget

Testi con `{percorso:formato}`, es. `{system.cpu:.0f}%`, `{stocks.0.price:,.2f}`, `{now:%H:%M}`.
Fonti: `system.*`, `media.*`, `weather.*` (+ `weather.days.N.*`), `stocks.N.*`, `claude.N.*`, `now`, `date.*`.
Formati extra: `mmss`, `hm`, `human`, `bytes`, `gb`, `meteo`, `giorno`, `reset`, `hide`.
Un widget nuovo = una classe con `@widget` in `widgets.py`.

### File e formati

| File | Cosa |
|---|---|
| `config.json` | impostazioni generali + una sezione per pagina (scritta da settings.py) |
| `themes/<id>/theme.json` | `name`, `colors` (bg, card, fg, muted, accent, good, warn, bad), `font` (regular, bold, scale), `backgrounds` (pagina → immagine), `background_dim` |
| `*.schermetto-theme` | zip piatto della cartella del tema: si condivide e si importa da settings.py |
| `schermetto.pid` / `stop.flag` | usati da service.py per sapere se gira e chiederne l'arresto |

### Pagina Claude Code

`sources/claude.py` legge i transcript `~/.claude/projects/*/*.jsonl` toccati negli ultimi 30 minuti:
modello, contesto usato (input + cache dell'ultima richiesta), token di output, turni, sessione attiva/in attesa.
Costo, dimensione reale della finestra di contesto e limiti del piano (5 ore / 7 giorni) esistono solo nel JSON
che Claude Code passa alla statusline: `claude_statusline.py` lo salva in `~/.schermetto/claude/`.
Per attivarla, in `~/.claude/settings.json`:

```json
"statusLine": {"type": "command",
  "command": "C:\\PROJECT\\schermetto\\.venv\\Scripts\\python.exe C:\\PROJECT\\schermetto\\claude_statusline.py"}
```

Altri agent (Codex, Gemini CLI, ...): stesso schema, una source che legge i loro log di sessione.

## 3. Piano di esecuzione

Ogni fase si chiude con un controllo concreto sullo schermo vero.

**Fase 0: prova del protocollo** (prima di tutto il resto)
- Chiudere `UsbMonitor.exe` (tiene occupata COM8).
- Script di prova: apri COM8 → HELLO (aspettarsi `01×6`) → orientamento → luminosità → riempi lo schermo
  di rosso → disegna un riquadro 100x100 verde a (50,50).
- Fatto quando: colori giusti (non invertiti), riquadro nella posizione corretta, misurato il tempo di
  un full frame.

**Fase 1: driver + loop + pagina orologio**
- `screen.py` con autodetect della porta, riconnessione se il cavo si stacca, invio a rettangoli.
- `main.py` con loop asyncio, diff dei frame, caricamento delle pagine.
- `pages/clock.py` + `preview.py`.
- Fatto quando: l'orologio aggiorna ogni secondo, staccare e riattaccare l'USB non fa crashare l'app.

**Fase 2: pagine sistema e media**
- `sources/system.py`, `sources/media.py` (porta il codice SMTC già scritto, copertina inclusa).
- `pages/system.py` (barre/grafici CPU-RAM), `pages/media.py` (copertina, titolo, barra progresso).
- Hotkey e rotazione automatica.
- Fatto quando: si cambia pagina da tastiera e la pagina media segue Spotify/YouTube.

**Fase 3: meteo e borsa**
- `sources/weather.py` (Open-Meteo), `sources/stocks.py` con cache e gestione offline
  (mostra l'ultimo dato e l'orario, non crasha senza rete).
- Fatto quando: entrambe le pagine si aggiornano e reggono un'ora senza rete.

**Fase 4: grafica**
- Font TTF veri (i default di Pillow sono minuscoli), icone meteo, tema colori comune.
- Testi lunghi troncati o a scorrimento.

**Fase 5: avvio automatico e uso quotidiano**
- Avvio al login (Utilità di pianificazione, `pythonw.exe` senza finestra).
- Log su file, spegnimento schermo quando il PC va in standby/blocco.
- Disinstallare/disabilitare l'avvio automatico di `UsbMonitor.exe`.

### Fuori scope per ora (aggiungibili dopo)

- Temperature CPU/GPU: su Windows `psutil` non le legge, serve LibreHardwareMonitor (servizio a parte).
- Editor grafico dei temi e lettura dei vecchi file `.data` di TURZX: formato proprietario, non serve
  per avere le pagine nuove.
- Icona nella tray (`pystray`), pagine touch (lo schermo non è touch).

## 4. Rischi

- **Velocità**: senza diff dei frame le animazioni sono impossibili; grafici e copertine vanno ridisegnati
  solo quando cambiano.
- **Porta occupata**: la nostra app e `UsbMonitor.exe` non possono girare insieme.
- **API borsa**: gli endpoint gratuiti di Yahoo non sono ufficiali e possono cambiare: tenere la source
  isolata in un file per poterla sostituire.
- **Firmware**: alcuni schermi Rev A si bloccano se ricevono comandi troppo ravvicinati; in quel caso
  un piccolo `sleep` dopo ogni comando.
