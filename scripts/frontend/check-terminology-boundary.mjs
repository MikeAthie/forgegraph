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
  /^frontend\/pages\/ops(?:\.tsx|\/)/,
  /^frontend\/pages\/workflows\//,
  /^frontend\/components\/graph-editor\//,
  /^frontend\/components\/ops\//,
  /^frontend\/components\/runs\//,
];

const primaryCopyAdvancedPathPatterns = advancedPathPatterns.filter(
  (pattern) =>
    !pattern.test("frontend/components/runs/MemoryActivityPanel.tsx"),
);

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

const runtimeCopyForbiddenPatterns = [
  /\bengine\b/i,
  /\bsnapshot\b/i,
  /\bcheckpoints?\b/i,
  /\bsource of truth\b/i,
];

const productCopyForbiddenPatterns = [
  /\bcompany operating graph\b/i,
  /\boperating graph\b/i,
  /\bcommercial media workflow\b/i,
  /\bworkflow proof\b/i,
  /\bagent-style\b/i,
  /\bdepartment agent\b/i,
  /\bActive Agents\b/i,
  /\bAgent steps\b/i,
  /\bAgent events\b/i,
  /\bcontinue this run\b/i,
  /\bFinal output\b/i,
  /\bRun memory timeline\b/i,
  /\bThis node recorded\b/i,
  /\bDead-lettered\b/i,
  /\bDead Letters\b/i,
  /\bProjection Lag\b/i,
  /\bRuntime Intent Lag\b/i,
  /\bCanonical state\b/i,
  /\bLifecycle ID\b/i,
  /\bRejected lifecycle events\b/i,
  /\bStale \/ late events\b/i,
];

const runtimeCopyAllowlist = [
  {
    path: /^frontend\/components\/company\/CompanyBuilderForm\.tsx$/,
    line: /technical execution internals/i,
  },
  {
    path: /^frontend\/components\/os\/OperationDetailView\.tsx$/,
    line: /technical execution internals/i,
  },
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

function shouldScanRuntimeCopyFile(filePath) {
  return /\.(tsx?|jsx?)$/.test(toRepoPath(filePath));
}

function shouldScanProductCopyFile(filePath) {
  const repoPath = toRepoPath(filePath);
  if (!/\.(tsx?|jsx?)$/.test(repoPath)) {
    return false;
  }
  return !primaryCopyAdvancedPathPatterns.some((pattern) =>
    pattern.test(repoPath),
  );
}

function isRuntimeCopyAllowed(repoPath, line) {
  return runtimeCopyAllowlist.some(
    (entry) => entry.path.test(repoPath) && entry.line.test(line),
  );
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

const runtimeCopyFiles = scanRoots
  .flatMap((root) => {
    const absoluteRoot = path.join(repoRoot, root);
    if (!fs.existsSync(absoluteRoot)) {
      return [];
    }

    const pending = [absoluteRoot];
    const collected = [];

    while (pending.length > 0) {
      const current = pending.pop();
      const stat = fs.statSync(current);
      if (stat.isDirectory()) {
        for (const child of fs.readdirSync(current)) {
          pending.push(path.join(current, child));
        }
      } else if (shouldScanRuntimeCopyFile(current)) {
        collected.push(current);
      }
    }

    return collected;
  })
  .filter((file, index, allFiles) => allFiles.indexOf(file) === index);

const productCopyFiles = scanRoots
  .flatMap((root) => {
    const absoluteRoot = path.join(repoRoot, root);
    if (!fs.existsSync(absoluteRoot)) {
      return [];
    }

    const pending = [absoluteRoot];
    const collected = [];

    while (pending.length > 0) {
      const current = pending.pop();
      const stat = fs.statSync(current);
      if (stat.isDirectory()) {
        for (const child of fs.readdirSync(current)) {
          pending.push(path.join(current, child));
        }
      } else if (shouldScanProductCopyFile(current)) {
        collected.push(current);
      }
    }

    return collected;
  })
  .filter((file, index, allFiles) => allFiles.indexOf(file) === index);

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

for (const file of runtimeCopyFiles) {
  const repoPath = toRepoPath(file);
  const lines = fs.readFileSync(file, "utf8").split(/\r?\n/);

  lines.forEach((line, index) => {
    if (isRuntimeCopyAllowed(repoPath, line)) {
      return;
    }

    const match = runtimeCopyForbiddenPatterns.find((pattern) =>
      pattern.test(line),
    );
    if (match) {
      violations.push(`${repoPath}:${index + 1}: ${line.trim()}`);
    }
  });
}

for (const file of productCopyFiles) {
  const repoPath = toRepoPath(file);
  const lines = fs.readFileSync(file, "utf8").split(/\r?\n/);

  lines.forEach((line, index) => {
    const match = productCopyForbiddenPatterns.find((pattern) =>
      pattern.test(line),
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
