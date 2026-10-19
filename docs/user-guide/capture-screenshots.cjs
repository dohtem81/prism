/*
 * Regenerates the screenshots used by docs/user-guide.md against the local
 * Docker stack (https://localhost via Caddy).
 *
 * Prerequisites:
 *   - stack running: docker compose -f deploy/compose/docker-compose.yml up -d
 *   - REGISTRATION_SERVICE_URL=https://localhost in .env (so the register page can reach /v1/register)
 *   - npm install playwright && npx playwright install chromium   (in any folder)
 *
 * Run (PowerShell), pointing NODE_PATH at the folder holding node_modules:
 *   $env:NODE_PATH="<folder>\node_modules"; node docs/user-guide/capture-screenshots.cjs
 */
const path = require("path");
const fs = require("fs");
const { chromium } = require("playwright");

const BASE = process.env.PRISM_URL || "https://localhost";
const OUT = path.join(__dirname, "img");
const PASSWORD = "DemoPass123!";
const USERS = {
  alice: { email: "alice@example.com", lang: "en" },
  bob: { email: "bob@example.com", lang: "pl" },
  carol: { email: "carol@example.com", lang: "de" },
};

fs.mkdirSync(OUT, { recursive: true });

const shot = (page, name) => page.screenshot({ path: path.join(OUT, name + ".png") });

async function register(page, name, capture) {
  await page.goto(`${BASE}/ui/register`);
  await page.fill("#email", USERS[name].email);
  await page.fill("#username", name);
  await page.fill("#password", PASSWORD);
  if (capture) await shot(page, "02-register-form");
  await page.click("button[type=submit]");
  await page.waitForTimeout(700);
  if (capture) await shot(page, "03-register-success");
  await page.waitForURL("**/ui/login", { timeout: 10000 });
}

async function login(page, name, capture) {
  await page.goto(`${BASE}/ui/login`);
  await page.fill("#usernameOrEmail", name);
  await page.fill("#password", PASSWORD);
  if (capture) await shot(page, "04-login-form");
  await page.click("button[type=submit]");
  await page.waitForURL(/\/ui$/, { timeout: 10000 });
  await page.waitForTimeout(800);
  if (capture) await shot(page, "05-dashboard");
}

async function openMenu(page, item) {
  await page.click("#menuButton");
  await page.click(item);
}

async function applyDialog(page, formSel) {
  await page.click(`${formSel} .apply-button`);
}

async function userId(page) {
  await page.click("#menuButton");
  await page.click("#menuSettings");
  await page.waitForFunction(() => document.querySelector("#ownUserId")?.textContent.trim());
  return (await page.textContent("#ownUserId")).trim();
}

(async () => {
  const browser = await chromium.launch();
  const mk = async () => {
    const ctx = await browser.newContext({
      ignoreHTTPSErrors: true,
      viewport: { width: 1280, height: 800 },
    });
    return ctx.newPage();
  };

  // 1. Welcome page
  const alice = await mk();
  await alice.goto(`${BASE}/`);
  await shot(alice, "01-welcome");

  // 2-3. Register
  await register(alice, "alice", true);
  for (const n of ["bob", "carol"]) {
    const p = await mk();
    await register(p, n, false);
    await p.context().close();
  }

  // 4-5. Login
  await login(alice, "alice", true);

  // 6-8. Create room
  await openMenu(alice, "#menuCreate");
  await alice.fill("#createRoomName", "Project Phoenix");
  await alice.fill("#createRoomLang", "en");
  await alice.waitForTimeout(300);
  await shot(alice, "06-menu-create-room");
  await applyDialog(alice, "#createRoomForm");
  await alice.waitForURL(/\/ui\/rooms\//, { timeout: 10000 });
  await alice.waitForSelector("#roomIdNote", { state: "visible" });
  await alice.waitForTimeout(800);
  const roomId = alice.url().split("/").pop();
  await shot(alice, "07-room-created");

  // Bob: login and fetch his user ID from Settings
  const bob = await mk();
  await login(bob, "bob", false);
  const bobId = await userId(bob);
  await bob.waitForTimeout(300);
  await shot(bob, "08-settings-user-id");
  await bob.keyboard.press("Escape");

  // 9-10. Alice adds Bob
  await alice.fill("#addMemberUserId", bobId);
  await alice.fill("#addMemberLang", "pl");
  await shot(alice, "09-add-member-form");
  await alice.click("#addMemberForm button[type=submit]");
  await alice.waitForTimeout(1200);
  await shot(alice, "10-member-added");

  // 11-12. Carol joins by room ID
  const carol = await mk();
  await login(carol, "carol", false);
  await openMenu(carol, "#menuJoin");
  await carol.fill("#joinRoomId", roomId);
  await carol.fill("#joinRoomLang", "de");
  await carol.waitForTimeout(300);
  await shot(carol, "11-join-room-dialog");
  await applyDialog(carol, "#joinRoomForm");
  await carol.waitForURL(/\/ui\/rooms\//, { timeout: 10000 });
  await carol.waitForTimeout(1000);
  await shot(carol, "12-joined-room");

  await browser.close();
  console.log("done; room", roomId);
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
