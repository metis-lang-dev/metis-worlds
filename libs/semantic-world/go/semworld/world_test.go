package semworld

import (
	"reflect"
	"strings"
	"testing"
)

func TestQuantiseIsSpec16(t *testing.T) {
	at, names := []float64{0.3, 0.7}, []string{"low", "mid", "high"}
	for p, want := range map[float64]string{0: "low", 0.29: "low", 0.3: "mid", 0.69: "mid", 0.7: "high", 1: "high"} {
		if got := Quantise(p, at, names); got != want {
			t.Errorf("Quantise(%v) = %s, want %s", p, got, want)
		}
	}
}

// a one-room world with a presence port and two members, one of which writes a conclusion
func board(t *testing.T) (*World, *Board) {
	w := New()
	w.Add(&Entry{ID: "r1", Kind: KPlace, Name: "lab"})
	w.Declare("r1", "presence", VOdds, nil, nil)
	b := NewBoard(w)
	b.Offer(&Port{Name: "present", Keys: func() [][]string { return [][]string{{"r1"}} },
		P: func(a []string) (float64, bool) {
			v := w.Var(a[0], "presence")
			return P(v.Odds), v.Src.Kind != "prior"
		},
		Src: func(a []string) Source { return w.Var(a[0], "presence").Src }})
	for _, n := range []string{"lights", "scenes"} {
		m := &Manifest{Name: n, Levels: map[string]LevelSpec{"presence": {From: map[string]string{"belief": "present"},
			At: []float64{0.3, 0.7}, Names: []string{"vacant", "unsure", "occupied"}}}}
		if err := b.Join(m); err != nil {
			t.Fatal(err)
		}
	}
	return w, b
}

func TestLevelLinesAndWake(t *testing.T) {
	w, b := board(t)
	b.Settle()
	if got := b.Lines("lights"); len(got) != 0 {
		t.Fatalf("unknown presence asserts nothing, got %v", got)
	}
	if !b.Wake("lights", 0) { // the first sight of the port (its unknown) is a change
		t.Fatal("a member wakes on its first reading")
	}
	if b.Wake("lights", 1) {
		t.Fatal("nothing changed, no clock: no beat")
	}
	w.ObserveOdds("r1", "presence", 4, Source{Kind: "sensor", Who: "radar"}, 2)
	b.Settle()
	if got := b.Lines("lights"); !reflect.DeepEqual(got, []string{"+presence(occupied, r1) 1"}) {
		t.Fatalf("lines %v", got)
	}
	if !b.Wake("lights", 2) || !b.Wake("scenes", 2) {
		t.Fatal("a world change wakes every reader")
	}
	w.ObserveOdds("r1", "presence", -4.5, Source{Kind: "sensor"}, 3)
	b.Settle()
	if got := b.Lines("lights"); !reflect.DeepEqual(got, []string{"-presence(occupied, r1) 1", "+presence(unsure, r1) 1"}) {
		t.Fatalf("the previous level retracted, one per key: %v", got)
	}
	// rule 3: a change written by scenes does not wake scenes, but wakes lights
	b.Wake("lights", 3)
	b.Wake("scenes", 3)
	w.ObserveOdds("r1", "presence", -3, Source{Kind: "metis", Who: "scenes"}, 4)
	b.Settle()
	if b.Wake("scenes", 4) {
		t.Fatal("no beat on one's own echo")
	}
	if !b.Wake("lights", 4) {
		t.Fatal("another member's write wakes a reader")
	}
	if b.C("present") != 4 {
		t.Fatalf("c_p = %d", b.C("present"))
	}
}

func TestClockWakes(t *testing.T) {
	_, b := board(t)
	b.members["lights"].Clock.Period = 60
	b.Settle()
	b.Wake("lights", 0)
	if b.Wake("lights", 30) || !b.Wake("lights", 60) {
		t.Fatal("the clock period wakes a member whose ports are quiet")
	}
}

func TestJoinRefusesAPortTheWorldLacks(t *testing.T) {
	_, b := board(t)
	err := b.Join(&Manifest{Name: "x", Beliefs: map[string]BeliefSpec{"a": {Port: "nope"}}})
	if err == nil || !strings.Contains(err.Error(), "present") {
		t.Fatalf("got %v", err)
	}
}

func TestReadManifest(t *testing.T) {
	m, err := ReadManifest("../testdata/comfort.domain.yaml", "comfort")
	if err != nil {
		t.Fatal(err)
	}
	if m.Levels["chill"].Names[2] != "cold" || m.Beliefs["occupied"].Port != "present" || m.Clock.Period != 60 {
		t.Fatalf("%+v", m)
	}
}

func TestReportAndConclude(t *testing.T) {
	w := New()
	w.Add(&Entry{ID: "u1", Kind: KDevice, Name: "bedroom ventilation"})
	w.Declare("u1", "power", VCat, []string{"on", "off"}, nil)
	if _, err := w.Report("assistant", "u1", "power", "on", 0, "", 0); err == nil {
		t.Fatal("the assistant's own words are refused")
	}
	if ok, _ := w.Report("pascal", "u1", "power", "on", 0, "utt-1", 1); !ok || w.Var("u1", "power").P("on") != 0.7 {
		t.Fatalf("a person's word is weak evidence: %v", w.Var("u1", "power").Cat)
	}
	w.ObserveCat("u1", "power", "off", 0.999, 0.5, Source{Kind: "sensor"}, 2)
	if ok, _ := w.Report("pascal", "u1", "power", "on", 0, "utt-2", 3); ok || len(w.Surprises) != 1 || w.Surprises[0].Kind != "evidential" {
		t.Fatalf("a word against a sure fresh sensor is a surprise, not evidence: %v", w.Surprises)
	}
	if !w.Conclude("comfort", "advise_heater(r1)", true, "cold_heater", 4) || w.Conclude("comfort", "advise_heater(r1)", true, "cold_heater", 5) {
		t.Fatal("a conclusion is written once")
	}
	if w.Var("u1", "power").Src.Kind != "sensor" {
		t.Fatal("a conclusion never touches a sensed variable")
	}
	ls := Project(w, 10, func(e *Entry, n string, v *Var) (Phrase, bool) { return Phrase{Subject: e.Name}, true })
	if len(ls) != 2 || ls[0].Stream != "reasoning" || !strings.Contains(ls[0].Text, "comfort holds advise_heater(r1) (rule cold_heater)") {
		t.Fatalf("%+v", ls)
	}
	if !strings.Contains(ls[1].Text, "bedroom ventilation: off (sure, sensor, just now)") {
		t.Fatalf("%+v", ls[1])
	}
}

func TestCheckBeliefSum(t *testing.T) {
	w := New()
	b := NewBoard(w)
	p := map[string]float64{"normal": 0.5, "night": 0.4, "boost": 0.2}
	b.Offer(&Port{Name: "preset", One: "M", Keys: func() [][]string {
		return [][]string{{"u1", "normal"}, {"u1", "night"}, {"u1", "boost"}}
	}, P: func(a []string) (float64, bool) { return p[a[1]], true }})
	if got := b.Check(); len(got) != 1 || !strings.HasPrefix(got[0], "belief-sum") {
		t.Fatalf("%v", got)
	}
	p["boost"] = 0.1
	if got := b.Check(); len(got) != 0 {
		t.Fatalf("%v", got)
	}
}

func TestGaussGate(t *testing.T) {
	g := Gauss{}
	g.Observe(21, 0.09, 4)
	g.Observe(21.2, 0.09, 4)
	if g.Observe(35, 0.09, 4) {
		t.Fatal("a 14 °C jump is an outlier")
	}
	g.Predict(36000, 0.0005) // ten hours unheard: vague enough to take it
	if !g.Observe(30, 0.09, 4) {
		t.Fatal("a vague belief takes any reading")
	}
}
