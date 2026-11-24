// Turn court file numbers in question text into links for the reviewer.
// Supreme Court case pages can be linked directly. The Federal Court and Tax Court file searches
// load a file only from a number typed into the page, so those numbers open the search page and
// copy the number to the clipboard for pasting.

// "#tab02" opens the search with the "Search by court number" tab selected
const FC_SEARCH = "https://www.fct-cf.ca/en/court-files-and-decisions/court-files#tab02";

// Working copies of the records (PDFs in a shared folder; see scripts/export_review_records.py).
// The folder link and the list of files come from the gitignored question data, never this file.
let RECORDS = {folder: null, have: new Set()};
export function useRecords(folder, files = []) {
  RECORDS = {folder: folder || null, have: new Set(files)};
}
const TCC_SEARCH = "https://www.tcc-cci.ca/en/pages/find-a-court-file";
const SCC_CASE = (n) => `https://www.scc-csc.ca/cases-dossiers/search-recherche/${n}/`;

const PATTERNS = [
  // Supreme Court: "case 38806" / "Case 38806" (the number is linked, not the word)
  {re: /\b([Cc]ase )(\d{5})\b/g, make: (m) => ({pre: m[1], text: m[2], href: SCC_CASE(m[2])})},
  // Tax Court: 2018-1523(IT), 2018-80(GST)APP, 2019-49(IT)I (copied whole; the search also
  // accepts the start of a number, which returns every file beginning with it).
  {
    re: /\b(\d{4}-\d{1,5})\([A-Z]{1,4}\)(?:APP|G|I)?(?![A-Za-z])/g,
    make: (m) => ({text: m[0], href: TCC_SEARCH, copy: m[0]})
  },
  // Federal Court and Federal Court of Appeal: T-501-18, A-336-24, IMM-123-25, and 19-A-40
  {
    re: /\b(?:(?:T|A|IMM)-\d{1,5}-\d{2}|\d{2}-A-\d{1,4})\b/g,
    make: (m) => ({text: m[0], href: FC_SEARCH, copy: m[0]})
  }
];

function link({text, href, copy}) {
  const a = document.createElement("a");
  a.target = "_blank";
  a.rel = "noopener";
  a.textContent = text;
  a.className = "filelink";
  if (copy && RECORDS.folder && RECORDS.have.has(copy)) {
    a.href = RECORDS.folder;
    a.title = `Opens the shared folder of record copies; the file is named "${copy}"`;
    return a;
  }
  a.href = href;
  if (copy) {
    a.title = `Opens the court's file search; ${copy} is copied for pasting`;
    a.addEventListener("click", () => navigator.clipboard?.writeText(copy).catch(() => {}));
  } else {
    a.title = "Opens the case page";
  }
  return a;
}

/** Text with file numbers linked, as an array of nodes. */
export function linkify(text) {
  const hits = [];
  for (const p of PATTERNS) {
    for (const m of text.matchAll(p.re)) {
      const start = m.index, end = m.index + m[0].length;
      if (hits.some((h) => start < h.end && end > h.start)) continue;
      hits.push({start, end, ...p.make(m)});
    }
  }
  hits.sort((a, b) => a.start - b.start);
  const out = [];
  let at = 0;
  for (const h of hits) {
    if (h.start > at) out.push(document.createTextNode(text.slice(at, h.start)));
    if (h.pre) out.push(document.createTextNode(h.pre));
    out.push(link(h));
    at = h.end;
  }
  if (at < text.length) out.push(document.createTextNode(text.slice(at)));
  return out;
}

/** Question text: blank line = paragraph, lines starting "- " = list; a short lead-in such as
 * "Question 1." or "Example:" is bold. */
export function richText(text, className = "q-text") {
  const frag = document.createElement("div");
  frag.className = className;
  for (const block of text.split(/\n\n+/)) {
    const lines = block.split("\n");
    if (lines.every((l) => l.startsWith("- "))) {
      const ul = document.createElement("ul");
      for (const l of lines) {
        const li = document.createElement("li");
        li.append(...linkify(l.slice(2)));
        ul.append(li);
      }
      frag.append(ul);
    } else {
      const p = document.createElement("p");
      const m = block.match(/^((?:Question \d+|Example|Our reading|What we meant by [^.]{3,40})[.:])\s(.*)$/s);
      if (m) {
        const b = document.createElement("strong");
        b.textContent = m[1];
        p.append(b, " ", ...linkify(m[2]));
      } else p.append(...linkify(block));
      frag.append(p);
    }
  }
  return frag;
}
