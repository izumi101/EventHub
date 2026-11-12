# Changelog

## [1.1.0](https://github.com/izumi101/EventHub/compare/v1.0.0...v1.1.0) (2026-11-12)


### Features

* **api:** version the API under /api/v1 with a generated OpenAPI contract ([109a61c](https://github.com/izumi101/EventHub/commit/109a61c6d9306a5cab640442181cb97d30318b94))
* **db:** Kazakhstan demo data and SQL data-integrity checks ([2121fd3](https://github.com/izumi101/EventHub/commit/2121fd3add984b2f9c9346ad743e778094657bd5))
* **db:** least-privilege PostgreSQL roles ([b5faa75](https://github.com/izumi101/EventHub/commit/b5faa75eb879cb5986b894584050f369df87185f))
* **events:** hand-picked showcase events for live demos ([9b78bcf](https://github.com/izumi101/EventHub/commit/9b78bcfd06d115f122ad9dd076ecf70058132183))
* **flags:** feature flag client with safe defaults and server-side evaluation ([345e404](https://github.com/izumi101/EventHub/commit/345e404ec1ce3225416f654a5d2f9871759ede0e))
* **fpay-emulator:** Freedom Pay gateway emulator ([880c9f1](https://github.com/izumi101/EventHub/commit/880c9f145c07345d7e65a41e43fc16130d9cc36e))
* **fpay-emulator:** full test card details and one-tap fill ([a10bfea](https://github.com/izumi101/EventHub/commit/a10bfeac08641c5bcb3bb939ae44954d937c5857))
* **frontend:** feature flag service ([01a80e1](https://github.com/izumi101/EventHub/commit/01a80e184e179177703c7d8acd1ad8c62773e90d))
* **frontend:** pay by QR code and poll the payment status ([a49c395](https://github.com/izumi101/EventHub/commit/a49c3953b92b0917305ce3c5719637e62eda6af1))
* **frontend:** QR payment for group bookings ([3e8692c](https://github.com/izumi101/EventHub/commit/3e8692c9ae1014d35c4aa1ce141351ec76042982))
* **frontend:** tell a phone that paid by QR code where the ticket is ([2f1e1b8](https://github.com/izumi101/EventHub/commit/2f1e1b81b53e98f73e2ecb639acda12f1f942d38))
* **frontend:** type the API from the OpenAPI schema; call /api/v1 ([0c179a8](https://github.com/izumi101/EventHub/commit/0c179a8938f11f9d7330df1b5fb688b67507588b))
* **payments:** complete phase 1 with group booking payments ([119f1d3](https://github.com/izumi101/EventHub/commit/119f1d3fc48d31321ed5cc924e04e27cb1719603))
* **payments:** Freedom Pay checkout for KZT events in demo mode ([8b5fc7d](https://github.com/izumi101/EventHub/commit/8b5fc7dda16641579f46db6e5f17afd341672b8f))
* **payments:** freedom pay demo with qr, provider layer and database roles ([86c628e](https://github.com/izumi101/EventHub/commit/86c628e61335a288443b46817d3e670223bf391b))
* **payments:** pay group bookings of KZT events through Freedom Pay ([4861789](https://github.com/izumi101/EventHub/commit/48617896de61c7602dcb17b7979944cda8532c38))
* **payments:** payment ledger models ([978e7b6](https://github.com/izumi101/EventHub/commit/978e7b6ab7dd3b6964c7771021edb7f10d5dad81))
* **payments:** payment state machine ([d9a967d](https://github.com/izumi101/EventHub/commit/d9a967d54245ce5a8afdcd40f65b5a202905716a))
* **payments:** provider interface, registry and mock provider ([d1b9382](https://github.com/izumi101/EventHub/commit/d1b93827c1a7890ae94511f2ac3c87b324bb0fbc))
* **payments:** Stripe provider ([b3efd51](https://github.com/izumi101/EventHub/commit/b3efd517d782bc370c7755ac6756babc32b062ed))


### Bug Fixes

* **events:** re-check a hold under the lock before cancelling it ([cf281a7](https://github.com/izumi101/EventHub/commit/cf281a719f646df564fb5f98ec85e75d2846319c))
* **frontend:** drop a stale or corrupted cached user on startup ([62160cd](https://github.com/izumi101/EventHub/commit/62160cd360cbff7c9dd1a9c8af349a507c4e0860))
* **frontend:** show the seat price that is actually charged ([14bb0d6](https://github.com/izumi101/EventHub/commit/14bb0d60ed5eda907a5999fa1858104d7d2cf995))


### Code Refactoring

* fix lint findings; enforce the full ruff rule set in CI ([f74feee](https://github.com/izumi101/EventHub/commit/f74feee0638daf3f81a84ee45393e56ec2934e2a))
* **frontend:** fix lint findings ([d64790c](https://github.com/izumi101/EventHub/commit/d64790cf05000873de533fad45bfdf263a166fb7))


### Documentation

* add a handoff note for continuing the production roadmap ([3bf71cd](https://github.com/izumi101/EventHub/commit/3bf71cda5387905dd07f87798d553dc259bad106))
* close phase 1 for the demo scope ([1a58042](https://github.com/izumi101/EventHub/commit/1a580421e1b8feadf53ddada8ff238e03f974d7a))
* feature flags guide ([987fbb0](https://github.com/izumi101/EventHub/commit/987fbb0bb1149d466099d4c82bb3b833119473cf))
* **payments:** ADR 0001 payment provider layer ([db39ba3](https://github.com/izumi101/EventHub/commit/db39ba37e8efc3e1072f0946954c0858fe6cb758))
* **payments:** Freedom Pay merchant API specification ([fe77e5c](https://github.com/izumi101/EventHub/commit/fe77e5cc2e8840901f5659323395a7b9ed9f0dad))
* phase 1 status and the demo script ([cdcc7bd](https://github.com/izumi101/EventHub/commit/cdcc7bdb00c070b610d92c0c67d6e3abd0e4b0fc))
* showcase data in the demo script, commit refs in reports ([576ef72](https://github.com/izumi101/EventHub/commit/576ef723c2c7b29706d6428b65050ab99a8c0e52))
