# Wikipedia Action API fixtures

These six JSON files are unmodified responses captured on 2026-11-11 using
`tools/capture_on_this_day.py`. The manifest records the exact endpoint, title,
revision, fetch timestamp (UTC for provenance only), and SHA-256 of each response.
Normal unit tests read these local files and do not contact Wikipedia.

Wikipedia article text remains subject to Wikipedia's attribution and licensing
terms (CC BY-SA). The manifest's revision and source endpoint identify the
original contributors and article history; the probe records permanent revision
URLs. Do not describe the historical content as generated or independently
fact-checked by Awqati.

Expected counts, in order: events, births, deaths, observances. Holiday counts
include readable grouping parents as well as all nested list items; the nested
context and its links are preserved separately on each child.

- ar_0, 11 November, revision 76824402: 17, 27, 18, 6.
- ar_1, 15 March, revision 77147368: 21, 33, 18, 7.
- ar_2, 1 January, revision 76949815: 79, 75, 30, 7.
- en_3, November 11, revision 1384999258: 75, 233, 115, 27.
- ar_4, 29 February, revision 77148069: 9, 23, 8, 2.
- en_5, February 29, revision 1382000164: 43, 133, 64, 5.

The independent streaming inventory in `tests/test_on_this_day.py` checks every
readable list item and every distinct safe original anchor/label pair, in
addition to fixed counts, link spans, and synthetic edge cases.
