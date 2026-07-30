import {assertSupportedNodeVersion} from './node-version.js';

// Keep the canonical gate on the same compatibility contract as the interactive TUI bootstrap.
assertSupportedNodeVersion(process.versions.node);
