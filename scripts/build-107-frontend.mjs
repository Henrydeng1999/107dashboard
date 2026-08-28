import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { spawnSync } from "node:child_process";

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const isWindows = process.platform === "win32";
const scriptPath = resolve(
  projectRoot,
  "scripts",
  isWindows ? "build-107-frontend.ps1" : "build-107-frontend.sh",
);

function findWindowsPowerShell() {
  for (const command of ["pwsh.exe", "powershell.exe"]) {
    const probe = spawnSync(command, ["-NoLogo", "-NoProfile", "-Command", "exit 0"], {
      stdio: "ignore",
      windowsHide: true,
    });
    if (!probe.error && probe.status === 0) {
      return command;
    }
  }
  return null;
}

const command = isWindows ? findWindowsPowerShell() : "bash";
if (command === null) {
  console.error("PowerShell is required to build the 107 frontend on Windows.");
  process.exit(1);
}

const argumentsForShell = isWindows
  ? ["-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", scriptPath]
  : [scriptPath];
const result = spawnSync(command, argumentsForShell, {
  cwd: projectRoot,
  stdio: "inherit",
  windowsHide: false,
});

if (result.error) {
  console.error(`Unable to start ${command}: ${result.error.message}`);
  process.exit(1);
}
process.exit(result.status ?? 1);
