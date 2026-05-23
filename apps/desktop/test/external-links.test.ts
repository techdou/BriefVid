import assert from "node:assert/strict";

import { isAllowedExternalUrl, isCrossOriginNavigation } from "../electron/externalLinks.ts";

function run(name: string, fn: () => Promise<void> | void) {
  Promise.resolve(fn()).then(() => {
    console.log(`ok - ${name}`);
  }).catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
}

run("allows only http and https external urls", () => {
  assert.equal(isAllowedExternalUrl("https://www.bilibili.com/video/BV1xx411c7mD"), true);
  assert.equal(isAllowedExternalUrl("http://127.0.0.1:3838/library"), true);
  assert.equal(isAllowedExternalUrl("file:///C:/Windows/System32/calc.exe"), false);
  assert.equal(isAllowedExternalUrl("javascript:alert(1)"), false);
  assert.equal(isAllowedExternalUrl("data:text/html,<script>alert(1)</script>"), false);
  assert.equal(isAllowedExternalUrl("mailto:test@example.com"), false);
  assert.equal(isAllowedExternalUrl("bilibili://video/BV1xx411c7mD"), false);
  assert.equal(isAllowedExternalUrl("not a url"), false);
});

run("detects cross origin navigations without throwing", () => {
  assert.equal(isCrossOriginNavigation("http://127.0.0.1:3838/a", "http://127.0.0.1:3838/b"), false);
  assert.equal(isCrossOriginNavigation("https://www.bilibili.com/video/BV1xx411c7mD", "http://127.0.0.1:3838/library"), true);
  assert.equal(isCrossOriginNavigation("not a url", "http://127.0.0.1:3838/library"), false);
});
