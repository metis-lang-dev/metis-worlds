package semworld

import (
	"math"
	"sort"
)

// The query API (core.py, map-queries step 1): the faces a host and the dialog read the map through.

// Next is the likeliest place of THING's belief not in EXCLUDED, ties by place id ("" when none is left).
func (d *Doc) Next(thing string, excluded ...string) string {
	ex := map[string]bool{}
	for _, e := range excluded {
		ex[e] = true
	}
	best, bp := "", 0.0
	for _, r := range sortedKeys(d.Belief[thing]) {
		p := d.Belief[thing][r]
		if p > 0 && !ex[r] && (best == "" || p > bp) {
			best, bp = r, p
		}
	}
	return best
}

// Weight is P(THING at PLACE) normalized over AMONG (1.0 when the map holds no belief there): the weight port.
func (d *Doc) Weight(thing, place string, among []string) float64 {
	return Normalized(d.Belief[thing], among)[place]
}

// Top is a belief's N likeliest places, rounded to 3 places: the journal's and the page's reading.
func Top(bel Belief, n int) [][2]any {
	ks := sortedKeys(bel)
	sort.SliceStable(ks, func(i, j int) bool { return bel[ks[i]] > bel[ks[j]] })
	if len(ks) > n {
		ks = ks[:n]
	}
	out := make([][2]any, len(ks))
	for i, k := range ks {
		out[i] = [2]any{k, math.Round(bel[k]*1000) / 1000}
	}
	return out
}

// ── the probabilistic updates a sensed world needs beyond the room's sure sensor ──

// Update is Bayes' rule with a likelihood over the places (an unreliable sensor: P(reading | place)):
// posterior ∝ prior · likelihood; places the likelihood omits keep likelihood FLOOR. A belief that is
// absent starts from PRIOR. → the posterior (also stored).
func (d *Doc) Update(thing string, like Belief, floor float64, prior Belief) Belief {
	bel := d.Belief[thing]
	if len(bel) == 0 {
		bel = copyBelief(prior)
	}
	post := Belief{}
	z := 0.0
	for _, p := range union(bel, like) {
		l, ok := like[p]
		if !ok {
			l = floor
		}
		post[p] = bel[p] * l
		z += post[p]
	}
	if z <= 0 { // the reading contradicts the belief outright: the reading wins
		post = Normalized(like, sortedKeys(like))
	} else {
		for p := range post {
			post[p] /= z
		}
	}
	d.Belief[thing] = post
	return post
}

// Relax is the staleness model: over DT the belief forgets toward PRIOR with half-life HALF
// (bel ← w·bel + (1−w)·prior, w = 2^(−dt/half)); a device unheard drifts back to "don't know".
func Relax(prior Belief, half float64) Model {
	return func(bel Belief, dt float64) Belief {
		if half <= 0 || dt <= 0 {
			return bel
		}
		w := math.Pow(2, -dt/half)
		out := Belief{}
		for _, p := range union(bel, prior) {
			out[p] = w*bel[p] + (1-w)*prior[p]
		}
		return out
	}
}

// Gauss is a scalar belief (a temperature): mean and variance, a 1-D Kalman filter.
type Gauss struct {
	Mean, Var float64
	Known     bool
}

// Predict grows the variance by Q per second over DT (the room's temperature wanders).
func (g *Gauss) Predict(dt, q float64) {
	if g.Known {
		g.Var += q * dt
	}
}

// Observe folds in a reading Z with noise variance R; a reading beyond GATE standard deviations of the
// innovation is an outlier and is refused (→ false), unless the belief is already too vague to judge.
func (g *Gauss) Observe(z, r, gate float64) bool {
	if !g.Known {
		*g = Gauss{Mean: z, Var: r, Known: true}
		return true
	}
	s := g.Var + r
	if gate > 0 && math.Abs(z-g.Mean) > gate*math.Sqrt(s) && g.Var < 4*r {
		return false
	}
	k := g.Var / s
	g.Mean += k * (z - g.Mean)
	g.Var *= 1 - k
	return true
}

// Sd is the standard deviation.
func (g *Gauss) Sd() float64 { return math.Sqrt(g.Var) }

// PBelow is P(value ≤ X) under the belief.
func (g *Gauss) PBelow(x float64) float64 {
	return 0.5 * (1 + math.Erf((x-g.Mean)/(g.Sd()*math.Sqrt2)))
}
