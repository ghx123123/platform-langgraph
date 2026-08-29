import { chromium } from 'playwright';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const errors = [];
page.on('console', (message) => message.type() === 'error' && errors.push(message.text()));
page.on('pageerror', (error) => errors.push(error.message));

await page.goto('http://127.0.0.1:5173', { waitUntil: 'networkidle' });
await page.getByRole('button', { name: '模型设置' }).click();
await page.getByRole('heading', { name: '模型服务设置' }).waitFor();
const historyItem = page.getByRole('button', { name: /MiniMax-M3/ });
await historyItem.waitFor();
await historyItem.click();
const historyModel = await page.locator('input[placeholder="例如 gpt-4.1-mini"]').inputValue();
await page.getByRole('button', { name: '本地演示模型' }).click();
await page.getByRole('button', { name: '查看模型' }).click();
await page.getByText('本地演示模型列表已就绪').waitFor();

const modelSelect = page.getByRole('combobox', { name: '选择已发现的模型' });
await modelSelect.selectOption('mock-teaching');
const selectedModel = await page.locator('input[placeholder="例如 gpt-4.1-mini"]').inputValue();
await page.getByRole('button', { name: 'OpenAI 兼容接口' }).click();
await page.locator('input[placeholder="https://api.openai.com/v1"]').fill('http://127.0.0.1:8000/not-a-model');
await page.locator('.secret-input input').fill('browser-test-key');
await page.getByRole('button', { name: '连接并获取模型' }).click();
await page.getByText(/接口返回 HTTP 404/).waitFor();
const failureState = await page.locator('.connection-state').textContent();
const desktopLayout = await page.evaluate(() => ({
  viewportWidth: window.innerWidth,
  documentWidth: document.documentElement.scrollWidth,
  modelCount: document.querySelectorAll('.model-picker option').length,
}));

await page.screenshot({ path: resolve(projectRoot, '.runtime/model-settings-discovery.png'), fullPage: true });
await page.setViewportSize({ width: 390, height: 844 });
await page.waitForTimeout(150);
const mobileLayout = await page.evaluate(() => ({
  viewportWidth: window.innerWidth,
  documentWidth: document.documentElement.scrollWidth,
  dialogVisible: Boolean(document.querySelector('.settings-dialog')),
}));

console.log(JSON.stringify({ historyModel, selectedModel, failureState, desktopLayout, mobileLayout, consoleErrors: errors }, null, 2));
await browser.close();
