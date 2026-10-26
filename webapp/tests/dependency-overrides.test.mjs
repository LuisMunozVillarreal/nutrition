import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { test } from "vitest";

const require = createRequire(import.meta.url);
const semver = require("semver");

// Overrides must satisfy ordinary dependency contracts, not only peers/engines.
// Resolve from each consumer so nested copies cannot hide an incompatible pin.
test.each([
  ["vite", "picomatch"],
  ["vitest", "picomatch"],
  ["vite", "postcss"],
  ["micromatch", "picomatch"],
])("%s resolves a patched %s within its declared dependency range", async (consumer, dependency) => {
  const consumerPath = require.resolve(`${consumer}/package.json`);
  const consumerRequire = createRequire(consumerPath);
  const declaredRange = require(consumerPath).dependencies[dependency];
  const installedVersion = consumerRequire(`${dependency}/package.json`).version;

  assert.equal(typeof declaredRange, "string");
  assert.ok(
    semver.satisfies(installedVersion, declaredRange),
    `${consumer} requires ${dependency}@${declaredRange}, resolved ${installedVersion}`,
  );

  const installed = consumerRequire(dependency);
  if (dependency === "picomatch") {
    const matches = installed("**/{meal,snack}.*");
    assert.equal(matches("recipes/meal.js"), true);
    assert.equal(matches("recipes/snack.ts"), true);
    assert.equal(matches("recipes/drink.js"), false);
  } else {
    const css = await installed([]).process(".meal { color: green; }", { from: undefined });
    assert.match(css.css, /\.meal/);
  }
});

test.each(["nanoid", "diff", "js-yaml", "serialize-javascript", "eslint-plugin-react-hooks"])(
  "%s overrides satisfy every installed consumer's declared range",
  (dependency) => {
    const lock = require("../package-lock.json");
    const consumers = Object.entries(lock.packages).filter(
      ([, metadata]) => metadata.dependencies?.[dependency],
    );
    assert.ok(consumers.length > 0, `the lockfile must contain ${dependency} consumers`);

    for (const [packagePath] of consumers) {
      const consumerPath = new URL(`../${packagePath}/package.json`, import.meta.url);
      const consumerRequire = createRequire(consumerPath);
      const consumer = consumerRequire(consumerPath.pathname);
      const declaredRange = consumer.dependencies[dependency];
      const installedVersion = consumerRequire(`${dependency}/package.json`).version;
      assert.ok(
        semver.satisfies(installedVersion, declaredRange),
        `${consumer.name} requires ${dependency}@${declaredRange}, resolved ${installedVersion}`,
      );
    }
  },
);

test("patched brace expansion remains compatible with every minimatch consumer", () => {
  const lock = require("../package-lock.json");
  const consumers = Object.entries(lock.packages).filter(
    ([, metadata]) => metadata.dependencies?.minimatch,
  );
  assert.ok(consumers.length > 0, "the lockfile must contain minimatch consumers");

  for (const [packagePath] of consumers) {
    // Resolve like the actual consumer, regardless of npm's hoisting layout.
    const consumerRequire = createRequire(
      new URL(`../${packagePath}/package.json`, import.meta.url),
    );
    const loaded = consumerRequire("minimatch");
    const minimatch = loaded.minimatch ?? loaded;
    assert.equal(minimatch("alpha.js", "{alpha,beta}.js"), true, packagePath);
    assert.equal(minimatch("beta.js", "{alpha,beta}.js"), true, packagePath);
    assert.equal(minimatch("gamma.js", "{alpha,beta}.js"), false, packagePath);
  }
});

test("YAML overrides preserve legacy ESLint and modern config loaders", () => {
  const directory = mkdtempSync(path.join(tmpdir(), "nutrition-yaml-"));
  try {
    const configPath = path.join(directory, "config.yaml");
    writeFileSync(configPath, "rules:\n  eqeqeq: error\n");
    const { Legacy } = require("@eslint/eslintrc");
    const configs = new Legacy.ConfigArrayFactory().loadFile(configPath);
    assert.equal(configs[0].rules.eqeqeq, "error");

    const { cosmiconfigSync } = require("cosmiconfig");
    const loaded = cosmiconfigSync("nutrition").load(configPath);
    assert.equal(loaded.config.rules.eqeqeq, "error");
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

test("Mocha loads YAML and renders assertion diffs from parallel workers", () => {
  const directory = mkdtempSync(path.join(tmpdir(), "nutrition-mocha-"));
  try {
    const configPath = path.join(directory, ".mocharc.yaml");
    const testPath = path.join(directory, "probe.cjs");
    writeFileSync(configPath, "reporter: spec\ncolor: false\n");
    writeFileSync(testPath, [
      'const assert = require("node:assert/strict");',
      'it("passes in a worker", () => assert.equal(1, 1));',
      'it("renders a diff", () => assert.equal("actual meal", "expected meal"));',
    ].join("\n"));
    const result = spawnSync(process.execPath, [
      require.resolve("mocha/bin/mocha.js"),
      "--config", configPath,
      "--parallel", "--jobs", "2",
      testPath,
    ], { cwd: directory, encoding: "utf8", timeout: 20_000 });
    assert.equal(result.error, undefined);
    assert.equal(result.status, 1, result.stdout + result.stderr);
    assert.match(result.stdout, /1 passing/);
    assert.match(result.stdout, /1 failing/);
    assert.match(result.stdout, /-actual meal/);
    assert.match(result.stdout, /\+expected meal/);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

test("scoped security overrides preserve the framework and test-runner APIs", async () => {
  const postcss = require("postcss");
  const css = await postcss([]).process(".meal { color: green; }", { from: undefined });
  assert.match(css.css, /\.meal/);

  const sharp = require("sharp");
  const image = await sharp({
    create: {
      width: 2,
      height: 2,
      channels: 4,
      background: { r: 0, g: 128, b: 0, alpha: 1 },
    },
  })
    .png()
    .toBuffer({ resolveWithObject: true });
  assert.equal(image.info.width, 2);
  assert.equal(image.info.height, 2);

  const mochaRequire = createRequire(require.resolve("mocha/package.json"));
  const diff = mochaRequire("diff");
  assert.deepEqual(
    diff.diffChars("macro", "micron").map(({ added, removed, value }) => ({
      added: Boolean(added),
      removed: Boolean(removed),
      value,
    })),
    [
      { added: false, removed: false, value: "m" },
      { added: false, removed: true, value: "a" },
      { added: true, removed: false, value: "i" },
      { added: false, removed: false, value: "cro" },
      { added: true, removed: false, value: "n" },
    ],
  );

  const serialize = mochaRequire("serialize-javascript");
  const serialized = serialize({ meal: /breakfast/ });
  const restored = Function(`"use strict"; return (${serialized});`)();
  assert.equal(restored.meal.test("breakfast"), true);
});
