// Single source of truth for the Sky Score API Gateway base URL.
//
// Loaded as a classic <script src=> before any inline JS that uses API_BASE.
// Sets window.API_BASE so inline scripts can pull it via:
//   const API_BASE = window.API_BASE;
//
// Tests (tests/api.test.mjs) duplicate the value because they run in Node
// where window does not exist; the /preflight skill's drift check (step 4d,
// added Wave 12.8) grep-asserts that all references resolve to one host.
//
// I-N5 offensive half (Wave 12.9). Pairs with the defensive drift check.
window.API_BASE = 'https://2gjfdzg20c.execute-api.eu-west-2.amazonaws.com/prod';
