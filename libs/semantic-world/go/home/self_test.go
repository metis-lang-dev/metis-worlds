package home

import (
	"strings"
	"testing"
)

// Errors of one kind build a belief (a hint, likely, sure), a success brings well back, and an
// unheard strain forgets back to well; a world without strains has no "nina" entry (old logs
// replay to the same hash).
func TestStrain(t *testing.T) {
	m, err := LoadMap("../testdata/home.map.json")
	if err != nil {
		t.Fatal(err)
	}
	h := New(m, DefaultParams)
	before := h.Hash()
	if h.W.Entries[Self] != nil {
		t.Fatal("a nina entry before any strain")
	}
	p := func() float64 { return h.W.Var(Self, "mind").P("busy") }
	var ps []float64
	for i := 0; i < 3; i++ {
		if _, err := h.Apply(Event{At: float64(i), Kind: "strain", ID: "mind", Value: "busy", Ref: "503 high demand"}); err != nil {
			t.Fatal(err)
		}
		ps = append(ps, p())
	}
	if !(ps[0] < 0.5 && ps[1] >= 0.5 && ps[2] >= 0.9) {
		t.Fatalf("busy after 1, 2, 3 errors: %v (want unsure, likely, sure)", ps)
	}
	if h.Hash() == before {
		t.Fatal("the strain did not change the world")
	}
	if got := line(h, 3, "nina.mind"); !strings.HasPrefix(got, "Nina's task model: busy: the service is in high demand") {
		t.Fatalf("line %q", got)
	}
	if _, err := h.Apply(Event{At: 4, Kind: "strain", ID: "mind", Value: "well"}); err != nil {
		t.Fatal(err)
	}
	if p() >= 0.85 {
		t.Fatalf("a success left busy sure: %v", p())
	}
	h.Apply(Event{At: 5, Kind: "strain", ID: "mind", Value: "busy"})
	h.Apply(Event{At: 6, Kind: "settle"})
	h.Apply(Event{At: 1806, Kind: "settle"}) // 30 min unheard
	if v, _ := h.W.Var(Self, "mind").Top(); v != "well" {
		t.Fatalf("after 30 min: %s", v)
	}
	if _, err := h.Apply(Event{At: 7, Kind: "strain", ID: "mind", Value: "angry"}); err == nil {
		t.Fatal("an unknown kind was taken")
	}
}
