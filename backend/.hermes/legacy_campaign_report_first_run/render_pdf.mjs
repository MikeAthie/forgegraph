
import { createRequire } from 'module';
const require = createRequire('C:/Users/mathi/projects/forgegraph/frontend/package.json');
const { chromium } = require('playwright');
const browser = await chromium.launch({ args: ['--no-sandbox', '--disable-dev-shm-usage'] });
const page = await browser.newPage({ viewport: { width: 1120, height: 1400 }, deviceScaleFactor: 1 });
await page.goto('file:///C:/Users/mathi/projects/forgegraph/backend/.hermes/legacy_campaign_report_first_run/Legacy_Optical_Noir_Campaign_Report.html', { waitUntil: 'networkidle' });
await page.emulateMedia({ media: 'print' });
await page.pdf({ path: 'C:/Users/mathi/projects/forgegraph/backend/.hermes/legacy_campaign_report_first_run/Legacy_Optical_Noir_Campaign_Report.pdf', format: 'Letter', printBackground: true, preferCSSPageSize: true });
await browser.close();
