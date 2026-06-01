import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import path from "node:path";

const containerName = process.env.FRONTEND_CONTAINER_NAME ?? "forgegraph-frontend";
const packageJsonPath = path.resolve(process.cwd(), "package.json");
const packageJson = JSON.parse(readFileSync(packageJsonPath, "utf8"));
const expected = {
  react: normalizeVersionSpec(packageJson.dependencies?.react),
  "react-dom": normalizeVersionSpec(packageJson.dependencies?.["react-dom"]),
};

let installed;
try {
  const output = execFileSync(
    "docker",
    [
      "exec",
      containerName,
      "sh",
      "-lc",
      "node -e \"const names=['react','react-dom']; const out={}; for (const name of names) out[name]=require(name + '/package.json').version; console.log(JSON.stringify(out));\"",
    ],
    { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] },
  );
  installed = JSON.parse(output);
} catch (error) {
  console.error(`Unable to inspect frontend dependencies inside Docker container '${containerName}'.`);
  console.error("Start the Docker frontend first, then rerun this doctor.");
  if (error?.stderr) {
    console.error(String(error.stderr).trim());
  }
  process.exit(1);
}

const mismatches = Object.entries(expected).filter(([name, version]) => {
  return !version || installed[name] !== version;
});

if (mismatches.length === 0) {
  console.log(
    `Frontend Docker volume matches package.json: react ${installed.react}, react-dom ${installed["react-dom"]}.`,
  );
  process.exit(0);
}

console.error("Frontend Docker node_modules volume is stale.");
for (const [name, version] of mismatches) {
  console.error(`- ${name}: expected ${version ?? "missing dependency"}, found ${installed[name] ?? "missing"}`);
}
console.error("");
console.error("Remediation:");
console.error("  docker compose -f docker-compose.yml -f docker-compose.dev.yml stop frontend");
console.error("  docker volume rm forgegraph_frontend_node_modules");
console.error("  docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d frontend");
process.exit(1);

function normalizeVersionSpec(spec) {
  if (typeof spec !== "string" || spec.trim() === "") {
    return "";
  }
  return spec.trim().replace(/^[~^]/, "");
}
