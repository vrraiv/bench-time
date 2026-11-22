-- Replies to the "Questions for review" page (D1 database docket-watch-replies, binding REPLIES).
-- Apply with: npx wrangler d1 execute docket-watch-replies --remote --file worker/schema.sql
CREATE TABLE IF NOT EXISTS replies (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  issue TEXT NOT NULL,          -- question number, e.g. FS-3
  author TEXT NOT NULL,         -- email from the Cloudflare Access login
  status TEXT NOT NULL,         -- answer | partial | dont-know | discuss | comment
  body TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX IF NOT EXISTS replies_issue ON replies (issue);
