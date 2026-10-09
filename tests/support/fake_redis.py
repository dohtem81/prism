import fnmatch


class FakeRedis:
    """In-memory subset of redis-py used by the token store and security counters."""

    def __init__(self) -> None:
        self.strings: dict[str, str] = {}
        self.hashes: dict[str, dict[str, str]] = {}
        self.lists: dict[str, list[str]] = {}
        self.ttls: dict[str, int] = {}

    def set(self, key, value, ex=None):
        self.strings[key] = value
        if ex:
            self.ttls[key] = ex

    def exists(self, key):
        return int(key in self.strings or key in self.hashes)

    def delete(self, key):
        removed = self.strings.pop(key, None) is not None or self.hashes.pop(key, None) is not None
        self.ttls.pop(key, None)
        return int(removed)

    def ttl(self, key):
        return self.ttls.get(key, -1)

    def expire(self, key, seconds):
        self.ttls[key] = seconds

    def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    def hset(self, key, field=None, value=None, mapping=None):
        bucket = self.hashes.setdefault(key, {})
        if field is not None:
            bucket[field] = value
        if mapping:
            bucket.update(mapping)

    def hsetnx(self, key, field, value):
        bucket = self.hashes.setdefault(key, {})
        if field in bucket:
            return 0
        bucket[field] = value
        return 1

    def scan_iter(self, match="*"):
        keys = list(self.strings) + list(self.hashes)
        return iter([key for key in keys if fnmatch.fnmatchcase(key, match)])

    def lpush(self, key, value):
        self.lists.setdefault(key, []).insert(0, value)

    def ltrim(self, key, start, stop):
        self.lists[key] = self.lists.get(key, [])[start : stop + 1]

    def lrange(self, key, start, stop):
        return list(self.lists.get(key, [])[start : stop + 1])

    def pipeline(self):
        return _FakePipeline(self)


class _FakePipeline:
    def __init__(self, client: FakeRedis) -> None:
        self._client = client
        self._ops = []

    def hset(self, key, mapping):
        self._ops.append(lambda: self._client.hset(key, mapping=mapping))

    def expire(self, key, seconds):
        self._ops.append(lambda: self._client.expire(key, seconds))

    def execute(self):
        for op in self._ops:
            op()
