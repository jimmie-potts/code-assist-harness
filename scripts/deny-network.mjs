/**
 * Disable Node.js network clients during the repository validation gate.
 *
 * This preload is defense in depth for the prepared, model-free test environment. It blocks the
 * common Node networking surfaces used by application code and dependencies; it is not an
 * operating-system sandbox and cannot constrain separately launched native executables.
 */

import dgram from "node:dgram";
import dns from "node:dns";
import dnsPromises from "node:dns/promises";
import http from "node:http";
import http2 from "node:http2";
import https from "node:https";
import {syncBuiltinESMExports} from "node:module";
import net from "node:net";
import tls from "node:tls";

const MESSAGE = "Network access is disabled by ./scripts/check";
const originalFetch = globalThis.fetch;
const DNS_METHODS = [
  "lookupService",
  "resolve",
  "resolve4",
  "resolve6",
  "resolveAny",
  "resolveCaa",
  "resolveCname",
  "resolveMx",
  "resolveNaptr",
  "resolveNs",
  "resolvePtr",
  "resolveSoa",
  "resolveSrv",
  "resolveTxt",
  "reverse",
];

function denyNetwork() {
  throw new Error(MESSAGE);
}

function localLookupResult(hostname, options) {
  const literalFamily = net.isIP(hostname);
  const requestedFamily = typeof options === "number" ? options : options?.family;
  const family = literalFamily || (requestedFamily === 6 ? 6 : 4);
  const address = literalFamily ? hostname : family === 6 ? "::1" : "127.0.0.1";
  return {address, family};
}

function isLocalLookup(hostname) {
  return (
    typeof hostname === "string" &&
    (hostname === "localhost" || hostname.endsWith(".localhost") || net.isIP(hostname) !== 0)
  );
}

function guardedDnsLookup(hostname, options, callback) {
  if (!isLocalLookup(hostname)) {
    return denyNetwork();
  }

  const normalizedOptions = typeof options === "function" ? undefined : options;
  const done = typeof options === "function" ? options : callback;
  const result = localLookupResult(hostname, normalizedOptions);
  process.nextTick(() => {
    if (normalizedOptions?.all) {
      done(null, [result]);
    } else {
      done(null, result.address, result.family);
    }
  });
}

function guardedDnsPromiseLookup(hostname, options) {
  if (!isLocalLookup(hostname)) {
    return Promise.reject(new Error(MESSAGE));
  }

  const result = localLookupResult(hostname, options);
  return Promise.resolve(options?.all ? [result] : result);
}

function guardedFetch(input, init) {
  const target = typeof input === "string" || input instanceof URL ? input : input?.url;
  const protocol = new URL(String(target), "file:///").protocol;
  if ((protocol === "data:" || protocol === "file:") && typeof originalFetch === "function") {
    return originalFetch(input, init);
  }
  return Promise.reject(new Error(MESSAGE));
}

function replaceMethods(target, methods) {
  for (const method of methods) {
    if (typeof target?.[method] === "function") {
      target[method] = denyNetwork;
    }
  }
}

replaceMethods(net, ["connect", "createConnection"]);
replaceMethods(net.Socket?.prototype, ["connect"]);
replaceMethods(tls, ["connect"]);
replaceMethods(http, ["get", "request"]);
replaceMethods(https, ["get", "request"]);
replaceMethods(http2, ["connect"]);
replaceMethods(dgram.Socket?.prototype, ["connect", "send"]);
replaceMethods(dns, DNS_METHODS);
replaceMethods(dns.promises, DNS_METHODS);
replaceMethods(dnsPromises, DNS_METHODS);
replaceMethods(dns.Resolver?.prototype, DNS_METHODS);
replaceMethods(dnsPromises.Resolver?.prototype, DNS_METHODS);
dns.lookup = guardedDnsLookup;
dns.promises.lookup = guardedDnsPromiseLookup;
dnsPromises.lookup = guardedDnsPromiseLookup;

// Built-in named exports are separate bindings until Node is asked to synchronize them with the
// patched default export. Without this step, `import {lookup} from "node:dns"` bypasses the guard.
syncBuiltinESMExports();

Object.defineProperty(globalThis, "fetch", {
  configurable: true,
  value: guardedFetch,
  writable: true,
});

Object.defineProperty(globalThis, "WebSocket", {
  configurable: true,
  value: class DeniedWebSocket {
    constructor() {
      denyNetwork();
    }
  },
  writable: true,
});
