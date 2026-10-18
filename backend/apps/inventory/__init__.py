"""inventory — owns stock: StockMovements, StockBalances, Batches, Deliveries, StockCounts, RestockRequests.

Layer 4 (ADR-0015): imports layers 0-3, and money (a delivery pays its supplier).
Transfers, ProductionRuns and BagOpenings arrive in R2.
"""
