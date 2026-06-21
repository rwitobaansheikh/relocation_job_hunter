'use strict';

/**
 * Generates candidate email addresses for a person at a given domain,
 * based on common corporate email naming conventions.
 *
 * Patterns are ordered roughly by how common they are across companies
 * in general (first.last is the most widely used convention, followed
 * by flast, firstlast, etc.) — but every company is different, which is
 * exactly why we verify each one against the real mail server afterwards.
 */
function generatePatterns(firstName, lastName, domain) {
  if (!firstName || !lastName || !domain) {
    throw new Error('firstName, lastName, and domain are all required');
  }

  const first = normalize(firstName);
  const last = normalize(lastName);
  const f = first[0];
  const l = last[0];
  const cleanDomain = domain
    .trim()
    .toLowerCase()
    .replace(/^https?:\/\//, '')
    .replace(/\/.*$/, '')
    .replace(/^www\./, '');

  const patterns = [
    { pattern: 'first.last', email: `${first}.${last}@${cleanDomain}` },
    { pattern: 'flast', email: `${f}${last}@${cleanDomain}` },
    { pattern: 'firstlast', email: `${first}${last}@${cleanDomain}` },
    { pattern: 'first', email: `${first}@${cleanDomain}` },
    { pattern: 'firstl', email: `${first}${l}@${cleanDomain}` },
    { pattern: 'first_last', email: `${first}_${last}@${cleanDomain}` },
    { pattern: 'f.last', email: `${f}.${last}@${cleanDomain}` },
    { pattern: 'last.first', email: `${last}.${first}@${cleanDomain}` },
    { pattern: 'lastfirst', email: `${last}${first}@${cleanDomain}` },
    { pattern: 'last', email: `${last}@${cleanDomain}` },
    { pattern: 'lastf', email: `${last}${f}@${cleanDomain}` },
    { pattern: 'fl', email: `${f}${l}@${cleanDomain}` },
  ];

  // De-duplicate — short names can collide (e.g. "Al Li" produces overlapping patterns)
  const seen = new Set();
  return patterns.filter((p) => {
    if (seen.has(p.email)) return false;
    seen.add(p.email);
    return true;
  });
}

function normalize(name) {
  return name
    .trim()
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '') // strip accents (e.g. é -> e)
    .replace(/[^a-z0-9]/g, ''); // strip hyphens, apostrophes, spaces
}

module.exports = { generatePatterns };
