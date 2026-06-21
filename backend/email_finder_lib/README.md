# email-finder

> **Production integration:** the Python port lives in `backend/app/services/smtp_email_verifier.py`
> and is used by `backend/app/services/email_finder.py`. The JavaScript files in this folder
> are the original reference implementation.

Generates likely email addresses for a person at a company (`first.last@domain.com`,
`flast@domain.com`, etc.) and checks each candidate against the company's real mail
server via SMTP — the same core technique paid tools like Hunter/Apollo/Snov use
under the hood, minus the database and the monthly fee.

## How it works

1. **`patterns.js`** — takes a first name, last name, and domain, returns ~12 candidate
   addresses ordered by how common each convention is.
2. **`verifier.js`** — looks up the domain's MX record, opens a raw SMTP connection,
   and runs `HELO` → `MAIL FROM` → `RCPT TO <candidate>` → `QUIT`. It never sends
   `DATA`, so no email is ever actually delivered — this only reads the mail
   server's own "does this mailbox exist" answer, which is a standard part of
   the SMTP protocol.
3. **`index.js`** — ties the two together: generates patterns, checks the domain
   for catch-all behaviour, then verifies each candidate in turn with a short
   delay between attempts.

## Usage

```js
const { findEmail } = require('./index');

const result = await findEmail('Jane', 'Smith', 'hertz.com', {
  heloDomain: 'yourdomain.com',   // use a domain you actually control
  mailFrom: 'verify@yourdomain.com',
});

console.log(result);
```

Run the example directly:

```bash
node example.js
```

### Output shape

```js
{
  domain: 'hertz.com',
  mxHost: 'mx.hertz.com',
  catchAll: false,
  bestGuess: 'jane.smith@hertz.com',   // first candidate with status 'accepted', or null
  candidates: [
    { email: 'jane.smith@hertz.com', pattern: 'first.last', smtpCode: 250, status: 'accepted' },
    { email: 'jsmith@hertz.com',     pattern: 'flast',      smtpCode: 550, status: 'rejected' },
    // ...
  ]
}
```

## Three things that will trip you up

**1. Outbound port 25 is often blocked.**
Most home/residential ISPs block it outright to fight spam, and AWS blocks it by
default on EC2 (yours included) unless you file a request to lift the restriction.
If every check times out with a "port 25 may be blocked" error, that's almost
certainly what's happening — try running it from a different network, or test
locally on your own machine first before assuming the code is broken.

**2. Catch-all domains make per-address verification meaningless.**
Some companies (often on Microsoft 365 / Google Workspace) configure their mail
server to accept *every* address at their domain — real or not — specifically to
defeat tools like this. `checkCatchAll()` probes a nonsense address first to
detect this; if `catchAll: true` comes back, treat `bestGuess` as a guess, not
a confirmed result.

**3. Be a polite guest on someone else's mail server.**
The 1.5s delay between candidates (`delayMs`) is there on purpose — hammering a
company's mail server with rapid-fire RCPT TO requests for one person is far more
likely to get your IP rate-limited or greylisted than checking patiently. Don't
lower it just to go faster, and don't run this against a long list of people in
a tight loop — one person at a time, as you actually need them, is the right
usage pattern for a job search tool like yours.

## Files

| File | Purpose |
|---|---|
| `patterns.js` | Pure function: name + domain → candidate addresses |
| `verifier.js` | DNS/MX lookup + raw SMTP probe + catch-all detection |
| `index.js` | Orchestrates the two, exports `findEmail()` |
| `example.js` | Minimal runnable example |
