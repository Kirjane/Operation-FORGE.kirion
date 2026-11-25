const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

function repoRoot() { return path.resolve(__dirname, '..', '..', '..'); }
function readJson(file) { return JSON.parse(fs.readFileSync(file, 'utf8')); }
function writeJson(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, JSON.stringify(value, null, 2) + '\n', 'utf8');
}
function sha256(value) { return crypto.createHash('sha256').update(value).digest('hex'); }
function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.keys(value).sort().map(k => [k, canonical(value[k])]));
  }
  return value;
}
function canonicalJson(value) { return JSON.stringify(canonical(value)); }
// Control inputs are already typed by JSON/MCP schemas. Never coerce a
// malformed caller value into a weaker risk dimension or a different signal.
function validateControlRecord(value, field, valid) {
  if (value === undefined) return {};
  if (!value || typeof value !== 'object' || Array.isArray(value) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(value))) {
    throw new Error(`${field} must be an object.`);
  }
  const entries = Object.entries(value);
  for (const [key, item] of entries) {
    if (!valid(item)) throw new Error(`Invalid ${field}.${key}`);
  }
  return Object.fromEntries(entries);
}
function validateRiskOverrides(value) {
  return validateControlRecord(value, 'risk_overrides', n => Number.isInteger(n) && n >= 0 && n <= 4);
}
function validateSignals(value) {
  return validateControlRecord(value, 'signals', v => typeof v === 'boolean');
}
function normalizeTask(task) {
  if (!task || task.version !== 1 || typeof task.id !== 'string' || !task.id.trim() || typeof task.intent !== 'string' || !task.intent.trim()) {
    throw new Error('Task must contain version=1, non-empty id, and non-empty intent.');
  }
  const journeys = Array.isArray(task.primary_journeys) ? task.primary_journeys : [];
  const ids = new Set();
  for (const j of journeys) {
    if (!j || typeof j.id !== 'string' || !/^[a-z0-9][a-z0-9._-]*$/.test(j.id) || typeof j.description !== 'string' || !j.description.trim()) {
      throw new Error('Each primary journey needs a stable lowercase id and description.');
    }
    if (ids.has(j.id)) throw new Error(`Duplicate primary journey id: ${j.id}`);
    ids.add(j.id);
  }
  return {version:1,id:task.id.trim(),intent:task.intent.trim(),...(task.type?{type:String(task.type).trim()}:{}),constraints:Array.isArray(task.constraints)?task.constraints.map(String):[],signals:validateSignals(task.signals),risk_overrides:validateRiskOverrides(task.risk_overrides),primary_journeys:journeys,repository:task.repository||{},acceptance:Array.isArray(task.acceptance)?task.acceptance.map(String):[]};
}
function loadConfig(root = repoRoot()) {
  const h = path.join(root, 'harness');
  return {manifest:readJson(path.join(h,'HARNESS_MANIFEST.json')),lanes:readJson(path.join(h,'config','lane-registry.json')),taskTypes:readJson(path.join(h,'config','task-types.json')),risk:readJson(path.join(h,'config','risk-model.json')),routing:readJson(path.join(h,'config','routing-rules.json')),gates:readJson(path.join(h,'config','gates.json')),evidence:readJson(path.join(h,'config','evidence-levels.json')),semanticProvider:readJson(path.join(h,'notion','control-plane.json')),routePack:readJson(path.join(h,'notion','route-pack.json'))};
}
module.exports = { repoRoot, readJson, writeJson, sha256, canonicalJson, normalizeTask, loadConfig, validateRiskOverrides, validateSignals };
