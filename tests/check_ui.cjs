// Offline browser checks using synthetic HTTP fixtures and Chrome's built-in CDP.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const os = require('node:os');
const path = require('node:path');
const {spawn} = require('node:child_process');
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const html = fs.readFileSync(path.join(__dirname, '..', 'web', 'index.html'));
const accounts = [
  {id:'me', label:'测试账号 A', studentMask:'20••••01', runAt:'21:01', enabled:true},
  {id:'alt', label:'测试账号 B', studentMask:'20••••02', runAt:'22:03', enabled:false}
];
const requests = [], errors = [];
const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost');
  requests.push(url.pathname);
  let value;
  if (url.pathname === '/moonuestc/') {
    res.setHeader('Content-Type', 'text/html; charset=utf-8');
    return res.end(html);
  }
  if (url.pathname.endsWith('/accounts.json')) value = {accounts};
  else if (url.pathname.endsWith('/status-me.json')) value = {
    history:[{result:'auth_ready',time:'2026-10-22T21:01:00+08:00'}],
    auth:{ok:true}, lastRun:{result:'auth_ready'}, location:{name:'Synthetic A'}
  };
  else if (url.pathname.endsWith('/status-alt.json')) {
    await pause(150);
    value = {history:[],location:{name:'Synthetic B'}};
  } else if (url.pathname === '/cgi-bin/moonuestc-api') {
    if (req.method === 'GET') value = {ok:true,authenticated:true};
    else {
      let body = '';
      for await (const part of req) body += part;
      const fields = JSON.parse(body);
      assert.equal(fields.action, 'get', 'Browser check must not write or submit');
      const account = accounts.find(a => a.id === fields.id);
      value = {ok:true,account:account ? {
        id:account.id,label:account.label,student_id:'2099999999999',
        run_at:account.runAt,automation_enabled:account.enabled,
        password_saved:true,fingerprint_saved:true,location:{name:'Synthetic custom',latitude:30.5,longitude:104.1}
      } : {run_at:'21:01',automation_enabled:false,location:{}}};
    }
  } else { res.statusCode = 404; return res.end(); }
  res.setHeader('Content-Type','application/json');
  res.end(JSON.stringify(value));
});

(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const base = 'http://127.0.0.1:' + server.address().port;
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'moonuestc-ui-'));
  const chrome = process.env.CHROME_PATH || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
  const child = spawn(chrome, [
    '--headless=new','--disable-gpu','--no-proxy-server','--disable-background-networking',
    '--disable-component-update','--disable-extensions','--no-first-run','--no-default-browser-check',
    '--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'
  ], {windowsHide:true,stdio:'ignore'});
  let ws;
  child.on('error', error => errors.push(error.message));
  try {
    const portFile = path.join(profile, 'DevToolsActivePort');
    for(let i=0; !fs.existsSync(portFile) && i<80; i++) await pause(100);
    assert.ok(fs.existsSync(portFile), 'Chrome did not start; set CHROME_PATH');
    const port = fs.readFileSync(portFile,'utf8').split('\n')[0];
    const tabs = await (await fetch('http://127.0.0.1:'+port+'/json/list')).json();
    ws = new WebSocket(tabs.find(t => t.type==='page').webSocketDebuggerUrl);
    await new Promise((resolve,reject) => {
      ws.addEventListener('open',resolve,{once:true});
      ws.addEventListener('error',reject,{once:true});
    });
    let sequence = 0;
    const pending = new Map();
    ws.addEventListener('message', event => {
      const message = JSON.parse(event.data);
      if(message.method==='Runtime.exceptionThrown') errors.push(JSON.stringify(message.params.exceptionDetails));
      if(pending.has(message.id)) {
        const p = pending.get(message.id); pending.delete(message.id); clearTimeout(p.timer);
        message.error ? p.reject(Error(message.error.message)) : p.resolve(message.result);
      }
    });
    const rpc = (method,params={}) => new Promise((resolve,reject) => {
      const id=++sequence, timer=setTimeout(()=>{pending.delete(id);reject(Error(method+' timed out'));},8000);
      pending.set(id,{resolve,reject,timer}); ws.send(JSON.stringify({id,method,params}));
    });
    const evaluate = async expression => {
      const r=await rpc('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
      if(r.exceptionDetails) throw Error(JSON.stringify(r.exceptionDetails));
      return r.result.value;
    };
    const waitFor = async expression => {
      for(let i=0;i<60;i++) { if(await evaluate(expression)) return; await pause(50); }
      throw Error('UI condition timed out: '+expression);
    };
    await rpc('Runtime.enable');
    await rpc('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
    await rpc('Page.navigate',{url:base+'/moonuestc/'});
    await waitFor("document.getElementById('location')?.textContent==='Synthetic A'");
    assert.equal(await evaluate("document.getElementById('window').textContent"),'尚未读取');
    await evaluate("document.getElementById('account-select').value='alt';document.getElementById('account-select').dispatchEvent(new Event('change'))");
    assert.equal(await evaluate("document.getElementById('history').textContent"),'暂无记录');
    await waitFor("document.getElementById('location').textContent==='Synthetic B'");
    assert.equal(await evaluate("document.getElementById('status').textContent"),'已暂停');
    for(const width of [1440,390]) {
      await rpc('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:width<500});
      assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth'), 'Horizontal overflow at '+width);
      await evaluate("document.getElementById('edit').click()");
      await waitFor("document.getElementById('account-dialog').open");
      assert.deepEqual(await evaluate("['school-password','fingerprint'].map(id=>document.getElementById(id).value)"),['','']);
      assert.deepEqual(await evaluate("['location-name','latitude','longitude'].map(id=>document.getElementById(id).value)"),['Synthetic custom','30.5','104.1']);
      assert.ok(await evaluate("document.getElementById('account-dialog').getBoundingClientRect().right<=innerWidth"));
      if(process.env.UI_SCREENSHOT_DIR) {
        fs.mkdirSync(process.env.UI_SCREENSHOT_DIR,{recursive:true});
        const shot=await rpc('Page.captureScreenshot',{format:'png'});
        fs.writeFileSync(path.join(process.env.UI_SCREENSHOT_DIR,'multi-ui-'+width+'.png'),Buffer.from(shot.data,'base64'));
      }
      await evaluate("document.getElementById('account-dialog').close()");
    }
    await evaluate("document.getElementById('add').click()");
    await waitFor("document.getElementById('account-dialog').open");
    assert.deepEqual(await evaluate("['location-name','latitude','longitude'].map(id=>document.getElementById(id).value)"),['欣苑组团','30.674521','104.096295']);
    assert.deepEqual(errors,[]);
    assert.ok(requests.includes('/cgi-bin/moonuestc-api'));
    console.log('Offline Chrome UI passed: account isolation, paused state, Xinyuan defaults and preserved custom coordinates, secret fields, desktop and 390px mobile.');
  } finally {
    if(ws) ws.close();
    child.kill();
    await pause(500);
    server.closeAllConnections(); server.close();
    const resolved=path.resolve(profile);
    if(path.dirname(resolved)!==path.resolve(os.tmpdir()) || !path.basename(resolved).startsWith('moonuestc-ui-'))
      throw Error('Refusing cleanup outside the temporary browser profile');
    fs.rmSync(resolved,{recursive:true,force:true,maxRetries:5,retryDelay:200});
  }
})().catch(error=>{console.error(error);process.exitCode=1;server.closeAllConnections();server.close();});
