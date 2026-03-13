"""
DirectMappedCache — Software reference model for Phase 3 I-cache and D-cache.

Models a direct-mapped, write-back, write-allocate cache. Used by the
verification scoreboard to validate RTL cache behavior.

Parameters match RTL (rv32i_cache_pkg.sv):
  - Cache size : 4 KB
  - Line size  : 16 B (4 words)
  - Sets       : 256  (direct-mapped, so N_WAYS=1)
  - Tag bits   : [31:12]  (20 bits)
  - Index bits : [11:4]   (8 bits)
  - Offset bits: [3:0]    (4 bits, word offset = [3:2])
"""

CACHE_SIZE_BYTES = 4096
LINE_SIZE_BYTES = 16
LINE_WORDS = LINE_SIZE_BYTES // 4  # 4 words per line
N_SETS = CACHE_SIZE_BYTES // LINE_SIZE_BYTES  # 256 sets
OFFSET_BITS = 4  # log2(LINE_SIZE_BYTES)
INDEX_BITS = 8  # log2(N_SETS)
TAG_BITS = 32 - INDEX_BITS - OFFSET_BITS  # 20


def _decompose(addr: int):
    """Return (tag, index, word_offset, byte_offset) for a 32-bit address."""
    byte_offset = addr & 0x3
    word_offset = (addr >> 2) & (LINE_WORDS - 1)
    index = (addr >> OFFSET_BITS) & (N_SETS - 1)
    tag = addr >> (OFFSET_BITS + INDEX_BITS)
    return tag, index, word_offset, byte_offset


class _CacheLine:
    """Internal representation of one cache line."""

    __slots__ = ("valid", "dirty", "tag", "data")

    def __init__(self):
        self.valid = False
        self.dirty = False
        self.tag = 0
        self.data = [0] * LINE_WORDS  # list of 4 32-bit words


class DirectMappedCache:
    """
    Reference model for a 4 KB direct-mapped write-back/write-allocate cache.

    Usage
    -----
    >>> mem = {addr: word_value, ...}   # backing store (word-addressed at word granularity)
    >>> cache = DirectMappedCache(backing_store=mem, write_policy='write_back')
    >>> data, hit = cache.read(0x1000)
    >>> cache.write(0x1000, 0xDEADBEEF, strobe=0xF)
    >>> cache.flush()          # FENCE.I — invalidate all lines

    Backing store
    -------------
    `backing_store` is a dict {word_address: word_value} where word_address
    is the byte address >> 2 (word-aligned).  The model reads/writes it on
    cache misses and write-back evictions.
    """

    def __init__(self, backing_store: dict | None = None, write_policy: str = "write_back"):
        if write_policy != "write_back":
            raise ValueError("Only 'write_back' policy is supported")

        self._lines = [_CacheLine() for _ in range(N_SETS)]
        self._mem = backing_store if backing_store is not None else {}

        # Statistics
        self.read_hits = 0
        self.read_misses = 0
        self.write_hits = 0
        self.write_misses = 0
        self.evictions = 0
        self.writebacks = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def read(self, addr: int) -> tuple[int, bool]:
        """
        Read a word from the cache.

        Returns (word_data, hit).  On a miss the cache line is filled
        from backing_store (write-allocate does not apply to reads).

        Args:
            addr: Byte address (word-aligned; low 2 bits ignored).

        Returns:
            (data: int, hit: bool)
        """
        addr &= ~0x3  # word-align
        tag, index, word_off, _ = _decompose(addr)
        line = self._lines[index]

        if line.valid and line.tag == tag:
            self.read_hits += 1
            return line.data[word_off], True

        # Miss — refill
        self.read_misses += 1
        self._refill(index, tag, addr)
        return self._lines[index].data[word_off], False

    def write(self, addr: int, data: int, strobe: int = 0xF) -> bool:
        """
        Write a word (with byte strobe) to the cache (write-back, write-allocate).

        On a write-hit  : update cache line in-place, set dirty.
        On a write-miss : refill the line (write-allocate), then apply write.

        Args:
            addr  : Byte address (word-aligned; low 2 bits ignored).
            data  : 32-bit word to write.
            strobe: 4-bit byte-enable mask (bit 0 = byte 0, LSB).

        Returns:
            hit (bool) — True if the line was already cached.
        """
        addr &= ~0x3  # word-align
        tag, index, word_off, _ = _decompose(addr)
        line = self._lines[index]

        if line.valid and line.tag == tag:
            # Write-hit
            self.write_hits += 1
            self._apply_strobe(line, word_off, data, strobe)
            line.dirty = True
            return True

        # Write-miss — write-allocate: refill, then write
        self.write_misses += 1
        self._refill(index, tag, addr)
        line = self._lines[index]
        self._apply_strobe(line, word_off, data, strobe)
        line.dirty = True
        return False

    def flush(self):
        """
        Invalidate all cache lines (FENCE.I / full invalidation).

        Dirty lines are written back to backing store before invalidation.
        """
        for index, line in enumerate(self._lines):
            if line.valid and line.dirty:
                self._writeback(index)
            line.valid = False
            line.dirty = False

    def evict(self, index: int) -> tuple[list[int] | None, bool]:
        """
        Evict (invalidate) a single cache set.

        Returns (data_words, was_dirty).  If was_dirty, the caller should
        write the returned words back to memory.  If the line was not valid,
        returns (None, False).
        """
        line = self._lines[index]
        if not line.valid:
            return None, False

        dirty = line.dirty
        data = list(line.data) if dirty else None
        if dirty:
            self._writeback(index)
        line.valid = False
        line.dirty = False
        return data, dirty

    # ------------------------------------------------------------------
    # Statistics helpers
    # ------------------------------------------------------------------

    @property
    def hit_rate(self) -> float:
        """Read hit rate (fraction, 0–1)."""
        total = self.read_hits + self.read_misses
        return self.read_hits / total if total else 0.0

    def reset_stats(self):
        """Clear all counters."""
        self.read_hits = 0
        self.read_misses = 0
        self.write_hits = 0
        self.write_misses = 0
        self.evictions = 0
        self.writebacks = 0

    def stats(self) -> dict:
        """Return a snapshot of all statistics."""
        return {
            "read_hits": self.read_hits,
            "read_misses": self.read_misses,
            "write_hits": self.write_hits,
            "write_misses": self.write_misses,
            "evictions": self.evictions,
            "writebacks": self.writebacks,
            "hit_rate": self.hit_rate,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _line_base_addr(self, index: int, tag: int) -> int:
        """Reconstruct the base byte-address of a cache line."""
        return ((tag << INDEX_BITS) | index) << OFFSET_BITS

    def _writeback(self, index: int):
        """Write a dirty line back to backing_store."""
        line = self._lines[index]
        base_word = self._line_base_addr(index, line.tag) >> 2  # word address
        for w in range(LINE_WORDS):
            self._mem[base_word + w] = line.data[w]
        self.writebacks += 1

    def _refill(self, index: int, tag: int, addr: int):
        """
        Fill cache set `index` with the line containing `addr`.

        If the current occupant is valid and dirty, write it back first.
        """
        line = self._lines[index]

        # Evict existing occupant (clean or dirty)
        if line.valid:
            self.evictions += 1
            if line.dirty:
                self._writeback(index)

        # Fill from backing store
        base_addr = (addr >> OFFSET_BITS) << OFFSET_BITS  # line-aligned byte addr
        base_word_addr = base_addr >> 2
        for w in range(LINE_WORDS):
            line.data[w] = self._mem.get(base_word_addr + w, 0)

        line.valid = True
        line.dirty = False
        line.tag = tag

    @staticmethod
    def _apply_strobe(line: _CacheLine, word_off: int, data: int, strobe: int):
        """Merge `data` into `line.data[word_off]` using byte strobe."""
        old = line.data[word_off]
        merged = 0
        for byte in range(4):
            if strobe & (1 << byte):
                merged |= data & (0xFF << (byte * 8))
            else:
                merged |= old & (0xFF << (byte * 8))
        line.data[word_off] = merged
