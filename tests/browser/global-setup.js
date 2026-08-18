const { spawn, spawnSync } = require("node:child_process");
const { mkdtempSync, rmSync } = require("node:fs");
const net = require("node:net");
const os = require("node:os");
const path = require("node:path");

function pythonCommand() {
  return (
    process.env.PYTHON || (process.platform === "win32" ? "python" : "python3")
  );
}

async function availablePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const { port } = server.address();
      server.close(() => resolve(port));
    });
  });
}

async function waitForServer(url, processHandle) {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    if (processHandle.exitCode !== null) {
      throw new Error(`Synthetic site server exited with ${processHandle.exitCode}`);
    }
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch (_error) {
      // The server may still be binding its socket.
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`Synthetic site server did not become ready at ${url}`);
}

module.exports = async () => {
  const repository = path.resolve(__dirname, "../..");
  const temporaryRoot = mkdtempSync(path.join(os.tmpdir(), "sprint-browser-ci-"));
  const site = path.join(temporaryRoot, "nested", "generated-site");
  const python = pythonCommand();
  const build = spawnSync(
    python,
    [path.join(repository, "tests/support/build_ci_site.py"), "--output", site],
    { cwd: repository, encoding: "utf8" },
  );
  if (build.status !== 0) {
    rmSync(temporaryRoot, { recursive: true, force: true });
    throw new Error(
      `Synthetic site generation failed (${build.status})\n` +
        `stdout:\n${build.stdout}\nstderr:\n${build.stderr}`,
    );
  }

  const port = await availablePort();
  const server = spawn(
    python,
    [
      "-m",
      "http.server",
      String(port),
      "--bind",
      "127.0.0.1",
      "--directory",
      temporaryRoot,
    ],
    { cwd: repository, stdio: "ignore" },
  );
  const baseUrl = `http://127.0.0.1:${port}/nested/generated-site/`;
  try {
    await waitForServer(baseUrl, server);
  } catch (error) {
    server.kill();
    rmSync(temporaryRoot, { recursive: true, force: true });
    throw error;
  }
  process.env.SPRINT_CI_SITE_URL = baseUrl;

  return async () => {
    server.kill();
    rmSync(temporaryRoot, { recursive: true, force: true });
  };
};
