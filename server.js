#!/usr/bin/env node
const express = require('express');
const sqlite3 = require('sqlite3').verbose();
const bodyParser = require('body-parser');
const crypto = require('crypto');
const stripe = require('stripe')(process.env.STRIPE_SECRET_KEY || '');

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
});

const app = express();
app.use(bodyParser.json({ verify: (req, res, buf) => { req.rawBody = buf } }));

const PORT = process.env.PORT || 3000;
const BASE_URL = process.env.BASE_URL || `http://localhost:${PORT}`;
const STRIPE_CLIENT_ID="REDACTED"'';
const STRIPE_WEBHOOK_SECRET="REDACTED"'';
const GITHUB_WEBHOOK_SECRET="REDACTED"'';
const GITHUB_TOKEN = process.env.GITHUB_TOKEN || '';

function dbRun(sql, params = []) {
  return new Promise((resolve, reject) => DB.run(sql, params, function (err) {
    if (err) reject(err); else resolve(this);
  }));
}
function dbGet(sql, params = []) {
  return new Promise((resolve, reject) => DB.get(sql, params, (err, row) => {
    if (err) reject(err); else resolve(row);
  }));
}
function dbAll(sql, params = []) {
  return new Promise((resolve, reject) => DB.all(sql, params, (err, rows) => {
    if (err) reject(err); else resolve(rows);
  }));
}

// 1) Start Stripe Connect OAuth
app.get('/start_connect', (req, res) => {
  const github = (req.query.github || '').trim();
  if (!github) return res.status(400).send('missing github query param');
  const state = Buffer.from(JSON.stringify({ github, ts: Date.now() })).toString('base64url');
  const params = new URLSearchParams({
    response_type: 'code',
    client_id: STRIPE_CLIENT_ID,
    scope: 'read_write',
    state,
    redirect_uri: `${BASE_URL}/stripe_oauth_cb`
  });
  res.redirect(`https://connect.stripe.com/oauth/authorize?${params.toString()}`);
});

// 2) Stripe OAuth callback
app.get('/stripe_oauth_cb', async (req, res) => {
  try {
    const code = req.query.code;
    const stateRaw = req.query.state || '';
    if (!code || !stateRaw) return res.status(400).send('missing code/state');
    const state = JSON.parse(Buffer.from(stateRaw, 'base64url').toString('utf8'));
    const githubLogin = state.github;

    const tok = await stripe.oauth.token({ grant_type: 'authorization_code', code });
    const accountId = tok.stripe_user_id;

    await dbRun(`INSERT INTO contributors (github_login, github_id, stripe_account_id, connected_at, role)
                 VALUES (?, NULL, ?, strftime('%s','now'), 'contributor')
                 ON CONFLICT(github_login) DO UPDATE SET stripe_account_id=excluded.stripe_account_id, connected_at=excluded.connected_at`,
      [githubLogin, accountId]);

    res.status(200).send(`Connected ${githubLogin} → ${accountId}. You can close this tab.`);
  } catch (e) {
    res.status(500).send('oauth failed');
  }
});

// 3) Stripe webhook
app.post('/webhook/stripe', (req, res) => {
  try {
    const sig = req.headers['stripe-signature'];
    const event = stripe.webhooks.constructEvent(req.rawBody, sig, STRIPE_WEBHOOK_SECRET);
    if (event.type === 'account.updated') {
      // no-op placeholder
    }
    res.json({ received: true });
  } catch (err) {
    res.status(400).send('invalid signature');
  }
});

// 4) GitHub webhook
app.post('/webhook/github', async (req, res) => {
  try {
    const sig = req.headers['x-hub-signature-256'] || '';
    const hmac = 'sha256=' + crypto.createHmac('sha256', GITHUB_WEBHOOK_SECRET).update(req.rawBody).digest('hex');
    if (!crypto.timingSafeEqual(Buffer.from(hmac), Buffer.from(sig))) return res.status(401).send('bad sig');

    const ev = req.headers['x-github-event'];
    const body = req.body;

    if (ev === 'member' && body.action === 'added') {
      const login = body.member?.login;
      const id = body.member?.id;
      if (login) {
        await dbRun(`INSERT INTO contributors (github_login, github_id, role)
                     VALUES (?, ?, 'contributor')
                     ON CONFLICT(github_login) DO NOTHING`, [login, id || null]);
      }
    }

    if (ev === 'issues' && body.action === 'labeled') {
      const login = body.sender?.login;
      const label = body.label?.name || '';
      if (login && /support/i.test(label)) {
        await dbRun(`INSERT INTO contributors (github_login, support_opt_in)
                     VALUES (?, 1)
                     ON CONFLICT(github_login) DO UPDATE SET support_opt_in=1`, [login]);
      }
    }

    res.json({ ok: true });
  } catch (e) {
    res.status(400).send('webhook error');
  }
});

// 5) Record revenue
app.post('/revenue', async (req, res) => {
  const period = (req.body.period || '').trim();
  const amount_cents = Number(req.body.amount_cents || 0) | 0;
  if (!period || amount_cents <= 0) return res.status(400).json({ error: 'bad payload' });
  await dbRun(`INSERT INTO revenues (period, amount_cents) VALUES (?, ?)`, [period, amount_cents]);
  res.json({ ok: true });
});

// 6) List contributors
app.get('/contributors', async (_req, res) => {
  const rows = await dbAll(`SELECT id, github_login, github_id, stripe_account_id, connected_at, role, support_opt_in FROM contributors ORDER BY github_login`);
  res.json(rows);
});

// 7) Opt-in/out support
app.post('/support_opt', async (req, res) => {
  const login = (req.body.github_login || '').trim();
  const on = req.body.support_opt_in ? 1 : 0;
  if (!login) return res.status(400).json({ error: 'missing login' });
  await dbRun(`INSERT INTO contributors (github_login, support_opt_in)
               VALUES (?, ?)
               ON CONFLICT(github_login) DO UPDATE SET support_opt_in=excluded.support_opt_in`, [login, on]);
  res.json({ ok: true });
});

// 8) Distribute payouts
app.post('/distribute_payouts', async (req, res) => {
  try {
    const period = (req.body.period || '').trim();
    const pool_percent = Number(req.body.pool_percent ?? 30);
    if (!period) return res.status(400).json({ error: 'missing period' });

    const rev = await dbGet(`SELECT COALESCE(SUM(amount_cents),0) AS sum FROM revenues WHERE period = ?`, [period]);
    const total = Number(rev?.sum || 0);
    if (total <= 0) return res.json({ ok: true, pool_cents: 0, transfers: [] });

    const pool = Math.floor(total * (pool_percent / 100));
    const contribs = await dbAll(`SELECT id, github_login, stripe_account_id FROM contributors WHERE stripe_account_id IS NOT NULL`);
    if (!contribs.length || pool <= 0) return res.json({ ok: true, pool_cents: 0, transfers: [] });

    const n = contribs.length;
    const base = Math.floor(pool / n);
    let rem = pool - base * n;

    const results = [];
    for (const c of contribs) {
      let amt = base + (rem > 0 ? 1 : 0);
      if (rem > 0) rem--;

      const t = await stripe.transfers.create({
        amount: amt,
        currency: 'usd',
        destination: c.stripe_account_id,
        description: `MMX revenue share ${period}`,
        metadata: { period, github_login: c.github_login }
      });

      await dbRun(`INSERT INTO payouts (contributor_id, amount_cents, stripe_transfer_id, period)
                   VALUES (?, ?, ?, ?)`, [c.id, amt, t.id, period]);

      results.push({ github_login: c.github_login, amount_cents: amt, transfer_id: t.id });
    }

    res.json({ ok: true, pool_cents: pool, transfers: results });
  } catch (e) {
    res.status(500).json({ error: 'payout_failed' });
  }
});

// 9) Health check endpoints
app.get('/healthz', (_req, res) => res.json({ ok: true }));
app.get('/health', (_req, res) => res.send('ok'));

// Start server
app.listen(PORT, () => {
  console.log(`MMX Ops server running at ${BASE_URL}`);
});
