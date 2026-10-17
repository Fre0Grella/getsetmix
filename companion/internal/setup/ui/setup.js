"use strict";
// GetSetMix Setup. The Go side owns the facts and does the work; this page
// asks one question per screen and shows progress. It polls /api/state.

const STR = {
  en: {
    setup: "Setup",
    rChoose: "Choose", rConnect: "Connect server", rServer: "Server", rComputer: "This computer",
    rInstall: "Install", rDone: "Done", rSetUp: "Set up",
    next: "Continue", back: "Back", install: "Install", close: "Close", tryAgain: "Try again",
    change: "Change…", copy: "Copy", copied: "Copied",

    welcomeTitle: "Set up GetSetMix",
    welcomeLede: "Send tracks from YouTube or SoundCloud straight into Rekordbox. First, where should GetSetMix run?",
    localTitle: "Just this computer",
    localDesc: "GetSetMix opens in its own window while you use it and puts tracks straight into Rekordbox.",
    localMeta: "Nothing else to set up.",
    localNone: "Not available for this computer yet: use a home server.",
    serverTitle: "With my home server",
    serverDesc: "Always on, so you can send tracks from your phone. This computer gets them in Rekordbox, and the server keeps the full collection as a backup.",
    serverMeta: "You'll paste one command on the server.",

    connectTitle: "Connect your server",
    connectLede: "Setup does the work on your server. It needs one command, pasted once.",
    how1: "Open a terminal on your server",
    how1d: "From this computer, type <code>ssh you@server</code> in Terminal or PowerShell, or use the server's own keyboard and screen.",
    how2: "Paste this and press Enter",
    how2d: "It may ask for your password: that's the server asking, for <code>sudo</code>.",
    how3: "Come back here",
    waiting: "Waiting for your server…",
    connected: "Connected to {0}",
    otherNet: "Server on another network?",
    otherNetD: "If your server can't reach this computer at that address, try another one:",
    kindLan: "home network", kindTailscale: "Tailscale",
    whatRuns: "What does this command run?",
    firewall: "If Windows asks whether GetSetMix Setup may use the network, choose Allow.",

    serverInstallTitle: "Install on {0}",
    existingTitle: "GetSetMix is already running here",
    existingBody: "Setup keeps it, with its tracks and settings, and connects this computer to it.",
    existingWill: "On the server, Setup will:",
    willRecreate: "run one copy at a time (two would share one database)",
    willPull: "always fetch the newest version when it restarts",
    willKeel: "install Keel and let it update GetSetMix automatically",
    willWatch: "add Watchtower to update GetSetMix automatically",
    willRestart: "restart it once, to update it now",
    runWith: "Run it with",
    noEngine: "This server has neither Docker nor Kubernetes. Setup will install Docker with its official installer (get.docker.com).",
    musicDir: "Keep the music in",
    musicDirHint: "A folder on the server. Your whole collection lives here.",
    free: "{0} GB free",
    autoUpdate: "Update automatically",
    autoUpdateDocker: "Watchtower checks for a new version every hour. Tracks and settings stay.",
    autoUpdateK8s: "Keel checks for a new version every 5 minutes. Tracks and settings stay.",
    tailscale: "Secure address with Tailscale",
    tailscaleD: "Gives {0}, which your phone needs to install GetSetMix and share to it.",
    noTailscale: "To install GetSetMix on your phone, it needs a secure (HTTPS) address. The easiest way is Tailscale: install it on the server and your phone, then run Setup again. Without it, your phone can still open GetSetMix on your home Wi-Fi.",
    getTailscale: "Get Tailscale",

    computerTitle: "This computer",
    computerLede: "New tracks come here from the server and go into Rekordbox.",
    localInstallTitle: "Install on this computer",
    localInstallLede: "GetSetMix opens in its own window while you use it. Tracks go into the folder you choose and into Rekordbox.",
    rbFound: "Rekordbox found",
    rbTracks: "{0} tracks in your collection",
    rbMissing: "Rekordbox isn't installed here",
    rbMissingD: "Tracks still download. Run Setup again after installing Rekordbox to add them to it automatically.",
    deliveryDownload: "Download them from the server",
    deliveryDownloadD: "Every 15 minutes while this computer is on, and whenever you open Rekordbox. The server keeps its copy.",
    deliverySynced: "My server's music folder is already synced here",
    deliverySyncedD: "With Nextcloud, Syncthing or similar. Setup only watches that folder.",
    saveIn: "Save tracks in",
    syncedIn: "The synced folder on this computer",
    copyExisting: "Also download the {0} tracks already on the server",
    copyExistingAll: "Also download the tracks already on the server",
    playlist: "Rekordbox playlist",
    playlistHint: "New tracks are added to this playlist.",
    pickPrompt: "Choose the folder for your tracks",
    sizeNote: "Downloads about 250 MB: GetSetMix, ffmpeg and Deno.",
    needFolder: "Choose a folder first.",

    installing: "Installing…",
    installedTitle: "Almost there",
    failedTitle: "Something went wrong",
    onServer: "On {0}",
    onComputer: "On this computer",
    waitingPlan: "Sending the plan to your server…",
    reach: "Check this computer can reach it",
    reachAsk: "Setup couldn't reach GetSetMix by itself. What address do you open it at?",
    reachPlaceholder: "http://192.168.1.10:8765",
    reachTry: "Connect",
    serverFailed: "The server stopped at this step. Fix what the details say, then run the command on the server again: Setup picks up from there.",
    pcFailed: "This computer stopped at this step. Close Setup, fix what the details say, and run it again.",
    details: "Details",

    s_docker: "Install Docker",
    s_folders: "Create the folders",
    s_app_install: "Install GetSetMix",
    s_app_adopt: "Update GetSetMix",
    s_updates: "Turn on automatic updates",
    s_start: "Start GetSetMix",
    s_link: "Connect this computer",
    s_https: "Turn on HTTPS with Tailscale",
    s_companion: "Install the Rekordbox companion",
    s_settings: "Save your choices",
    s_rekordbox: "Connect to Rekordbox",
    s_first: "Start the first download",
    s_app_local: "Download GetSetMix",
    s_ffmpeg: "Download ffmpeg",
    s_deno: "Download Deno",
    s_shortcuts_win: "Add GetSetMix to the Start menu",
    s_shortcuts_mac: "Add GetSetMix to Applications",
    s_shortcuts_other: "Add GetSetMix shortcuts",

    c_docker_install: "Docker didn't install.",
    c_folders: "The folders couldn't be created.",
    c_pull: "The GetSetMix image couldn't be downloaded. Is the server online?",
    c_run: "Docker couldn't start GetSetMix. Is something else using the port?",
    c_watchtower: "Watchtower couldn't start.",
    c_health: "GetSetMix didn't start in time.",
    c_link: "This computer couldn't be added to the server.",
    c_no_port: "The existing GetSetMix doesn't publish a port, so nothing can reach it.",
    c_patch: "The existing deployment couldn't be changed.",
    c_keel: "Keel couldn't be installed.",
    c_restart: "GetSetMix couldn't be restarted.",
    c_apply: "Kubernetes refused the GetSetMix manifest.",
    c_tailscale: "Tailscale couldn't turn on HTTPS. In the Tailscale admin console, enable MagicDNS and HTTPS certificates, then run Setup again.",
    c_update: "The update didn't finish; GetSetMix keeps running its current version.",

    doneTitle: "GetSetMix is ready",
    doneLocalTitle: "GetSetMix is installed",
    yourGsm: "Your GetSetMix",
    open: "Open",
    openApp: "Open GetSetMix",
    showFolder: "Show folder",
    phoneTitle: "On your phone",
    phone1: "<strong>Scan this</strong> with your phone's camera.",
    phone2: "In Chrome, tap <strong>⋮</strong> then <strong>Install app</strong>.",
    phone3: "From YouTube or SoundCloud, <strong>Share</strong> a track to <strong>GetSetMix</strong>.",
    phoneHttp: "Your phone can open this address on your home Wi-Fi. Installing it and sharing to it need a secure (HTTPS) address: set up Tailscale on the server and run Setup again.",
    rbLauncher: "Open Rekordbox with <strong>Rekordbox (GetSetMix)</strong> from now on: it adds new tracks before Rekordbox starts.",
    rbScheduled: "New tracks also download every 15 minutes while this computer is on, into {0}.",
    rbSynced: "Tracks arrive through your sync app in {0}.",
    rbNone: "Install Rekordbox, then run Setup again to add tracks to it automatically.",
    localDone: "Open GetSetMix from the Start menu or the desktop. Tracks go to {0}.",
    localDoneMac: "Open GetSetMix from Applications. Tracks go to {0}.",
    demo: "Demo: nothing is installed",
  },
  it: {
    setup: "Installazione",
    rChoose: "Scelta", rConnect: "Collega il server", rServer: "Server", rComputer: "Questo computer",
    rInstall: "Installa", rDone: "Fatto", rSetUp: "Configura",
    next: "Continua", back: "Indietro", install: "Installa", close: "Chiudi", tryAgain: "Riprova",
    change: "Cambia…", copy: "Copia", copied: "Copiato",

    welcomeTitle: "Installa GetSetMix",
    welcomeLede: "Manda tracce da YouTube o SoundCloud direttamente in Rekordbox. Prima di tutto: dove deve girare GetSetMix?",
    localTitle: "Solo questo computer",
    localDesc: "GetSetMix si apre in una sua finestra mentre lo usi e mette le tracce direttamente in Rekordbox.",
    localMeta: "Nient'altro da configurare.",
    localNone: "Non ancora disponibile per questo computer: usa un server di casa.",
    serverTitle: "Con il mio server di casa",
    serverDesc: "Sempre acceso, così puoi mandare tracce dal telefono. Questo computer le riceve in Rekordbox e il server tiene la collezione completa come backup.",
    serverMeta: "Incollerai un solo comando sul server.",

    connectTitle: "Collega il tuo server",
    connectLede: "Il lavoro sul server lo fa l'installazione. Serve un solo comando, da incollare una volta.",
    how1: "Apri un terminale sul server",
    how1d: "Da questo computer scrivi <code>ssh tu@server</code> nel Terminale o in PowerShell, oppure usa tastiera e schermo del server.",
    how2: "Incolla questo e premi Invio",
    how2d: "Potrebbe chiederti la password: è il server che la chiede, per <code>sudo</code>.",
    how3: "Torna qui",
    waiting: "In attesa del server…",
    connected: "Collegato a {0}",
    otherNet: "Il server è su un'altra rete?",
    otherNetD: "Se il server non raggiunge questo computer a quell'indirizzo, provane un altro:",
    kindLan: "rete di casa", kindTailscale: "Tailscale",
    whatRuns: "Cosa esegue questo comando?",
    firewall: "Se Windows chiede se GetSetMix Setup può usare la rete, scegli Consenti.",

    serverInstallTitle: "Installa su {0}",
    existingTitle: "GetSetMix è già in funzione qui",
    existingBody: "L'installazione lo tiene, con tracce e impostazioni, e gli collega questo computer.",
    existingWill: "Sul server, l'installazione:",
    willRecreate: "farà girare una copia alla volta (due condividerebbero lo stesso database)",
    willPull: "scaricherà sempre la versione più recente al riavvio",
    willKeel: "installerà Keel per aggiornare GetSetMix da solo",
    willWatch: "aggiungerà Watchtower per aggiornare GetSetMix da solo",
    willRestart: "lo riavvierà una volta, per aggiornarlo subito",
    runWith: "Fallo girare con",
    noEngine: "Questo server non ha né Docker né Kubernetes. L'installazione metterà Docker con il suo installer ufficiale (get.docker.com).",
    musicDir: "Tieni la musica in",
    musicDirHint: "Una cartella sul server. Qui vive tutta la tua collezione.",
    free: "{0} GB liberi",
    autoUpdate: "Aggiorna automaticamente",
    autoUpdateDocker: "Watchtower controlla ogni ora se c'è una nuova versione. Tracce e impostazioni restano.",
    autoUpdateK8s: "Keel controlla ogni 5 minuti se c'è una nuova versione. Tracce e impostazioni restano.",
    tailscale: "Indirizzo sicuro con Tailscale",
    tailscaleD: "Ti dà {0}, che serve al telefono per installare GetSetMix e condividerci tracce.",
    noTailscale: "Per installare GetSetMix sul telefono serve un indirizzo sicuro (HTTPS). Il modo più semplice è Tailscale: installalo sul server e sul telefono, poi rilancia l'installazione. Senza, il telefono può comunque aprire GetSetMix sul Wi-Fi di casa.",
    getTailscale: "Scarica Tailscale",

    computerTitle: "Questo computer",
    computerLede: "Le nuove tracce arrivano qui dal server e finiscono in Rekordbox.",
    localInstallTitle: "Installa su questo computer",
    localInstallLede: "GetSetMix si apre in una sua finestra mentre lo usi. Le tracce vanno nella cartella che scegli e in Rekordbox.",
    rbFound: "Rekordbox trovato",
    rbTracks: "{0} tracce nella tua collezione",
    rbMissing: "Rekordbox non è installato qui",
    rbMissingD: "Le tracce si scaricano comunque. Rilancia l'installazione dopo aver installato Rekordbox per aggiungerle in automatico.",
    deliveryDownload: "Scaricale dal server",
    deliveryDownloadD: "Ogni 15 minuti mentre il computer è acceso, e ogni volta che apri Rekordbox. Il server tiene la sua copia.",
    deliverySynced: "La cartella musica del server è già sincronizzata qui",
    deliverySyncedD: "Con Nextcloud, Syncthing o simili. L'installazione tiene d'occhio solo quella cartella.",
    saveIn: "Salva le tracce in",
    syncedIn: "La cartella sincronizzata su questo computer",
    copyExisting: "Scarica anche le {0} tracce già sul server",
    copyExistingAll: "Scarica anche le tracce già sul server",
    playlist: "Playlist di Rekordbox",
    playlistHint: "Le nuove tracce si aggiungono a questa playlist.",
    pickPrompt: "Scegli la cartella per le tue tracce",
    sizeNote: "Scarica circa 250 MB: GetSetMix, ffmpeg e Deno.",
    needFolder: "Prima scegli una cartella.",

    installing: "Installazione in corso…",
    installedTitle: "Quasi fatto",
    failedTitle: "Qualcosa è andato storto",
    onServer: "Su {0}",
    onComputer: "Su questo computer",
    waitingPlan: "Invio del piano al server…",
    reach: "Verifica che questo computer lo raggiunga",
    reachAsk: "L'installazione non è riuscita a raggiungere GetSetMix da sola. A che indirizzo lo apri?",
    reachPlaceholder: "http://192.168.1.10:8765",
    reachTry: "Collega",
    serverFailed: "Il server si è fermato a questo passo. Risolvi quello che dicono i dettagli, poi rilancia il comando sul server: l'installazione riparte da lì.",
    pcFailed: "Questo computer si è fermato a questo passo. Chiudi l'installazione, risolvi quello che dicono i dettagli e rilanciala.",
    details: "Dettagli",

    s_docker: "Installa Docker",
    s_folders: "Crea le cartelle",
    s_app_install: "Installa GetSetMix",
    s_app_adopt: "Aggiorna GetSetMix",
    s_updates: "Attiva gli aggiornamenti automatici",
    s_start: "Avvia GetSetMix",
    s_link: "Collega questo computer",
    s_https: "Attiva HTTPS con Tailscale",
    s_companion: "Installa il companion per Rekordbox",
    s_settings: "Salva le tue scelte",
    s_rekordbox: "Collega a Rekordbox",
    s_first: "Avvia il primo download",
    s_app_local: "Scarica GetSetMix",
    s_ffmpeg: "Scarica ffmpeg",
    s_deno: "Scarica Deno",
    s_shortcuts_win: "Aggiungi GetSetMix al menu Start",
    s_shortcuts_mac: "Aggiungi GetSetMix ad Applicazioni",
    s_shortcuts_other: "Aggiungi i collegamenti di GetSetMix",

    c_docker_install: "Docker non si è installato.",
    c_folders: "Non è stato possibile creare le cartelle.",
    c_pull: "Non è stato possibile scaricare l'immagine di GetSetMix. Il server è online?",
    c_run: "Docker non è riuscito ad avviare GetSetMix. La porta è usata da altro?",
    c_watchtower: "Watchtower non è partito.",
    c_health: "GetSetMix non è partito in tempo.",
    c_link: "Non è stato possibile aggiungere questo computer al server.",
    c_no_port: "Il GetSetMix esistente non pubblica una porta, quindi niente può raggiungerlo.",
    c_patch: "Non è stato possibile modificare il deployment esistente.",
    c_keel: "Non è stato possibile installare Keel.",
    c_restart: "Non è stato possibile riavviare GetSetMix.",
    c_apply: "Kubernetes ha rifiutato il manifest di GetSetMix.",
    c_tailscale: "Tailscale non è riuscito ad attivare HTTPS. Nella console di Tailscale abilita MagicDNS e i certificati HTTPS, poi rilancia l'installazione.",
    c_update: "L'aggiornamento non è finito; GetSetMix continua con la versione attuale.",

    doneTitle: "GetSetMix è pronto",
    doneLocalTitle: "GetSetMix è installato",
    yourGsm: "Il tuo GetSetMix",
    open: "Apri",
    openApp: "Apri GetSetMix",
    showFolder: "Mostra cartella",
    phoneTitle: "Sul telefono",
    phone1: "<strong>Inquadra questo</strong> con la fotocamera del telefono.",
    phone2: "In Chrome tocca <strong>⋮</strong> e poi <strong>Installa app</strong>.",
    phone3: "Da YouTube o SoundCloud, <strong>Condividi</strong> una traccia con <strong>GetSetMix</strong>.",
    phoneHttp: "Il telefono può aprire questo indirizzo sul Wi-Fi di casa. Per installarlo e condividerci tracce serve un indirizzo sicuro (HTTPS): configura Tailscale sul server e rilancia l'installazione.",
    rbLauncher: "D'ora in poi apri Rekordbox con <strong>Rekordbox (GetSetMix)</strong>: aggiunge le nuove tracce prima di avviare Rekordbox.",
    rbScheduled: "Le nuove tracce si scaricano anche ogni 15 minuti mentre il computer è acceso, in {0}.",
    rbSynced: "Le tracce arrivano tramite la tua app di sincronizzazione in {0}.",
    rbNone: "Installa Rekordbox, poi rilancia l'installazione per aggiungerci le tracce in automatico.",
    localDone: "Apri GetSetMix dal menu Start o dal desktop. Le tracce vanno in {0}.",
    localDoneMac: "Apri GetSetMix da Applicazioni. Le tracce vanno in {0}.",
    demo: "Demo: non viene installato nulla",
  },
};

let lang = "en";
try { lang = localStorage.getItem("gsm_setup_lang") || ""; } catch (e) { /* storage blocked */ }
if (lang !== "en" && lang !== "it") lang = (navigator.language || "en").toLowerCase().startsWith("it") ? "it" : "en";

function T(key, ...args) {
  let s = (STR[lang] && STR[lang][key]) ?? STR.en[key] ?? key;
  args.forEach((v, i) => { s = s.split(`{${i}}`).join(v); });
  return s;
}
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const $ = (sel, el = document) => el.querySelector(sel);
const num = (n) => new Intl.NumberFormat(lang).format(n);

// ------------------------------------------------------------------ icons
const I = {
  laptop: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="5" width="16" height="11" rx="1.5"/><path d="M2 19h20"/></svg>',
  server: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3.5" y="4" width="17" height="7" rx="1.5"/><rect x="3.5" y="13" width="17" height="7" rx="1.5"/><path d="M7.5 7.5h.01M7.5 16.5h.01"/></svg>',
  check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M5.5 12.5l4.2 4.2 8.8-9.4"/></svg>',
  cross: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M7 7l10 10M17 7L7 17"/></svg>',
  warn: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4l9 16H3z"/><path d="M12 10v4M12 17h.01"/></svg>',
  info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5h.01"/></svg>',
  copy: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/></svg>',
  disc: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="2.5"/></svg>',
  os: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 9l3 3-3 3M12 15h5"/></svg>',
  box: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/><path d="M4 7.5l8 4.5 8-4.5M12 12v9"/></svg>',
  lock: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>',
};

// ------------------------------------------------------------------ state
let S = null;          // last /api/state
let screen = "welcome";
let mode = null;       // "local" | "server"
const choice = {
  server: { adopt: false, target: "", musicDir: "", autoUpdate: true, tailscale: true, installDocker: false },
  pc: { folder: "", delivery: "download", playlist: "GetSetMix", copyExisting: true, syncedFolder: "" },
  addr: 0,
};
let seeded = false;    // server choices filled from the facts once
let busy = false;

async function api(path, body) {
  const opts = body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  };
  const r = await fetch(path, opts);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
  return data;
}

// ------------------------------------------------------------------ rail
const RAIL = {
  none: [["welcome", "rChoose"], ["setup", "rSetUp"], ["install", "rInstall"], ["done", "rDone"]],
  local: [["welcome", "rChoose"], ["local", "rComputer"], ["install", "rInstall"], ["done", "rDone"]],
  server: [["welcome", "rChoose"], ["connect", "rConnect"], ["server", "rServer"], ["computer", "rComputer"], ["install", "rInstall"], ["done", "rDone"]],
};

function renderRail() {
  const steps = RAIL[mode || "none"];
  const at = steps.findIndex(([id]) => id === screen);
  $("#steps").innerHTML = steps.map(([id, key], i) =>
    `<li class="${i === at ? "is-current" : i < at ? "is-done" : ""}"${i === at ? ' aria-current="step"' : ""}>${esc(T(key))}</li>`
  ).join("");
  document.querySelectorAll("[data-t]").forEach((el) => { el.textContent = T(el.dataset.t); });
  document.querySelectorAll(".lang button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.lang === lang)));
  document.documentElement.lang = lang;
  $("#version").textContent = S ? (S.demo ? T("demo") : S.version === "dev" ? "dev" : `v${S.version}`) : "";
}

// --------------------------------------------------------------- screens
const screens = {};

function go(next) {
  screen = next;
  render();
  $("#page").scrollTop = 0;
  $("#page").focus({ preventScroll: true });
}

function render() {
  renderRail();
  const s = screens[screen];
  $("#page").innerHTML = s.page();
  $("#bar").innerHTML = s.bar ? s.bar() : "";
  s.wire && s.wire();
  refresh();
}

function refresh() {
  const s = screens[screen];
  s.refresh && s.refresh();
}

function bar(left, right) {
  return `<span class="spacer">${left || ""}</span>${right}`;
}

// welcome --------------------------------------------------------------------
screens.welcome = {
  page() {
    const local = S && S.pc.localSupported;
    return `
      <h1>${esc(T("welcomeTitle"))}</h1>
      <p class="lede">${esc(T("welcomeLede"))}</p>
      <div class="choices" role="radiogroup">
        <label class="choice${local ? "" : " is-disabled"}">
          <input type="radio" name="mode" value="local" ${mode === "local" ? "checked" : ""} ${local ? "" : "disabled"} />
          <span class="ic">${I.laptop}</span>
          <span><strong>${esc(T("localTitle"))}</strong><span class="d">${esc(T("localDesc"))}</span>
            <span class="m">${esc(T(local ? "localMeta" : "localNone"))}</span></span>
          <span class="dot"></span>
        </label>
        <label class="choice">
          <input type="radio" name="mode" value="server" ${mode === "server" ? "checked" : ""} />
          <span class="ic">${I.server}</span>
          <span><strong>${esc(T("serverTitle"))}</strong><span class="d">${esc(T("serverDesc"))}</span>
            <span class="m">${esc(T("serverMeta"))}</span></span>
          <span class="dot"></span>
        </label>
      </div>`;
  },
  bar() { return bar("", `<button class="btn btn-primary" id="next" ${mode ? "" : "disabled"}>${esc(T("next"))}</button>`); },
  wire() {
    document.querySelectorAll('input[name="mode"]').forEach((r) => r.addEventListener("change", () => {
      mode = r.value; renderRail(); $("#next").disabled = false;
    }));
    $("#next").onclick = async () => {
      if (mode === "server") {
        await api("/api/pair/start", {}).catch(() => {});
        S = await api("/api/state");
      }
      go(mode === "local" ? "local" : "connect");
    };
  },
};

// local ----------------------------------------------------------------------
function rekordboxRow() {
  const rb = S.pc.rekordbox;
  if (rb.found) {
    return `<div class="rb"><span class="ok">${I.check}</span><div><strong>${esc(T("rbFound"))}</strong>
      <div class="small">${esc(T("rbTracks", num(rb.tracks)))}</div></div></div>`;
  }
  return `<div class="rb"><span class="warn">${I.warn}</span><div><strong>${esc(T("rbMissing"))}</strong>
    <div class="small">${esc(T("rbMissingD"))}</div></div></div>`;
}

function folderField(id, label, value, hint) {
  return `<div class="field"><label for="${id}">${esc(label)}</label>
    <div class="path-row"><input class="input" id="${id}" value="${esc(value)}" spellcheck="false" />
    <button class="btn btn-quiet" type="button" data-pick="${id}">${esc(T("change"))}</button></div>
    ${hint ? `<div class="hint">${esc(hint)}</div>` : ""}</div>`;
}

function wirePickers() {
  document.querySelectorAll("[data-pick]").forEach((b) => {
    b.onclick = async () => {
      const input = $("#" + b.dataset.pick);
      try {
        const r = await api("/api/pick", { prompt: T("pickPrompt"), start: input.value });
        if (r.path) { input.value = r.path; input.dispatchEvent(new Event("input")); }
      } catch (e) { /* the dialog failed: typing still works */ }
    };
  });
}

screens.local = {
  page() {
    if (!choice.pc.folder) choice.pc.folder = S.pc.musicDefault;
    return `
      <h1>${esc(T("localInstallTitle"))}</h1>
      <p class="lede">${esc(T("localInstallLede"))}</p>
      ${rekordboxRow()}
      ${folderField("folder", T("saveIn"), choice.pc.folder)}
      <div class="field"><label for="playlist">${esc(T("playlist"))}</label>
        <input class="input" id="playlist" value="${esc(choice.pc.playlist)}" style="max-width:280px" />
        <div class="hint">${esc(T("playlistHint"))}</div></div>
      <p class="small">${esc(T("sizeNote"))}</p>`;
  },
  bar() {
    return bar(`<button class="btn btn-quiet" id="back">${esc(T("back"))}</button>`,
      `<p class="error" id="err" hidden></p><button class="btn btn-primary" id="go">${esc(T("install"))}</button>`);
  },
  wire() {
    wirePickers();
    $("#folder").oninput = (e) => { choice.pc.folder = e.target.value; };
    $("#playlist").oninput = (e) => { choice.pc.playlist = e.target.value; };
    $("#back").onclick = () => go("welcome");
    $("#go").onclick = async () => {
      try {
        await api("/api/local/install", { folder: choice.pc.folder, playlist: choice.pc.playlist });
        S = await api("/api/state");
        go("install");
      } catch (e) { $("#err").textContent = e.message; $("#err").hidden = false; }
    };
  },
};

// connect --------------------------------------------------------------------
screens.connect = {
  page() {
    const cmds = S.pair.commands || [];
    const cmd = cmds[choice.addr] ? cmds[choice.addr].command : S.pair.command;
    const others = cmds.length > 1 ? `
      <details class="more"><summary>${esc(T("otherNet"))}</summary>
        <p class="muted">${esc(T("otherNetD"))}</p>
        <div class="addr">${cmds.map((c, i) => `<label><input type="radio" name="addr" value="${i}" ${i === choice.addr ? "checked" : ""}/>
          <span class="mono">${esc(c.ip)}</span> <span class="small">${esc(T(c.kind === "tailscale" ? "kindTailscale" : "kindLan"))}</span></label>`).join("")}</div>
      </details>` : "";
    return `
      <h1>${esc(T("connectTitle"))}</h1>
      <p class="lede">${esc(T("connectLede"))}</p>
      <ol class="howto">
        <li><div><strong>${esc(T("how1"))}</strong><p>${T("how1d")}</p></div></li>
        <li><div><strong>${esc(T("how2"))}</strong>
          <div class="cmd"><code id="cmd">${esc(cmd)}</code>
            <button type="button" id="copy">${I.copy}<span>${esc(T("copy"))}</span></button></div>
          <p style="margin-top:8px">${T("how2d")}</p></div></li>
        <li><div><strong>${esc(T("how3"))}</strong>
          <div class="waiting" id="wait"><span class="pulse"></span><span id="waitText">${esc(T("waiting"))}</span></div></div></li>
      </ol>
      ${others}
      <details class="more" id="whatRuns"><summary>${esc(T("whatRuns"))}</summary><pre id="script"></pre></details>
      ${S.os === "windows" ? `<p class="small" style="margin-top:18px">${esc(T("firewall"))}</p>` : ""}`;
  },
  bar() {
    return bar(`<button class="btn btn-quiet" id="back">${esc(T("back"))}</button>`,
      `<button class="btn btn-primary" id="next" disabled>${esc(T("next"))}</button>`);
  },
  wire() {
    $("#copy").onclick = async () => {
      try { await navigator.clipboard.writeText($("#cmd").textContent); } catch (e) {
        const r = document.createRange(); r.selectNodeContents($("#cmd"));
        const sel = getSelection(); sel.removeAllRanges(); sel.addRange(r); document.execCommand("copy");
      }
      $("#copy span").textContent = T("copied");
      setTimeout(() => { const s = $("#copy span"); if (s) s.textContent = T("copy"); }, 1600);
    };
    document.querySelectorAll('input[name="addr"]').forEach((r) => r.onchange = () => {
      choice.addr = Number(r.value);
      $("#cmd").textContent = S.pair.commands[choice.addr].command;
    });
    $("#whatRuns").addEventListener("toggle", async (e) => {
      if (e.target.open && !$("#script").textContent) {
        $("#script").textContent = await (await fetch("/api/script")).text();
      }
    });
    $("#back").onclick = () => go("welcome");
    $("#next").onclick = () => go("server");
    if (S.demo && !S.pair.connected) {
      setTimeout(() => { if (screen === "connect") api("/api/demo/connect", { variant: new URLSearchParams(location.search).get("variant") || "docker" }); }, 2500);
    }
  },
  refresh() {
    const on = S.pair.connected;
    $("#wait").classList.toggle("is-on", on);
    $("#waitText").textContent = on ? T("connected", S.pair.facts.hostname) : T("waiting");
    $("#next").disabled = !on;
  },
};

// server ---------------------------------------------------------------------
function seedServer() {
  const f = S.pair.facts;
  if (seeded || !f) return;
  seeded = true;
  Object.assign(choice.server, {
    adopt: !!f.existing, target: f.defaults.target, musicDir: f.defaults.musicDir,
    installDocker: f.defaults.installDocker, tailscale: !!f.tailscale, autoUpdate: true,
  });
  choice.pc.copyExisting = !f.existing;
}

function freeFor(dir) {
  const free = S.pair.facts.freeGB || {};
  const keys = Object.keys(free).sort((a, b) => b.length - a.length);
  const k = keys.find((p) => dir === p || dir.startsWith(p.replace(/\/$/, "") + "/"));
  return k ? free[k] : null;
}

screens.server = {
  page() {
    seedServer();
    const f = S.pair.facts;
    const c = choice.server;
    const engines = [];
    if (f.docker) engines.push(["docker", `Docker ${f.docker}`]);
    if (f.kubernetes) engines.push(["kubernetes", f.kubernetes]);
    const factsRow = `<div class="facts">
      <span>${I.os}${esc(f.os || "Linux")} · ${esc(f.arch)}</span>
      ${engines.map(([, label]) => `<span>${I.box}${esc(label)}</span>`).join("")}
      ${f.tailscale ? `<span>${I.lock}Tailscale</span>` : ""}</div>`;

    let body;
    if (f.existing) {
      const k8s = f.existing.kind === "kubernetes";
      const will = k8s
        ? [T("willRecreate"), T("willPull"), c.autoUpdate ? T("willKeel") : null, T("willRestart")]
        : [c.autoUpdate ? T("willWatch") : null, T("willRestart")];
      body = `
        <div class="note">${I.info}<div><p><strong>${esc(T("existingTitle"))}</strong> <span class="mono">${esc(f.existing.where)}</span></p>
          <p>${esc(T("existingBody"))}</p>
          <p class="muted" style="margin-top:10px">${esc(T("existingWill"))}</p>
          <ul>${will.filter(Boolean).map((w) => `<li>${esc(w)}</li>`).join("")}</ul></div></div>
        ${toggleRow("autoUpdate", T("autoUpdate"), T(k8s ? "autoUpdateK8s" : "autoUpdateDocker"), c.autoUpdate)}`;
    } else {
      const segs = engines.length > 1 ? `<div class="field"><span class="label">${esc(T("runWith"))}</span>
        <div class="seg" role="radiogroup">${engines.map(([id, label]) => `<label><input type="radio" name="target" value="${id}" ${c.target === id ? "checked" : ""}/><span>${esc(label)}</span></label>`).join("")}</div></div>` : "";
      const free = freeFor(c.musicDir);
      body = `
        ${engines.length === 0 ? `<div class="note">${I.info}<p>${esc(T("noEngine"))}</p></div>` : ""}
        ${segs}
        <div class="field"><label for="musicDir">${esc(T("musicDir"))}</label>
          <input class="input mono" id="musicDir" value="${esc(c.musicDir)}" spellcheck="false" />
          <div class="hint" id="freeHint">${esc(T("musicDirHint"))}${free != null ? " " + esc(T("free", num(Math.round(free)))) : ""}</div></div>
        ${toggleRow("autoUpdate", T("autoUpdate"), T(c.target === "kubernetes" ? "autoUpdateK8s" : "autoUpdateDocker"), c.autoUpdate)}`;
    }
    const ownAddress = f.existing && !f.existing.port;
    const ts = ownAddress ? "" : f.tailscale
      ? toggleRow("tailscale", T("tailscale"), T("tailscaleD", "https://" + f.tailscale), c.tailscale)
      : `<div class="note warn" style="margin-top:20px">${I.lock}<div><p>${esc(T("noTailscale"))}</p>
          <p><button class="btn btn-text" type="button" id="getTs">${esc(T("getTailscale"))}</button></p></div></div>`;
    return `<h1>${esc(T("serverInstallTitle", f.hostname))}</h1>${factsRow}${body}${ts}`;
  },
  bar() {
    return bar(`<button class="btn btn-quiet" id="back">${esc(T("back"))}</button>`,
      `<button class="btn btn-primary" id="next">${esc(T("next"))}</button>`);
  },
  wire() {
    const c = choice.server;
    document.querySelectorAll('input[name="target"]').forEach((r) => r.onchange = () => { c.target = r.value; render(); });
    const md = $("#musicDir");
    if (md) md.oninput = () => {
      c.musicDir = md.value;
      const free = freeFor(c.musicDir);
      $("#freeHint").textContent = T("musicDirHint") + (free != null ? " " + T("free", num(Math.round(free))) : "");
    };
    wireToggle("autoUpdate", (v) => { c.autoUpdate = v; if (S.pair.facts.existing) render(); });
    wireToggle("tailscale", (v) => { c.tailscale = v; });
    const ts = $("#getTs");
    if (ts) ts.onclick = () => api("/api/open", { what: "tailscale" });
    $("#back").onclick = () => go("connect");
    $("#next").onclick = () => go("computer");
  },
};

function toggleRow(id, title, desc, on) {
  return `<label class="toggle"><span><strong>${esc(title)}</strong><span>${esc(desc)}</span></span>
    <span class="switch"><input type="checkbox" role="switch" id="${id}" ${on ? "checked" : ""}/><i></i></span></label>`;
}
function wireToggle(id, fn) {
  const el = $("#" + id);
  if (el) el.onchange = () => fn(el.checked);
}

// computer -------------------------------------------------------------------
screens.computer = {
  page() {
    const p = choice.pc;
    if (!p.folder) p.folder = S.pc.musicDefault;
    if (!p.syncedFolder) p.syncedFolder = S.pc.rekordbox.folder || "";
    const synced = p.delivery === "synced";
    const existing = S.pair.facts && S.pair.facts.existing;
    return `
      <h1>${esc(T("computerTitle"))}</h1>
      <p class="lede">${esc(T("computerLede"))}</p>
      ${rekordboxRow()}
      <div class="choices" role="radiogroup" style="margin-bottom:24px">
        ${deliveryChoice("download", T("deliveryDownload"), T("deliveryDownloadD"), !synced)}
        ${deliveryChoice("synced", T("deliverySynced"), T("deliverySyncedD"), synced)}
      </div>
      ${synced ? folderField("folder", T("syncedIn"), p.syncedFolder) : folderField("folder", T("saveIn"), p.folder)}
      ${!synced && existing ? `<label class="check"><input type="checkbox" id="copyExisting" ${p.copyExisting ? "checked" : ""}/>
        <span>${esc(T("copyExistingAll"))}</span></label>` : ""}
      <div class="field"><label for="playlist">${esc(T("playlist"))}</label>
        <input class="input" id="playlist" value="${esc(p.playlist)}" style="max-width:280px" />
        <div class="hint">${esc(T("playlistHint"))}</div></div>`;
  },
  bar() {
    return bar(`<button class="btn btn-quiet" id="back">${esc(T("back"))}</button>`,
      `<p class="error" id="err" hidden></p><button class="btn btn-primary" id="go">${esc(T("install"))}</button>`);
  },
  wire() {
    const p = choice.pc;
    wirePickers();
    document.querySelectorAll('input[name="delivery"]').forEach((r) => r.onchange = () => { p.delivery = r.value; render(); });
    $("#folder").oninput = (e) => { if (p.delivery === "synced") p.syncedFolder = e.target.value; else p.folder = e.target.value; };
    $("#playlist").oninput = (e) => { p.playlist = e.target.value; };
    const ce = $("#copyExisting");
    if (ce) ce.onchange = () => { p.copyExisting = ce.checked; };
    $("#back").onclick = () => go("server");
    $("#go").onclick = install;
  },
};

function deliveryChoice(value, title, desc, on) {
  return `<label class="choice compact"><input type="radio" name="delivery" value="${value}" ${on ? "checked" : ""}/>
    <span><strong>${esc(title)}</strong><span class="d">${esc(desc)}</span></span><span class="dot"></span></label>`;
}

async function install() {
  const p = choice.pc;
  const folder = p.delivery === "synced" ? p.syncedFolder : p.folder;
  if (!folder) { $("#err").textContent = T("needFolder"); $("#err").hidden = false; return; }
  const c = choice.server;
  try {
    $("#go").disabled = true;
    await api("/api/server/install", {
      adopt: c.adopt, target: c.target, installDocker: c.installDocker, musicDir: c.musicDir,
      autoUpdate: c.autoUpdate, tailscale: c.tailscale, language: lang,
      pc: { folder, delivery: p.delivery, playlist: p.playlist, copyExisting: !!p.copyExisting },
    });
    S = await api("/api/state");
    go("install");
  } catch (e) {
    $("#go").disabled = false;
    $("#err").textContent = e.message; $("#err").hidden = false;
  }
}

// install --------------------------------------------------------------------
function stepLabel(id, group) {
  if (group === "server") {
    if (id === "app") return T(S.server.plan && S.server.plan.adopt ? "s_app_adopt" : "s_app_install");
    return T("s_" + id);
  }
  if (id === "app") return T("s_app_local");
  if (id === "shortcuts") return T(S.os === "windows" ? "s_shortcuts_win" : S.os === "darwin" ? "s_shortcuts_mac" : "s_shortcuts_other");
  return T("s_" + id);
}

function taskRow(st, label, extra = "") {
  const icon = { ok: I.check, warn: I.warn, fail: I.cross, running: '<span class="spin"></span>' }[st.status] || "";
  let sub = "";
  if (st.code) sub = `<div class="sub">${esc(T("c_" + st.code))}</div>`;
  if (st.status === "running" && st.progress > 0) sub += `<div class="meter"><i style="width:${Math.round(st.progress * 100)}%"></i></div>`;
  const detail = st.detail && (st.status === "fail" || st.status === "warn")
    ? `<details class="more" style="margin-top:6px"><summary>${esc(T("details"))}</summary><pre>${esc(st.detail)}</pre></details>` : "";
  return `<li class="task" data-s="${esc(st.status)}"><span class="i">${icon}</span><div class="t">${esc(label)}${sub}${detail}${extra}</div></li>`;
}

screens.install = {
  page() {
    return `<h1 id="title">${esc(T("installing"))}</h1><div id="groups"></div>`;
  },
  bar() { return bar("", `<button class="btn btn-quiet" id="close" hidden>${esc(T("close"))}</button>`); },
  wire() { $("#close").onclick = () => window.close(); },
  refresh() {
    const groups = [];
    let failed = false;
    if (mode === "server") {
      const sv = S.server;
      if (!sv.plan) { seeded = false; go("server"); return; } // the command was run again: choose again
      const rows = sv.steps.map((st) => taskRow(st, stepLabel(st.id, "server")));
      if (sv.state === "waiting") rows.unshift(`<li class="task" data-s="running"><span class="i"><span class="spin"></span></span><div class="t">${esc(T("waitingPlan"))}</div></li>`);
      if (sv.state === "done" || sv.urlState) {
        const st = { id: "reach", status: sv.urlState === "ok" ? "ok" : sv.urlState === "need" ? "warn" : "running" };
        let ask = "";
        if (sv.urlState === "need") {
          ask = `<div class="ask"><p class="muted" style="margin:0">${esc(T("reachAsk"))}</p>
            <div class="path-row"><input class="input" id="url" placeholder="${esc(T("reachPlaceholder"))}" value="${esc(($("#url") || {}).value || "")}"/>
            <button class="btn btn-primary" id="tryUrl">${esc(T("reachTry"))}</button></div>
            <p class="error" id="urlErr" ${sv.urlError ? "" : "hidden"}>${esc(sv.urlError || "")}</p></div>`;
        }
        rows.push(taskRow(st, T("reach"), ask));
      }
      if (sv.state === "failed") { failed = true; rows.push(`<li class="note bad" style="margin-top:12px">${I.warn}<p>${esc(T("serverFailed"))}</p></li>`); }
      groups.push(`<section class="group"><h2>${esc(T("onServer", S.pair.facts ? S.pair.facts.hostname : "server"))}</h2><ul class="tasks">${rows.join("")}</ul></section>`);
    }
    const pcRows = S.local.steps.map((st) => taskRow(st, stepLabel(st.id, "pc")));
    if (S.local.state === "failed") { failed = true; pcRows.push(`<li class="note bad" style="margin-top:12px">${I.warn}<p>${esc(T("pcFailed"))}</p></li>`); }
    groups.push(`<section class="group"><h2>${esc(T("onComputer"))}</h2><ul class="tasks">${pcRows.join("")}</ul></section>`);

    // Keep a half-typed address across refreshes.
    const typing = document.activeElement && document.activeElement.id === "url";
    const typed = typing ? $("#url").value : null;
    if (!typing) $("#groups").innerHTML = groups.join("");
    else {
      const g = document.createElement("div"); g.innerHTML = groups.join("");
      $("#groups").querySelectorAll(".group").forEach((old, i) => { if (!old.querySelector("#url")) old.replaceWith(g.children[i].cloneNode(true)); });
      if (typed != null) $("#url").value = typed;
    }
    const t = $("#tryUrl");
    if (t) t.onclick = async () => {
      try { await api("/api/server/url", { url: $("#url").value }); }
      catch (e) { $("#urlErr").textContent = e.message; $("#urlErr").hidden = false; }
    };
    $("#title").textContent = failed ? T("failedTitle") : T("installing");
    $("#close").hidden = !failed;
    if (S.local.state === "done") go("done");
  },
};

// done -----------------------------------------------------------------------
screens.done = {
  page() {
    const folder = choice.pc.delivery === "synced" && mode === "server" ? choice.pc.syncedFolder : choice.pc.folder;
    const rb = S.pc.rekordbox.found;
    if (mode === "local") {
      return `
        <h1>${esc(T("doneLocalTitle"))}</h1>
        <p class="lede">${esc(T(S.os === "darwin" ? "localDoneMac" : "localDone", folder))}</p>
        <div class="split"><p>${rb ? T("rbLauncher") : esc(T("rbNone"))}</p></div>`;
    }
    const sv = S.server;
    const phone = sv.https
      ? `<div class="phone"><div class="qr"><img src="/api/qr" alt="" /></div>
          <div><h2 style="margin-top:0">${esc(T("phoneTitle"))}</h2><ol><li>${T("phone1")}</li><li>${T("phone2")}</li><li>${T("phone3")}</li></ol></div></div>`
      : `<div class="phone"><div class="qr"><img src="/api/qr" alt="" /></div>
          <div><h2 style="margin-top:0">${esc(T("phoneTitle"))}</h2><p class="muted">${esc(T("phoneHttp"))}</p></div></div>`;
    const pcLines = [];
    pcLines.push(rb ? T("rbLauncher") : esc(T("rbNone")));
    pcLines.push(esc(T(choice.pc.delivery === "synced" ? "rbSynced" : "rbScheduled", folder)));
    return `
      <h1>${esc(T("doneTitle"))}</h1>
      <div class="hero-url" style="margin-top:24px"><div><div class="label">${esc(T("yourGsm"))}</div>
        <a href="#" id="srv">${esc(sv.url)}</a></div>
        <button class="btn btn-quiet" id="openSrv">${esc(T("open"))}</button></div>
      ${phone}
      <div class="split">${pcLines.map((l) => `<p>${l}</p>`).join("")}</div>`;
  },
  bar() {
    const primary = mode === "local"
      ? `<button class="btn btn-quiet" id="folderBtn">${esc(T("showFolder"))}</button><button class="btn btn-primary" id="openApp">${esc(T("openApp"))}</button>`
      : `<button class="btn btn-quiet" id="folderBtn">${esc(T("showFolder"))}</button><button class="btn btn-primary" id="closeBtn">${esc(T("close"))}</button>`;
    return bar("", primary);
  },
  wire() {
    const open = (what) => api("/api/open", { what }).catch(() => {});
    const s = $("#srv"); if (s) s.onclick = (e) => { e.preventDefault(); open("server"); };
    const o = $("#openSrv"); if (o) o.onclick = () => open("server");
    const a = $("#openApp"); if (a) a.onclick = () => open("app");
    const f = $("#folderBtn"); if (f) f.onclick = () => open("folder");
    const c = $("#closeBtn"); if (c) c.onclick = () => window.close();
  },
};

screens.setup = screens.welcome;

// ------------------------------------------------------------------ boot
document.querySelectorAll(".lang button").forEach((b) => b.addEventListener("click", () => {
  lang = b.dataset.lang;
  try { localStorage.setItem("gsm_setup_lang", lang); } catch (e) { /* storage blocked */ }
  render();
}));

async function poll() {
  try {
    const next = await api("/api/state");
    const first = !S;
    S = next;
    if (first) render(); else refresh();
  } catch (e) { /* Setup is closing */ }
  setTimeout(poll, screen === "install" || screen === "connect" ? 600 : 1500);
}
poll();
