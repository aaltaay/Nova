import { expect, test } from '@playwright/test';

test('progress survives closing, controls stay reachable, and dragging commits one seek', async ({ page }) => {
  const errors: string[] = [];
  let seeks = 0;
  let minute = 165;
  const start = Date.parse('2026-09-18T08:00:00Z') / 1000;
  const selection = {symbol:'IMCC',date:'2026-09-18',start:'04:00',end:'09:30',coverage_through:start+9900,trade_count:1000,download_status:'running'};
  page.on('pageerror', error => errors.push(error.message));
  await page.route('http://127.0.0.1:8999/**', async route => {
    const path = new URL(route.request().url()).pathname;
    let body: unknown = {};
    if (path === '/api/ibkr/status') body={mode:'sim',connected:true,enabled:true};
    if (path === '/api/sim/clock') {
      if (route.request().method()==='POST') {seeks++;minute=route.request().postDataJSON().minute_from_open??minute;}
      body={sim:true,paused:true,minute_from_open:minute,minute_max:330,replay_source:'historical',replay_symbol:'IMCC',replay_date:'2026-09-18',session_open_et:'2026-09-18T04:00:00-04:00',session_close_et:'2026-09-18T09:30:00-04:00',sim_time_et:new Date((start+minute*60)*1000).toISOString()};
    }
    if(path==='/api/capture/sessions') body={days:[],tickers_by_day:{}};
    if(path==='/api/sim/history') body={selection,default_date:'2026-09-18',jobs:[{...selection,id:'job',kind:'trades',status:'running',count:1000,pages:1,error:null,progress_pct:50,downloaded_through:start+9900,eta_seconds:90,age_seconds:1,stale:false}]};
    if(path==='/api/sim/history/select') body=selection;
    if(path.startsWith('/api/sim/history/snapshot/')) body={active:true,symbol:'IMCC',selection,source:'trades',as_of:'2026-09-18T10:45:00Z',last:10,volume:1000,prints:Array.from({length:200},(_,i)=>({ordinal:i,time:'2026-09-18T10:45:00Z',price:10,size:100,exchange:'NASDAQ'}))};
    await route.fulfill({json:body});
  });
  await page.goto('/e2e/fixtures/replay-desk.html');
  const trigger=page.getByRole('button',{name:'Historical replay',exact:true});
  await expect(page.locator('.sim-history__summary')).toContainText('50%');
  const slider=page.getByTestId('sim-session-scrubber');
  await expect(slider).toHaveAttribute('aria-label','Sim replay time');
  await page.evaluate(() => {
    const header = document.querySelector<HTMLElement>('.sim-session-header')!;
    Object.assign(header.style, {position: 'relative', zIndex: '40', isolation: 'isolate'});
    const overlay = document.createElement('div');
    overlay.id = 'audit-context-overlay';
    Object.assign(overlay.style, {position: 'fixed', left: '700px', top: '100px', width: '560px', height: '450px', zIndex: '10050'});
    document.body.append(overlay);
  });
  await trigger.click();
  const panel=page.getByLabel('Historical replay setup');
  await expect(panel).toBeVisible();
  expect(await panel.evaluate(el => {
    const rect = el.getBoundingClientRect();
    return !el.closest('.sim-session-header') && el.contains(document.elementFromPoint(rect.x + rect.width/2, rect.y + rect.height/2));
  })).toBe(true);
  await page.evaluate(() => document.getElementById('audit-context-overlay')?.remove());
  await expect(panel.getByText(/Estimated 2m remaining/)).toBeVisible();
  const dark=await panel.evaluate(el=>getComputedStyle(el).backgroundColor);
  await page.keyboard.press('Escape');
  await expect(panel).not.toBeVisible();
  await expect(trigger).toBeFocused();
  await expect(page.locator('.sim-history__summary')).toContainText('50%');
  await page.evaluate(()=>document.documentElement.setAttribute('data-theme','light'));
  await page.setViewportSize({width:768,height:900});
  await trigger.click();
  const bounds=await panel.boundingBox();
  expect(bounds?.x).toBeGreaterThanOrEqual(0);
  expect((bounds?.x??0)+(bounds?.width??0)).toBeLessThanOrEqual(768);
  expect(await panel.evaluate(el=>getComputedStyle(el).backgroundColor)).not.toBe(dark);
  await panel.getByRole('button',{name:/Use this window:/}).click();
  await expect(page.getByRole('textbox',{name:'Historical ticker'})).toHaveValue('IMCC');
  await panel.getByRole('button',{name:'Load replay',exact:true}).click();
  await expect(panel).not.toBeVisible();
  await expect(page.locator('.sim-history__selection')).toContainText('IMCC');
  const rect=await slider.boundingBox();
  expect(rect).not.toBeNull();
  const before=seeks;
  await page.mouse.move(rect!.x+rect!.width/2,rect!.y+rect!.height/2);
  await page.mouse.down();
  await page.mouse.move(rect!.x+rect!.width*.8,rect!.y+rect!.height/2,{steps:8});
  expect(seeks).toBe(before);
  await page.mouse.up();
  await expect.poll(()=>seeks).toBe(before+1);
  expect(errors).toEqual([]);
});
