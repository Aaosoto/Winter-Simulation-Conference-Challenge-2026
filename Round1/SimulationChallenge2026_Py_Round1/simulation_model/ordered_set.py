"""
OrderedSet — a set whose iteration order matches the reference runtime's HashSet<T>.

The original version of this file claimed ``the reference runtime HashSet<T>`` preserves
insertion order.  That is wrong whenever remove + add churn happens.

**What the reference runtime's HashSet<T> actually does** (verified against the reference runtime
reference source, ``src/libraries/System.Private.CoreLib/src/System/Collections/Generic/HashSet.cs``):

* Internally, a HashSet<T> has two parallel arrays of the same length:
  ``_buckets`` (length = next prime ≥ count) and ``_entries`` (each entry is
  ``{ int hashCode, int next, T value }``).
* ``_buckets[i]`` stores the **1-based** index of the head of the
  collision chain for bucket ``i`` (``0`` means empty bucket).
* ``_entries[i].next`` is the **0-based** index of the next entry in the
  chain, or ``-1`` if it is the last entry.
* On ``Add``: scan the bucket chain; if equal value is found, do nothing.
  Otherwise allocate a slot — preferring the **head of a free list** (a
  singly linked list of removed entry indices) over appending — and
  splice the new entry in as the new head of the bucket chain.
* On ``Remove``: unlink the entry from its bucket chain, push its index
  onto the head of the free list, and (for reference types) zero out the
  value so iteration can skip it.
* **Iteration** walks ``_entries`` in entry-array order from ``0`` to
  ``_count - 1`` (NOT ``_entries.Length - 1``) and yields entries whose
  ``next >= -1`` (i.e. NOT in the free list).
* **Resize** is triggered when ``_count == _entries.Length`` (i.e. the
  dense array is full).  ``Resize`` allocates a new ``_entries`` of size
  ``ExpandPrime(_count)`` and **copies the first ``_count`` entries**
  (free-list slots are dropped) and rebuilds the bucket chains.
  After a resize, ``_freeList == -1`` and ``_freeCount == 0``.

**The iteration-order consequence**:

    add A; add B; add C; remove B; add D
    the reference runtime:  entries = [A, D, C]   (D reused B's slot 1)
    insertion-order (dict-backed OrderedSet):  [A, C, D]

**Why this matters for the WSC port** (WSC Simulation Challenge 2026):

Greedy vessel loading in ``VesselBeingServed`` iterates ``p_start_signals``
(a ``HashSet<Shipment>``) in iteration order to first-fit shipments until
capacity is exhausted.  When two implementations agree on the same set of
candidates but disagree on the iteration order, they pick **different
subsets** at full capacity.  That single-slot difference per vessel was the
source of the S4 30-TEU divergence (-9.3% on S4) seen in the 10-day
baseline.

Implementation notes
--------------------

We use Python's ``hash(value)`` (or ``id(value)`` if unhashable) as the
bucket hash — this mirrors ``EqualityComparer<T>.Default.GetHashCode``,
which uses the value's own ``GetHashCode`` if defined, else falls back
to ``Object.GetHashCode`` (the runtime-private sync-block-index hash).

We use **prime-sized** buckets (matching the reference runtime's ``HashHelpers.ExpandPrime``)
for full behavioral equivalence of bucket chain shape.  The first 100
primes are taken from the reference runtime's ``HashHelpers`` table.
"""

from typing import TypeVar, Generic, Iterator, Iterable, Optional, MutableSet, Any

T = TypeVar("T")

# Reference runtime prime-size table used by the hash bucket implementation.
_PRIMES = [
    3, 7, 11, 17, 23, 29, 37, 47, 59, 71,
    89, 107, 131, 163, 197, 239, 293, 353, 431, 521,
    631, 761, 919, 1103, 1327, 1597, 1913, 2297, 2753, 3301,
    3967, 4761, 5717, 6863, 8237, 9887, 11873, 14249, 17099, 20519,
    24623, 29537, 35441, 42527, 51031, 61231, 73487, 88181, 105817, 126961,
    152347, 182809, 219371, 263237, 315881, 379051, 454859, 545827, 654989, 785981,
    943171, 1131799, 1358147, 1629767, 1955711, 2346841, 2816201, 3379433, 4055303, 4866343,
    5839589, 7007489, 8408969, 10090741, 12108889, 14530633, 17436751, 20924099, 25108897, 30130657,
    36156779, 43388093, 52065691, 62478793, 74974499, 89969353, 107963131, 129555757, 155466889, 186560207,
    223872211, 268646579, 322375873, 386851019, 464221187, 557065387, 668478427, 802174067, 962608819, 1155130583,
    1386156677, 1663388009, 1996065583, 2395278673, 2874334357, 3449201197, 4139041381, 4966849627, 5960219509, 7152263387,
]


def _h(value: T) -> int:
    """Bucket hash for a value, mirroring ``EqualityComparer<T>.Default.GetHashCode``."""
    try:
        return hash(value)
    except TypeError:
        return id(value)


_NO_NEXT = -1
_START_OF_FREE_LIST = -3


class _Entry(Generic[T]):
    __slots__ = ("hash_code", "next", "value")

    def __init__(self, hash_code: int, next_idx: int, value: T):
        self.hash_code = hash_code
        self.next = next_idx
        self.value = value


def _get_prime(min_size: int) -> int:
    """Match the reference runtime's ``HashHelpers.GetPrime``: smallest prime in the table ≥ ``min_size``."""
    if min_size <= 0:
        return _PRIMES[0]
    for p in _PRIMES:
        if p >= min_size:
            return p
    # Past the table — fall back to a hash.  In practice the WSC port never
    # gets anywhere near this size.
    return min_size | 1  # next odd ≥ min_size


def _expand_prime(old_size: int) -> int:
    """Match the reference runtime's ``HashHelpers.ExpandPrime``: return the smallest prime
    ≥ ``2 * old_size``.  Always strictly greater than ``old_size`` for any
    ``old_size > 0`` (since 2× of any positive integer exceeds the previous
    prime table entry)."""
    return _get_prime(2 * old_size)


class OrderedSet(MutableSet, Generic[T]):
    """A set whose iteration order matches the reference runtime's ``HashSet<T>``.

    Iteration walks the dense ``_entries`` array in index order, skipping
    slots that are in the free list (``entry.next < -1``).  ``Add`` prefers
    to fill the lowest-indexed free slot before appending.

    Layout mirrors ``HashSet<T>``:
    * ``_buckets`` 1-based, length = entries length = prime.
    * ``_entries[i].next`` = next chain index (0-based) or -1 (chain end)
      or < -1 (in free list).
    * Resize when ``_count == len(_entries)`` (i.e. dense array full).
    """

    __slots__ = ("_buckets", "_entries", "_count", "_free_list", "_free_count")

    def __init__(self, iterable: Optional[Iterable[T]] = None):
        self._buckets: list[int] = []
        self._entries: list[Optional[_Entry]] = []
        self._count: int = 0
        self._free_list: int = _NO_NEXT
        self._free_count: int = 0
        if iterable is not None:
            for item in iterable:
                self.add(item)

    # ------------------------------------------------------------------ #
    # Internal mechanics                                                 #
    # ------------------------------------------------------------------ #

    def _initialize(self, capacity: int) -> None:
        """Allocate buckets + entries arrays of the same prime size.
        Matches the reference runtime's ``Initialize``: size = ``GetPrime(capacity)``."""
        size = _get_prime(capacity)
        self._buckets = [0] * size        # 1-based; 0 = empty
        self._entries = [None] * size
        self._free_list = _NO_NEXT
        self._free_count = 0
        # NOTE: _count is NOT reset — caller manages it.

    def _bucket_index(self, hash_code: int, buckets_length: int) -> int:
        """1-based bucket index.  Matches the reference runtime's `buckets[(uint)hashCode % len]`."""
        # 1-based: return value is 1..len, or just `hash % len` then use as
        # the slot whose value is 1-based.  We'll do the 1-based wrap in the
        # caller.
        return hash_code % buckets_length

    def _resize(self) -> None:
        """Match the reference runtime's Resize: new size = ExpandPrime(_count), copy first
        ``_count`` entries (free-list slots are dropped), rebuild buckets."""
        new_size = _expand_prime(self._count)
        # the reference runtime does:
        #   var entries = new Entry[newSize];
        #   Array.Copy(_entries, entries, count);
        #   _buckets = new int[newSize];
        #   for (i = 0; i < count; i++) if (entry.Next >= -1) repaint.
        # i.e. only the first _count entries are copied — free-list slots
        # are *discarded* and the free list is empty after resize.
        new_entries: list[Optional[_Entry]] = [None] * new_size
        for i in range(self._count):
            new_entries[i] = self._entries[i]
        new_buckets = [0] * new_size
        for i in range(self._count):
            e = new_entries[i]
            b = e.hash_code % new_size
            e.next = new_buckets[b] - 1   # value stored is 1-based
            new_buckets[b] = i + 1
        self._entries = new_entries
        self._buckets = new_buckets
        self._free_list = _NO_NEXT
        self._free_count = 0

    def add(self, item: T) -> None:
        """Insert if not present.  Returns nothing (matches ``MutableSet.add``)."""
        if not self._buckets:
            self._initialize(0)

        hc = _h(item)
        b_len = len(self._buckets)

        # Step 1: scan bucket chain for an existing equal value.
        i = self._buckets[hc % b_len] - 1   # 1-based to 0-based
        while i != _NO_NEXT:
            e = self._entries[i]
            if e.hash_code == hc and e.value == item:
                return  # already present
            i = e.next

        # Step 2: pick a slot — prefer free-list head, else append.
        if self._free_count > 0:
            index = self._free_list
            self._free_count -= 1
            # Free-list chain encoded as `entry.next = _START_OF_FREE_LIST - old_free_list`.
            # So: old_free_list = _START_OF_FREE_LIST - entry.next = -3 - entry.next.
            self._free_list = _START_OF_FREE_LIST - self._entries[index].next
        else:
            if self._count == len(self._entries):
                self._resize()
                # After resize, re-derive bucket index.
                b_len = len(self._buckets)
            index = self._count
            self._count += 1

        # Step 3: write the entry and link into the bucket chain head.
        b = hc % b_len
        prev_head = self._buckets[b] - 1   # 1-based to 0-based
        e = _Entry(hc, prev_head, item)
        self._entries[index] = e
        self._buckets[b] = index + 1       # store 1-based

    def discard(self, item: T) -> None:
        """Remove if present.  Matches the reference runtime's ``HashSet<T>.Remove`` semantics."""
        if not self._buckets:
            return
        b_len = len(self._buckets)
        hc = _h(item)
        b = hc % b_len
        i = self._buckets[b] - 1
        last = _NO_NEXT
        while i != _NO_NEXT:
            e = self._entries[i]
            if e.hash_code == hc and e.value == item:
                # Unlink
                if last == _NO_NEXT:
                    self._buckets[b] = e.next + 1
                else:
                    self._entries[last].next = e.next
                # Push to free list
                e.next = _START_OF_FREE_LIST - self._free_list
                # For reference-like types, the reference runtime zeros out the value to help
                # GC.  We don't, but it doesn't affect iteration (which
                # skips slots with next < -1).
                self._free_list = i
                self._free_count += 1
                return
            last = i
            i = e.next

    def remove(self, item: T) -> None:
        if item not in self:
            raise KeyError(item)
        self.discard(item)

    def pop(self) -> T:
        if self._count == 0:
            raise KeyError("pop from empty OrderedSet")
        for i in range(self._count):
            e = self._entries[i]
            if e is not None and e.next >= _NO_NEXT:
                v = e.value
                self.discard(v)
                return v
        raise KeyError("pop from empty OrderedSet")  # unreachable

    def clear(self) -> None:
        self._buckets = []
        self._entries = []
        self._count = 0
        self._free_list = _NO_NEXT
        self._free_count = 0

    def __contains__(self, item: Any) -> bool:
        if not self._buckets:
            return False
        hc = _h(item)
        b_len = len(self._buckets)
        i = self._buckets[hc % b_len] - 1
        while i != _NO_NEXT:
            e = self._entries[i]
            if e.hash_code == hc and e.value == item:
                return True
            i = e.next
        return False

    def __iter__(self) -> Iterator[T]:
        # Mirrors the reference runtime Enumerator.MoveNext:
        #   for (i = 0; i < _count; i++) if (entries[i].next >= -1) yield.
        # _count is the dense-append boundary, so iterating [0, _count) and
        # skipping free-list slots is the exact contract.
        i = 0
        while i < self._count:
            e = self._entries[i]
            i += 1
            if e is not None and e.next >= _NO_NEXT:
                yield e.value

    def __len__(self) -> int:
        return self._count - self._free_count

    # ------------------------------------------------------------------ #
    # Misc                                                                #
    # ------------------------------------------------------------------ #

    def __repr__(self) -> str:
        return f"OrderedSet({list(self)})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, OrderedSet):
            if (self._count - self._free_count) != (other._count - other._free_count):
                return False
            return all(x in other for x in self)
        if isinstance(other, set):
            return (self._count - self._free_count) == len(other) and all(x in other for x in self)
        return NotImplemented

    def __ne__(self, other: object) -> bool:
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __hash__(self) -> int:
        raise TypeError("unhashable type: 'OrderedSet'")

    def copy(self) -> "OrderedSet[T]":
        new = OrderedSet()
        new._buckets = self._buckets.copy()
        new._entries = self._entries.copy()
        new._count = self._count
        new._free_list = self._free_list
        new._free_count = self._free_count
        return new

    # ----- Set algebra (kept for any consumer that uses them) -----

    def issubset(self, other) -> bool:
        return (self._count - self._free_count) <= len(other) and all(x in other for x in self)

    def issuperset(self, other) -> bool:
        return len(other) <= (self._count - self._free_count) and all(x in self for x in other)

    def union(self, *others):
        result = self.copy()
        for other in others:
            for item in other:
                result.add(item)
        return result

    def intersection(self, *others):
        result = OrderedSet()
        for item in self:
            if all(item in other for other in others):
                result.add(item)
        return result

    def difference(self, *others):
        result = self.copy()
        for other in others:
            for item in other:
                result.discard(item)
        return result

    def symmetric_difference(self, other):
        result = OrderedSet()
        for item in self:
            if item not in other:
                result.add(item)
        for item in other:
            if item not in self:
                result.add(item)
        return result

    def isdisjoint(self, other) -> bool:
        for item in self:
            if item in other:
                return False
        return True
