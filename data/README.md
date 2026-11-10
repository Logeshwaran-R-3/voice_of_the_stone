# Data

## Raw (untouchable sources)
`raw/hultzsch/` holds three archive.org OCR dumps of South-Indian Inscriptions
Vol. II (Hultzsch 1891–1895, Venkayya 1913), all public domain ASI publications.
Never edit these files; every cleaned string cites its file + line span.

## MVP slice (`mvp/`)
- `corpus.json`: 8 hand-cleaned entries (SII Nos. 9, 10, 11, 12, 32, 40, 42, 43)
  with intro, translation paragraphs, and entity lists for retrieval bridging.
  OCR fixes are conservative (obvious misreads only); scan gaps are marked
  `[illegible in scan]` or `[name lost]`, never filled.
- `photos.json`: 8 Wikimedia Commons wall-inscription photos with author,
  license (CC BY 2.0 / BY-SA 3.0 / BY-SA 4.0), and URL. Hotlinked: the dev
  sandbox blocks binary download, so vendor these at deploy time on Render.
- `ta.json`: draft Tamil summaries, UNVERIFIED, pending native-speaker review.

## Known caveats
- Commons photos are not labeled by SII number, so photo↔text pairing is
  recorded as `unverified` everywhere it surfaces.
- Printed Tamil "Text" sections OCR as gibberish; transliteration ground truth
  needs Tamil-model re-OCR or an epigraphist (open item).
