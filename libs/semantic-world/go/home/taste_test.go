package home

import (
	"testing"

	sw "github.com/metis-lang-dev/metis-worlds/libs/semantic-world/go/semworld"
)

// TestTasteIsAFoldOverEvents: items, evidence and priors are events: the hash follows them, a
// replay reaches the same hash, a snapshot restores the same choices.
func TestTasteIsAFoldOverEvents(t *testing.T) {
	ev := []Event{
		{At: 1, Kind: "item", Item: &sw.Item{ID: "vinyl", Kind: "station", Name: "Classic Vinyl HD", Tags: []string{"jazz"}}},
		{At: 1, Kind: "item", Item: &sw.Item{ID: "jazzfm", Kind: "station", Name: "Jazz FM", Tags: []string{"jazz"}}},
		{At: 2, Kind: "prior", Value: "classic", Pref: &sw.Context{Part: "evening"}, Delta: 1.5},
		{At: 3, Kind: "prefer", ID: "jazzfm", Pref: &sw.Context{Part: "morning"}, Delta: 1},
		{At: 4, Kind: "settle"},
	}
	a, b := dayHome(t), dayHome(t)
	h0 := a.Hash()
	for _, e := range ev {
		if _, err := a.Apply(e); err != nil {
			t.Fatal(err)
		}
		b.Apply(e)
	}
	if a.Hash() == h0 || a.Hash() != b.Hash() {
		t.Fatalf("the hash: before %s, after %s, replayed %s", h0, a.Hash(), b.Hash())
	}
	pick := func(h *Home) string {
		c, _ := h.W.Taste.Select("station", []string{"jazz"}, sw.Context{Part: "evening"}, nil, 5)
		return c.ID
	}
	if pick(a) != "vinyl" {
		t.Fatalf("the evening's jazz, by character: %s", pick(a))
	}
	snap, err := a.Snapshot()
	if err != nil {
		t.Fatal(err)
	}
	r := dayHome(t)
	if err := r.Restore(snap); err != nil {
		t.Fatal(err)
	}
	if r.Hash() != a.Hash() || pick(r) != pick(a) {
		t.Fatalf("restored: %s / %s, chose %s", r.Hash(), a.Hash(), pick(r))
	}
}

// TestTheTasteOutlivesAnotherWorld: a world built otherwise refuses the snapshot, but keeps the taste.
func TestTheTasteOutlivesAnotherWorld(t *testing.T) {
	a := dayHome(t)
	a.Apply(Event{At: 1, Kind: "item", Item: &sw.Item{ID: "vinyl", Kind: "station", Tags: []string{"jazz"}}})
	a.Apply(Event{At: 2, Kind: "prefer", ID: "vinyl", Pref: &sw.Context{Part: "evening"}, Delta: 1})
	snap, _ := a.Snapshot()
	m, _ := LoadMap("../testdata/home.wired.map.json")
	other := New(m, DefaultParams) // no members joined: another world
	if err := other.RestoreTaste(snap); err != nil {
		t.Fatal(err)
	}
	if other.W.Taste.HashText() != a.W.Taste.HashText() {
		t.Fatal("the taste was not carried over")
	}
}
