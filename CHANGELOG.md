# Changelog

## [0.2.0](https://github.com/jack-bita/mpc/compare/v0.1.0...v0.2.0) (2026-11-07)


### Features

* **control:** audit trail, with an edit history the database writes itself ([#114](https://github.com/jack-bita/mpc/issues/114)) ([b67ee9d](https://github.com/jack-bita/mpc/commit/b67ee9de5309c34cb3ef98d50a1137106544c89c))
* **control:** flags, one review queue for every difference ([#112](https://github.com/jack-bita/mpc/issues/112)) ([7472693](https://github.com/jack-bita/mpc/commit/74726935a64fc6ec897271a7460f80493ce59526))
* **control:** the two books name the device ([#141](https://github.com/jack-bita/mpc/issues/141)) ([7c4dd56](https://github.com/jack-bita/mpc/commit/7c4dd568e5429da17f36fd2b47e29ee44df4c617))
* **core:** api conventions, first used by a shop's sides ([#108](https://github.com/jack-bita/mpc/issues/108)) ([f04f100](https://github.com/jack-bita/mpc/commit/f04f1003e1824cecaf1ec5e347e41de5ce3c22cd))
* **core:** append-only tables, enforced by PostgreSQL ([#102](https://github.com/jack-bita/mpc/issues/102)) ([61dc373](https://github.com/jack-bita/mpc/commit/61dc3739ae51bc7c5b5bcef5349c6a7cda201ff9))
* **core:** dated settings, read for a day and a side ([#104](https://github.com/jack-bita/mpc/issues/104)) ([e1b219b](https://github.com/jack-bita/mpc/commit/e1b219b6ffcc8250faea24702b88aa48ebb98142))
* **core:** exact money and quantities ([#106](https://github.com/jack-bita/mpc/issues/106)) ([0cab51e](https://github.com/jack-bita/mpc/commit/0cab51e77f1a3ccb56b7b1e4e9fc8f0443732a69))
* **core:** office routes check permissions per side ([#119](https://github.com/jack-bita/mpc/issues/119)) ([4e59304](https://github.com/jack-bita/mpc/commit/4e5930467c3a426a9d6868dbc8f09cb298d2123c))
* **core:** tenancy guard that fails closed ([#96](https://github.com/jack-bita/mpc/issues/96)) ([97b96da](https://github.com/jack-bita/mpc/commit/97b96dac21cd7baf1890f66e21b7041e97e4260a))
* **frontend:** a test slip for the receipt printer ([#93](https://github.com/jack-bita/mpc/issues/93)) ([cc6b933](https://github.com/jack-bita/mpc/commit/cc6b933cf52dbece1239c23ea7b4b8c85b813917))
* **frontend:** a typed api client, with errors in the shop's words ([#154](https://github.com/jack-bita/mpc/issues/154)) ([27cb90e](https://github.com/jack-bita/mpc/commit/27cb90e96f9a9a3a49fb584aedc9b142fa6ac14b))
* **frontend:** log in by pin at a shared laptop, with quick switch and an idle lock ([#158](https://github.com/jack-bita/mpc/issues/158)) ([ca1678d](https://github.com/jack-bita/mpc/commit/ca1678d58f5a3b8b45b16fb64da0a21927722906))
* **frontend:** register a device, and block it from the manager's phone ([#156](https://github.com/jack-bita/mpc/issues/156)) ([e8a639c](https://github.com/jack-bita/mpc/commit/e8a639c50ce4aabded9430dc0f8288c961ed05b3))
* **frontend:** screens build from the shop's own pieces ([#149](https://github.com/jack-bita/mpc/issues/149)) ([3fd5a70](https://github.com/jack-bita/mpc/commit/3fd5a709e010674529b7eeb9a4eb67c154bd597c))
* **frontend:** swahili and english, exact numbers, and the app's frame ([#152](https://github.com/jack-bita/mpc/issues/152)) ([5788ace](https://github.com/jack-bita/mpc/commit/5788ace9eaaa70c3b68075b124288a7bc09f756a))
* **frontend:** the app installs and opens offline ([#87](https://github.com/jack-bita/mpc/issues/87)) ([243fe32](https://github.com/jack-bita/mpc/commit/243fe32de2d1100b3a379e15d2a04637cd34c7b0))
* **frontend:** the app wears the shop's look ([#147](https://github.com/jack-bita/mpc/issues/147)) ([7ff84f0](https://github.com/jack-bita/mpc/commit/7ff84f0040e34d0e3cd67ec25fecd341e5a36d7c))
* **people:** a new device pairs with a shop, and can be blocked ([#121](https://github.com/jack-bita/mpc/issues/121)) ([fbe5733](https://github.com/jack-bita/mpc/commit/fbe57333224b38600c029a111818dd93e2739e93))
* **people:** a paired device logs in with its key ([#126](https://github.com/jack-bita/mpc/issues/126)) ([81938e7](https://github.com/jack-bita/mpc/commit/81938e70223c80804a302ce581da4cb81a6d10db))
* **people:** custom user model, the first migration ([#80](https://github.com/jack-bita/mpc/issues/80)) ([eea2b52](https://github.com/jack-bita/mpc/commit/eea2b520c6da1d10800a7513bcb8f1d0fc9d7450))
* **people:** managers confirm, list, rename and block devices ([#129](https://github.com/jack-bita/mpc/issues/129)) ([c826b24](https://github.com/jack-bita/mpc/commit/c826b2403f282301f20fec718540892d8b73ddc9))
* **people:** passwords for the owner and managers ([#132](https://github.com/jack-bita/mpc/issues/132)) ([b288306](https://github.com/jack-bita/mpc/commit/b2883061658449eff1323071d1bc5f954d896522))
* **people:** roles and permissions per side ([#116](https://github.com/jack-bita/mpc/issues/116)) ([43122bc](https://github.com/jack-bita/mpc/commit/43122bce12438f5c55f8f9841b32dd554feac67f))
* **people:** staff members and their PINs ([#98](https://github.com/jack-bita/mpc/issues/98)) ([fda3750](https://github.com/jack-bita/mpc/commit/fda375088e5dec72fb25203daf22440b7c733dc3))
* **people:** the owner sets a temporary password face to face ([#136](https://github.com/jack-bita/mpc/issues/136)) ([500d791](https://github.com/jack-bita/mpc/commit/500d7914ff3f9b63c4c8ab0b926c03ff4ca0348d))
* **people:** workers log in by PIN on a shop's device ([#138](https://github.com/jack-bita/mpc/issues/138)) ([6b4bb15](https://github.com/jack-bita/mpc/commit/6b4bb15d6471281dcc1882b573f610fafc37401e))
* **shops:** sides, stock locations and cash drawers ([#100](https://github.com/jack-bita/mpc/issues/100)) ([7810be9](https://github.com/jack-bita/mpc/commit/7810be9aab3a7518f9a80a434a9c58972844a0ee))
* **shops:** the shop, with its rules and its admin page ([#94](https://github.com/jack-bita/mpc/issues/94)) ([e953b62](https://github.com/jack-bita/mpc/commit/e953b6273f0281145b6bdc33b61c5d700b18b558))

## 0.1.0 (2026-10-22)


### Features

* **core:** abstract base models ([#77](https://github.com/jack-bita/mpc/issues/77)) ([e9651d2](https://github.com/jack-bita/mpc/commit/e9651d22217fe05703ee079c022c9e576856c5d9))
