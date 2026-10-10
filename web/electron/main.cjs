/**
 * Desktop shell for BMW Product Decision Lab.
 *
 * Runs the Next.js standalone server inside the Electron main process on a
 * free local port (127.0.0.1 only) and shows it in a native window. The
 * server reads evidence, policy and profile files from the bmw-hackathon
 * repository folder, chosen on first launch and remembered afterwards.
 */
const { app, BrowserWindow, dialog, Menu, shell } = require("electron");
const fs = require("node:fs");
const http = require("node:http");
const net = require("node:net");
const os = require("node:os");
const path = require("node:path");

const APP_NAME = "BMW Product Decision Lab";
app.setName(APP_NAME);

const configPath = () => path.join(app.getPath("userData"), "config.json");

function readConfig() {
  try {
    return JSON.parse(fs.readFileSync(configPath(), "utf8"));
  } catch {
    return {};
  }
}

function writeConfig(config) {
  fs.mkdirSync(path.dirname(configPath()), { recursive: true });
  fs.writeFileSync(configPath(), JSON.stringify(config, null, 2));
}

const looksLikeRepo = (dir) => Boolean(dir) && fs.existsSync(path.join(dir, "configs", "exploratory_equal_v1.json"));

/** Repository folder: saved choice → env → common locations → ask. */
async function resolveRepoRoot(forceAsk = false) {
  const config = readConfig();
  if (!forceAsk) {
    const candidates = [
      config.repoRoot,
      process.env.BMW_REPO_ROOT,
      path.join(os.homedir(), "bmw-hackathon"),
      path.resolve(__dirname, "..", ".."),
    ];
    const found = candidates.find(looksLikeRepo);
    if (found) {
      if (found !== config.repoRoot) writeConfig({ ...config, repoRoot: found });
      return found;
    }
  }
  const result = await dialog.showOpenDialog({
    title: "Select the bmw-hackathon repository folder",
    message: "Select the bmw-hackathon folder. Evidence, policy and profile files are read from it.",
    properties: ["openDirectory"],
    defaultPath: config.repoRoot ?? os.homedir(),
  });
  if (result.canceled || !result.filePaths[0]) return config.repoRoot ?? null;
  const chosen = result.filePaths[0];
  if (!looksLikeRepo(chosen)) {
    await dialog.showMessageBox({
      type: "warning",
      message: "This folder does not contain configs/exploratory_equal_v1.json.",
      detail: "The app will open with built-in defaults and without pipeline evidence. Use File → Choose Repository Folder to change it.",
    });
  }
  writeConfig({ ...config, repoRoot: chosen });
  return chosen;
}

function freePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.unref();
    srv.on("error", reject);
    srv.listen(0, "127.0.0.1", () => {
      const { port } = srv.address();
      srv.close(() => resolve(port));
    });
  });
}

function waitForServer(url, timeoutMs = 20000) {
  const started = Date.now();
  return new Promise((resolve, reject) => {
    const attempt = () => {
      http
        .get(url, (res) => {
          res.resume();
          resolve();
        })
        .on("error", () => {
          if (Date.now() - started > timeoutMs) reject(new Error("The local server did not start in time."));
          else setTimeout(attempt, 150);
        });
    };
    attempt();
  });
}

function serverEntry() {
  const packaged = path.join(process.resourcesPath ?? "", "app-server", "server.js");
  if (app.isPackaged && fs.existsSync(packaged)) return packaged;
  return path.resolve(__dirname, "..", ".next", "standalone", "server.js");
}

let baseUrl = null;
let mainWindow = null;

async function startServer() {
  const entry = serverEntry();
  if (!fs.existsSync(entry)) {
    throw new Error(`Server bundle not found at ${entry}. Run "npm run app:prepare" first.`);
  }
  const port = await freePort();
  process.env.PORT = String(port);
  process.env.HOSTNAME = "127.0.0.1";
  process.env.NODE_ENV = "production";
  require(entry);
  baseUrl = `http://127.0.0.1:${port}`;
  await waitForServer(baseUrl);
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1520,
    height: 960,
    minWidth: 1024,
    minHeight: 680,
    title: APP_NAME,
    backgroundColor: "#FAFAFA",
    show: false,
    webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true },
  });
  mainWindow.once("ready-to-show", () => mainWindow.show());
  // Source URLs (ADAC, manufacturer pages) open in the default browser, not inside the app.
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (!url.startsWith(baseUrl)) shell.openExternal(url);
    return { action: "deny" };
  });
  mainWindow.webContents.on("will-navigate", (event, url) => {
    if (!url.startsWith(baseUrl)) {
      event.preventDefault();
      shell.openExternal(url);
    }
  });
  mainWindow.loadURL(baseUrl);
  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

function buildMenu() {
  const isMac = process.platform === "darwin";
  const template = [
    ...(isMac ? [{ role: "appMenu" }] : []),
    {
      label: "File",
      submenu: [
        {
          label: "Choose Repository Folder…",
          click: async () => {
            const chosen = await resolveRepoRoot(true);
            if (chosen) {
              process.env.BMW_REPO_ROOT = chosen;
              mainWindow?.reload();
            }
          },
        },
        {
          label: "Reveal Repository Folder",
          click: () => {
            const root = process.env.BMW_REPO_ROOT;
            if (root) shell.openPath(root);
          },
        },
        { type: "separator" },
        isMac ? { role: "close" } : { role: "quit" },
      ],
    },
    { role: "editMenu" },
    {
      label: "View",
      submenu: [
        { label: "Reload Data", accelerator: "CmdOrCtrl+R", click: () => mainWindow?.reload() },
        { role: "toggleDevTools" },
        { type: "separator" },
        { role: "resetZoom" },
        { role: "zoomIn" },
        { role: "zoomOut" },
        { type: "separator" },
        { role: "togglefullscreen" },
      ],
    },
    { role: "windowMenu" },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

const singleInstance = app.requestSingleInstanceLock();
if (!singleInstance) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  app.whenReady().then(async () => {
    try {
      const root = await resolveRepoRoot();
      if (root) process.env.BMW_REPO_ROOT = root;
      buildMenu();
      await startServer();
      createWindow();
    } catch (error) {
      dialog.showErrorBox(APP_NAME, `The app could not start.\n\n${error instanceof Error ? error.message : String(error)}`);
      app.quit();
    }
  });

  app.on("activate", () => {
    if (!mainWindow && baseUrl) createWindow();
  });

  app.on("window-all-closed", () => {
    app.quit();
  });
}
