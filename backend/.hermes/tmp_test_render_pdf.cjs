const { chromium } = require('playwright');
const path = require('path');
(async()=>{
 const browser = await chromium.launch({headless:true});
 const page = await browser.newPage();
 await page.goto('data:text/html,<html><body><h1>Hello PDF</h1><p>test</p></body></html>', {waitUntil:'load'});
 await page.emulateMedia({media:'print'});
 await page.pdf({path: path.resolve('../backend/.hermes/tmp_test_render_pdf.pdf'), format:'Letter', printBackground:true, margin:{top:'0',right:'0',bottom:'0',left:'0'}, preferCSSPageSize:true});
 await browser.close();
})();
