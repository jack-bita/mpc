"""demo — owns the demo shop's seed: the made-up shop the public demo's visitors log in to (DATA-1, ADR-0029), and the
one-tap demo, which makes a visitor's browser a device of it and shows the sellers' PINs (OPS-3, BP15).

Layer 7, the top (03 §5.1): it may import every app, and no app imports it. Not a domain module: it holds no tables
of its own, only the seed, which builds the demo shop through the other apps' services, and the one-tap demo's two
routes (api/), which alone may read the seed's people and their PINs. It sits on top because the seed grows with
them: clock-ins and a pay run (DATA-2, staffpay), then products and sales (DATA-7).
"""
