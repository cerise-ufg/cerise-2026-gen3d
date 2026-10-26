// Captura do Swagger (/docs) e do /api/v1/health pelo encaminhamento local, com Playwright (Chromium headless).
// Uso: node shot_docs.js <base> <pasta_saida> [chromium.exe]
const { chromium } = require('playwright-core');
(async () => {
  const base = process.argv[2] || 'http://127.0.0.1:18095';
  const out = process.argv[3] || '.';
  const exe = process.argv[4];
  const browser = await chromium.launch({ headless: true, executablePath: exe });
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 1.5 });
  await page.goto(base + '/docs', { waitUntil: 'networkidle', timeout: 60000 });
  await page.waitForSelector('.opblock', { timeout: 30000 });
  await page.screenshot({ path: out + '/swagger_docs.png', fullPage: true });
  // abre o POST /api/v1/jobs para mostrar o formulario multipart
  const op = page.locator('#operations-jobs-create_job_api_v1_jobs_post');
  await op.locator('.opblock-summary').click();
  await page.waitForTimeout(800);
  await op.screenshot({ path: out + '/swagger_post_jobs.png' });
  await browser.close();
  console.log('ok');
})().catch(e => { console.error(e); process.exit(1); });
