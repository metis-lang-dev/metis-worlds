// Package semworld is the Go port of semantic_world's generic core (libs/semantic-world/semantic_world:
// bayes.py, core.py's query API, store.py): the belief over where each thing is, its existence log-odds,
// and the levels a port reads. Held to the Python by testdata/bayes_cases.json (gen_bayes_cases.py).
package semworld

import (
	"math"
	"sort"
)

// bayes.py's constants.
const (
	LHit  = 0.85 // a sighting raises exists by this
	LMiss = 0.4  // the constant miss before step 3b (kept for parity; Missed weighs the evidence)
	LMax  = 4.0  // exists is clamped to ±LMax
)

// Belief is {place: p}.
type Belief map[string]float64

// Thing is a thing's entry: where it was last seen (nil: in hand / nowhere).
type Thing struct {
	In *string `json:"in"`
}

// Doc is the map document every adapter shares (store.py): the places, the things, the beliefs, the
// existence log-odds, the places a thing was looked for in vain, the things gone.
type Doc struct {
	Places  map[string]map[string]any `json:"places"`
	Things  map[string]*Thing         `json:"things"`
	Belief  map[string]Belief         `json:"belief"`
	Exists  map[string]float64        `json:"exists"`
	Looked  map[string][]string       `json:"looked,omitempty"`
	Gone    []string                  `json:"gone,omitempty"`
	Binding map[string]string         `json:"binding,omitempty"`
}

// NewDoc is an empty document over PLACES.
func NewDoc(places ...string) *Doc {
	d := &Doc{Places: map[string]map[string]any{}, Things: map[string]*Thing{}, Belief: map[string]Belief{},
		Exists: map[string]float64{}, Looked: map[string][]string{}, Binding: map[string]string{}}
	for _, p := range places {
		d.Places[p] = map[string]any{}
	}
	return d
}

func round6(x float64) float64 { return math.Round(x*1e6) / 1e6 }

// AddExists moves THING's existence log-odds by DELTA, clamped to ±LMax (bayes._exists).
func (d *Doc) AddExists(thing string, delta float64) {
	d.Exists[thing] = round6(math.Max(-LMax, math.Min(LMax, d.Exists[thing]+delta)))
}

// Seen: THING seen at PLACE ("" = in hand: its belief dropped). → changed.
func (d *Doc) Seen(thing, place string) bool {
	t := d.Things[thing]
	if t == nil {
		t = &Thing{}
		d.Things[thing] = t
	}
	changed := false
	cur := ""
	if t.In != nil {
		cur = *t.In
	}
	bel := d.Belief[thing]
	// bayes.seen compares belief.get(thing) with the posterior: for in-hand that is None != {}, always a change
	same := place != "" && len(bel) == 1 && bel[place] == 1.0
	if cur != place || !same {
		changed = true
		if place != "" {
			p := place
			t.In = &p
			d.Belief[thing] = Belief{place: 1.0}
		} else {
			t.In = nil
			delete(d.Belief, thing)
		}
	}
	d.AddExists(thing, LHit)
	return changed
}

// Prior is an adapter's belief for a thing when nothing is left.
type Prior func(thing string) Belief

// Uniform is the core's prior: uniform over the document's places.
func (d *Doc) Uniform(string) Belief {
	ps := sortedKeys(d.Places)
	out := Belief{}
	for _, p := range ps {
		out[p] = 1.0 / float64(len(ps))
	}
	return out
}

// Missed: PLACE looked into; every thing believed there and not seen there (SEENAT) loses it, renormalized
// (PRIOR when nothing is left), its exists falling by log(1 − p), p the mass it held there. → the things.
func (d *Doc) Missed(place string, seenAt map[string]string, prior Prior) []string {
	var out []string
	for _, thing := range sortedKeys(d.Belief) {
		bel := d.Belief[thing]
		if bel[place] <= 0 || seenAt[thing] == place {
			continue
		}
		d.Looked[thing] = append(d.Looked[thing], place)
		total := sum(bel)
		frac := 1.0
		if total > 0 {
			frac = bel[place] / total
		}
		delete(bel, place)
		z := sum(bel)
		if z > 0 {
			nb := Belief{}
			for x, q := range bel {
				nb[x] = q / z
			}
			d.Belief[thing] = nb
		} else {
			d.Belief[thing] = prior(thing)
		}
		d.AddExists(thing, math.Max(-LMax, math.Log(math.Max(1e-12, 1-frac))))
		out = append(out, thing)
	}
	return out
}

// Model is a motion model: belief after dt turns.
type Model func(bel Belief, dt float64) Belief

// Still is the identity (a household's things move only by a hand).
func Still(bel Belief, _ float64) Belief { return bel }

// Alive is the alive decay: exists falls by Rate per turn; below Floor the belief is dropped (gone).
type Alive struct{ Rate, Floor float64 }

// Predict is the motion step for every thing with a model, then the alive decay. → changed.
func (d *Doc) Predict(dt float64, models map[string]Model, alive *Alive) bool {
	changed := false
	for _, thing := range sortedKeys(models) {
		if bel := d.Belief[thing]; len(bel) > 0 {
			nb := models[thing](copyBelief(bel), dt)
			if !equal(nb, bel) {
				d.Belief[thing] = nb
				changed = true
			}
		}
		if alive != nil {
			if _, ok := d.Belief[thing]; ok {
				d.AddExists(thing, -alive.Rate*dt)
				if d.Exists[thing] < alive.Floor {
					delete(d.Belief, thing)
					d.Gone = append(d.Gone, thing)
					changed = true
				}
			}
		}
	}
	return changed
}

// Walk is the random walk over a graph (bayes.walk): per step each place keeps STAY of its mass and spreads
// the rest over its neighbours weighted exp(−bias·toward(n)); a fractional speed·dt mixes in one more step.
func Walk(neighbours func(string) []string, toward func(string) float64, stay, bias, speed, eps float64) Model {
	one := func(bel Belief) Belief {
		nw := Belief{}
		for _, p := range sortedKeys(bel) {
			m := bel[p]
			ns := neighbours(p)
			if len(ns) == 0 {
				nw[p] += m
				continue
			}
			nw[p] += m * stay
			ws := make([]float64, len(ns))
			z := 0.0
			for i, n := range ns {
				ws[i] = 1.0
				if toward != nil {
					ws[i] = math.Exp(-bias * toward(n))
				}
				z += ws[i]
			}
			for i, n := range ns {
				nw[n] += m * (1 - stay) * ws[i] / z
			}
		}
		return keepNorm(nw, eps, bel)
	}
	return func(bel Belief, dt float64) Belief {
		n, f := math.Modf(math.Max(0, speed*dt))
		for i := 0; i < int(n); i++ {
			bel = one(bel)
		}
		if f > 1e-9 {
			more := one(bel)
			mixed := Belief{}
			for _, p := range union(bel, more) {
				mixed[p] = (1-f)*bel[p] + f*more[p]
			}
			bel = keepNorm(mixed, eps, bel)
		}
		return bel
	}
}

func keepNorm(b Belief, eps float64, fallback Belief) Belief {
	keep := Belief{}
	z := 0.0
	for p, m := range b {
		if m >= eps {
			keep[p] = m
			z += m
		}
	}
	if z <= 0 {
		return fallback
	}
	for p := range keep {
		keep[p] /= z
	}
	return keep
}

// Normalized is the belief over AMONG only, normalized (1.0 flat when it holds none of them).
func Normalized(bel Belief, among []string) Belief {
	z := 0.0
	for _, r := range among {
		z += bel[r]
	}
	out := Belief{}
	for _, r := range among {
		if z > 0 {
			out[r] = bel[r] / z
		} else {
			out[r] = 1.0
		}
	}
	return out
}

// P is the probability of a log-odds.
func P(logOdds float64) float64 { return 1 / (1 + math.Exp(-logOdds)) }

// LogOdds of a probability (clamped to ±LMax·3 for 0 and 1).
func LogOdds(p float64) float64 {
	p = math.Min(math.Max(p, 1e-6), 1-1e-6)
	return math.Log(p / (1 - p))
}

// Levels quantises a probability: below Cuts[0] Names[0], below Cuts[1] Names[1], else Names[2]
// (the README's presence levels: 0.3 / 0.7, improbable / doubtful / likely).
type Levels struct {
	Cuts  [2]float64
	Names [3]string
}

// DefaultLevels are the README's.
var DefaultLevels = Levels{Cuts: [2]float64{0.3, 0.7}, Names: [3]string{"improbable", "doubtful", "likely"}}

// Of is p's level.
func (l Levels) Of(p float64) string {
	switch {
	case p < l.Cuts[0]:
		return l.Names[0]
	case p < l.Cuts[1]:
		return l.Names[1]
	}
	return l.Names[2]
}

func sum(b Belief) float64 {
	z := 0.0
	for _, p := range sortedKeys(b) {
		z += b[p]
	}
	return z
}

func copyBelief(b Belief) Belief {
	out := make(Belief, len(b))
	for k, v := range b {
		out[k] = v
	}
	return out
}

func equal(a, b Belief) bool {
	if len(a) != len(b) {
		return false
	}
	for k, v := range a {
		if w, ok := b[k]; !ok || w != v {
			return false
		}
	}
	return true
}

func union(a, b Belief) []string {
	s := map[string]bool{}
	for k := range a {
		s[k] = true
	}
	for k := range b {
		s[k] = true
	}
	return sortedKeys(s)
}

func sortedKeys[V any](m map[string]V) []string {
	out := make([]string, 0, len(m))
	for k := range m {
		out = append(out, k)
	}
	sort.Strings(out)
	return out
}

// Distances is the graph distance from START to every place within LIMIT, unit edges (bayes.distances).
func Distances(neighbours func(string) []string, start string, limit float64) map[string]float64 {
	dist := map[string]float64{start: 0}
	frontier := []string{start}
	for len(frontier) > 0 {
		var next []string
		for _, p := range frontier {
			for _, n := range neighbours(p) {
				g := dist[p] + 1
				if _, ok := dist[n]; !ok && g <= limit+1e-9 {
					dist[n] = g
					next = append(next, n)
				}
			}
		}
		frontier = next
	}
	return dist
}
