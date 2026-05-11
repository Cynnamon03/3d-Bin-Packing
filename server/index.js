const express    = require("express");
const cors       = require("cors");
const fs         = require("fs");
const path       = require("path");
const { spawn }  = require("child_process");
const readline   = require("readline");
const WebSocket  = require("ws");

const app     = express();
const PORT    = 3001;
const WS_PORT = 3002;

const DATA_ROOT = path.join(__dirname, "..", "data", "CLP-Datasets-Main", "BR");
const OPTIMIZER  = path.join(__dirname, "..", "optimizer", "main_optimizer.py");

app.use(cors());
app.use(express.json());

// ─────────────────────────────────────────────────────────────────────────────
// WebSocket server (port 3002)
// React connects here to receive live optimizer updates.
// ─────────────────────────────────────────────────────────────────────────────
const wss     = new WebSocket.Server({ port: WS_PORT });
const clients = new Set();

wss.on("connection", (ws) => {
  clients.add(ws);
  console.log(`WS client connected   (${clients.size} total)`);
  ws.on("close", () => {
    clients.delete(ws);
    console.log(`WS client disconnected (${clients.size} remaining)`);
  });
});

function broadcast(data) {
  const msg = JSON.stringify(data);
  for (const client of clients) {
    if (client.readyState === WebSocket.OPEN) client.send(msg);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// GET /api/instances
// ─────────────────────────────────────────────────────────────────────────────
app.get("/api/instances", (req, res) => {
  try {
    const instances = [];
    const sets = fs.readdirSync(DATA_ROOT)
      .filter(n => fs.statSync(path.join(DATA_ROOT, n)).isDirectory())
      .sort((a, b) => parseInt(a.replace("BR", "")) - parseInt(b.replace("BR", "")));

    for (const setName of sets) {
      const setPath = path.join(DATA_ROOT, setName);
      const files   = fs.readdirSync(setPath)
        .filter(f => f.endsWith(".json"))
        .sort((a, b) => parseInt(a) - parseInt(b));

      for (const file of files) {
        instances.push({
          set:   setName,
          file,
          label: `${setName} / ${file}`,
          path:  path.join(setPath, file),
        });
      }
    }
    res.json({ count: instances.length, instances });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ─────────────────────────────────────────────────────────────────────────────
// POST /api/run-optimizer   (single instance, unchanged behaviour)
// ─────────────────────────────────────────────────────────────────────────────
app.post("/api/run-optimizer", (req, res) => {
  const { instancePath } = req.body;
  if (!instancePath) return res.status(400).json({ error: "instancePath required" });

  const norm = path.resolve(instancePath);
  if (!norm.startsWith(path.resolve(DATA_ROOT)))
    return res.status(403).json({ error: "Path outside data directory" });
  if (!fs.existsSync(norm))
    return res.status(404).json({ error: "File not found" });

  const py = spawn("python", [OPTIMIZER, norm], {
    env: { ...process.env, PYTHONMALLOC: "malloc" },
  });

  let stdout = "", stderr = "";
  py.stdout.on("data", c => { stdout += c; });
  py.stderr.on("data", c => { stderr += c; });

  py.on("close", code => {
    if (code !== 0)
      return res.status(500).json({ error: "Optimizer failed", detail: stderr.slice(-2000) });
    try   { res.json(JSON.parse(stdout)); }
    catch { res.status(500).json({ error: "Bad optimizer output", raw: stdout.slice(-2000) }); }
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// POST /api/run-batch   { "set": "BR0" }
// Streams every optimizer update to connected WebSocket clients.
// ─────────────────────────────────────────────────────────────────────────────
let batchRunning = false;

app.post("/api/run-batch", (req, res) => {
  if (batchRunning)
    return res.status(409).json({ error: "A batch is already running. Restart the server to cancel." });

  const { set: setName } = req.body;
  
  if (!setName) return res.status(400).json({ error: "'set' field required (e.g. 'BR0')" });

  const setPath = path.join(DATA_ROOT, setName);
  if (!fs.existsSync(setPath))
    return res.status(404).json({ error: `Set '${setName}' not found at ${setPath}` });

  const files = fs.readdirSync(setPath)
    .filter(f => f.endsWith(".json"))
    .sort((a, b) => parseInt(a) - parseInt(b));

  if (!files.length) return res.status(404).json({ error: "No JSON files found in set folder" });

  // Respond immediately so the browser isn't left waiting
  res.json({ status: "started", set: setName, total: files.length });

  batchRunning = true;
  runBatch(setName, setPath, files).finally(() => { batchRunning = false; });

  const py = spawn("python", [OPTIMIZER, filePath, "--stream", "--max-time", String(maxTime)], {
    env: {  ...process.env, PYTHONMALLOC: "malloc" },
  });  
});
 
// ── Sequential batch runner ───────────────────────────────────────────────────
async function runBatch(setName, setPath, files) {
  console.log(`\n▶ Batch start: ${setName} (${files.length} instances)`);
  broadcast({ type: "batch_start", set: setName, total: files.length });
const filesToRun = files.slice(0, 5); // test with 5 first
  for (let i = 0; i < filesToRun.length; i++) {
    const file     = filesToRun[i];
    const filePath = path.join(setPath, file);

    console.log(`  [${i + 1}/${filesToRun.length}] ${setName}/${file}`);
    broadcast({
      type:  "instance_start",
      set:   setName,
      file,
      index: i,
      total: files.length,
      label: `${setName} / ${file}`,
    });

    try {
      await runStreamingInstance(filePath);
    } catch (err) {
      console.error(`  ERROR on ${file}:`, err.message);
      broadcast({ type: "instance_error", file, error: err.message });
      // Continue with next instance
    }
  }

  broadcast({ type: "batch_complete", set: setName, total: files.length });
  console.log(`✔ Batch ${setName} complete.\n`);
}

// ── Spawn one Python instance in streaming mode ───────────────────────────────
function runStreamingInstance(filePath) {
  return new Promise((resolve, reject) => {
    const py = spawn("python", [OPTIMIZER, filePath, "--stream", "--max-time", "15"], {
      env: {
        ...process.env,
        PYTHONMALLOC:            "malloc",
        MALLOC_TRIM_THRESHOLD_:  "65536",
      },
    });

    // Read Python stdout line by line; each line is a JSON message
    const rl = readline.createInterface({ input: py.stdout, crlfDelay: Infinity });
    rl.on("line", (line) => {
      const trimmed = line.trim();
      if (!trimmed) return;
      try {
        const msg = JSON.parse(trimmed);
        broadcast(msg);
      } catch {
        // Ignore non-JSON lines (shouldn't appear in --stream mode)
      }
    });

    // Forward Python stderr to our console for debugging
    py.stderr.on("data", chunk => process.stdout.write(chunk));

    py.on("close", (code) => {
      rl.close();
      if (code === 0) resolve();
      else reject(new Error(`Python exited with code ${code}`));
    });

    py.on("error", reject);
  });
}

// ─────────────────────────────────────────────────────────────────────────────
app.listen(PORT, () => {
  console.log(`\n✅  HTTP API  →  http://localhost:${PORT}`);
  console.log(`✅  WebSocket →  ws://localhost:${WS_PORT}`);
  console.log(`    Dataset   →  ${DATA_ROOT}\n`);
});