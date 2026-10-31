const assert = require("node:assert/strict");
const test = require("node:test");
const { extractAnalysisPath, resolveAnalysisPath, videoPathToFileUrl } = require("../app-utils");

test("extracts the exact generated analysis path, including spaces", () => {
  const expected = String.raw`C:\Users\Player Name\analisis\match_20261014_120000_data.json`;
  const line = `✅ 3 observaciones guardadas en ${expected}`;

  assert.equal(extractAnalysisPath(line), expected);
});

test("returns null when the script did not report a result path", () => {
  assert.equal(extractAnalysisPath("Análisis terminado"), null);
});

test("resolves a relative result path from the Python script directory", () => {
  assert.equal(
    resolveAnalysisPath(String.raw`C:\coach`, String.raw`analisis\match_data.json`),
    String.raw`C:\coach\analisis\match_data.json`
  );
});

test("converts Windows paths with reserved characters to valid file URLs", () => {
  const videoPath = String.raw`C:\Users\Player Name\Match #1.mp4`;

  assert.equal(
    videoPathToFileUrl(videoPath),
    "file:///C:/Users/Player%20Name/Match%20%231.mp4"
  );
});