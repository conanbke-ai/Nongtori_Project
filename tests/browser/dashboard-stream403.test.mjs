// 실제 제품 컴포넌트와 native Response를 사용하는 브라우저 회귀입니다.
// 사전 설치된 도구·공식 빌드만 재사용하며 설치/서버/실제 API를 실행하지 않습니다.
import assert from "node:assert/strict";
import { test } from "node:test";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { readFileSync, writeFileSync, readdirSync, mkdirSync, mkdtempSync, existsSync } from "node:fs";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { tmpdir } from "node:os";
import path from "node:path";
import { finishBrowserReceipt, prepareLinuxChildObservation } from './dashboard-stream403-runner.mjs';
test("미종료 native 403 본문에서도 실제 Dashboard DOM과 이전 목록 응답을 차단한다", { timeout: 3e4 }, async () => {
  const processObservation = prepareLinuxChildObservation({ platform: process.platform, pid: process.pid, execFile: execFileSync });
  const root = fileURLToPath(new URL("../../", import.meta.url)), source = root;
  const executablePath = process.env.NONGTORI_CHROMIUM_EXECUTABLE;
  assert.ok(executablePath && path.isAbsolute(executablePath) && existsSync(executablePath), "설치된 Chromium의 절대 경로를 NONGTORI_CHROMIUM_EXECUTABLE로 지정하세요. 자동 설치하지 않습니다.");
  const qa = process.env.NONGTORI_QA_OUTPUT_DIR ? path.resolve(process.env.NONGTORI_QA_OUTPUT_DIR) : mkdtempSync(path.join(tmpdir(), "nongtori-stream403-"));
  if (process.env.NONGTORI_QA_OUTPUT_DIR) mkdirSync(qa);
  const req = createRequire(path.join(root, "package.json"));
  // 로컬 의존성 또는 실행기가 표준 Node 경로로 제공한 도구만 사용합니다.
  // 임의 경로 탐색·fallback·동적 설치를 하지 않습니다.
  const playwrightEntry = req.resolve("playwright");
  const provisionedTool = { entry: playwrightEntry, node: process.execPath, inheritedNodePath: process.env.NODE_PATH ?? null };
  const esbuild = await import(createRequire(req.resolve("vite")).resolve("esbuild")), pw = (await import(playwrightEntry)).default;
  const hash = (b) => createHash("sha256").update(b).digest("hex");
  function pins(folder, p = "") {
    return Object.fromEntries(readdirSync(path.join(folder, p), { withFileTypes: true }).flatMap((e) => {
      assert.ok(!e.isSymbolicLink(), "제품 소스의 예상 밖 링크");
      const n = p ? p + "/" + e.name : e.name;
      return e.isDirectory() ? Object.entries(pins(folder, n)) : e.isFile() ? [[n, hash(readFileSync(path.join(folder, n)))]] : [];
    }).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0));
  }
  function protectedState() {
    return { source: pins(path.join(root, "app")), package: hash(readFileSync(path.join(root, "package.json"))), lock: hash(readFileSync(path.join(root, "pnpm-lock.yaml"))) };
  }
  const before = protectedState();
  const cssDirectory = path.join(root, "dist/client/_next/static/css");
  assert.ok(existsSync(cssDirectory), "공식 npm run build 산출물이 필요합니다. 이 검사는 빌드/설치를 자동 실행하지 않습니다.");
  const roots = readdirSync(cssDirectory).filter((name) => /^index\..*\.css$/.test(name));
  assert.equal(roots.length, 1, "현재 공식 빌드 root CSS는 하나여야 합니다.");
  const rootStyle = readFileSync(path.join(cssDirectory, roots[0]));
  assert.ok(!/@import\b|url\s*\(/i.test(rootStyle.toString()), "추가 자산을 요청하는 CSS는 이 합성 경계에서 허용하지 않습니다.");
  const result = { source: "현재 저장소의 실제 제품 컴포넌트", provisionedTool, appSourceIdentity: hash(Buffer.from(JSON.stringify(before.source))), startedAt: (new Date()).toISOString(), pid: process.pid, status: "IN_PROGRESS", resources: [], network: [], pageErrors: [], consoleErrors: [], checks: [] };
  const origin = "http://127.0.0.1:41873", documentURL = origin + "/fixture?screen=alerts";
  let browser, context, page, receiptWritten = false;
  const snap = () => page.evaluate(() => window.qa.snapshot()), frame = () => page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
  async function pending(route) {
    await page.waitForFunction((route2) => window.qa.snapshot().calls.some((c) => new URL(c.url, location.href).pathname === route2 && !c.settled), route, { timeout: 4e3 });
    return (await snap()).calls.filter((c) => new URL(c.url, origin).pathname === route && !c.settled).at(-1);
  }
  const settle = (id, status, body) => page.evaluate(({ id: id2, status: status2, body: body2 }) => window.qa.resolve(id2, status2, body2), { id, status, body });
  const check = (name, pass, details) => {
    result.checks.push({ name, pass, details });
    assert.ok(pass, name);
  };
  function dashboard(actor) {
    return { farms: [{ id: "farm-a", name: "합성 농장 QA", timezone: "UTC" }], selectedFarm: { id: "farm-a", name: "합성 농장 QA", timezone: "UTC" }, account: { authenticated: true, memberId: "member-" + actor, loginId: "synthetic-" + actor, email: "synthetic-" + actor + "@example.invalid", displayName: "합성 사용자 " + actor.toUpperCase() + " QA", publicName: "합성 사용자 " + actor.toUpperCase() + " QA", accountCode: actor === "a" ? "W-A001" : "W-B002", phone: null, phoneVerified: false, notificationsEnabled: false, preferredLanguage: "ko", role: "WORKER", roleLabel: "작업자", permissions: { viewRevenue: false, manageMembers: false, manageFarm: false, uploadMedia: true, reviewAlerts: true, viewHistory: true }, loginManagedExternally: true }, summary: { robotCount: 0, todayRecordedSessions: 0, alertCount: 0, pestBreakdown: [{ code: "OTHER", label: "기타", openCount: 0, capability: "RECORD_ONLY" }], harvestCandidates: 0, pendingSessions: 0 }, cameras: [], alerts: [], alertPagination: { status: "OPEN", page: 1, limit: 20, total: 0, pageCount: 0, openCount: 0, doneCount: 0 }, recentSessions: [], pendingSessionsByItem: [], items: [{ id: "item-a", crop_code: "STRAWBERRY", crop_name: "딸기", cultivar_code: "SEOLHYANG", cultivar_name: "설향", display_name: "합성 설향 QA", crop_image_uri: null, crop_description: null }], guides: [], setupRequired: false, membershipRequired: false };
  }
  const row = (actor) => ({ id: "loc", farm_id: "farm-a", location_key: "H:B:Z", display_location: "합성 구역 " + actor.toUpperCase() + " QA", house_code: "H", bed_code: "B", zone_code: "Z", current_state: "FIELD_CHECK_REQUIRED", active_case_id: "case", primary_issue_code: null, issue_family: "PEST", case_status: "OPEN", observation_count: 1, latest_humidity: null, latest_leaf_temp: null, latest_reference_temp: null, latest_ambient_temp: null, latest_risk_signal: null, last_alert_reason: null, last_alert_at: null, last_observed_at: null, last_field_check_at: null, last_action_at: null });
  try {
    const imageAdapter = { name: "qa-native-image", setup(build) {
      build.onResolve({ filter: /^next\/image$/ }, () => ({ path: "qa-native-image", namespace: "qa-image" }));
      build.onLoad({ filter: /.*/, namespace: "qa-image" }, () => ({ contents: 'import React from "react";export default function Image({alt=""}){return React.createElement("img",{alt,src:"data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%221%22 height=%221%22/%3E",width:16,height:16});}', loader: "jsx", resolveDir: qa }));
    } };
    const built = await esbuild.build({ entryPoints: [path.join(root, "tests/browser/dashboard-stream403.fixture.tsx")], bundle: true, write: false, outdir: qa + "/virtual-build", format: "iife", platform: "browser", target: "chrome120", nodePaths: [root + "/node_modules"], jsx: "automatic", define: { "process.env.NODE_ENV": '"production"' }, alias: { "@": source, react: path.dirname(req.resolve("react")), "react-dom": path.dirname(req.resolve("react-dom")) }, plugins: [imageAdapter], logLevel: "silent" });
    await esbuild.stop();
    const js = built.outputFiles.find((f) => f.path.endsWith(".js")).text, css = built.outputFiles.find((f) => f.path.endsWith(".css")).text;
    assert.ok(!/@import\b|url\s*\(/i.test(css));
    result.bundleSha256 = hash(Buffer.from(js));
    result.componentCssSha256 = hash(Buffer.from(css));
    browser = await pw.chromium.launch({ executablePath, headless: true, timeout: 8e3, args: ["--proxy-server=http://127.0.0.1:9", "--proxy-bypass-list=<-loopback>", "--disable-background-networking"] });
    result.resources.push({ event: "browser-start", at: (new Date()).toISOString(), children: processObservation.observe() });
    context = await browser.newContext({ viewport: { width: 1365, height: 900 }, serviceWorkers: "block" });
    page = await context.newPage();
    page.setDefaultTimeout(4e3);
    page.on("pageerror", (e) => result.pageErrors.push(String(e)));
    page.on("console", (m) => {
      if (m.type() === "error") result.consoleErrors.push(m.text());
    });
    let served = false;
    await context.route("**/*", async (route) => {
      const r = route.request();
      if (!served && r.isNavigationRequest() && r.url() === documentURL) {
        served = true;
        return route.fulfill({ status: 200, contentType: "text/html", body: '<!doctype html><html lang="ko"><head><meta charset="utf-8"><link rel="icon" href="data:,"></head><body><div id="root"></div></body></html>' });
      }
      result.network.push({ method: r.method(), url: r.url() });
      await route.abort("blockedbyclient");
      await page.close();
    });
    await page.goto(documentURL, { waitUntil: "domcontentloaded", timeout: 4e3 });
    await page.addStyleTag({ content: rootStyle.toString() });
    await page.addStyleTag({ content: css });
    await page.addScriptTag({ content: js });
    await page.evaluate(() => window.qa.mount());
    await settle((await pending("/api/farmer-dashboard")).id, 200, dashboard("a"));
    await settle((await pending("/api/scouting-locations")).id, 200, { rows: [row("a")] });
    await page.locator(".scouting-location-row").waitFor({ state: "visible" });
    await frame();
    check("초기 합성 비공개 행 표시", await page.locator(".scouting-location-row").innerText().then((t) => t.includes("합성 구역 A QA")));
    await page.screenshot({ path: qa + "/loaded.png", fullPage: false });
    await page.locator(".scouting-queue-heading > button").click();
    const late = await pending("/api/scouting-locations");
    result.lateRequestId = late.id;
    await page.locator(".refresh-button").click();
    const denied = await pending("/api/farmer-dashboard");
    result.deniedRequestId = denied.id;
    await page.evaluate(() => {
      const e = document.querySelector("[data-private-dashboard]");
      window.qaPrivateOwner = e;
      window.qaPrivateMutations = [];
      window.qaObserver = new MutationObserver((records) => {
        for (const record of records) window.qaPrivateMutations.push({ at: performance.now(), attribute: record.attributeName, hidden: e.hasAttribute("hidden"), inert: e.hasAttribute("inert") });
      });
      window.qaObserver.observe(e, { attributes: true, attributeFilter: ["hidden", "inert"] });
    });
    await page.evaluate((id) => window.qa.streaming403(id), denied.id);
    await page.waitForFunction(() => document.querySelector("[data-private-dashboard]")?.hasAttribute("hidden") && document.querySelector("[data-private-dashboard]")?.hasAttribute("inert"), null, { timeout: 4e3 });
    await frame();
    result.denied = await page.evaluate(() => ({ at: performance.now(), samePrivateOwner: window.qaPrivateOwner === document.querySelector("[data-private-dashboard]"), streams: window.qa.streamSnapshot(), mutations: window.qaPrivateMutations, privateText: document.querySelector("[data-private-dashboard]")?.textContent }));
    check("본문 미종료 상태에서 차단 DOM commit", result.denied.streams.length === 1 && result.denied.streams[0].status === 403 && !result.denied.streams[0].bodyUsed && !result.denied.streams[0].locked && !result.denied.streams[0].cancelled && !result.denied.streams[0].producerClosed, result.denied.streams);
    check("기존 private DOM 소유자 유지", result.denied.samePrivateOwner);
    check("실제 비공개 영역 비가시", !await page.locator("[data-private-dashboard]").isVisible());
    check("명시 재확인 패널 표시", await page.locator(".dashboard-access-denied").isVisible());
    await page.screenshot({ path: qa + "/stream-open-denied.png", fullPage: false });
    const lateRow = { ...row("a"), display_location: "SYNTHETIC_LATE_PRIVATE_SHOULD_NOT_APPEAR" };
    await settle(late.id, 200, { rows: [lateRow] });
    await frame();
    result.afterLate = await page.evaluate(() => ({ hidden: document.querySelector("[data-private-dashboard]")?.hasAttribute("hidden"), inert: document.querySelector("[data-private-dashboard]")?.hasAttribute("inert"), lateMarker: document.body.textContent.includes("SYNTHETIC_LATE_PRIVATE_SHOULD_NOT_APPEAR"), streams: window.qa.streamSnapshot(), mutations: window.qaPrivateMutations }));
    check("이전 읽기 응답이 비공개 화면을 복원하지 못함", result.afterLate.hidden && result.afterLate.inert && !result.afterLate.lateMarker, result.afterLate);
    result.beforeCleanup = await snap();
    check("추가 자동 조회·쓰기가 없음", result.beforeCleanup.calls.length === 5 && result.beforeCleanup.calls.every((c) => c.method === "GET" && c.settled), result.beforeCleanup.calls);
    check("예상 밖 요청·브라우저 오류 없음", result.network.length === 0 && result.pageErrors.length === 0 && result.consoleErrors.length === 0 && result.beforeCleanup.unexpected.length === 0);
    await page.evaluate(() => window.qa.unmount());
    await frame();
    await page.evaluate(() => window.qa.cleanupStreams());
    result.streamCleanup = await page.evaluate(() => window.qa.streamSnapshot());
    result.fixture = await snap();
    check("합성 stream 정리 및 unmount", result.streamCleanup.every((s) => s.cancelled) && result.fixture.mounts === 1 && result.fixture.unmounts === 1, result.streamCleanup);
    result.status = "PASS";
  } catch (error) {
    result.status = error?.code === "ERR_ASSERTION" ? "FAIL" : "BLOCKED";
    result.failure = String(error?.stack ?? error);
    if (page) try {
      await page.screenshot({ path: qa + "/failure.png", fullPage: false });
      result.failureFixture = await snap();
    } catch (e) {
      result.failureCapture = String(e);
    }
  } finally {
    const cleanupErrors = [];
    async function cleanup(name, action) {
      let timer;
      try {
        await Promise.race([action(), new Promise((_, reject) => {
          timer = setTimeout(() => reject(Error(name + " 정리 시간 초과")), 4e3);
        })]);
        result.resources.push({ event: name + "-cleanup", status: "closed", at: (new Date()).toISOString() });
      } catch (error) {
        cleanupErrors.push({ name, error: String(error) });
      } finally {
        clearTimeout(timer);
      }
    }
    if (page && !page.isClosed()) await cleanup("fixture", () => page.evaluate(async () => {
      window.qaObserver?.disconnect();
      if (window.qa) {
        try {
          const s = window.qa.snapshot();
          if (s.mounts > s.unmounts) window.qa.unmount();
        } finally {
          await window.qa.cleanupStreams();
        }
      }
    }));
    if (context) await cleanup("context", () => context.close());
    if (browser) await cleanup("browser", () => browser.close());
    await cleanup("esbuild", () => esbuild.stop());
    result.cleanupErrors = cleanupErrors;
    const final = finishBrowserReceipt(result, {
      preservationCheck: () => JSON.stringify(before) === JSON.stringify(protectedState()),
      observeChildren: processObservation.observe,
      writeReceipt: value => writeFileSync(qa + "/result.json", JSON.stringify(value, null, 2) + "\n", { flag: "wx" }),
    });
    receiptWritten = final.receiptWritten;
    console.log(JSON.stringify({ status: result.status, summary: result.summary, checks: result.checks.map((c) => ({ name: c.name, pass: c.pass })), protectedUnchanged: result.protectedUnchanged, failure: result.failure, cleanupErrors: result.cleanupErrors, finalizationErrors: result.finalizationErrors, receiptWriteError: result.receiptWriteError, receiptWritten, result: qa + "/result.json" }));
  }
  assert.equal(result.status, "PASS", JSON.stringify({ failure: result.failure, cleanupErrors: result.cleanupErrors, finalizationErrors: result.finalizationErrors, receiptWriteError: result.receiptWriteError }));
  assert.equal(receiptWritten, true, '영수증 쓰기 성공이 확인돼야 합니다.');
  assert.equal(result.protectedUnchanged, true);
});
