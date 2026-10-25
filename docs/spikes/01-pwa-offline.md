# Spike 01 — Offline on the real shop devices

**Card:** SPIKE-1 (04, v1.9) · **Tested:** 25 Oct 2026, on the demo, version `243fe32`
**Status:** boxes 1, 2, 3 and 5 are answered here. Box 4, the update prompt, is checked on the deploy of the pull request that brings this report; the card-tick pull request adds its result below.

Two words used below:
- **Service worker:** a small script the browser keeps running for a website. It saves the app's files on the device and answers from them when there is no internet (03 §7.7, `frontend/src/sw.ts`).
- **Persistent storage:** the browser's promise not to delete a website's saved data by itself, for example when the disk runs low (03 §6.7).

## The question

Does the static app install, open with no internet and keep its data on the shop's own laptop and phone? (ADR-0016, ADR-0019)

## The answer

**Yes, on both devices tested.** Installed from Chrome, the app opens in airplane mode, its saved rows survive closing the browser and restarting the device, and Chrome grants persistent storage.

## How it was tested

- From the demo address, <https://mabatinipumba-demo.onrender.com>, version `243fe32` (pull request #87). A throwaway `/spike/` page saved rows in IndexedDB through Dexie, asked for persistent storage, and showed the browser's facts. It was removed again in the pull request that brings this report.
- On each device: open `/spike/`; install the app; save two rows; ask for persistent storage; turn on airplane mode with Wi-Fi off, open the installed app, then `/spike/?test=1` in Chrome; close the app and the browser, restart the device, still offline, and open `/spike/` again.
- Before that merge, the same checks in Chrome on the laptop, against the image running on `localhost`, including the update prompt twice.

## The devices

The shop's devices change over time (OWN-2), so these are the ones in use on 25 Oct 2026: Jack's phone and laptop, both used in the shop.

| | Phone | Laptop |
|---|---|---|
| Device | Samsung Galaxy S21 (SM-G991N) | Lenovo 20S1SCAS01 |
| System | Android 15 | Windows 11 (Chrome reports it as "Windows 15.0.0") |
| Browser | Google Chrome 156.0.8078.47 | Google Chrome 156.0.8078.48 |

## Results

| Done when | Phone | Laptop |
|---|---|---|
| It installs as an app and opens in airplane mode | ✓ | ✓ |
| A Dexie row survives closing the browser and restarting the device | ✓ two rows | ✓ two rows |
| Persistent storage is granted, or the reason it isn't is written down | ✓ granted | ✓ granted |
| A new deploy shows an update prompt and switches | after this report's deploy | after this report's deploy |

- Chrome allowed about 10 GB of storage on both devices (10,242.3 MB); the app used 2.3 MB.
- An address with a query string, `/spike/?test=1`, also opened offline on both.

## What we learned

**Installing on Android**
- Chrome's menu starts with a row of small icons. The download arrow there saves the page to read later; it does not install. Installing is in the list below it: ⋮ → **Add to home screen** → **Install**.
- Chrome turns the site into a small Android app through Google's servers. Samsung put it in the app list, not on the home screen.
- On the laptop, the install icon sits at the right end of the address bar.
- Each web address is its own app: the app installed from `localhost` and the one from the demo are two apps, both named MPC.

**Persistent storage: test it on the real address**
- On `localhost`, Chrome said no, even with the app installed and the page bookmarked.
- On the demo address, with the app installed, it said yes on both devices.
- Chrome shows no prompt; it decides by itself, from signals such as an install. So 03 §6.7 holds: install the app on every shop device, and its storage becomes persistent.

**The first visit**
- On the very first visit, the page loads before the service worker takes charge of it. One reload puts the page under its control. The first visit has to be online anyway.

**Other browsers**
- The demo also opened in Edge and in Samsung Internet. Both use Chrome's engine, but only Chrome was tested offline.

**Typing the address**
- A misspelled address reached another person's suspended site on Render. Shop devices should open the app from its icon, not from a typed address.

## Notes for later cards

- **SYNC-13, updates:** the browser looks for a new version only when a page loads; it sets no timer. A counter that keeps the app open all day sees a deploy only after a reload, so SYNC-13 should check regularly (`registration.update()`). A waiting version also takes over, with no bar, when every window of the app is closed.
- **03 §6.8, after a switch:** an old tab is then served by the new service worker, which has deleted the old version's code. A tab that still needs code it never loaded fails until it reloads. Today every page loads its code at once.
- **Offline addresses:** the cache knows `/spike/`, not `/spike` without the final slash, nor unknown paths; those show Chrome's offline page. The links Next.js makes always end in a slash.
- **Big files:** Serwist leaves out any file over 2 MB, with only a warning in the build log. The largest file today is about 230 KB; a check in the build could catch it later.
- **Design-system card:** Tailwind 4 gives buttons no hand-shaped pointer, so on a laptop they look as if they can't be clicked.
- **The spike's data:** the `mpc-spike` database stays on the two test devices. To remove it, open Chrome's site settings for the demo address and delete its data.

## Open questions

- **iPhones.** Some workers have iPhones. The plan keeps iPhones to the owner's office screens, online (03 §7.3): on an iPhone every browser uses Safari's engine, Safari may delete a site's data after some days without use, installing is hidden in the Share menu, and Background Sync is missing. Workers clock in on the shop's own counter devices. Jack decides whether workers' own iPhones are needed; if they are, they need a test of their own.
- **A second laptop** was not tested.

## The setup that stays

- The manifest, `frontend/src/app/manifest.ts`, and placeholder icons drawn by `frontend/scripts/make-icons.mjs`, until the design system.
- The service worker, `frontend/src/sw.ts`, built after `next build` by `serwist build` (`frontend/serwist.config.mjs`), with no Next.js bundler plugin. This is the build 03 §7.7 said SPIKE-1 would prove.
- The update bar, `frontend/src/components/update-prompt.tsx`, and its logic, `frontend/src/offline/service-worker.ts`.
- The version on the home page, `frontend/src/lib/version.ts`.
