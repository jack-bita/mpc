# Media

Pictures the README and the write-ups show. Each one is made from the live demo, with its fake shop and people only.

## offline-clock-in.gif

The README's GIF (FOLIO-2): Asha clocks in with no internet, the laptop keeps the record, and it is sent by itself once the internet is back. Five pictures, 720 × 696, about 14 seconds a loop, 83 KB.

How it was made, on 15 November 2026:

1. A Playwright script opened the live demo in a fresh Chromium: a 720 × 640 window, Swahili (`sw-TZ`), Tanzania's clock. It took the steps of `frontend/e2e/one-tap-demo.spec.ts`: *Jaribu demo*, Asha's tile, her PIN, *Mahudhurio*, the network off (`setOffline`), *Ingia kazini*, the network back, then a wait for *Kumbukumbu zote zimetumwa*.
2. It took a screenshot at five moments, and put each on a page with a caption strip under it: the app's green (`#15803d`), Source Sans 3 from `frontend/src/fonts/`.
3. A Pillow script joined the five pictures into the GIF: 2.2 s each for the first three, then 3.2 s and 3.8 s, looping. Each picture has its own 256 colours, with no dithering. One set shared by all five turned the white page faint grey.

The scripts were kept outside the repo, as this was one job. Make the GIF again when a screen in it changes, for example when ATT-3 adds the photo to the clock-in.
