import assert from "node:assert/strict";
import { createRequire } from "node:module";
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

function minimatchFrom(modulePath) {
  const loaded = require(modulePath);
  return loaded.minimatch ?? loaded;
}

test("patched brace expansion remains compatible with every legacy minimatch consumer", () => {
  const consumers = [
    minimatchFrom("minimatch"),
    minimatchFrom("find-cypress-specs/node_modules/minimatch"),
    minimatchFrom("mocha/node_modules/minimatch"),
  ];

  for (const minimatch of consumers) {
    assert.equal(minimatch("alpha.js", "{alpha,beta}.js"), true);
    assert.equal(minimatch("beta.js", "{alpha,beta}.js"), true);
    assert.equal(minimatch("gamma.js", "{alpha,beta}.js"), false);
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
