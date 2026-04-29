import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../..",
);
const scanRoots = ["frontend/pages", "frontend/components"];
const extraFiles = ["frontend/lib/seo.ts"];

// These surfaces are explicit advanced/admin tooling. Primary product surfaces
// must stay outside this list and must pass the product terminology boundary.
const advancedPathPatterns = [
  /^frontend\/pages\/admin\//,
  /^frontend\/pages\/analytics\//,
  /^frontend\/pages\/executions\//,
  /^frontend\/pages\/graphs(?:\.tsx|\/)/,
  /^frontend\/pages\/workflows\//,
  /^frontend\/components\/graph-editor\//,
  /^frontend\/components\/runs\//,
];

const routeLiteralPatterns = [
  /\/runs(?=\/|\?|["'`}]|$)/g,
  /\/executions(?=\/|\?|["'`}]|$)/g,
  /\/graphs(?=\/|\?|["'`}]|$)/g,
  /\/workflows(?=\/|\?|["'`}]|$)/g,
  /"@graph"/g,
];

const forbiddenPatterns = [
  /\bgraph\b/i,
  /\bnode\b/i,
  /\brun\b/i,
  /\bruns\b/i,
  /\bexecution\b/i,
  /\bexecutions\b/i,
  /\bworkflow\b/i,
  /\bworkflows\b/i,
  /\bgraph_id\b/i,
  /\bgraph_name\b/i,
  /\bgraph_version(?:_id)?\b/i,
  /\bgraph_json\b/i,
  /\brun_id\b/i,
  /\bexecution_id\b/i,
  /workflow_id/i,
  /workflow_revision_id/i,
  /\bnode_id\b/i,
  /\bnode_type\b/i,
  /\bnode_runs\b/i,
  /\boutput_json\b/i,
  /\bGraph(?:Detail|Json|ListItem|Version|VersionSummary)?\b/,
  /\bRun(?:Detail|ListItem|MemoryActivitySummary|LLMAccess)?\b/,
  /\bNodeRun(?:Item|Status)?\b/,
  /\bGraph[A-Z][A-Za-z0-9_]*\b/,
  /\bNode[A-Z][A-Za-z0-9_]*\b/,
  /\bRun[A-Z][A-Za-z0-9_]*\b/,
  /\bExecution[A-Z][A-Za-z0-9_]*\b/,
  /\bWorkflow[A-Z][A-Za-z0-9_]*\b/,
];

function toRepoPath(filePath) {
  return path.relative(repoRoot, filePath).replaceAll(path.sep, "/");
}

function shouldScanFile(filePath) {
  const repoPath = toRepoPath(filePath);
  if (!/\.(tsx?|jsx?)$/.test(repoPath)) {
    return false;
  }
  return !advancedPathPatterns.some((pattern) => pattern.test(repoPath));
}

function collectFiles(root) {
  const absoluteRoot = path.join(repoRoot, root);
  if (!fs.existsSync(absoluteRoot)) {
    return [];
  }

  const pending = [absoluteRoot];
  const files = [];

  while (pending.length > 0) {
    const current = pending.pop();
    const stat = fs.statSync(current);
    if (stat.isDirectory()) {
      for (const child of fs.readdirSync(current)) {
        pending.push(path.join(current, child));
      }
    } else if (shouldScanFile(current)) {
      files.push(current);
    }
  }

  return files;
}

const files = [
  ...scanRoots.flatMap(collectFiles),
  ...extraFiles
    .map((file) => path.join(repoRoot, file))
    .filter((file) => fs.existsSync(file)),
];

const violations = [];

for (const file of files) {
  const repoPath = toRepoPath(file);
  const lines = fs.readFileSync(file, "utf8").split(/\r?\n/);

  lines.forEach((line, index) => {
    const searchableLine = routeLiteralPatterns.reduce(
      (current, pattern) => current.replace(pattern, ""),
      line,
    );
    const match = forbiddenPatterns.find((pattern) =>
      pattern.test(searchableLine),
    );
    if (match) {
      violations.push(`${repoPath}:${index + 1}: ${line.trim()}`);
    }
  });
}

if (violations.length > 0) {
  console.error(
    "Terminology boundary violations found in primary frontend surfaces:",
  );
  console.error(violations.map((violation) => `- ${violation}`).join("\n"));
  console.error(
    "\nUse product ViewModels/repositories or move internal terminology into an advanced/internal surface.",
  );
  process.exit(1);
}

console.log("Terminology boundary check passed.");
