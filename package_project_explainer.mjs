#!/usr/bin/env node

import {
  existsSync,
  readFileSync,
  readdirSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

function parseArguments(argv) {
  const options = {
    input: "project_explainer_artifact.json",
    output: "project_explainer.html",
  };
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === "--help" || argument === "-h") return { help: true };
    if (!["--input", "--output", "--plugin-root"].includes(argument)) {
      throw new Error(`Unknown argument: ${argument}`);
    }
    const value = argv[index + 1];
    if (!value || value.startsWith("--")) {
      throw new Error(`${argument} requires a value.`);
    }
    options[argument.slice(2)] = value;
    index += 1;
  }
  return options;
}

function findPluginRoot(configuredRoot) {
  if (configuredRoot) {
    const explicitRoot = resolve(configuredRoot);
    if (!existsSync(explicitRoot)) {
      throw new Error(`Data Analytics plugin root does not exist: ${explicitRoot}`);
    }
    return explicitRoot;
  }

  const cacheRoot = join(
    homedir(),
    ".codex",
    "plugins",
    "cache",
    "openai-curated-remote",
    "data-analytics",
  );
  if (!existsSync(cacheRoot)) {
    throw new Error("Data Analytics plugin cache was not found. Pass --plugin-root explicitly.");
  }
  const versions = readdirSync(cacheRoot, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .sort()
    .reverse();
  for (const version of versions) {
    const candidate = join(cacheRoot, version);
    const builder = join(
      candidate,
      "skills",
      "build-report",
      "scripts",
      "build_portable_artifact.mjs",
    );
    if (existsSync(builder)) return candidate;
  }
  throw new Error("No installed Data Analytics portable-report builder was found.");
}

async function main() {
  const options = parseArguments(process.argv.slice(2));
  if (options.help) {
    process.stdout.write(
      "Usage: node package_project_explainer.mjs " +
        "[--input artifact.json] [--output report.html] [--plugin-root path]\n",
    );
    return;
  }

  const pluginRoot = findPluginRoot(options["plugin-root"]);
  const scriptRoot = join(pluginRoot, "skills", "build-report", "scripts");
  const { buildPortableArtifact } = await import(
    pathToFileURL(join(scriptRoot, "build_portable_artifact.mjs")).href
  );
  const { extractPortableChartSvgs } = await import(
    pathToFileURL(join(scriptRoot, "extract_portable_chart_svgs.mjs")).href
  );
  const { verifyPortableArtifact } = await import(
    pathToFileURL(join(scriptRoot, "verify_portable_artifact.mjs")).href
  );

  const artifactPath = resolve(options.input);
  const outputPath = resolve(options.output);
  const temporaryPath = join(dirname(outputPath), `${outputPath.split(/[\\/]/).at(-1)}.prepatch.tmp.html`);
  const artifact = JSON.parse(readFileSync(artifactPath, "utf8"));

  try {
    let html = buildPortableArtifact(artifact);
    writeFileSync(temporaryPath, html, "utf8");
    const staticCharts = await extractPortableChartSvgs({
      actionTimeoutMs: 5_000,
      htmlPath: temporaryPath,
      readyTimeoutMs: 30_000,
    });
    html = buildPortableArtifact(artifact, { staticCharts });

    // The shared reader's 100vw top bar includes the Windows scrollbar width.
    // This narrow chrome-only override preserves the canonical payload and reader.
    const overflowFix = `<style id="project-reader-overflow-fix">
.analytics-top-bar{width:100%!important;margin-right:0!important;margin-left:0!important}
</style>`;
    html = html.replace("</head>", `${overflowFix}</head>`);
    writeFileSync(outputPath, html, "utf8");

    const verification = await verifyPortableArtifact({
      actionTimeoutMs: 5_000,
      artifactPath,
      htmlPath: outputPath,
      readyTimeoutMs: 30_000,
      screenshotPath: resolve("project_explainer_verification_failure.png"),
      timeoutMs: 45_000,
    });
    process.stdout.write(
      `${JSON.stringify(
        {
          ok: true,
          html: outputPath,
          staticChartCount: Object.keys(staticCharts).length,
          verification,
        },
        null,
        2,
      )}\n`,
    );
  } finally {
    rmSync(temporaryPath, { force: true });
  }
}

main().catch((error) => {
  process.stderr.write(`${error.stack || error.message || String(error)}\n`);
  process.exitCode = 1;
});
