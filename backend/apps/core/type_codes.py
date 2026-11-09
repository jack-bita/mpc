"""apps/core/type_codes.py — the shape of a type code: the short name a table is stored by, such as "side" or
"staff", in a generic link (apps/core/links.py) and in a line of the change log (Change, apps/core/models.py).

A small file of its own, which imports nothing of ours, because both of those need it: links.py imports models.py
(for ShopScoped), so models.py can't import links.py back without each needing the other half-loaded (from SYNC-1's
review). It owns the two values below; links.py still owns the list of codes.
"""

# The shape of a code: small letters and underscores, starting with a letter ("drawer_session"), and its longest
# length, the size of the column that stores it. The tables that store a code use both: the column (control.Flag's
# subject_type, Change's entity) and a database rule on its shape. A code that broke either would be refused only when
# the first row naming its table is written, perhaps while a device's records are posted, which must never fail; so a
# test checks every code in the list instead (apps/core/tests/test_links.py).
TYPE_CODE_SHAPE = r"^[a-z][a-z_]*$"
TYPE_CODE_MAX_LENGTH = 40
