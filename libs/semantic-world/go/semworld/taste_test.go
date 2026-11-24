package semworld

import (
	"math"
	"testing"
)

func taste() *Taste {
	t := NewTaste()
	for _, it := range []Item{
		{ID: "jazzfm", Kind: "station", Name: "Jazz FM", Tags: []string{"jazz", "evening"}},
		{ID: "vinyl", Kind: "station", Name: "Classic Vinyl HD", Tags: []string{"jazz", "classic"}},
		{ID: "drone", Kind: "station", Name: "Drone Zone", Tags: []string{"ambient", "calm"}},
		{ID: "amber", Kind: "colour", Name: "amber 30%", Tags: []string{"warm", "calm", "dim"}},
		{ID: "daylight", Kind: "colour", Name: "white 80%", Tags: []string{"cool", "bright", "focus"}},
	} {
		t.Register(it)
	}
	return t
}

var evening, morning = Context{Part: "evening"}, Context{Part: "morning"}

// TestSelectByTagsKindAndTaste: the kind and the tags choose the candidates (the name's words, a
// stem); the taste in the context chooses among them; the time of day keeps tastes apart.
func TestSelectByTagsKindAndTaste(t *testing.T) {
	ts := taste()
	if c, ok := ts.Select("station", []string{"calm"}, evening, nil, 0); !ok || c.ID != "drone" {
		t.Fatalf("calm station: %+v %v", c, ok)
	}
	if c, ok := ts.Select("colour", []string{"relaxing calm"}, evening, nil, 0); !ok || c.ID != "amber" || c.Match < 0.5 {
		t.Fatalf("a calm colour: %+v %v", c, ok)
	}
	if _, ok := ts.Select("station", []string{"techno"}, evening, nil, 0); ok {
		t.Fatal("no techno station, yet one was chosen")
	}
	for i := 0; i < 3; i++ {
		ts.Prefer("vinyl", evening, 1, 100)
		ts.Prefer("jazzfm", morning, 1, 100)
	}
	if c, _ := ts.Select("station", []string{"jazz"}, evening, nil, 100); c.ID != "vinyl" || c.Explored {
		t.Fatalf("jazz in the evening: %+v", c)
	}
	if c, _ := ts.Select("station", []string{"jazz"}, morning, nil, 100); c.ID != "jazzfm" || c.Explored {
		t.Fatalf("jazz in the morning: %+v", c)
	}
	if c, _ := ts.Select("station", []string{"jazz"}, evening, []string{"vinyl"}, 100); c.ID != "jazzfm" {
		t.Fatalf("jazz in the evening, the favourite left out: %+v", c)
	}
}

// TestTheHomesCharacterLeansWithoutEvidence: a prior per tag and context chooses before the person
// has said anything; the person's evidence then overrides it.
func TestTheHomesCharacterLeansWithoutEvidence(t *testing.T) {
	ts := taste()
	ts.Prior("warm", evening, 2)
	ts.Prior("bright", morning, 2)
	if c, _ := ts.Select("colour", nil, evening, nil, 0); c.ID != "amber" || c.Explored {
		t.Fatalf("the evening's light, by character: %+v", c)
	}
	if c, _ := ts.Select("colour", nil, morning, nil, 0); c.ID != "daylight" || c.Explored {
		t.Fatalf("the morning's light, by character: %+v", c)
	}
	for i := 0; i < 4; i++ { // the person prefers daylight in the evening
		ts.Prefer("daylight", evening, 1, 10)
		ts.Prefer("amber", evening, -1, 10)
	}
	if c, _ := ts.Select("colour", nil, evening, nil, 10); c.ID != "daylight" {
		t.Fatalf("the person over the character: %+v", c)
	}
}

// TestCuriosityIsDeterministic: with nothing known the home tries the least tried; with evidence,
// one time in seven it tries something else on purpose; the same state chooses the same.
func TestCuriosityIsDeterministic(t *testing.T) {
	ts := taste()
	c, _ := ts.Select("station", []string{"jazz"}, evening, nil, 0)
	if !c.Explored || c.ID != "jazzfm" {
		t.Fatalf("nothing known: %+v", c)
	}
	for i := 0; i < 6; i++ {
		ts.Prefer("vinyl", evening, 1, 0)
	}
	if c, _ := ts.Select("station", []string{"jazz"}, evening, nil, 0); c.ID != "vinyl" || c.Explored {
		t.Fatalf("six times kept: %+v", c)
	}
	ts.Prefer("vinyl", evening, 1, 0) // the seventh: curious
	a, _ := ts.Select("station", []string{"jazz"}, evening, nil, 0)
	b, _ := ts.Select("station", []string{"jazz"}, evening, nil, 0)
	if !a.Explored || a.ID != "jazzfm" || a != b {
		t.Fatalf("curious: %+v, again %+v", a, b)
	}
}

// TestTasteFades: evidence halves every half-life, and new evidence adds to what is left.
func TestTasteFades(t *testing.T) {
	ts := taste()
	ts.Prefer("drone", Context{}, 2, 0)
	p0, _ := ts.Score("drone", Context{}, 0)
	p1, _ := ts.Score("drone", Context{}, ts.HalfLife)
	l0, l1 := math.Log(p0/(1-p0)), math.Log(p1/(1-p1))
	if math.Abs(l1-l0/2) > 1e-9 {
		t.Fatalf("after a half-life: log-odds %.3f, want %.3f", l1, l0/2)
	}
}

// TestTheWordsBecomeTags: the person's words, once kept, are tags: each word and the words together.
func TestTheWordsBecomeTags(t *testing.T) {
	ts := taste()
	ts.Tag("drone", "something calm for reading")
	if c, ok := ts.Select("station", []string{"reading"}, evening, nil, 0); !ok || c.ID != "drone" {
		t.Fatalf("reading: %+v", c)
	}
}
