/* Run against an isolated local demo database. See docs/UI_REVIEW.md. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const modules = process.env.KRISHI_BROWSER_MODULES;
const browsers = require(modules ? path.join(modules, 'playwright') : 'playwright');
const engine = process.env.KRISHI_BROWSER_ENGINE || 'chromium';
const baseURL = process.env.KRISHI_BASE_URL || 'http://127.0.0.1:8080';
const output = path.resolve('artifacts/ui-review', engine);
fs.mkdirSync(output, {recursive: true});
const sensorFeed = {feeds: [
    {created_at: new Date(Date.now() - 60000).toISOString(), field1: 28, field2: 65, field3: 44, field4: 600, field5: 'on'},
    {created_at: new Date().toISOString(), field1: 29, field2: null, field3: 43, field4: 620, field5: null}
], anomalies: {alerts: []}};
const report = {viewports: [], accessibility: [], checks: [], errors: []};
const axePath = process.env.KRISHI_AXE_PATH || path.resolve('.browser-tools/axe.min.js');

(async () => {
    const browser = await browsers[engine].launch({channel: engine === 'chromium' ? process.env.KRISHI_BROWSER_CHANNEL || 'msedge' : undefined, headless: true});
    const context = await browser.newContext({viewport: {width: 1440, height: 1000}, reducedMotion: 'reduce'});
    const page = await context.newPage();
    page.on('pageerror', error => report.errors.push(error.message));
    page.on('console', message => { if (message.type() === 'warning') report.errors.push(message.text()); });
    await page.route('**/api/data', route => route.fulfill({json: sensorFeed}));
    const pages = [
        ['/', '#cropForm'], ['/farmer-dashboard', '#farmerCrop'], ['/decision-intelligence', '#decisionCrop'],
        ['/dashboard', '#sensorStatus'], ['/marketplace', '.market-card h3'],
        ['/community-dashboard', '#communityInsight'], ['/login', '.auth-card'], ['/disease-prediction', 'h1']
    ];
    for (const [route, selector] of pages) {
        await page.goto(baseURL + route);
        await page.locator(selector).first().waitFor();
        if (['/farmer-dashboard', '/decision-intelligence', '/community-dashboard'].includes(route)) {
            await page.waitForFunction(sel => !/Loading/.test(document.querySelector(sel).textContent), selector, {timeout: 25000});
        }
        if (route === '/dashboard') await page.waitForFunction(() => document.querySelector('#sensorStatus').textContent.includes('Last reading'));
        for (const width of [320, 390, 540, 768, 820, 1024, 1440, 1920, 2560]) {
            await page.setViewportSize({width, height: 1000});
            await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
            const layout = await page.evaluate(() => ({width: innerWidth, content: document.documentElement.scrollWidth}));
            assert(layout.content <= width + 1, route + ' overflows at ' + width + ': ' + JSON.stringify(layout));
            report.viewports.push({route, width, overflow: false});
        }
        for (const width of [320, 1440]) {
            await page.setViewportSize({width, height: 1000});
            await page.addScriptTag({path: axePath});
            const violations = await page.evaluate(async () => (await axe.run(document, {runOnly: {type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa']}})).violations.map(v => ({id:v.id, impact:v.impact, nodes:v.nodes.map(n => n.target)})));
            report.accessibility.push({route, width, violations});
        }
        await page.screenshot({path: path.join(output, (route === '/' ? 'recommendations' : route.slice(1)) + '-desktop.png'), fullPage: true});
    }
    report.checks.push('Eight routes render; responsive layout at nine widths');

    await page.setViewportSize({width:390, height:844});
    await page.goto(baseURL);
    await page.getByRole('button', {name: 'Open navigation'}).click();
    assert.equal(await page.locator('#app-navigation').isVisible(), true);
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('#app-navigation').isVisible(), false);
    assert.equal(await page.getByRole('button', {name:'Open navigation'}).getAttribute('aria-expanded'), 'false');
    await page.getByRole('button', {name:'More navigation'}).click();
    await page.locator('#app-navigation').getByRole('link', {name:'Community'}).click();
    assert(page.url().endsWith('/community-dashboard'));
    await page.goto(baseURL);
    await page.setViewportSize({width:844, height:390});
    assert(await page.locator('html').evaluate(el => el.scrollWidth <= innerWidth));
    await page.setViewportSize({width:390, height:844});
    report.checks.push('Mobile menu, Escape focus return, bottom navigation and landscape');
    report.mobileFormTop = await page.locator('#cropForm').evaluate(el => el.getBoundingClientRect().top);

    await page.getByRole('button', {name:'Try sample inputs'}).click();
    await page.locator('#temperature').fill('28.5');
    await page.locator('#cropForm [type=submit]').click();
    await page.locator('#cropResult:not(.d-none)').waitFor();
    assert((await page.locator('#recommendedCrop').innerText()).length > 0);
    await page.screenshot({path:path.join(output, 'recommendations-mobile.png'), fullPage:true});
    await page.locator('#ph').fill('15');
    assert.equal(await page.locator('#ph').evaluate(el => el.checkValidity()), false);
    assert.equal(await page.locator('#cropResult').isVisible(), false);
    await page.locator('#ph').fill('6.6');
    await page.route('**/api/crop-recommendation', route => route.fulfill({status:503, json:{detail:'Temporarily unavailable'}}));
    await page.locator('#cropForm [type=submit]').click();
    await page.waitForFunction(() => document.querySelector('#cropStatus').textContent.includes('Temporarily unavailable'));
    assert.equal(await page.locator('#ph').inputValue(), '6.6');
    assert.equal(await page.locator('#cropForm [type=submit]').isEnabled(), true);
    await page.unroute('**/api/crop-recommendation');
    await page.locator('#cropForm [type=submit]').click();
    await page.locator('#cropResult:not(.d-none)').waitFor();
    report.checks.push('Real crop inference, decimal input, validation, stale-result clearing, failure and retry');

    await page.getByRole('tab', {name:'Fertilizer', exact:true}).click();
    for (const [id,value] of [['fertilizerNitrogen','70'], ['fertilizerPhosphorus','45'], ['fertilizerPotassium','40']]) await page.locator('#'+id).fill(value);
    await page.locator('#soilType').selectOption('Loamy');
    await page.locator('#cropType').selectOption('Maize');
    await page.locator('#fertilizerForm [type=submit]').click();
    await page.locator('#fertilizerResult:not(.d-none)').waitFor();
    assert((await page.locator('#recommendedFertilizer').innerText()).length > 0);
    await page.getByRole('tab', {name:'Price', exact:true}).click();
    await page.locator('#priceCrop').selectOption('MAIZE');
    await page.locator('#priceForm [type=submit]').click();
    await page.locator('#priceResult:not(.d-none)').waitFor();
    assert(['Favourable','Stable','Weak'].includes(await page.locator('#priceOutlook').innerText()));
    assert(!(await page.locator('#priceAction').innerText()).includes('Unavailable'));
    await page.goto(baseURL + '/#disease');
    await page.locator('#disease.show').waitFor();
    assert.equal(await page.locator('input[type=file]').count(), 0);
    report.checks.push('Real fertilizer and price flows; disease deep link without upload');

    await page.goto(baseURL + '/decision-intelligence');
    const hostileText = '<img src=x onerror=alert(1)>';
    await page.route('**/api/assistant', route => route.fulfill({json:{answer:hostileText, recommended_action:'Review', data_used:['sample'], confidence:'Low', limitations:['Sample']}}));
    await page.locator('#assistantQuestion').fill(hostileText);
    await page.locator('#assistantForm [type=submit]').click();
    await page.waitForFunction(() => document.querySelector('#assistantLog').getAttribute('aria-busy') === 'false');
    assert.equal(await page.locator('#assistantLog img').count(), 0);
    assert((await page.locator('#assistantLog').innerText()).includes(hostileText));
    await page.unroute('**/api/assistant');
    await page.route('**/api/assistant', route => route.fulfill({status:503, json:{detail:'Assistant unavailable'}}));
    await page.locator('#assistantQuestion').fill('What should I do today?');
    await page.locator('#assistantForm [type=submit]').click();
    await page.waitForFunction(() => document.querySelector('#assistantLog').getAttribute('aria-busy') === 'false');
    assert.equal(await page.locator('#assistantQuestion').inputValue(), 'What should I do today?');
    assert.equal(await page.locator('#assistantForm [type=submit]').isEnabled(), true);
    report.checks.push('Assistant treats input and response as text; failed questions are retained');

    await page.route('**/api/decision-card', route => route.fulfill({json:{
        input_mode:'test fixture', final_recommended_action:'Monitor', alerts:[{code:'sudden_moisture_change', message:'Moisture changed', severity:'Info', recommended_action:'Inspect'}],
        latest_sensor_reading:{soil_moisture:55}, explanation_trust:[]
    }}));
    await page.goto(baseURL + '/farmer-dashboard');
    await page.waitForFunction(() => document.querySelector('#irrigationNeeded').textContent === 'Monitor');
    await page.unroute('**/api/decision-card');
    report.checks.push('Sudden moisture change is not displayed as irrigation needed');

    await page.goto(baseURL + '/dashboard');
    await page.waitForFunction(() => document.querySelector('#sensorStatus').textContent.includes('Last reading'));
    assert.equal(await page.locator('#sensorDataTable tr:first-child td:last-child').innerText(), '—');
    await page.unroute('**/api/data');
    await page.route('**/api/data', route => route.fulfill({json:{feeds:[], anomalies:{alerts:[]}}}));
    await page.locator('#refreshSensors').click();
    await page.waitForFunction(() => document.querySelector('#sensorStatus').textContent.includes('No sensor readings'));
    assert((await page.locator('#sensorDataTable').innerText()).includes('No readings'));
    await page.unroute('**/api/data');
    await page.route('**/api/data', route => route.fulfill({status:502, json:{detail:'Unable to fetch sensor data'}}));
    await page.locator('#refreshSensors').click();
    await page.waitForFunction(() => document.querySelector('#sensorStatus').textContent.includes('Use Refresh to retry'));
    report.checks.push('Sensor missing values, empty data and upstream failure states');

    await page.route('**/api/community/summary', route => route.fulfill({status:503, json:{detail:'Community unavailable'}}));
    await page.goto(baseURL + '/community-dashboard');
    await page.locator('#pageNotice:not([hidden])').waitFor();
    assert(!(await page.locator('#main-content').innerText()).includes('Loading'));
    report.checks.push('Dashboard error does not leave indefinite loading placeholders');
    fs.writeFileSync(path.join(output,'report.json'), JSON.stringify(report,null,2));
    console.log(JSON.stringify({checks:report.checks, layouts:report.viewports.length, accessibilityViolations:report.accessibility.filter(v=>v.violations.length), errors:report.errors, mobileFormTop:report.mobileFormTop}, null, 2));
    await browser.close();
    assert.equal(report.errors.length, 0);
    assert.equal(report.accessibility.filter(v=>v.violations.length).length, 0, 'Accessibility violations');
})().catch(error => {
    fs.writeFileSync(path.join(output,'report.json'), JSON.stringify(report,null,2));
    console.error(error); process.exit(1);
});
