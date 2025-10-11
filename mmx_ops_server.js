#!/usr/bin/env node
const express = require('express');
const sqlite3 = require('sqlite3').verbose();
const bodyParser = require('body-parser');
const crypto = require('crypto');
const stripe = require('stripe')(process.env.STRIPE_SECRET_KEY || '');

const PORT = Number(process.env.PORT || 3000);
const BASE_URL = process.env.BASE_URL || `http://localhost:${PORT}`;
const STRIPE_CLIENT_ID="REDACTED"'';
const STRIPE_WEBHOOK_SECRET="REDACTED"'';
const GITHUB_WEBHOOK_SECRET="REDACTED"'';
const ADMIN_TOKEN = process.env.ADMIN_TOKEN || '';
const DEFAULT_POOL_PCT = Number(process.env.POOL_PERCENT || 30);
const SALE_COMMISSION_PCT = Number(process.env.SALE_COMMISSION_PCT || 30);
const SUPPORT_RATE_CPM = Number(process.env.SUPPORT_RATE_CPM || 50);

const DB = new sqlite3.Database('./mmx_ops.db');
DB.serialize(() => {
  DB.run(`CREATE TABLE IF NOT EXISTS contributors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    github_login TEXT UNIQUE,
    github_id INTEGER,
    stripe_account_id TEXT,
    connected_at INTEGER,
    role TEXT,
    support_opt_in INTEGER DEFAULT 0
  )`);
  DB.run(`CREATE TABLE IF NOT EXISTS revenues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT,
    amount_cents INTEGER,
    recorded_at INTEGER DEFAULT (strftime('%s','now'))
  )`);
  DB.run(`CREATE TABLE IF NOT EXISTS payouts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contributor_id INTEGER,
    amount_cents INTEGER,
    stripe_transfer_id TEXT,
    created_at INTEGER DEFAULT (strftime('%s','now')),
    period TEXT
  )`);
  DB.run(`CREATE TABLE IF NOT EXISTS sales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT,
    amount_cents INTEGER,
    app_fee_cents INTEGER,
    currency TEXT,
    buyer_email TEXT,
    seller_github TEXT,
    stripe_pi TEXT,
    created_at INTEGER DEFAULT (strftime('%s','now'))
  )`);
  DB.run(`CREATE TABLE IF NOT EXISTS support_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    github_login TEXT,
    ticket_id TEXT,
    channel TEXT,
    started_at INTEGER,
    ended_at INTEGER,
    minutes INTEGER,
    approved_by TEXT,
    approval_at INTEGER,
    evidence_json TEXT
  )`);
  DB.run(`CREATE TABLE IF NOT EXISTS entitlements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    github_login TEXT,
    period TEXT,
    category TEXT,
    amount_cents INTEGER,
    source_table TEXT,
    source_id INTEGER,
    meta_json TEXT
  )`);
});

const app = express();
app.use(bodyParser.json({ verify: (req, _res, buf) => { req.rawBody = buf; } }));

function dbRun(sql, params = []) { return new Promise((res, rej) => DB.run(sql, params, function(e){ e?rej(e):res(this); })); }
function dbGet(sql, params = []) { return new Promise((res, rej) => DB.get(sql, params, (e,row)=>{ e?rej(e):res(row); })); }
function dbAll(sql, params = []) { return new Promise((res, rej) => DB.all(sql, params, (e,rows)=>{ e?rej(e):res(rows); })); }

function periodFromUnix(ts) {
  const d = new Date(ts*1000);
  const y = d.getUTCFullYear();
  const m = (d.getUTCMonth()+1).toString().padStart(2,'0');
  return `${y}-${m}`;
}

app.get('/health', (_req,res)=>res.send('ok'));
app.get('/healthz', (_req,res)=>res.json({ok:true}));

app.get('/start_connect', (req,res)=>{
  const github = (req.query.github||'').trim();
  if(!github) return res.status(400).send('missing github');
  const state = Buffer.from(JSON.stringify({github, ts: Date.now()})).toString('base64url');
  const url = new URL('https://connect.stripe.com/oauth/authorize');
  url.searchParams.set('response_type','code');
  url.searchParams.set('client_id', STRIPE_CLIENT_ID);
  url.searchParams.set('scope','read_write');
  url.searchParams.set('state', state);
  url.searchParams.set('redirect_uri', `${BASE_URL}/stripe_oauth_cb`);
  res.redirect(url.toString());
});

app.get('/stripe_oauth_cb', async (req,res)=>{
  try{
    const code = req.query.code;
    const stateRaw = req.query.state;
    if(!code||!stateRaw) return res.status(400).send('missing code/state');
    const state = JSON.parse(Buffer.from(stateRaw,'base64url').toString('utf8'));
    const githubLogin = state.github;
    const tok = await stripe.oauth.token({grant_type:'authorization_code', code});
    const accountId = tok.stripe_user_id;
    await dbRun(
      `INSERT INTO contributors (github_login, github_id, stripe_account_id, connected_at, role)
       VALUES (?, NULL, ?, strftime('%s','now'), 'contributor')
       ON CONFLICT(github_login) DO UPDATE SET stripe_account_id=excluded.stripe_account_id, connected_at=excluded.connected_at`,
       [githubLogin, accountId]
    );
    res.status(200).send(`Connected ${githubLogin} → ${accountId}. You can close this tab.`);
  }catch(e){
    res.status(500).send('oauth failed');
  }
});

app.post('/webhook/stripe', (req,res)=>{
  let event;
  try{
    const sig = req.headers['stripe-signature'];
    event = stripe.webhooks.constructEvent(req.rawBody, sig, STRIPE_WEBHOOK_SECRET);
  }catch(err){
    return res.status(400).send('invalid signature');
  }
  (async ()=>{
    if(event.type === 'payment_intent.succeeded'){
      const pi = event.data.object;
      const created = pi.created || Math.floor(Date.now()/1000);
      const period = periodFromUnix(created);
      const amount = Number(pi.amount||0);
      const appFee = Number(pi.application_fee_amount||0);
      const currency = (pi.currency||'usd');
      const buyer = (pi.receipt_email||'') || (pi.charges?.data?.[0]?.billing_details?.email||'');
      const seller = (pi.metadata?.seller_github || pi.metadata?.seller || '').trim();

      await dbRun(
        `INSERT INTO sales (period, amount_cents, app_fee_cents, currency, buyer_email, seller_github, stripe_pi)
         VALUES (?,?,?,?,?,?,?)`,
         [period, amount, appFee, currency, buyer, seller, pi.id]
      );

      if(seller){
        const give = Math.min(appFee, Math.floor(appFee * (SALE_COMMISSION_PCT/100)));
        if(give>0){
          try{
            await dbRun(
              `INSERT INTO entitlements (github_login, period, category, amount_cents, source_table, source_id, meta_json)
               VALUES (?,?,?,?,? , (SELECT id FROM sales WHERE stripe_pi=?), ?)`,
               [seller, period, 'sale_commission', give, 'sales', pi.id, JSON.stringify({pi:pi.id, app_fee_cents:appFee})]
            );
          }catch{
            const sale = await dbGet(`SELECT id FROM sales WHERE stripe_pi=?`, [pi.id]);
            if(sale){
              await dbRun(
                `INSERT INTO entitlements (github_login, period, category, amount_cents, source_table, source_id, meta_json)
                 VALUES (?,?,?,?,?,?,?)`,
                 [seller, period, 'sale_commission', give, 'sales', sale.id, JSON.stringify({pi:pi.id, app_fee_cents:appFee})]
              );
            }
          }
        }
      }
    }
  })().then(()=>res.json({received:true})).catch(()=>res.json({received:true}));
});

app.post('/webhook/github', async (req,res)=>{
  try{
    const sig = req.headers['x-hub-signature-256'] || '';
    const hmac = 'sha256=' + crypto.createHmac('sha256', GITHUB_WEBHOOK_SECRET).update(req.rawBody).digest('hex');
    if(!crypto.timingSafeEqual(Buffer.from(hmac), Buffer.from(sig))) return res.status(401).send('bad sig');
    const ev = req.headers['x-github-event'];
    const body = req.body;
    if (ev === 'issues' && body.action === 'labeled') {
      const login = body.sender?.login;
      const label = body.label?.name || '';
      if (login && /support/i.test(label)) {
        await dbRun(`INSERT INTO contributors (github_login, support_opt_in)
                     VALUES (?, 1)
                     ON CONFLICT(github_login) DO UPDATE SET support_opt_in=1`, [login]);
      }
    }
    res.json({ok:true});
  }catch(e){ res.status(400).send('webhook error'); }
});

app.post('/support/start', async (req,res)=>{
  const login=(req.body.github_login||'').trim();
  const ticket=(req.body.ticket_id||'').trim();
  const channel=(req.body.channel||'').trim()||'github';
  const now=Math.floor(Date.now()/1000);
  if(!login) return res.status(400).json({error:'missing login'});
  await dbRun(`INSERT INTO support_sessions (github_login,ticket_id,channel,started_at) VALUES (?,?,?,?)`,
    [login,ticket,channel,now]);
  const row=await dbGet(`SELECT last_insert_rowid() AS id`,[]);
  res.json({ok:true, session_id: row.id});
});

app.post('/support/stop', async (req,res)=>{
  const id=Number(req.body.session_id||0);
  const evidence=req.body.evidence_json?JSON.stringify(req.body.evidence_json):null;
  if(!id) return res.status(400).json({error:'missing id'});
  const sess=await dbGet(`SELECT * FROM support_sessions WHERE id=?`,[id]);
  if(!sess||sess.ended_at) return res.status(400).json({error:'bad session'});
  const now=Math.floor(Date.now()/1000);
  const minutes=Math.max(1, Math.floor((now - (sess.started_at||now))/60));
  await dbRun(`UPDATE support_sessions SET ended_at=?, minutes=?, evidence_json=? WHERE id=?`,
    [now, minutes, evidence, id]);
  res.json({ok:true, minutes});
});

app.post('/support/approve', async (req,res)=>{
  if(!ADMIN_TOKEN || req.headers['x-admin-token']!==ADMIN_TOKEN) return res.status(403).json({error:'forbidden'});
  const id=Number(req.body.session_id||0);
  if(!id) return res.status(400).json({error:'missing id'});
  const s=await dbGet(`SELECT * FROM support_sessions WHERE id=?`,[id]);
  if(!s||!s.minutes) return res.status(400).json({error:'bad session'});
  const mins=Number(s.minutes||0);
  const cents = mins * SUPPORT_RATE_CPM;
  const period = periodFromUnix((s.ended_at||s.started_at||Math.floor(Date.now()/1000)));
  await dbRun(
    `INSERT INTO entitlements (github_login, period, category, amount_cents, source_table, source_id, meta_json)
     VALUES (?,?,?,?,?,?,?)`,
     [s.github_login, period, 'support', cents, 'support_sessions', id, JSON.stringify({minutes:mins})]
  );
  await dbRun(`UPDATE support_sessions SET approved_by='admin', approval_at=strftime('%s','now') WHERE id=?`,[id]);
  res.json({ok:true, cents});
});

app.post('/revenue', async (req,res)=>{
  const period=(req.body.period||'').trim();
  const amount_cents = Number(req.body.amount_cents||0)|0;
  if(!period || amount_cents<=0) return res.status(400).json({error:'bad payload'});
  await dbRun(`INSERT INTO revenues (period, amount_cents) VALUES (?,?)`,[period, amount_cents]);
  res.json({ok:true});
});

app.get('/contributors', async (_req,res)=>{
  const rows = await dbAll(`SELECT id, github_login, github_id, stripe_account_id, connected_at, role, support_opt_in FROM contributors ORDER BY github_login`);
  res.json(rows);
});

app.get('/earnings', async (req,res)=>{
  const login=(req.query.github_login||'').trim();
  const period=(req.query.period||'').trim();
  if(!login) return res.status(400).json({error:'missing login'});
  const rows = await dbAll(
    `SELECT period, category, SUM(amount_cents) AS sum_cents
     FROM entitlements
     WHERE github_login=? ${period? 'AND period=?':''}
     GROUP BY period, category
     ORDER BY period DESC, category`, period? [login,period]:[login]
  );
  res.json(rows);
});

app.get('/periods/latest', async (_req,res)=>{
  const row = await dbGet(`SELECT period FROM revenues ORDER BY recorded_at DESC LIMIT 1`,[]);
  if(row?.period) return res.json({period: row.period});
  const d=new Date(); const p=`${d.getUTCFullYear()}-${String(d.getUTCMonth()+1).padStart(2,'0')}`;
  res.json({period: p});
});

app.post('/distribute_payouts', async (req,res)=>{
  try{
    const inputPeriod=(req.body.period||'').trim();
    const pool_percent = Number(req.body.pool_percent ?? DEFAULT_POOL_PCT);
    let period = inputPeriod;
    if(!period){
      const r = await dbGet(`SELECT period FROM revenues ORDER BY recorded_at DESC LIMIT 1`,[]);
      period = r?.period || null;
      if(!period) return res.json({ok:true, pool_cents:0, transfers:[]});
    }
    const rev = await dbGet(`SELECT COALESCE(SUM(amount_cents),0) AS sum FROM revenues WHERE period=?`,[period]);
    const total = Number(rev?.sum||0);
    if(total<=0) return res.json({ok:true, pool_cents:0, transfers:[]});
    const pool = Math.floor(total * (pool_percent/100));
    const ents = await dbAll(
      `SELECT e.github_login, SUM(e.amount_cents) AS sum_cents, c.id AS contributor_id, c.stripe_account_id
       FROM entitlements e
       JOIN contributors c ON c.github_login=e.github_login
       WHERE e.period=? AND c.stripe_account_id IS NOT NULL
       GROUP BY e.github_login, c.id, c.stripe_account_id`, [period]
    );
    if(!ents.length) return res.json({ok:true, pool_cents:0, transfers:[]});
    const entTotal = ents.reduce((a,b)=>a+Number(b.sum_cents||0),0);
    if(entTotal<=0) return res.json({ok:true, pool_cents:0, transfers:[]});

    const transfers=[];
    for(const row of ents){
      const share = Math.floor(pool * (Number(row.sum_cents)/entTotal));
      if(share<=0) continue;
      try{
        const t = await stripe.transfers.create({
          amount: share,
          currency: 'usd',
          destination: row.stripe_account_id,
          description: `MMX revenue share ${period}`,
          metadata: { period, github_login: row.github_login }
        });
        await dbRun(`INSERT INTO payouts (contributor_id, amount_cents, stripe_transfer_id, period) VALUES (?,?,?,?)`,
          [row.contributor_id, share, t.id, period]);
        transfers.push({github_login: row.github_login, amount_cents: share, transfer_id: t.id});
      }catch(err){
        console.error('[payouts] error:', err?.message||err);
      }
    }
    res.json({ok:true, pool_cents: pool, transfers});
  }catch(e){
    console.error('[payouts] fatal:', e);
    res.status(500).json({error:'payout_failed'});
  }
});

app.get('/', (_req,res)=>res.redirect('/dashboard.html'));
app.use(express.static('public'));

app.listen(PORT, ()=>{ console.log(`MMX Ops server on ${BASE_URL} (client_id=${STRIPE_CLIENT_ID?.slice(0,10)}…)`); });
