import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const errors = [];
page.on('console', (message) => message.type() === 'error' && errors.push(message.text()));
page.on('pageerror', (error) => errors.push(error.message));

await page.goto('http://127.0.0.1:5173', { waitUntil: 'networkidle' });
await page.getByRole('button', { name: '模型设置' }).click();
await page.getByRole('heading', { name: '模型服务设置' }).waitFor();
await page.getByRole('button', { name: '测试连接' }).click();
await page.getByText('模型连接正常').waitFor();
await page.screenshot({ path: 'screenshots/model-settings.png', fullPage: true });

const layout = await page.evaluate(() => ({
  viewportWidth: window.innerWidth,
  documentWidth: document.documentElement.scrollWidth,
  dialogVisible: Boolean(document.querySelector('.settings-dialog')),
  secretType: document.querySelector('.secret-input input')?.getAttribute('type'),
}));
console.log(JSON.stringify({ layout, consoleErrors: errors }, null, 2));
await browser.close();
