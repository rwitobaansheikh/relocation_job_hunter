'use strict';

const { findEmail } = require('./index');

async function main() {
  const result = await findEmail('Jane', 'Smith', 'example.com', {
    // Use a domain you actually control here, not a placeholder —
    // some mail servers won't answer honestly otherwise.
    heloDomain: 'rwitobaansheikh.com',
    mailFrom: 'verify@rwitobaansheikh.com',
  });

  console.log(JSON.stringify(result, null, 2));
}

main().catch((err) => {
  console.error('Error:', err.message);
  process.exitCode = 1;
});
