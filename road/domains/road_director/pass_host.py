"""The pass's host (the road director): no world of its own — it exists so the agent can take lines
into the director's session (the relayed reports and statuses, its grants' ages). Nothing to read, nothing to do;
the agent's world lines (a stop's +tick__stop / -tick__stop, step 3c) are handed in at its next tick, as every tree
director's host does."""


class PassHost:
    def __init__(self):
        self.beat, self.due, self.script, self.last, self.queue = 0, (), {}, None, []

    def bind(self, reg):
        pass

    def tick(self, counts):
        self.beat += 1
        dos, self.queue = self.queue, []
        return dos

    def on_event(self, name, args):
        pass

    def observe(self, counts):
        return {}

    def reading(self):
        return {}

    def sync(self, counts):
        return []

    def pending(self):
        return False

    def world(self, lines):
        self.queue += [l.strip() for l in lines if l.strip()]

    def snapshot(self):
        return {"beat": self.beat, "queue": list(self.queue)}

    def restore(self, snap):
        self.beat, self.queue = snap["beat"], list(snap.get("queue", ()))


def make(case=None):
    return PassHost()
