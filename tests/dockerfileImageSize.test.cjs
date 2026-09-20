'use strict';

// The runtime image must not inherit the package-manager/build toolchain used
// to assemble the release bundle. Keeping that toolchain in the final image
// makes every Wekan rebuild unnecessarily large and leaves old layers to pile
// up on the VPS.

const assert = require('assert');
const fs = require('fs');
const path = require('path');

const dockerfile = fs.readFileSync(path.join(__dirname, '..', 'Dockerfile'), 'utf8');

function test(name, fn) {
  try {
    fn();
    console.log(`  ok - ${name}`);
  } catch (error) {
    console.error(`  not ok - ${name}`);
    throw error;
  }
}

test('uses a separate minimal runtime stage after the build stage', () => {
  assert.match(dockerfile, /^FROM debian:trixie AS builder$/m);
  assert.match(dockerfile, /^FROM debian:trixie AS runtime$/m);
  assert.ok(dockerfile.indexOf('FROM debian:trixie AS runtime') > dockerfile.indexOf('FROM debian:trixie AS builder'));
});

test('copies only the prepared runtime into the final image', () => {
  const runtime = dockerfile.slice(dockerfile.indexOf('FROM debian:trixie AS runtime'));
  assert.match(runtime, /COPY --from=builder \/build \/build/);
  assert.match(runtime, /COPY --from=builder \/usr\/local\/bin\/node \/usr\/local\/bin\/node/);
  assert.doesNotMatch(runtime, /apt-get install[^\n]*BUILD_DEPS/);
  assert.doesNotMatch(runtime, /ENV BUILD_DEPS/);
});
