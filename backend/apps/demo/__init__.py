"""demo — owns the demo shop's seed: the made-up shop the public demo's visitors log in to (DATA-1, ADR-0029).

Layer 7, the top (03 §5.1): it may import every app, and no app imports it. Not a domain module: it holds no tables
of its own, only the seed, which builds the demo shop through the other apps' services. It sits on top because the
seed grows with them: clock-ins and a pay run (DATA-2, staffpay), then products and sales (DATA-7).
"""
