"""Translations. Code and default layouts are written in English; _() returns the active language.

Adding a language: add it to LANGUAGES and give it a table like IT (missing strings stay in English).
Layout texts are translated as whole strings, so a user-typed text that is not in the table is shown as is.
"""
LANGUAGES = {"it": "Italiano", "en": "English"}
_lang = "it"

DATES = {
    "en": {"weekdays": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
           "short": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
           "months": ["January", "February", "March", "April", "May", "June", "July", "August",
                      "September", "October", "November", "December"]},
    "it": {"weekdays": ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"],
           "short": ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"],
           "months": ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
                      "settembre", "ottobre", "novembre", "dicembre"]},
}

IT = {
    # --- screen texts (default layouts and widgets)
    "SYSTEM": "SISTEMA", "CORES": "CORE", "DISK": "DISCO", "WEATHER": "METEO", "MARKETS": "MERCATI",
    "HARDWARE": "HARDWARE", "AGENTS": "AGENTI", "CALENDAR": "CALENDARIO", "NOTIFICATIONS": "NOTIFICHE",
    "up for {system.uptime:hm}": "acceso da {system.uptime:hm}",
    "Nothing playing": "Niente in riproduzione", "No active session": "Nessuna sessione attiva",
    "Waiting for data…": "In attesa dei dati…", "context": "contesto", "output": "output", "turns": "turni",
    "cost{claude.0.cost:hide}": "costo{claude.0.cost:hide}",
    "Limit 5 h  {claude.0.rate_limits.five_hour.used_percentage:.0f}%":
        "Limite 5 ore  {claude.0.rate_limits.five_hour.used_percentage:.0f}%",
    "Limit 7 days  {claude.0.rate_limits.seven_day.used_percentage:.0f}%":
        "Limite 7 giorni  {claude.0.rate_limits.seven_day.used_percentage:.0f}%",
    "reset {claude.0.rate_limits.five_hour.resets_at:reset}": "reset {claude.0.rate_limits.five_hour.resets_at:reset}",
    "Feels like {weather.feels:.0f}° · Humidity {weather.humidity}% · Wind {weather.wind:.0f} km/h":
        "Percepita {weather.feels:.0f}° · Umidità {weather.humidity}% · Vento {weather.wind:.0f} km/h",
    "No upcoming events": "Nessun evento in arrivo", "No notifications": "Nessuna notifica",
    "No agents running": "Nessun agente attivo",
    "Today": "Oggi", "Tomorrow": "Domani", "all day": "tutto il giorno",
    "Clear": "Sereno", "Mostly clear": "Poco nuvoloso", "Partly cloudy": "Parz. nuvoloso", "Overcast": "Coperto",
    "Fog": "Nebbia", "Drizzle": "Pioviggine", "Rain": "Pioggia", "Snow": "Neve", "Thunderstorm": "Temporale",
    "CPU temp": "Temp. CPU", "GPU temp": "Temp. GPU", "GPU load": "Carico GPU", "CPU load": "Carico CPU",
    "Requires administrator": "Serve amministratore", "limit": "limite", "Agent": "Agente",
    "cost{agent.cost:hide}": "costo{agent.cost:hide}",
    "Limit {agent.limits.0.label}  {agent.limits.0.pct:.0f}%": "Limite {agent.limits.0.label}  {agent.limits.0.pct:.0f}%",
    "Limit {agent.limits.1.label}  {agent.limits.1.pct:.0f}%": "Limite {agent.limits.1.label}  {agent.limits.1.pct:.0f}%",
    "Agent mascot": "Mascotte agente", "Agent (field)": "Agente (campo)", "Working when (field)": "Al lavoro se (campo)",
    "Colour (auto = agent colour)": "Colore (auto = colore dell'agente)",
    "Claude image (optional)": "Immagine Claude (facoltativa)", "Codex image (optional)": "Immagine Codex (facoltativa)",
    # --- page names
    "Clock": "Orologio", "System": "Sistema", "Media": "Media", "Weather": "Meteo", "Markets": "Mercati",
    "Hardware": "Hardware", "Agents": "Agenti", "Agenda": "Agenda", "Notifications": "Notifiche",
    "Dark": "Scuro", "Light": "Chiaro", "Neon": "Neon",
    "Screen not found: check the USB cable.": "Schermo non trovato: controlla il cavo USB.",
    # --- settings window: tabs and general
    "settings": "impostazioni", "General": "Generale", "Pages": "Pagine", "Data": "Dati", "Theme": "Tema",
    "Service": "Servizio", "Language": "Lingua", "Port": "Porta", "Orientation": "Orientamento",
    "Portrait": "Verticale", "Portrait (upside down)": "Verticale capovolto", "Landscape": "Orizzontale",
    "Landscape (upside down)": "Orizzontale capovolto", "Brightness": "Luminosità",
    "Automatic page change (s, 0 = never)": "Cambio pagina automatico (s, 0 = mai)",
    "Animation frames per second": "Fotogrammi al secondo delle animazioni",
    "Switch to the media page when a song starts": "Passa alla pagina media quando parte un brano",
    "Turn the screen off when the PC is locked": "Spegni lo schermo quando il PC è bloccato",
    "Record…": "Registra…", "Press the keys…": "Premi i tasti…", "Default": "Predefinita", "Shortcut": "Scorciatoia",
    "Record: press the button, then the key combination (Esc cancels).":
        "Registra: premi il pulsante, poi la combinazione di tasti (Esc annulla).",
    "This combination is already used by the other shortcut.": "Questa combinazione è già usata dall'altra scorciatoia.",
    "A single key will also change page every time you use it for something else. Use it anyway?":
        "Un tasto singolo cambierà pagina anche ogni volta che lo usi per altro. Usarlo comunque?",
    "Hardware sensors: CPU temperatures and power need the free PawnIO driver used by LibreHardwareMonitor. Install it "
    "from pawnio.eu, then restart the app.": "Sensori hardware: temperature e potenza della CPU richiedono il driver "
    "gratuito PawnIO usato da LibreHardwareMonitor. Installalo da pawnio.eu e riavvia l'app.",
    "max_agent_pages": "massimo pagine agente",
    "Choose stocks": "Scegli i titoli", "Choose stocks…": "Scegli titoli…", "Search": "Cerca", "All": "Tutte",
    "Symbol": "Simbolo", "Name": "Nome", "Category": "Categoria", "Add →": "Aggiungi →", "Add": "Aggiungi",
    "Other Yahoo symbol:": "Altro simbolo Yahoo:", "Chosen": "Scelti", "Cancel": "Annulla", "Symbol not found on Yahoo: ": "Simbolo non trovato su Yahoo: ",
    "With more than 5 stocks the page becomes a grid of cards.": "Con più di 5 titoli la pagina diventa una griglia di card.",
    "US stocks": "Azioni USA", "European stocks": "Azioni Europa", "Italian stocks": "Azioni Italia", "ETF": "ETF",
    "Indices": "Indici", "Commodities & FX": "Materie prime e valute", "Crypto": "Crypto",
    "Markets (list or grid)": "Mercati (lista o griglia)", "Rows up to (then grid)": "Righe fino a (poi griglia)",
    "Maximum stocks shown": "Massimo titoli mostrati", "Gap": "Spaziatura",
    "Next page shortcut": "Scorciatoia pagina successiva", "Previous page shortcut": "Scorciatoia pagina precedente",
    # --- data tab
    "Settings of the data sources used by the widgets.": "Impostazioni delle fonti di dati usate dai widget.",
    "Hardware sensors: complete (running as administrator).": "Sensori hardware: completi (in esecuzione come amministratore).",
    "Hardware sensors: CPU temperatures need the app to run as administrator.":
        "Sensori hardware: le temperature della CPU richiedono l'esecuzione come amministratore.",
    "Calendar": "Calendario", "Find city and set coordinates": "Cerca città e imposta le coordinate",
    "City not found: ": "Città non trovata: ",
    "Paste the secret iCal address of your calendars, separated by commas. Google Calendar: Settings > calendar > "
    "Integrate calendar > Secret address in iCal format. Outlook: Settings > Calendar > Shared calendars > Publish a "
    "calendar > ICS.": "Incolla l'indirizzo iCal segreto dei tuoi calendari, separati da virgole. Google Calendar: "
    "Impostazioni > calendario > Integra calendario > Indirizzo segreto in formato iCal. Outlook: Impostazioni > "
    "Calendario > Calendari condivisi > Pubblica un calendario > ICS.",
    "active_minutes": "minuti di attività", "city": "città", "context_window": "finestra di contesto", "days": "giorni",
    "disk": "disco", "hide_apps": "app da nascondere",
    "lat": "latitudine", "lon": "longitudine", "max": "massimo", "tickers": "titoli", "urls": "indirizzi iCal",
    # --- theme tab
    "Preview": "Anteprima", "Duplicate": "Duplica", "Rename": "Rinomina", "Delete": "Elimina", "Import…": "Importa…",
    "Export…": "Esporta…", "Colours": "Colori", "Background": "Sfondo", "Cards": "Riquadri", "Text": "Testo",
    "Secondary text": "Testo secondario", "Accent": "Accento", "Positive / OK": "Positivo / OK", "Warning": "Attenzione",
    "Negative / critical": "Negativo / critico", "Font": "Font", "Fonts": "Font", "Regular": "Normale", "Bold": "Grassetto",
    "From file…": "Da file…", "Text scale": "Scala del testo", "Page backgrounds": "Sfondi per pagina",
    "Choose image…": "Scegli immagine…", "Remove": "Rimuovi", "Darken": "Oscuramento", "no background": "nessuno sfondo",
    "Choose a page": "Scegli una pagina", "Backgrounds": "Sfondi", "Choose the page first.": "Scegli prima la pagina.",
    "New theme": "Nuovo tema", "Name of the new theme:": "Nome del nuovo tema:", "New name:": "Nuovo nome:",
    "It is the only theme left.": "È l'unico tema rimasto.", "Delete theme": "Elimina tema",
    "Delete the theme and its files?": "Eliminare il tema e i suoi file?", "Screen theme": "Tema schermo",
    "Import theme": "Importa tema", "Invalid file: ": "File non valido: ", "Images": "Immagini", "Error": "Errore",
    # --- service tab and tray
    "Start": "Avvia", "Stop": "Ferma", "Restart": "Riavvia", "Running": "In esecuzione", "Stopped": "Fermo",
    "Start the screen when I sign in to Windows": "Avvia lo schermo all'accesso a Windows",
    "Open log": "Apri log", "Open data folder": "Apri cartella dati", "Startup": "Avvio automatico",
    "Changes apply immediately, without restarting. This app and UsbMonitor.exe cannot run together: close UsbMonitor "
    "and remove it from startup.": "Le modifiche si applicano subito, senza riavviare. Questa app e UsbMonitor.exe non "
    "possono funzionare insieme: chiudi UsbMonitor e togli il suo avvio automatico.",
    "Enabled without administrator rights: CPU temperatures will not be available. Open the settings as administrator "
    "and enable it again.": "Attivato senza diritti di amministratore: le temperature della CPU non saranno disponibili. "
    "Apri le impostazioni come amministratore e riattivalo.",
    "Settings": "Impostazioni", "Page": "Pagina", "Next page": "Pagina successiva", "Quit": "Esci",
    # --- page editor
    "Pages on the screen": "Pagine sullo schermo", "Hide": "Togli", "Other pages": "Altre pagine",
    "▲ Show on the screen": "▲ Mostra sullo schermo", "New page": "Nuova pagina", "Duplicate page": "Duplica pagina",
    "Rename page": "Rinomina pagina", "Delete page": "Elimina pagina", "Import page…": "Importa pagina…",
    "Export page…": "Esporta pagina…", "At least one page must stay on the screen.": "Serve almeno una pagina sullo schermo.",
    "Page name:": "Nome della pagina:", "It is the last page left.": "È l'ultima pagina rimasta.",
    "Delete this page?": "Eliminare questa pagina?", "Screen page": "Pagina schermo", "Import page": "Importa pagina",
    "Copy from the other orientation": "Copia dall'altro orientamento", "Grid": "Griglia", "Guides": "Guide",
    "Undo": "Annulla", "Bring forward": "Porta avanti", "Send backward": "Porta indietro",
    "Show on screen": "Mostra sullo schermo", "Copy": "Copia", "The other orientation is empty.": "L'altro orientamento è vuoto.",
    "Replace this layout with the adapted one?": "Sostituire il layout attuale con quello adattato?",
    "Drag a widget from the palette onto the screen. Shift+click: multiple selection. Ctrl+G: group.":
        "Trascina un widget dalla tavolozza sullo schermo. Maiusc+clic: selezione multipla. Ctrl+G: raggruppa.",
    "Palette (drag onto the screen)": "Tavolozza (trascina sullo schermo)", "Layers (top = front)": "Livelli (in alto = davanti)",
    "Properties": "Proprietà", "Select a widget on the screen.": "Seleziona un widget sullo schermo.",
    "widgets selected": "widget selezionati", "Align left": "Allinea a sinistra", "Centre": "Centra",
    "Align right": "Allinea a destra", "Align top": "Allinea in alto", "Middle": "Al centro", "Align bottom": "Allinea in basso",
    "Group (Ctrl+G)": "Raggruppa (Ctrl+G)", "Ungroup": "Separa", "Choose…": "Scegli…", "+ field": "+ campo",
    "Formats: {field:.0f} {field:mmss} {field:human} {field:bytes} {field:gb} {field:hm} {field:weather} "
    "{field:weekday} {field:reset} {now:%H:%M}. Colours: level = green/yellow/red, sign = green if positive.":
        "Formati: {campo:.0f} {campo:mmss} {campo:human} {campo:bytes} {campo:gb} {campo:hm} {campo:weather} "
        "{campo:weekday} {campo:reset} {now:%H:%M}. Colori: level = verde/giallo/rosso, sign = verde se positivo.",
    # --- widget names and properties
    "Text / value": "Testo / valore", "Scrolling text": "Testo scorrevole", "Bar": "Barra", "Ring": "Anello",
    "Box": "Riquadro", "Status dot": "Pallino di stato", "Emoji": "Emoji", "Weather icon": "Icona meteo",
    "Animated weather": "Meteo animato", "Image / animated GIF": "Immagine / GIF animata", "Song cover": "Copertina brano",
    "Background from cover": "Sfondo da copertina", "Line chart": "Grafico a linea", "History chart": "Grafico storico",
    "Per-core load": "Carico per core", "Play / pause": "Play / pausa", "Stock": "Titolo di borsa",
    "Forecast day": "Giorno di previsione", "Other Claude sessions": "Altre sessioni Claude", "Agent sessions": "Sessioni agenti",
    "Calendar events": "Eventi del calendario", "Windows notifications": "Notifiche di Windows",
    "Text ({field:format})": "Testo ({campo:formato})", "Size": "Dimensione", "Colour": "Colore", "Alignment": "Allineamento",
    "When data is missing": "Se mancano i dati", "Speed (px/s)": "Velocità (px/s)", "Alignment when it fits": "Allineamento se entra",
    "Value": "Valore", "Maximum (number or field)": "Massimo (numero o campo)", "Thickness": "Spessore",
    "Corner radius": "Arrotondamento", "On when (field)": "Acceso se (campo)", "Colour when on": "Colore acceso",
    "Colour when off": "Colore spento", "Weather code": "Codice meteo", "Drops / flakes": "Gocce / fiocchi", "File": "File",
    "Fit": "Adattamento", "Blur": "Sfocatura", "Darken (0-1)": "Oscuramento (0-1)", "Series of values": "Serie di valori",
    "Time span (s)": "Intervallo (s)", "Minimum (empty = auto)": "Minimo (vuoto = automatico)",
    "Maximum (empty = auto)": "Massimo (vuoto = automatico)", "Fill below": "Riempi sotto",
    "Stock number (0 = first)": "Numero titolo (0 = primo)", "Day (0 = today)": "Giorno (0 = oggi)",
    "From session number": "Dalla sessione numero", "Row height": "Altezza riga", "From event number": "Dall'evento numero",
}


def set_language(code: str):
    global _lang
    _lang = code if code in LANGUAGES else "it"


def language() -> str:
    return _lang


def _(text: str) -> str:
    if _lang == "it":
        return IT.get(text, text)
    return text


def dates() -> dict:
    return DATES.get(_lang, DATES["en"])
