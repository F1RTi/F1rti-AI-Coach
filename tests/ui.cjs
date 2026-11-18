/* Browser acceptance test against a temporary database and the official API response contract. */
const { chromium } = require("node:module").createRequire(
  require("node:path").resolve("frontend/package.json"),
)("playwright");
const { spawn } = require("node:child_process");
const { once } = require("node:events");
const fs = require("node:fs"),
  path = require("node:path"),
  net = require("node:net"),
  assert = require("node:assert/strict");
async function main() {
  const dir = fs.mkdtempSync(path.resolve(".work/ui-"));
  const listener = net.createServer().listen(0, "127.0.0.1");
  await once(listener, "listening");
  const port = listener.address().port;
  await new Promise((r) => listener.close(r));
  const host = spawn(
    path.resolve(".venv/Scripts/python.exe"),
    ["-m", "tests.ui_host", dir, String(port)],
    { windowsHide: true },
  );
  let browser;
  try {
    const url = "http://127.0.0.1:" + port + "/";
    for (let i = 0; i < 120; i++) {
      if (
        await fetch(url)
          .then((r) => r.ok)
          .catch(() => false)
      )
        break;
      await new Promise((r) => setTimeout(r, 250));
    }
    const executablePath = [
      process.env["ProgramFiles(x86)"] +
        "/Microsoft/Edge/Application/msedge.exe",
      process.env.ProgramFiles + "/Google/Chrome/Application/chrome.exe",
    ].find((p) => fs.existsSync(p));
    browser = await chromium.launch({ executablePath, headless: true });
    const page = await browser.newPage({
      viewport: { width: 1440, height: 1000 },
      acceptDownloads: true,
    });
    const errors = [];
    page.on("pageerror", (e) => errors.push(String(e)));
    await page.goto(url + "#ui-test-only");
    const btn = (name) => page.getByRole("button", { name, exact: true });
    await btn("Подключить").waitFor();
    await page.screenshot({ path: path.join(dir, "first-run.png") });
    await btn("Подключить").click();
    await page.getByPlaceholder("Ввести API-ключ").fill("test-fixture");
    await btn("Сохранить настройки").click();
    await btn("Обзор").click();
    await page
      .getByText("1 655", { exact: false })
      .first()
      .waitFor({ timeout: 45000 });
    await btn("Разбор матчей").click();
    await btn("Разбор ↗").first().click();
    await page.getByText("Карточка FACEIT", { exact: true }).waitFor();
    await btn("Тренировки").click();
    await page.getByLabel("Направление").selectOption("Aim");
    await btn("Создать план").click();
    await page.getByRole("heading", { name: "Aim", exact: true }).waitFor();
    await btn("Отметить выполнение").first().click();
    await btn("Отменить отметку").first().waitFor();
    await btn("Демозаписи").click();
    await page
      .locator("input[type=file]")
      .setInputFiles(path.resolve(".work/upstream.dem"));
    await btn("Открыть").first().waitFor({ timeout: 90000 });
    await btn("Открыть").first().click();
    await page.getByRole("heading", { name: "Таймлайн раунда" }).waitFor();
    await page.getByLabel("Раунд", { exact: true }).selectOption("2");
    await page.getByLabel("Тип события").selectOption("player_death");
    await page.locator(".timeline summary").first().waitFor();
    await btn("Отчёты").click();
    await btn("Просмотр").first().click();
    await page
      .frameLocator("iframe")
      .getByText("K/D", { exact: true })
      .waitFor();
    const file = page.waitForEvent("download", { timeout: 90000 });
    await btn("PDF ↓").first().click();
    const pdf = await file;
    const saved = path.join(dir, "report.pdf");
    await pdf.saveAs(saved);
    assert.equal(fs.readFileSync(saved).subarray(0, 5).toString(), "%PDF-");
    assert.deepEqual(errors, []);
    console.log("UI acceptance passed. Evidence:", dir);
  } finally {
    if (browser) await browser.close();
    host.kill();
  }
}
main().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
