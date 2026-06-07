const express   = require("express");
const cors      = require("cors");
const fs        = require("fs");
const path      = require("path");
const { spawn } = require("child_process");
const readline  = require("readline");
const WebSocket = require("ws");

const app     = express();
const PORT    = 3001;
const WS_PORT = 3002;

const TRAIN_JSON = path.join(__dirname, "..", "data", "train", "instances.json");
const OPTIMIZER = path.join(__dirname, "..", "optimizer", "run_preprocessed.py");

app.use(cors());
app.use(express.json());

// ─────────────────────────────────────────────────────────────────────────────
// WebSocket server (port 3002)
//
// Each client connection owns its own Python child process.
// Protocol (client → server):
//   { action: "run",  instancePath: "<abs path>", maxTime?: 90 }
//   { action: "stop" }
//
// Protocol (server → client, each message is a JSON line from Python or a
// synthetic control message):
//   { type: "instance_info",    container, n_items, lower_bound }
//   { type: "iteration_update", iteration, max_iter, best_bins,
//           best_dissipation, best_composite, temperature,
//           last_udhc, udhc_accepted, solution:[...] }
//   { type: "integration_applied", bins_reduced_by, new_bins }
//   { type: "instance_complete", bins_used, lower_bound, gap_pct,
//           dissipation, composite_score, volume_util_pct, runtime_s,
//           container, n_items, items:[...] }
//   { type: "stopped" }
//   { type: "error",       error: "..." }
//   { type: "run_closed",  code: 0|1 }
// ─────────────────────────────────────────────────────────────────────────────
const wss = new WebSocket.Server({ port: WS_PORT });

wss.on("connection", (ws) => {
  console.log("WS client connected");
  let childProc = null;

  function send(obj) {
    if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj));
  }

  function killChild() {
    if (childProc) {
      try { childProc.kill("SIGTERM"); } catch {}
      childProc = null;
    }
  }

  ws.on("message", (raw) => {
    let msg;
    try { msg = JSON.parse(raw); } catch { return; }

    if (msg.action === "run") {
      killChild(); // abort any prior run for this connection

      const instanceIndex = msg.instanceIndex;
      if (instanceIndex === undefined || instanceIndex === null) {
        send({ type: "error", error: "instanceIndex required" });
        return;
      }

      // Load preprocessed training dataset
      let trainData;
      try {
        trainData = JSON.parse(fs.readFileSync(TRAIN_JSON, 'utf8'));
      } catch (err) {
        send({ type: "error", error: `Failed to load training dataset: ${err.message}` });
        return;
      }

      const instances = trainData.instances || [];
      if (instanceIndex < 0 || instanceIndex >= instances.length) {
        send({ type: "error", error: `Instance index ${instanceIndex} out of range` });
        return;
      }

      const maxTime = Math.min(Number(msg.maxTime) || 90, 300);

      childProc = spawn(
        "python",
        [OPTIMIZER, String(instanceIndex), "--stream", "--max-time", String(maxTime)],
        { env: { ...process.env, PYTHONMALLOC: "malloc" } }
      );

      const rl = readline.createInterface({ input: childProc.stdout, crlfDelay: Infinity });
      rl.on("line", (line) => {
        const t = line.trim();
        if (!t) return;
        try { send(JSON.parse(t)); } catch {}
      });

      childProc.stderr.on("data", (chunk) => process.stdout.write(chunk));

      childProc.on("close", (code) => {
        rl.close();
        send({ type: "run_closed", code });
        childProc = null;
      });

      childProc.on("error", (err) => {
        send({ type: "error", error: err.message });
        childProc = null;
      });
    }

    if (msg.action === "stop") {
      killChild();
      send({ type: "stopped" });
    }
  });

  ws.on("close", () => {
    console.log("WS client disconnected");
    killChild();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// GET /api/instances
// Returns all preprocessed training instances from data/train/instances.json.
// ─────────────────────────────────────────────────────────────────────────────
app.get("/api/instances", (req, res) => {
  try {
    if (!fs.existsSync(TRAIN_JSON)) {
      return res.status(404).json({ error: "Training dataset not found. Run preprocess.py first." });
    }
    
    const trainData = JSON.parse(fs.readFileSync(TRAIN_JSON, 'utf8'));
    const instances = trainData.instances || [];
    
    const result = instances.map((inst, index) => ({
      index,
      id: inst.id,
      label: inst.id,
      item_count: inst.item_count || inst.items?.length || 0,
    }));
    
    res.json({ count: result.length, instances: result });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ─────────────────────────────────────────────────────────────────────────────
app.listen(PORT, () => {
  console.log(`\n✅  HTTP API  →  http://localhost:${PORT}`);
  console.log(`✅  WebSocket →  ws://localhost:${WS_PORT}`);
  console.log(`    Dataset   →  ${TRAIN_JSON}\n`);
});
