// Captures application screenshots by driving Edge over the DevTools protocol.
const fs = require('fs')
const path = require('path')
const puppeteer = require('puppeteer-core')

const EDGE = process.env.SHOT_BROWSER || 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const BASE = 'http://localhost:8000'
const DOCS = 'D:/codin/idea lab/docs/figures/screenshots'
const SHOTS = path.join(__dirname, 'shots')
const SCALE = 1.5

const PAGES = [
  { p: '/', f: 'dashboard', h: 1000 },
  { p: '/billing', f: 'billing', h: 1250 },
  { p: '/ambulance', f: 'ambulance', h: 1050 },
  { p: '/twin', f: 'twin', h: 1600, wait: 9000 },
  { p: '/governance', f: 'governance', h: 1650, wait: 9000 },
  { p: '/monitor', f: 'monitor', h: 1000, wait: 6000 },
  { p: '/handover', f: 'handover', h: 1100 },
  { p: '/agents?ask=ICU%20mein%20kitne%20bed%20khali%20hain%3F', f: 'copilot', h: 950, wait: 12000 },
  { p: '/display', f: 'display', h: 900 },
  { p: '/kiosk', f: 'kiosk', h: 900, w: 1000 },
  { p: '/portal', f: 'portal', role: 'patient', h: 1450 },
  { p: '/emergency', f: 'emergency', h: 1000 },
  { p: '/inpatients', f: 'inpatients', h: 1000 },
]

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

;(async () => {
  const extra = process.argv[2] ? JSON.parse(process.argv[2]) : null   // optional: [{p,f,h,role,wait}]
  const list = extra || PAGES
  fs.mkdirSync(SHOTS, { recursive: true })
  const browser = await puppeteer.launch({ executablePath: EDGE, headless: 'new', defaultViewport: null,
    args: ['--hide-scrollbars', '--disable-gpu', '--no-first-run'] })
  for (const item of list) {
    const role = item.role || 'admin'
    const w = item.w || 1440
    const page = await browser.newPage()
    await page.setViewport({ width: w, height: item.h || 900, deviceScaleFactor: SCALE })
    const sep = item.p.includes('?') ? '&' : '?'
    try {
      await page.goto(`${BASE}${item.p}${sep}demo=${role}`, { waitUntil: 'networkidle2', timeout: 60000 })
    } catch { /* keep going — SPA keeps websockets open */ }
    await sleep(item.wait || 4000)
    const file = `${item.f}.png`
    const buf = await page.screenshot({ type: 'png' })
    fs.writeFileSync(path.join(DOCS, file), buf)
    fs.writeFileSync(path.join(SHOTS, file), buf)
    console.log(file.padEnd(22), buf.length, 'bytes')
    await page.close()
  }
  await browser.close()
})()
