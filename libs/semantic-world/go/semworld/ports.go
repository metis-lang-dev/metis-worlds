package semworld

import (
	"fmt"
	"os"
	"sort"
	"strings"

	"gopkg.in/yaml.v3"
)

// ── the Metis face: a package manifest's beliefs:/levels: bound onto world queries ──
//
// A world adapter registers belief PORTS: a name, its ground keys (the args a rule may read it at),
// and a probability per key. A manifest (domain.yaml, spec 16) names them:
//
//	beliefs: {occupied: {port: present}}                       # §2: independent, one p per key
//	levels:  {presence: {from: {belief: present}, at: [0.3, 0.7], names: [vacant, unsure, occupied]}}
//
// The Board quantises each level key by spec 16 §4 (names[#{t ∈ at : t ≤ p}], no hysteresis: that is
// the rules'), turns the changes into do-lines (+presence(occupied, r1) 1 / -presence(unsure, r1) 1),
// keeps spec 15's change counter c_p per port, each change tagged with its source (rule 3), and
// answers the wake test for a member (rule 1). Weight ports read the same probabilities (Weight).

// Port is a belief port an adapter offers.
type Port struct {
	Name string
	// Keys are the ground args the port is defined at (["r1"], ["u1"], ["l1"]…), in order.
	Keys func() [][]string
	// P is the probability at ARGS, and whether the world knows it (unknown: no level atom asserted).
	P func(args []string) (float64, bool)
	// Src is the variable's source at ARGS (the change tag).
	Src func(args []string) Source
	// One / Lone name the arg a categorical port sums over (spec 16 §2), "" independent.
	One, Lone string
}

// LevelSpec is a manifest's level port.
type LevelSpec struct {
	From  map[string]string `yaml:"from"` // {belief: port} (an {evaluate: q} level is the runtime's own)
	At    []float64         `yaml:"at"`
	Names []string          `yaml:"names"`
}

// BeliefSpec is a manifest's belief entry.
type BeliefSpec struct {
	Port string `yaml:"port"`
	One  string `yaml:"one,omitempty"`
	Lone string `yaml:"lone,omitempty"`
}

// Manifest is the part of domain.yaml the world serves.
type Manifest struct {
	Name    string                `yaml:"-"`
	Beliefs map[string]BeliefSpec `yaml:"beliefs"`
	Levels  map[string]LevelSpec  `yaml:"levels"`
	Clock   struct {
		Beats  int     `yaml:"beats"`
		Period float64 `yaml:"period"`
	} `yaml:"clock"`
}

// ReadManifest reads domain.yaml (flow or block YAML); NAME is the member's name.
func ReadManifest(path, name string) (*Manifest, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	m := &Manifest{Name: name}
	if err := yaml.Unmarshal(b, m); err != nil {
		return nil, fmt.Errorf("%s: %w", path, err)
	}
	for k, l := range m.Levels {
		if len(l.Names) != len(l.At)+1 {
			return nil, fmt.Errorf("%s: level %s: |names| must be |at|+1", path, k)
		}
		for i := 1; i < len(l.At); i++ {
			if l.At[i] <= l.At[i-1] {
				return nil, fmt.Errorf("%s: level %s: at must increase", path, k)
			}
		}
	}
	return m, nil
}

// Quantise is spec 16 §4's rule: names[i] iff at[i−1] ≤ p < at[i].
func Quantise(p float64, at []float64, names []string) string {
	i := 0
	for _, t := range at {
		if t <= p {
			i++
		}
	}
	return names[i]
}

// Atom is a level atom: pred(level, args…).
func Atom(pred, level string, args []string) string {
	return pred + "(" + strings.Join(append([]string{level}, args...), ", ") + ")"
}

type change struct {
	c   uint64
	tag string
}

// Board serves one world's ports to the members that read them.
type Board struct {
	W       *World
	ports   map[string]*Port
	members map[string]*Manifest
	levels  map[string]map[string]string // member → level key "pred|args" → asserted atom
	c       map[string]uint64            // spec 15 c_p, per port
	last    map[string][]change          // per port, the recent changes with their tags
	pv      map[string]string            // per port, the quantised readings last seen (all members' levels)
	seen    map[string]map[string]uint64 // seen_d(p)
	beat    map[string]float64           // a member's last beat (s)
}

// NewBoard over W.
func NewBoard(w *World) *Board {
	return &Board{W: w, ports: map[string]*Port{}, members: map[string]*Manifest{},
		levels: map[string]map[string]string{}, c: map[string]uint64{}, last: map[string][]change{},
		pv: map[string]string{}, seen: map[string]map[string]uint64{}, beat: map[string]float64{}}
}

// Offer registers an adapter's port.
func (b *Board) Offer(p *Port) { b.ports[p.Name] = p }

// Ports are the offered ports' names.
func (b *Board) Ports() []string { return sortedKeys(b.ports) }

// Join enters a member; every port its manifest names must be offered.
func (b *Board) Join(m *Manifest) error {
	for k, bs := range m.Beliefs {
		if b.ports[bs.Port] == nil {
			return fmt.Errorf("%s: belief %s reads port %s, which this world does not offer (it has: %s)",
				m.Name, k, bs.Port, strings.Join(b.Ports(), ", "))
		}
	}
	for k, l := range m.Levels {
		if p := l.From["belief"]; p != "" && b.ports[p] == nil {
			return fmt.Errorf("%s: level %s reads port %s, which this world does not offer", m.Name, k, p)
		}
	}
	b.members[m.Name] = m
	b.levels[m.Name] = map[string]string{}
	b.seen[m.Name] = map[string]uint64{}
	return nil
}

// In is a member's wake set: the ports its manifest reads.
func (b *Board) In(member string) []string {
	m := b.members[member]
	s := map[string]bool{}
	for _, bs := range m.Beliefs {
		s[bs.Port] = true
	}
	for _, l := range m.Levels {
		if p := l.From["belief"]; p != "" {
			s[p] = true
		}
	}
	return sortedKeys(s)
}

// Settle is the boundary step: every port is read through every level that quantises it; a port whose
// quantised reading changed advances c_p, tagged with the source of what changed it. Call it once a
// beat, after the writers, before Wake / Lines.
func (b *Board) Settle() {
	type spec struct {
		at    []float64
		names []string
	}
	byPort := map[string][]spec{}
	for _, mn := range sortedKeys(b.members) {
		for _, lk := range sortedKeys(b.members[mn].Levels) {
			l := b.members[mn].Levels[lk]
			if p := l.From["belief"]; p != "" {
				byPort[p] = append(byPort[p], spec{l.At, l.Names})
			}
		}
	}
	for _, pn := range sortedKeys(b.ports) {
		p := b.ports[pn]
		for _, args := range p.Keys() {
			k := pn + "|" + strings.Join(args, ",")
			pr, ok := p.P(args)
			var sig []string
			if !ok {
				sig = []string{"?"}
			}
			for _, s := range byPort[pn] {
				if ok {
					sig = append(sig, Quantise(pr, s.at, s.names))
				}
			}
			if len(byPort[pn]) == 0 && ok { // a port no level reads (a weight port): two decimals
				sig = append(sig, fmt.Sprintf("%.2f", pr))
			}
			now := strings.Join(sig, "/")
			if old, seen := b.pv[k]; !seen || old != now {
				b.pv[k] = now
				b.c[pn]++
				tag := "world"
				if p.Src != nil {
					tag = p.Src(args).Tag()
				}
				b.last[pn] = append(b.last[pn], change{b.c[pn], tag})
				if n := len(b.last[pn]); n > 64 {
					b.last[pn] = b.last[pn][n-64:]
				}
			}
		}
	}
}

// C is c_p.
func (b *Board) C(port string) uint64 { return b.c[port] }

// Wake is spec 15 §8.5 rule 1 with rule 3: MEMBER beats at NOW iff a port it reads changed since it
// last saw it through a change not tagged with itself, or its clock period (s) has elapsed. A beat
// marks the ports seen.
func (b *Board) Wake(member string, now float64) bool {
	m := b.members[member]
	wake := false
	for _, p := range b.In(member) {
		for _, ch := range b.last[p] {
			if ch.c > b.seen[member][p] && ch.tag != member {
				wake = true
			}
		}
	}
	if m.Clock.Period > 0 {
		if t, ok := b.beat[member]; !ok || now-t >= m.Clock.Period {
			wake = true
		}
	}
	if wake {
		for _, p := range b.In(member) {
			b.seen[member][p] = b.c[p]
		}
		b.beat[member] = now
	}
	return wake
}

// Lines are the do-lines that bring MEMBER's level atoms to the world now: exactly one atom per known
// key (spec 16 §4), the previous one retracted; an unknown key holds no atom. Applied, they are the
// member's new levels (the one-tick instrument: beliefs constant over the tick, read once here).
func (b *Board) Lines(member string) []string {
	m := b.members[member]
	cur := b.levels[member]
	want := map[string]string{}
	for _, pred := range sortedKeys(m.Levels) {
		l := m.Levels[pred]
		p := b.ports[l.From["belief"]]
		if p == nil {
			continue
		}
		for _, args := range p.Keys() {
			if pr, ok := p.P(args); ok {
				want[pred+"|"+strings.Join(args, ",")] = Atom(pred, Quantise(pr, l.At, l.Names), args)
			}
		}
	}
	var del, add []string
	for _, k := range sortedKeys(cur) {
		if want[k] != cur[k] {
			del = append(del, "-"+cur[k]+" 1")
		}
	}
	for _, k := range sortedKeys(want) {
		if cur[k] != want[k] {
			add = append(add, "+"+want[k]+" 1")
		}
	}
	b.levels[member] = want
	return append(del, add...)
}

// LevelAtoms are MEMBER's level atoms now as a host's readings: for each key a port knows, every level
// name's atom, true for the one the belief quantises to; for a key whose belief is unknown, every one
// false (spec 16 §4: an unknown key holds no atom). Atoms are in the runtime's canonical spelling
// (pred(level,arg), no spaces), so a host corrects them against the program's counts like any reading
// — which also takes the program's own #init of a level into account (Lines does not see it).
func (b *Board) LevelAtoms(member string) map[string]bool {
	m := b.members[member]
	out := map[string]bool{}
	if m == nil {
		return out
	}
	for _, pred := range sortedKeys(m.Levels) {
		l := m.Levels[pred]
		p := b.ports[l.From["belief"]]
		if p == nil {
			continue
		}
		for _, args := range p.Keys() {
			pr, ok := p.P(args)
			q := ""
			if ok {
				q = Quantise(pr, l.At, l.Names)
			}
			for _, n := range l.Names {
				out[pred+"("+strings.Join(append([]string{n}, args...), ",")+")"] = ok && n == q
			}
		}
	}
	return out
}

// Counts is the runtime's counts during a weight call (rt.Counts has the same method).
type Counts interface{ Count(atom string) int }

// Weight is a weight port's function for metis_rt_bind_weight (rt.WeightFunc's shape: metis-agent
// binds it as rt.WeightFunc(func(a []string, c rt.Counts) float64 { return f(a, c) })). The args are
// the rule's resolved args; an unknown key prices at 1 (spec 16: no belief, the flat reading).
func (b *Board) Weight(port string) func(args []string, counts Counts) float64 {
	p := b.ports[port]
	return func(args []string, _ Counts) float64 {
		if p == nil {
			return 1
		}
		b.W.Lock()
		defer b.W.Unlock()
		if pr, ok := p.P(args); ok {
			return pr
		}
		return 1
	}
}

// Check is spec 16 §2's sum rule over a categorical port (one: = 1, lone: ≤ 1) for every key,
// grouping by the args other than the summed one (its last arg). → the violations ("belief-sum").
func (b *Board) Check() []string {
	var out []string
	for _, pn := range sortedKeys(b.ports) {
		p := b.ports[pn]
		if p.One == "" && p.Lone == "" {
			continue
		}
		sums := map[string]float64{}
		for _, a := range p.Keys() {
			pr, _ := p.P(a)
			sums[strings.Join(a[:len(a)-1], ",")] += pr
		}
		for _, g := range sortedKeys(sums) {
			s := sums[g]
			if (p.One != "" && (s < 1-1e-9 || s > 1+1e-9)) || (p.Lone != "" && s > 1+1e-9) {
				out = append(out, fmt.Sprintf("belief-sum: %s(%s, ·) sums to %.6f", pn, g, s))
			}
		}
	}
	sort.Strings(out)
	return out
}

// BoardState is the board's own state, exported for a checkpoint's hash: what a replay must
// reproduce besides the world (the levels asserted, the counters, the seen sets, the beats).
type BoardState struct {
	Levels map[string]map[string]string `json:"levels"`
	C      map[string]uint64            `json:"c"`
	Last   map[string][][2]any          `json:"last"`
	PV     map[string]string            `json:"pv"`
	Seen   map[string]map[string]uint64 `json:"seen"`
	Beat   map[string]float64           `json:"beat"`
}

// State is a copy of the board's state (encoding/json sorts its maps' keys).
func (b *Board) State() BoardState {
	last := map[string][][2]any{}
	for p, chs := range b.last {
		for _, ch := range chs {
			last[p] = append(last[p], [2]any{ch.c, ch.tag})
		}
	}
	return BoardState{Levels: b.levels, C: b.c, Last: last, PV: b.pv, Seen: b.seen, Beat: b.beat}
}

// Members are the joined members' names, sorted.
func (b *Board) Members() []string { return sortedKeys(b.members) }
