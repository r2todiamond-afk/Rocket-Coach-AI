const path = require("path");
const { pathToFileURL } = require("url");

function extractAnalysisPath(line) {
  const match = String(line).match(/observaciones guardadas en (.+_data\.json)\s*$/i);
  return match ? match[1].trim() : null;
}

function videoPathToFileUrl(videoPath) {
  return pathToFileURL(videoPath).href;
}

function resolveAnalysisPath(scriptDir, reportedPath) {
  return path.resolve(scriptDir, reportedPath);
}

module.exports = { extractAnalysisPath, resolveAnalysisPath, videoPathToFileUrl };