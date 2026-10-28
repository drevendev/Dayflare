"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const script = fs.readFileSync(path.join(__dirname, "../tools/m1_dataset_share.js"), "utf8");
const digest = "a".repeat(64);
const method = "v0-empirical-35d";
const end = "2026-10-25";
const good = new URLSearchParams({
  df_dataset: digest, df_method: method, df_end: end,
  df_edition: "en.wikipedia", df_page: "1234",
}).toString();
function check(search, targetExists = true) {
  const trace = [];
  const status = {
    dataset: {dataset: digest, method, end}, style: {},
    setAttribute: (k, v) => trace.push(["role", k, v]),
    focus: () => trace.push(["status-focus"]),
  };
  const message = {textContent: "No JavaScript fallback"};
  const heading = {
    setAttribute: (k, v) => trace.push(["heading-attribute", k, v]),
    focus: () => trace.push(["heading-focus"]),
  };
  const detail = {
    querySelector: (sel) => (sel === "h3" ? heading : null),
    scrollIntoView: () => trace.push(["scrolled"]),
  };
  const ids = [];
  const document = {getElementById: (id) => {
    ids.push(id);
    if (id === "share-restore") return status;
    if (id === "share-message") return message;
    if (targetExists && id === "detail-en-wikipedia-1234") return detail;
    return null;
  }};
  vm.runInNewContext(script, {window: {location: {search}}, document, URLSearchParams});
  return {status, message, ids, trace};
}
const ok = check("?" + good);
assert.match(ok.message.textContent, /Shared history verified/);
assert.ok(ok.trace.some((row) => row[0] === "scrolled"));
assert.ok(ok.trace.some((row) => row[0] === "heading-focus"));
assert.deepEqual(ok.ids.slice(-1), ["detail-en-wikipedia-1234"]);
for (const [label, url, existing] of [
  ["stale dataset", good.replace(digest, "b".repeat(64)), true],
  ["duplicate", good + "&df_dataset=" + digest, true],
  ["extraneous", good + "&extra=1", true],
  ["invalid edition", good.replace("en.wikipedia", "en.wiktionary"), true],
  ["missing page", good, false],
  ["negative ID", good.replace("df_page=1234", "df_page=-3"), true],
]) {
  const result = check("?" + url, existing);
  assert.equal(result.status.style.display, "block", label);
  assert.match(result.message.textContent, /No different history has been substituted/, label);
  assert.ok(result.trace.some((row) => row[0] === "status-focus"), label);
  assert.ok(!result.trace.some((row) => row[0] === "scrolled"), label);
}
assert.equal(check("").message.textContent, "No JavaScript fallback");
console.log("M1 dataset-bound share restore: valid, stale, duplicate, extra, invalid edition/page, no-JS fallback PASS");
