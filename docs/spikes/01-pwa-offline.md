# Spike 01 — Offline on the real shop devices

**Card:** SPIKE-1 (04) · **Tested:** 25 Oct 2026, on the demo, versions `243fe32` and `9c836a7`
**Status:** all five *Done when* boxes are answered here. Box 4, the update prompt, was checked on the deploy of the pull request that brought this report (#88).

Words used below (the first three are also in the 03 glossary, §19):
- **Service worker:** a small script the browser keeps for a website and starts when it is needed. It saves the app's files on the device and answers from them when there is no internet (03 §7.7, `frontend/src/sw.ts`).
- **IndexedDB:** the database built into the browser. Each website has its own, on the device.
- **Dexie:** a library that makes IndexedDB easy to use. The app's offline data lives there (ADR-0019).
- **Persistent storage:** the browser's promise not to delete a website's saved data by itself, for example when the disk runs low (03 §6.7).

## The question

Does the static app install, open with no internet and keep its data on the shop's own laptop and phone? (ADR-0016, ADR-0019)

## The answer

**Yes, on both devices tested.** Installed from Chrome, the app opens in airplane mode, and its saved rows survive closing the browser and restarting the device. On the demo address, Chrome granted persistent storage. A new deploy showed the update bar, and a tap switched to the new version.

## How it was tested

The tests ran from the demo address, <https://mabatinipumba-demo.onrender.com>, on version `243fe32` (pull request #87). A throwaway `/spike/` page saved rows in IndexedDB through Dexie, asked for persistent storage, and showed the browser's facts. It was removed again in the pull request that brings this report.

On each device:
1. Open `/spike/`.
2. Install the app.
3. Save two rows, and ask for persistent storage.
4. Turn on airplane mode, with Wi-Fi off.
5. Open the installed app, then `/spike/?test=1` in Chrome.
6. Close the app and the browser, and restart the device, still offline.
7. Open `/spike/` again: the two rows must be there.

Before that, the laptop ran the same checks in Chrome against the image on `localhost`. The update prompt was tested there twice.

## The devices

The shop's devices change over time (OWN-2). These are the ones in use on 25 Oct 2026: Jack's phone and laptop, both used in the shop.

| | Phone | Laptop |
|---|---|---|
| Device | Samsung Galaxy S21, model SM-G991N | Lenovo, model 20S1SCAS01 (as Windows reports it) |
| System | Android 15 | Windows 11 |
| Browser | Google Chrome 156.0.8078.47 | Google Chrome 156.0.8078.48 |

Chrome reports Windows 11 as "Windows 15.0.0": in its numbering, 13 and up means Windows 11.

## Results

| Done when | Phone | Laptop |
|---|---|---|
| It installs as an app and opens in airplane mode | ✓ | ✓ |
| A Dexie row survives closing the browser and restarting the device | ✓ two rows | ✓ two rows |
| Persistent storage is granted, or the reason it isn't is written down | ✓ granted | ✓ granted |
| A new deploy shows an update prompt and switches | ✓ `243fe32` → `9c836a7` | ✓ `243fe32` → `9c836a7` |

- An address with a query string, `/spike/?test=1`, also opened offline on both.
- Storage: the page showed "2.3 / 10,242.3 MB" on both devices. That is the 2.3 MB the app used plus exactly 10,240 MB (10 GB). The same figure on two different devices means Chrome reports a fixed allowance, not each device's real free space. So we know at least 10 GB was free; the real limit isn't shown. (The page counted 1,024 × 1,024 bytes as one MB.)

## The update (box 4)

Pull request #88 removed the `/spike/` page and brought this report. Its merge deployed version `9c836a7` to the demo. Then, on each device, with internet on:
1. Open the installed app. It showed the old version, *Toleo 243fe32*.
2. Within seconds, the bar *Toleo jipya liko tayari* appeared, with **Sasisha**.
3. Tap **Sasisha**. The page reloaded and showed *Toleo 9c836a7*.

Nothing reloaded by itself before the tap. The phone and the laptop passed alike.

## What we learned

**Installing on Android**
- Chrome's menu starts with a row of small icons. The download arrow there saves the page to read later; it does not install.
- Installing is in the list below it: ⋮ → **Add to home screen** → **Install**.
- Chrome turns the site into a small Android app through Google's servers. Samsung put it in the app list, not on the home screen.
- On the laptop, the install icon sits at the right end of the address bar.
- Each web address is its own app. The app installed from `localhost` and the one from the demo are two apps, both named MPC.

**Persistent storage: test it on the real address**
- On `localhost`, Chrome said no, even with the app installed and the page bookmarked.
- On the demo address, the page asked, the app was installed, and Chrome said yes on both devices.
- Chrome shows no prompt; it decides by itself, from signals such as an install. So 03 §6.7 holds: the app asks for persistent storage (SYNC-12), and is installed on every shop device.
- For SYNC-12: on `localhost`, the answer is no, so its "storage isn't persistent" warning will show in development and in the end-to-end tests (UI-6).

**The first visit**
- On the very first visit, the spike page showed "Service worker: Hapana", and "Ndiyo" after a reload.
- The worker does take charge of the open page by itself once it has saved the files (`clientsClaim` in `sw.ts`). The page had read the fact as it loaded, before that moment, and never read it again.
- The first visit has to be online anyway: that is when the files are saved.

**Other browsers**
- The demo also opened in Edge and in Samsung Internet. Both use Chrome's engine, but only Chrome was tested offline. 03 §7.3 lists Edge as a shop browser, so Edge offline is still to test.

**Typing the address**
- A misspelled address reached another person's suspended site on Render. Shop devices should open the app from its icon, not from a typed address.

## Notes for later cards

- **SYNC-13, updates:**
  - The browser looks for a new version only when a page loads; it sets no timer. Moving between pages inside the app doesn't count as a page load.
  - So a counter that keeps the app open all day sees a deploy only after a reload. SYNC-13 should check regularly (`registration.update()`).
  - A waiting version also takes over, with no bar, when every window of the app is closed.
- **03 §6.8, after a switch:** an old tab is then served by the new service worker, which has deleted the old version's code. A tab that still needs code it never loaded fails until it reloads. Today the app has one page, so nothing is left to load later.
- **Offline addresses:** the cache knew `/spike/`, but not `/spike` without the final slash, nor unknown paths; those showed Chrome's offline page. The links Next.js makes always end in a slash (`trailingSlash: true` in `frontend/next.config.ts`).
- **Big files:** Serwist leaves out any file over 2 MB, with only a warning in the build log. The largest file today is about 230 KB; a check in the build could catch it later.
- **The design-system card** (still to be written, before UI-1): Tailwind 4 gives buttons no hand-shaped pointer, so on a laptop they look as if they can't be clicked.
- **The spike's data:** the `mpc-spike` database stays on the two test devices, and the laptop has a second copy from the `localhost` tests. To remove one, open Chrome's site settings for that address and delete its data. For the demo address, that also deletes the app's saved files, so the app needs one online visit afterwards.

## Open questions

- **iPhones.** Some workers have iPhones. The plan keeps iPhones to the owner's office screens, online (03 §7.3).
  - On an iPhone, every browser uses Safari's engine.
  - Safari may delete a site's data after some days without use.
  - Installing is hidden in the Share menu, and Background Sync is missing.
  - Workers clock in on the shop's own counter devices. Jack decides whether workers' own iPhones are needed; if they are, they need a test of their own.
- **A second laptop** wasn't tested; that was Jack's choice. The risk is low if it runs the same Chrome on Windows. It is tested when it is paired and installed as a shop device, before go-live (04, the LIVE checklist).
- **One counter device per side** (OWN-2) stays open: which device serves the Drugs side and which the Foods side is settled when the devices are paired.
- **Edge offline**, as above.

## The setup that stays

- The manifest, `frontend/src/app/manifest.ts`, and placeholder icons drawn by `frontend/scripts/make-icons.mjs`, until the design system.
- The service worker, `frontend/src/sw.ts`, built after `next build` by `serwist build` (`frontend/serwist.config.mjs`), with no Next.js bundler plugin. This is the build 03 §7.7 said SPIKE-1 would prove.
- The update bar, `frontend/src/components/update-prompt.tsx`, and its logic, `frontend/src/offline/service-worker.ts`.
- The version on the home page, `frontend/src/lib/version.ts`.
