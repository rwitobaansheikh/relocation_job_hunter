'use strict';

const { generatePatterns } = require('./patterns');
const { checkCatchAll, verifyEmail } = require('./verifier');

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Generates likely email addresses for a person at a company domain, then
 * checks each candidate against the company's real mail server over SMTP.
 *
 * @param {string} firstName
 * @param {string} lastName
 * @param {string} domain          e.g. "hertz.com"
 * @param {object} [options]
 * @param {string} [options.heloDomain]  Domain to identify yourself as. Use one you
 *                                       actually control — some mail servers check
 *                                       MAIL FROM has valid MX/SPF before answering honestly.
 * @param {string} [options.mailFrom]    Defaults to verify@<heloDomain>.
 * @param {number} [options.timeoutMs]   Per-SMTP-step timeout. Default 10000.
 * @param {number} [options.delayMs]     Pause between candidate checks, to stay
 *                                       polite to the target's mail server. Default 1500.
 */
async function findEmail(firstName, lastName, domain, options = {}) {
  const delayMs = options.delayMs ?? 1500;
  const patterns = generatePatterns(firstName, lastName, domain);

  const { mxHost, isCatchAll } = await checkCatchAll(domain, options);

  const candidates = [];
  for (const { pattern, email } of patterns) {
    try {
      const result = await verifyEmail(email, mxHost, options);
      candidates.push({ ...result, pattern });
    } catch (err) {
      candidates.push({ email, pattern, status: 'error', error: err.message });
    }
    await sleep(delayMs);
  }

  if (isCatchAll) {
    return {
      domain,
      mxHost,
      catchAll: true,
      note:
        'This domain accepts mail for any address, so SMTP cannot confirm which pattern ' +
        'is real. bestGuess is just the statistically most common convention — confirm it ' +
        'another way (company site, LinkedIn, etc.) before relying on it.',
      bestGuess: patterns[0].email,
      candidates,
    };
  }

  const accepted = candidates.filter((c) => c.status === 'accepted');
  return {
    domain,
    mxHost,
    catchAll: false,
    bestGuess: accepted[0]?.email || null,
    candidates,
  };
}

module.exports = { findEmail, generatePatterns };
