package semworld

import (
	"fmt"
	"math"
	"sort"
	"sync"
)

// ── the semantic world: a blackboard of typed entries whose variables are beliefs ──
//
// Writers: the world's sensors (Observe*), Metis (Conclude), a person (Report), the host's own
// commands (Command). Readers: Metis through its quantised ports (ports.go), the LLM through the
// projection (project.go). Every variable keeps its provenance and a change counter; the ports keep
// spec 15's counters c_p, each change tagged with its source member (or "world").

// Kind is an entry's kind.
type Kind string

const (
	KPlace    Kind = "place"
	KThing    Kind = "thing"
	KAgent    Kind = "agent" // a person, the ego
	KDevice   Kind = "device"
	KQuantity Kind = "quantity"
	KInferred Kind = "inferred" // a Metis member's conclusions
)

// Source is who wrote a variable last.
type Source struct {
	Kind string `json:"kind"`          // sensor | command | metis | person | prior | world
	Who  string `json:"who,omitempty"` // the entity id, the member, the person
	Ref  string `json:"ref,omitempty"` // a rule, an utterance id
}

// Tag is the spec-15 source tag of a change: the member for a Metis write, else "world".
func (s Source) Tag() string {
	if s.Kind == "metis" {
		return s.Who
	}
	return "world"
}

// VKind is a variable's belief form.
type VKind string

const (
	VCat   VKind = "cat"   // a categorical distribution over values
	VOdds  VKind = "odds"  // the log-odds of a binary (existence, presence)
	VGauss VKind = "gauss" // a continuous estimate with variance
	VFact  VKind = "fact"  // a fact a member asserts (true while asserted)
)

// Var is one belief.
type Var struct {
	Kind   VKind    `json:"kind"`
	Values []string `json:"values,omitempty"` // VCat's domain, in order
	Cat    Belief   `json:"cat,omitempty"`
	Odds   float64  `json:"odds,omitempty"`
	G      Gauss    `json:"g,omitempty"`
	Fact   bool     `json:"fact,omitempty"`
	Src    Source   `json:"src"`
	At     float64  `json:"at"`     // the last evidence's time (s)
	C      uint64   `json:"c"`      // changes so far
	Unsure bool     `json:"unsure"` // no evidence can reach it now (a device unavailable, a feed down)
}

// P is the probability of VALUE (VCat), of true (VOdds, VFact).
func (v *Var) P(value string) float64 {
	switch v.Kind {
	case VCat:
		return v.Cat[value]
	case VOdds:
		return P(v.Odds)
	case VFact:
		if v.Fact {
			return 1
		}
	}
	return 0
}

// Top is a categorical's likeliest value and its probability (ties by value order).
func (v *Var) Top() (string, float64) {
	best, bp := "", -1.0
	for _, x := range v.Values {
		if v.Cat[x] > bp {
			best, bp = x, v.Cat[x]
		}
	}
	return best, bp
}

// Entry is a thing in the world.
type Entry struct {
	ID    string            `json:"id"`
	Kind  Kind              `json:"kind"`
	Name  string            `json:"name"`
	In    string            `json:"in,omitempty"` // the place it belongs to
	Attrs map[string]string `json:"attrs,omitempty"`
	Vars  map[string]*Var   `json:"vars"`
}

// Surprise is evidence of a spec-20 surprise the world can see (never a rule's response itself):
// a commanded state not read back, a person contradicting a sure sensor, a level at its floor.
type Surprise struct {
	Kind string  `json:"kind"` // spec 20's: probabilistic | evidential | world
	Key  string  `json:"key"`
	Why  string  `json:"why"`
	At   float64 `json:"at"`
}

// World is the blackboard.
type World struct {
	mu        sync.Mutex
	Entries   map[string]*Entry `json:"entries"`
	Where     *Doc              `json:"where"` // things over places: the shared bayes core (road, room, grid)
	Surprises []Surprise        `json:"surprises,omitempty"`
	Now       float64           `json:"now"`
	listeners []func(key string, v *Var)
}

// New is an empty world.
func New() *World { return &World{Entries: map[string]*Entry{}, Where: NewDoc()} }

// Lock and Unlock guard a sequence of reads (the projection, a port evaluation) against writers.
func (w *World) Lock()   { w.mu.Lock() }
func (w *World) Unlock() { w.mu.Unlock() }

// Add enters an entry (replacing one of the same id).
func (w *World) Add(e *Entry) *Entry {
	if e.Vars == nil {
		e.Vars = map[string]*Var{}
	}
	w.Entries[e.ID] = e
	if e.Kind == KPlace {
		w.Where.Places[e.ID] = map[string]any{}
	}
	return e
}

// Declare a variable on an entry with its prior (VCat: uniform over values unless PRIOR given).
func (w *World) Declare(id, name string, kind VKind, values []string, prior Belief) *Var {
	e := w.Entries[id]
	if e == nil {
		e = w.Add(&Entry{ID: id, Kind: KThing, Name: id})
	}
	v := &Var{Kind: kind, Values: values, Src: Source{Kind: "prior"}, Unsure: true}
	if kind == VCat {
		if prior == nil {
			prior = Belief{}
			for _, x := range values {
				prior[x] = 1 / float64(len(values))
			}
		}
		v.Cat = copyBelief(prior)
	}
	e.Vars[name] = v
	return v
}

// Var is id.name's variable (nil when none).
func (w *World) Var(id, name string) *Var {
	if e := w.Entries[id]; e != nil {
		return e.Vars[name]
	}
	return nil
}

// Key of a variable: "id.name".
func Key(id, name string) string { return id + "." + name }

// OnChange registers a listener called (under the lock) after any variable changes.
func (w *World) OnChange(f func(key string, v *Var)) { w.listeners = append(w.listeners, f) }

func (w *World) changed(id, name string, v *Var) {
	v.C++
	for _, f := range w.listeners {
		f(Key(id, name), v)
	}
}

func (w *World) mustVar(id, name string) *Var {
	v := w.Var(id, name)
	if v == nil {
		panic(fmt.Sprintf("semworld: no variable %s", Key(id, name)))
	}
	return v
}

// Likelihood of a reading VALUE from a sensor of RELIABILITY r over a categorical's values:
// r at VALUE, the rest shared evenly.
func Likelihood(values []string, value string, r float64) Belief {
	like := Belief{}
	for _, x := range values {
		if x == value {
			like[x] = r
		} else {
			like[x] = (1 - r) / math.Max(1, float64(len(values)-1))
		}
	}
	return like
}

// ObserveCat folds a categorical reading in: first the transition since the last reading (MIX: the
// weight the uniform takes, a switchable device having had time to change: 0 a fixed thing, 0.5 a light
// anyone may switch), then Bayes' rule with the sensor's reliability R. → changed.
func (w *World) ObserveCat(id, name, value string, r, mix float64, src Source, now float64) bool {
	v := w.mustVar(id, name)
	old := copyBelief(v.Cat)
	prior := v.Cat
	if mix > 0 {
		prior = Belief{}
		for _, x := range v.Values {
			prior[x] = (1-mix)*v.Cat[x] + mix/float64(len(v.Values))
		}
	}
	d := &Doc{Belief: map[string]Belief{"x": prior}}
	v.Cat = d.Update("x", Likelihood(v.Values, value, r), 0, nil)
	v.At, v.Src, v.Unsure = now, src, false
	if !near1(old, v.Cat) {
		w.changed(id, name, v)
		return true
	}
	return false
}

// SetCat sets a categorical outright (a command's prediction, a Metis conclusion). → changed.
func (w *World) SetCat(id, name string, bel Belief, src Source, now float64) bool {
	v := w.mustVar(id, name)
	old := v.Cat
	v.Cat, v.At, v.Src = copyBelief(bel), now, src
	if !near1(old, v.Cat) {
		w.changed(id, name, v)
		return true
	}
	return false
}

// ObserveOdds adds DELTA log-odds of evidence, clamped to ±LMax. → changed.
func (w *World) ObserveOdds(id, name string, delta float64, src Source, now float64) bool {
	v := w.mustVar(id, name)
	old := v.Odds
	v.Odds = round6(math.Max(-LMax, math.Min(LMax, v.Odds+delta)))
	v.At, v.Src, v.Unsure = now, src, false
	if v.Odds != old {
		w.changed(id, name, v)
		return true
	}
	return false
}

// ObserveGauss folds a continuous reading Z (noise variance R, outlier GATE in sd) in. → accepted.
func (w *World) ObserveGauss(id, name string, z, r, gate float64, src Source, now float64) bool {
	v := w.mustVar(id, name)
	if !v.G.Observe(z, r, gate) {
		return false
	}
	v.At, v.Src, v.Unsure = now, src, false
	w.changed(id, name, v)
	return true
}

// Relax lets an unheard categorical forget toward its uniform prior (half-life HALF s) over DT.
func (w *World) Relax(id, name string, dt, half float64) {
	v := w.mustVar(id, name)
	prior := Belief{}
	for _, x := range v.Values {
		prior[x] = 1 / float64(len(v.Values))
	}
	nb := Relax(prior, half)(v.Cat, dt)
	if !near1(nb, v.Cat) {
		v.Cat = nb
		w.changed(id, name, v)
	}
}

// Surprised records evidence of a surprise.
func (w *World) Surprised(kind, key, why string, now float64) {
	w.Surprises = append(w.Surprises, Surprise{Kind: kind, Key: key, Why: why, At: now})
}

// ── the conversation and Metis as writers ──

// Report is a person's word as weak evidence (reliability R, default 0.7) on a categorical: never the
// assistant's own restatement (that is not evidence: refused). A report against a sure sensor (≥ 0.95,
// read in the last minute) is not folded in: it is evidence of a surprise. → folded.
func (w *World) Report(person, id, name, value string, r float64, ref string, now float64) (bool, error) {
	if person == "" || person == "assistant" {
		return false, fmt.Errorf("semworld: the assistant's own words are not evidence")
	}
	v := w.Var(id, name)
	if v == nil || v.Kind != VCat {
		return false, fmt.Errorf("semworld: no categorical %s", Key(id, name))
	}
	if r <= 0 {
		r = 0.7
	}
	if top, p := v.Top(); v.Src.Kind == "sensor" && p >= 0.95 && now-v.At < 60 && top != value {
		w.Surprised("evidential", Key(id, name), fmt.Sprintf("%s says %s; the sensor reads %s (%.0f%%)", person, value, top, 100*p), now)
		return false, nil
	}
	return w.ObserveCat(id, name, value, r, 0, Source{Kind: "person", Who: person, Ref: ref}, now), nil
}

// Conclude is a Metis member's write: a fact it asserts (or retracts) about an entry, kept on the
// member's own inferred entry ("metis.<member>"), never fused into a sensed variable (a conclusion
// drawn from the world is not new evidence about it). → changed.
func (w *World) Conclude(member, fact string, on bool, rule string, now float64) bool {
	id := "metis." + member
	e := w.Entries[id]
	if e == nil {
		e = w.Add(&Entry{ID: id, Kind: KInferred, Name: member})
	}
	v := e.Vars[fact]
	if v == nil {
		v = &Var{Kind: VFact}
		e.Vars[fact] = v
	}
	src := Source{Kind: "metis", Who: member, Ref: rule}
	if v.Fact == on && v.Src == src {
		return false
	}
	v.Fact, v.Src, v.At, v.Unsure = on, src, now, false
	w.changed(id, fact, v)
	return true
}

// Facts are a member's asserted facts, sorted.
func (w *World) Facts(member string) []string {
	e := w.Entries["metis."+member]
	if e == nil {
		return nil
	}
	var out []string
	for k, v := range e.Vars {
		if v.Fact {
			out = append(out, k)
		}
	}
	sort.Strings(out)
	return out
}

func near1(a, b Belief) bool {
	for _, k := range union(a, b) {
		if math.Abs(a[k]-b[k]) > 1e-9 {
			return false
		}
	}
	return true
}
