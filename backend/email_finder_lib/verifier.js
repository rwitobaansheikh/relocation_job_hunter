'use strict';

const dns = require('dns').promises;
const net = require('net');

const DEFAULT_TIMEOUT = 10000;
const DEFAULT_HELO = 'verifier.local';

/** Looks up MX records for a domain, sorted by priority (lowest = preferred). */
async function getMxRecords(domain) {
  const records = await dns.resolveMx(domain);
  if (!records.length) throw new Error(`No MX records found for ${domain}`);
  return records.sort((a, b) => a.priority - b.priority);
}

/** Reads one full (possibly multi-line) SMTP response from a socket. */
function readSmtpResponse(socket, timeoutMs) {
  return new Promise((resolve, reject) => {
    let buffer = '';
    const cleanup = () => {
      clearTimeout(timer);
      socket.removeListener('data', onData);
      socket.removeListener('error', onError);
    };
    const onData = (chunk) => {
      buffer += chunk.toString('utf8');
      const lines = buffer.split('\r\n').filter(Boolean);
      const last = lines[lines.length - 1];
      // Multi-line SMTP responses use "250-text" for continuation lines and
      // "250 text" (space, not hyphen) for the final line of the response.
      if (last && /^\d{3} /.test(last)) {
        cleanup();
        resolve({ code: parseInt(last.slice(0, 3), 10), lines });
      }
    };
    const onError = (err) => {
      cleanup();
      reject(err);
    };
    const timer = setTimeout(() => {
      cleanup();
      reject(new Error('Timed out waiting for SMTP response'));
    }, timeoutMs);
    socket.on('data', onData);
    socket.on('error', onError);
  });
}

/**
 * Opens an SMTP connection to mxHost and runs a HELO / MAIL FROM / RCPT TO
 * conversation, then QUITs before ever sending DATA — so no email is ever
 * actually delivered. We only care how the server answers RCPT TO, which
 * is the standard "does this mailbox exist" signal every mail server
 * implements as part of the SMTP protocol itself.
 */
function smtpProbe(mxHost, { heloDomain, mailFrom, rcptTo, timeoutMs }) {
  return new Promise((resolve, reject) => {
    const socket = net.createConnection({ host: mxHost, port: 25 });
    let settled = false;

    const fail = (err) => {
      if (settled) return;
      settled = true;
      socket.destroy();
      reject(err);
    };

    socket.setTimeout(timeoutMs, () =>
      fail(
        new Error(
          `Connection to ${mxHost}:25 timed out — outbound port 25 may be blocked on this network ` +
            '(common on home ISPs, and on AWS/most cloud providers by default)'
        )
      )
    );
    socket.once('error', fail);

    socket.once('connect', async () => {
      try {
        await readSmtpResponse(socket, timeoutMs); // 220 banner
        socket.write(`EHLO ${heloDomain}\r\n`);
        await readSmtpResponse(socket, timeoutMs); // 250 EHLO ack
        socket.write(`MAIL FROM:<${mailFrom}>\r\n`);
        await readSmtpResponse(socket, timeoutMs); // 250 sender ok
        socket.write(`RCPT TO:<${rcptTo}>\r\n`);
        const rcptResp = await readSmtpResponse(socket, timeoutMs); // the answer we actually want
        socket.write('QUIT\r\n');
        socket.end();
        settled = true;
        resolve(rcptResp);
      } catch (err) {
        fail(err);
      }
    });
  });
}

function classify(code) {
  if (code === 250 || code === 251) return 'accepted';
  if (code >= 550 && code <= 553) return 'rejected';
  if ([450, 451, 452].includes(code)) return 'greylisted'; // temp-fail, try again later
  return 'unknown';
}

function withDefaults(options) {
  const heloDomain = options.heloDomain || DEFAULT_HELO;
  return {
    heloDomain,
    mailFrom: options.mailFrom || `verify@${heloDomain}`,
    timeoutMs: options.timeoutMs || DEFAULT_TIMEOUT,
  };
}

/**
 * Checks whether a domain's mail server is a "catch-all" — i.e. it accepts
 * mail for literally any address at that domain, real or not. If so, every
 * RCPT TO will return 250 regardless of which pattern you try, which means
 * per-address verification can't tell you anything useful on that domain.
 * This is common on Microsoft 365 / Google Workspace tenants configured
 * defensively, specifically to defeat probing tools like this one.
 */
async function checkCatchAll(domain, options = {}) {
  const opts = withDefaults(options);
  const mxRecords = await getMxRecords(domain);
  const mxHost = mxRecords[0].exchange;
  const probeUser = `noexist-${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
  const resp = await smtpProbe(mxHost, { ...opts, rcptTo: `${probeUser}@${domain}` });
  return { mxHost, isCatchAll: classify(resp.code) === 'accepted' };
}

/** Verifies a single email address via SMTP RCPT TO against a known MX host. */
async function verifyEmail(email, mxHost, options = {}) {
  const opts = withDefaults(options);
  const resp = await smtpProbe(mxHost, { ...opts, rcptTo: email });
  return { email, smtpCode: resp.code, status: classify(resp.code) };
}

module.exports = { getMxRecords, checkCatchAll, verifyEmail, classify };
